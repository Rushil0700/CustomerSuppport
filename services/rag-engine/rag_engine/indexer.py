"""Build the vector index from the Markdown knowledge base.

Used both by ``scripts/seed_kb.py`` (offline) and the service's
``POST /api/index/rebuild`` endpoint (online re-index after a KB edit).
"""

from __future__ import annotations

import time
from pathlib import Path

from support_common import cache
from support_common.config import Settings, get_settings
from support_common.logging import get_logger
from support_common.metrics import KB_DOCUMENTS

from rag_engine.embeddings import Embedder, get_embedder
from rag_engine.loader import chunk_documents, load_documents
from rag_engine.retriever import CACHE_NAMESPACE
from rag_engine.vector_store import VectorRecord, VectorStore, build_vector_store

log = get_logger(__name__)


class IndexReport:
    """Outcome of an indexing run."""

    def __init__(self, documents: int, chunks: int, took_seconds: float, reset: bool) -> None:
        self.documents = documents
        self.chunks = chunks
        self.took_seconds = round(took_seconds, 2)
        self.reset = reset

    def as_dict(self) -> dict[str, float | int | bool]:
        return {
            "documents": self.documents,
            "chunks": self.chunks,
            "took_seconds": self.took_seconds,
            "reset": self.reset,
        }


async def build_index(
    *,
    kb_dir: Path | None = None,
    reset: bool = False,
    batch_size: int = 128,
    vector_store: VectorStore | None = None,
    embedder: Embedder | None = None,
    settings: Settings | None = None,
) -> IndexReport:
    """Embed every knowledge base chunk and upsert it into the vector store.

    ``reset=True`` drops the collection first, which is the right choice after
    deleting or renaming documents; an incremental run only overwrites chunks
    whose content hash still matches their id.
    """
    settings = settings or get_settings()
    kb_dir = kb_dir or settings.kb_dir
    store = vector_store or build_vector_store(settings)
    embed = embedder or get_embedder(settings)

    started = time.perf_counter()
    documents = load_documents(kb_dir)
    if not documents:
        raise FileNotFoundError(f"no markdown documents found under {kb_dir}")

    chunks = chunk_documents(
        documents, chunk_size=settings.kb_chunk_size, overlap=settings.kb_chunk_overlap
    )

    if reset:
        await store.reset()

    written = 0
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        vectors = await embed.embed_documents([c.embedding_text for c in batch])
        written += await store.upsert(
            [
                VectorRecord(
                    id=chunk.chunk_id,
                    text=chunk.content,
                    embedding=vector,
                    metadata=chunk.to_metadata(),
                )
                for chunk, vector in zip(batch, vectors, strict=True)
            ]
        )
        log.info("kb.index_progress", written=written, total=len(chunks))

    # Stale search results would otherwise survive a KB correction for a full TTL.
    invalidated = await cache.invalidate(f"support:{CACHE_NAMESPACE}:*")
    KB_DOCUMENTS.set(await store.count())

    report = IndexReport(
        documents=len(documents),
        chunks=written,
        took_seconds=time.perf_counter() - started,
        reset=reset,
    )
    log.info("kb.index_complete", **report.as_dict(), cache_keys_invalidated=invalidated)
    return report
