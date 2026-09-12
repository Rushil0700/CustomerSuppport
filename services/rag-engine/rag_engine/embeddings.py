"""Embedding providers.

Two local options, both free and key-less:

``sentence_transformers``  all-MiniLM-L6-v2 on CPU, 384-dim, ~5ms/query
``ollama``                 nomic-embed-text via the daemon already running the
                           chat model, 768-dim, slightly better recall

The provider is chosen by ``EMBEDDING_PROVIDER``. Both implement the same tiny
interface so the vector store never needs to know which one is active.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

import httpx
from support_common.config import Settings, get_settings
from support_common.errors import UpstreamUnavailable
from support_common.logging import get_logger

log = get_logger(__name__)


class Embedder(ABC):
    """Turns text into dense vectors."""

    model_name: str
    dimensions: int

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of knowledge base chunks."""

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Embed a single search query."""


class SentenceTransformerEmbedder(Embedder):
    """Local CPU embeddings via sentence-transformers.

    The model is loaded lazily on first use (it costs ~2s and ~90MB of RAM) and
    encoding runs in a worker thread so it never blocks the event loop.
    """

    def __init__(self, model_name: str, batch_size: int = 64) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._model: object | None = None
        self._lock = asyncio.Lock()
        self.dimensions = 384

    async def _get_model(self) -> object:
        if self._model is not None:
            return self._model
        async with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                log.info("embeddings.loading_model", model=self.model_name)
                model = await asyncio.to_thread(SentenceTransformer, self.model_name)
                # Renamed in sentence-transformers 5; support both spellings.
                get_dim = (
                    getattr(model, "get_embedding_dimension", None)
                    or model.get_sentence_embedding_dimension
                )
                self.dimensions = int(get_dim())
                self._model = model
                log.info("embeddings.model_ready", dimensions=self.dimensions)
        return self._model

    async def _encode(self, texts: list[str], is_query: bool) -> list[list[float]]:
        model = await self._get_model()

        def _run() -> list[list[float]]:
            vectors = model.encode(  # type: ignore[attr-defined]
                texts,
                batch_size=self.batch_size,
                normalize_embeddings=True,  # cosine similarity becomes a dot product
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            return [v.tolist() for v in vectors]

        del is_query  # symmetric model: queries and documents share an encoder
        return await asyncio.to_thread(_run)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._encode(texts, is_query=False)

    async def embed_query(self, text: str) -> list[float]:
        return (await self._encode([text], is_query=True))[0]


class OllamaEmbedder(Embedder):
    """Embeddings from the Ollama daemon (e.g. ``nomic-embed-text``)."""

    def __init__(self, host: str, model_name: str, timeout: float = 60.0) -> None:
        self.host = host.rstrip("/")
        self.model_name = model_name
        self.dimensions = 768
        self._client = httpx.AsyncClient(base_url=self.host, timeout=timeout)

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = await self._client.post(
                "/api/embed", json={"model": self.model_name, "input": texts}
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable(f"ollama embeddings failed: {exc}") from exc

        vectors = response.json().get("embeddings", [])
        if vectors:
            self.dimensions = len(vectors[0])
        return [_normalise(v) for v in vectors]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text]))[0]

    async def aclose(self) -> None:
        await self._client.aclose()


def _normalise(vector: list[float]) -> list[float]:
    """Scale to unit length so cosine distance behaves consistently."""
    magnitude = sum(x * x for x in vector) ** 0.5
    if magnitude == 0:
        return vector
    return [x / magnitude for x in vector]


_embedder: Embedder | None = None


def build_embedder(settings: Settings | None = None) -> Embedder:
    """Construct the configured embedder without caching it."""
    settings = settings or get_settings()
    if settings.embedding_provider == "ollama":
        return OllamaEmbedder(
            settings.ollama_host,
            settings.ollama_embedding_model,
            timeout=settings.ollama_timeout_seconds,
        )
    return SentenceTransformerEmbedder(
        settings.embedding_model, batch_size=settings.embedding_batch_size
    )


def get_embedder(settings: Settings | None = None) -> Embedder:
    """Return the process-wide embedder.

    A module-level singleton rather than ``lru_cache``: the model weights are
    ~90MB and loading them twice in one process is pure waste, and ``Settings``
    is not hashable so it cannot be a cache key anyway.
    """
    global _embedder
    if _embedder is None:
        _embedder = build_embedder(settings)
    return _embedder


def reset_embedder() -> None:
    """Drop the cached embedder. For tests that swap the provider."""
    global _embedder
    _embedder = None
