"""Vector store abstraction over Chroma (local) and Pinecone (cloud).

Chroma is the default: it is embedded, needs no account, and persists to disk,
which makes the whole stack runnable on a laptop. Pinecone is wired up behind
the same interface for the cloud deployment, selected by ``VECTOR_BACKEND``.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from support_common.config import Settings, get_settings
from support_common.errors import IndexNotReady
from support_common.logging import get_logger

log = get_logger(__name__)


@dataclass
class VectorRecord:
    """A chunk to index."""

    id: str
    text: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VectorHit:
    """A retrieval result with a similarity score in [0, 1]."""

    id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore(ABC):
    """Minimal vector index interface used by the RAG engine."""

    backend: str

    @abstractmethod
    async def upsert(self, records: list[VectorRecord]) -> int:
        """Insert or replace records; returns how many were written."""

    @abstractmethod
    async def query(
        self,
        embedding: list[float],
        top_k: int,
        *,
        where: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        """Return the ``top_k`` nearest chunks, most similar first."""

    @abstractmethod
    async def count(self) -> int:
        """Number of indexed chunks."""

    @abstractmethod
    async def reset(self) -> None:
        """Drop and recreate the collection (used by a full re-index)."""


class ChromaVectorStore(VectorStore):
    """Embedded Chroma with on-disk persistence.

    Chroma's Python client is synchronous, so every call is pushed to a worker
    thread; the event loop stays free to serve other searches.
    """

    backend = "chroma"

    def __init__(self, persist_dir: str, collection_name: str) -> None:
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self._collection: Any | None = None
        self._client: Any | None = None
        self._lock = asyncio.Lock()

    def _connect(self) -> Any:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self._client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
        # Cosine space matches our unit-normalised embeddings; the default L2
        # would rank longer documents differently for no good reason.
        return self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    async def _get_collection(self) -> Any:
        if self._collection is not None:
            return self._collection
        async with self._lock:
            if self._collection is None:
                self._collection = await asyncio.to_thread(self._connect)
                log.info(
                    "vectorstore.connected",
                    backend=self.backend,
                    collection=self.collection_name,
                    path=self.persist_dir,
                )
        return self._collection

    async def upsert(self, records: list[VectorRecord]) -> int:
        if not records:
            return 0
        collection = await self._get_collection()

        def _write() -> None:
            collection.upsert(
                ids=[r.id for r in records],
                embeddings=[r.embedding for r in records],
                documents=[r.text for r in records],
                metadatas=[_flatten_metadata(r.metadata) for r in records],
            )

        await asyncio.to_thread(_write)
        return len(records)

    async def query(
        self,
        embedding: list[float],
        top_k: int,
        *,
        where: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        collection = await self._get_collection()

        def _search() -> dict[str, Any]:
            return collection.query(
                query_embeddings=[embedding],
                n_results=top_k,
                where=where or None,
                include=["documents", "metadatas", "distances"],
            )

        raw = await asyncio.to_thread(_search)
        ids = (raw.get("ids") or [[]])[0]
        documents = (raw.get("documents") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]

        hits: list[VectorHit] = []
        for doc_id, text, meta, distance in zip(
            ids, documents, metadatas, distances, strict=False
        ):
            hits.append(
                VectorHit(
                    id=doc_id,
                    text=text or "",
                    # Chroma returns cosine *distance*; convert to similarity
                    # and clamp, since float error can push it just outside [0,1].
                    score=max(0.0, min(1.0, 1.0 - float(distance))),
                    metadata=dict(meta or {}),
                )
            )
        return hits

    async def count(self) -> int:
        collection = await self._get_collection()
        return int(await asyncio.to_thread(collection.count))

    async def reset(self) -> None:
        await self._get_collection()  # guarantees self._client is connected
        client = self._client

        def _drop() -> None:
            try:
                client.delete_collection(self.collection_name)
            except Exception:  # collection may already be gone
                pass

        async with self._lock:
            await asyncio.to_thread(_drop)
            self._collection = None
        await self._get_collection()
        log.info("vectorstore.reset", collection=self.collection_name)


class PineconeVectorStore(VectorStore):
    """Pinecone serverless index, for the cloud deployment."""

    backend = "pinecone"

    def __init__(
        self,
        api_key: str,
        index_name: str,
        dimensions: int,
        cloud: str = "aws",
        region: str = "us-east-1",
    ) -> None:
        if not api_key:
            raise IndexNotReady("PINECONE_API_KEY is required when VECTOR_BACKEND=pinecone")
        self.api_key = api_key
        self.index_name = index_name
        self.dimensions = dimensions
        self.cloud = cloud
        self.region = region
        self._index: Any | None = None
        self._lock = asyncio.Lock()

    def _connect(self) -> Any:
        from pinecone import Pinecone, ServerlessSpec

        client = Pinecone(api_key=self.api_key)
        existing = {i["name"] for i in client.list_indexes()}
        if self.index_name not in existing:
            client.create_index(
                name=self.index_name,
                dimension=self.dimensions,
                metric="cosine",
                spec=ServerlessSpec(cloud=self.cloud, region=self.region),
            )
        return client.Index(self.index_name)

    async def _get_index(self) -> Any:
        if self._index is not None:
            return self._index
        async with self._lock:
            if self._index is None:
                self._index = await asyncio.to_thread(self._connect)
                log.info("vectorstore.connected", backend=self.backend, index=self.index_name)
        return self._index

    async def upsert(self, records: list[VectorRecord]) -> int:
        if not records:
            return 0
        index = await self._get_index()
        # Pinecone caps a single upsert request; 100 vectors stays well inside
        # the 2MB payload limit for our chunk size.
        batches = [records[i : i + 100] for i in range(0, len(records), 100)]

        def _write() -> None:
            for batch in batches:
                index.upsert(
                    vectors=[
                        {
                            "id": r.id,
                            "values": r.embedding,
                            "metadata": {**_flatten_metadata(r.metadata), "text": r.text},
                        }
                        for r in batch
                    ]
                )

        await asyncio.to_thread(_write)
        return len(records)

    async def query(
        self,
        embedding: list[float],
        top_k: int,
        *,
        where: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        index = await self._get_index()

        def _search() -> Any:
            return index.query(
                vector=embedding,
                top_k=top_k,
                include_metadata=True,
                filter=where or None,
            )

        raw = await asyncio.to_thread(_search)
        hits = []
        for match in raw.get("matches", []):
            metadata = dict(match.get("metadata") or {})
            text = metadata.pop("text", "")
            hits.append(
                VectorHit(
                    id=match["id"],
                    text=text,
                    score=max(0.0, min(1.0, float(match.get("score", 0.0)))),
                    metadata=metadata,
                )
            )
        return hits

    async def count(self) -> int:
        index = await self._get_index()
        stats = await asyncio.to_thread(index.describe_index_stats)
        return int(stats.get("total_vector_count", 0))

    async def reset(self) -> None:
        index = await self._get_index()
        await asyncio.to_thread(lambda: index.delete(delete_all=True))
        log.info("vectorstore.reset", index=self.index_name)


def _flatten_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Both backends accept only scalar metadata values; join lists, drop None."""
    flat: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, list | tuple | set):
            flat[key] = ",".join(str(v) for v in value)
        elif isinstance(value, str | int | float | bool):
            flat[key] = value
        else:
            flat[key] = str(value)
    return flat


def build_vector_store(settings: Settings | None = None) -> VectorStore:
    """Instantiate the configured backend."""
    settings = settings or get_settings()
    if settings.vector_backend == "pinecone":
        return PineconeVectorStore(
            api_key=settings.pinecone_api_key,
            index_name=settings.pinecone_index,
            dimensions=settings.embedding_dimensions,
            cloud=settings.pinecone_cloud,
            region=settings.pinecone_region,
        )
    settings.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
    return ChromaVectorStore(str(settings.chroma_persist_dir), settings.chroma_collection)
