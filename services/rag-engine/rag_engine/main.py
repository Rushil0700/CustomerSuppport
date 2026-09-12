"""RAG Engine service (port 8002).

Owns the knowledge base index and answers semantic search queries. The agent is
its only production caller, but the search endpoint is deliberately usable on
its own so support staff can sanity-check retrieval without invoking the LLM.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Query
from fastapi.responses import JSONResponse
from support_common import cache
from support_common.app import create_app
from support_common.config import get_settings
from support_common.errors import IndexNotReady
from support_common.logging import get_logger
from support_common.schemas import IndexStats, SearchRequest, SearchResponse
from support_common.security import require_api_key

from rag_engine.indexer import build_index
from rag_engine.retriever import Retriever

log = get_logger(__name__)

SERVICE = "rag-engine"
VERSION = "0.1.0"

_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    """FastAPI dependency returning the process-wide retriever."""
    if _retriever is None:  # pragma: no cover - guarded by lifespan
        raise IndexNotReady("retriever not initialised")
    return _retriever


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Warm the embedding model and vector store before serving traffic.

    Doing this at startup rather than on the first request keeps the p99 of the
    first few searches from including a 2s model load.
    """
    global _retriever
    settings = get_settings()
    _retriever = Retriever(settings=settings)
    try:
        await _retriever.embedder.embed_query("warmup")
        count = await _retriever.vector_store.count()
        log.info("rag.ready", indexed_chunks=count, model=_retriever.embedder.model_name)
        if count == 0:
            log.warning("rag.empty_index", hint="run `make kb` to seed the knowledge base")
    except Exception as exc:
        # Serve anyway: /ready will report false and Kubernetes will hold traffic.
        log.error("rag.warmup_failed", error=str(exc))
    yield
    await cache.close()


app = create_app(
    service=SERVICE,
    title="Support RAG Engine",
    description="Semantic search over the support knowledge base (Chroma + sentence-transformers).",
    version=VERSION,
    lifespan=lifespan,
)

router = APIRouter(prefix="/api", tags=["rag"])


@router.post("/search", response_model=SearchResponse, summary="Semantic knowledge base search")
async def search(
    request: SearchRequest,
    use_cache: bool = Query(default=True, description="Set false to bypass the Redis cache"),
    retriever: Retriever = Depends(get_retriever),
) -> SearchResponse:
    """Return the top-k knowledge base chunks for a natural language query."""
    return await retriever.search(request, use_cache=use_cache)


@router.get("/stats", response_model=IndexStats, summary="Index size and configuration")
async def stats(retriever: Retriever = Depends(get_retriever)) -> IndexStats:
    return await retriever.stats()


@router.post(
    "/index/rebuild",
    summary="Re-index the knowledge base from disk",
    dependencies=[Depends(require_api_key)],
)
async def rebuild_index(
    reset: bool = Query(default=False, description="Drop the collection before indexing"),
    retriever: Retriever = Depends(get_retriever),
) -> dict[str, float | int | bool]:
    """Re-read ``support-kb/`` and refresh the vector index.

    Synchronous on purpose: a full rebuild of a few thousand chunks takes well
    under a minute locally, and an operator running it wants the count back.

    Reuses this process's own vector store and embedder rather than opening a
    second connection to the same on-disk collection - the vector store's own
    retry logic still protects against a *separate* process resetting the
    index concurrently, but there is no reason to open a redundant handle here.
    """
    report = await build_index(
        reset=reset, vector_store=retriever.vector_store, embedder=retriever.embedder
    )
    return report.as_dict()


app.include_router(router)


@app.get("/ready", include_in_schema=False)
async def ready() -> JSONResponse:
    """Readiness probe: the index must be populated before we take traffic."""
    retriever = _retriever
    index_ok = await retriever.ready() if retriever else False
    status = "ok" if index_ok else "degraded"
    return JSONResponse(
        status_code=200 if index_ok else 503,
        content={
            "status": status,
            "service": SERVICE,
            "version": VERSION,
            "dependencies": {
                "vector_store": "ok" if index_ok else "empty_or_unreachable",
                "cache": "ok" if await cache.healthy() else "unavailable",
            },
        },
    )
