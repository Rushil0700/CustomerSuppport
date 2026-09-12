"""Semantic search over the indexed knowledge base."""

from __future__ import annotations

import time
from typing import Any

from support_common import cache
from support_common.config import Settings, get_settings
from support_common.logging import get_logger
from support_common.metrics import (
    KB_DOCUMENTS,
    RAG_LATENCY,
    RAG_QUERIES,
    RAG_TOP_SCORE,
)
from support_common.schemas import (
    IndexStats,
    RetrievedDocument,
    SearchRequest,
    SearchResponse,
)

from rag_engine.embeddings import Embedder, get_embedder
from rag_engine.vector_store import VectorStore, build_vector_store

log = get_logger(__name__)

CACHE_NAMESPACE = "rag:search"


class Retriever:
    """Embeds a query, searches the vector store, and shapes the results.

    Results are cached in Redis keyed by the exact query plus its filters.
    Support questions repeat heavily, so the cache absorbs a large share of
    traffic and keeps the p50 search well under the latency budget.
    """

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        embedder: Embedder | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.vector_store = vector_store or build_vector_store(self.settings)
        self.embedder = embedder or get_embedder(self.settings)

    async def search(self, request: SearchRequest, *, use_cache: bool = True) -> SearchResponse:
        """Return the knowledge base chunks most similar to ``request.query``."""
        started = time.perf_counter()
        top_k = request.top_k or self.settings.rag_top_k
        min_score = (
            request.min_score if request.min_score is not None else self.settings.rag_min_score
        )
        key = cache.cache_key(
            CACHE_NAMESPACE, request.query.lower().strip(), top_k, min_score, *request.categories
        )

        if use_cache:
            if (cached := await cache.get_json(key)) is not None:
                RAG_QUERIES.labels("hit").inc()
                response = SearchResponse.model_validate(cached)
                response.cached = True
                response.took_ms = round((time.perf_counter() - started) * 1000, 2)
                return response

        RAG_QUERIES.labels("miss").inc()
        embedding = await self.embedder.embed_query(request.query)

        where = self._build_filter(request.categories)
        # Over-fetch so the score floor cannot leave us with fewer than top_k
        # usable hits when the head of the list is weak.
        raw_hits = await self.vector_store.query(embedding, top_k=top_k * 2, where=where)

        results: list[RetrievedDocument] = []
        for hit in raw_hits:
            if hit.score < min_score:
                continue
            meta = hit.metadata
            results.append(
                RetrievedDocument(
                    doc_id=str(meta.get("doc_id", hit.id)),
                    title=str(meta.get("title", "Untitled")),
                    source=str(meta.get("source", "")),
                    category=str(meta.get("category", "general")),
                    content=hit.text,
                    score=round(hit.score, 4),
                    chunk_index=int(meta.get("chunk_index", 0) or 0),
                    metadata={"section": meta.get("section", ""), "tags": meta.get("tags", "")},
                )
            )
            if len(results) >= top_k:
                break

        elapsed = time.perf_counter() - started
        RAG_LATENCY.observe(elapsed)
        if results:
            RAG_TOP_SCORE.observe(results[0].score)

        response = SearchResponse(
            query=request.query,
            results=results,
            took_ms=round(elapsed * 1000, 2),
            cached=False,
        )
        log.info(
            "rag.search",
            query_chars=len(request.query),
            hits=len(results),
            top_score=response.top_score,
            duration_ms=response.took_ms,
        )
        if use_cache and results:
            await cache.set_json(key, response.model_dump(mode="json"))
        return response

    @staticmethod
    def _build_filter(categories: list[str]) -> dict[str, Any] | None:
        """Translate a category list into backend-agnostic filter syntax."""
        if not categories:
            return None
        if len(categories) == 1:
            return {"category": categories[0]}
        return {"category": {"$in": categories}}

    async def stats(self) -> IndexStats:
        """Describe the live index, for the ``/api/stats`` endpoint."""
        chunks = await self.vector_store.count()
        KB_DOCUMENTS.set(chunks)
        return IndexStats(
            collection=self.settings.chroma_collection,
            backend=self.vector_store.backend,
            documents=chunks,  # refined by the indexer, which knows doc count
            chunks=chunks,
            embedding_model=self.embedder.model_name,
            dimensions=self.embedder.dimensions,
        )

    async def ready(self) -> bool:
        """Readiness: the index exists and is not empty."""
        try:
            return await self.vector_store.count() > 0
        except Exception as exc:
            log.warning("rag.readiness_failed", error=str(exc))
            return False
