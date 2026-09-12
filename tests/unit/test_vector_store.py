"""Tests for the Chroma vector store, against a real on-disk collection.

Chroma is embedded (no network, no server process), so these run at unit-test
speed while exercising the real backend rather than a fake.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rag_engine.vector_store import (
    ChromaVectorStore,
    VectorRecord,
    _flatten_metadata,
    build_vector_store,
)


def vec(x: float, y: float) -> list[float]:
    """A 2D unit-ish vector; Chroma doesn't require normalisation to work."""
    return [x, y, 0.0, 0.0]


@pytest.fixture
def store(tmp_path: Path) -> ChromaVectorStore:
    return ChromaVectorStore(str(tmp_path / "chroma"), "test_collection")


class TestUpsertAndQuery:
    async def test_upserting_nothing_is_a_no_op(self, store: ChromaVectorStore) -> None:
        assert await store.upsert([]) == 0

    async def test_a_record_can_be_written_and_retrieved(self, store: ChromaVectorStore) -> None:
        written = await store.upsert(
            [
                VectorRecord(
                    id="a", text="hello world", embedding=vec(1, 0), metadata={"doc_id": "d1"}
                )
            ]
        )
        assert written == 1
        assert await store.count() == 1

        hits = await store.query(vec(1, 0), top_k=5)
        assert len(hits) == 1
        assert hits[0].id == "a"
        assert hits[0].text == "hello world"
        assert hits[0].score == pytest.approx(1.0, abs=1e-4)

    async def test_results_are_ranked_by_similarity(self, store: ChromaVectorStore) -> None:
        await store.upsert(
            [
                VectorRecord(id="close", text="t", embedding=vec(1, 0), metadata={}),
                VectorRecord(id="far", text="t", embedding=vec(0, 1), metadata={}),
            ]
        )
        hits = await store.query(vec(1, 0), top_k=2)
        assert [h.id for h in hits] == ["close", "far"]
        assert hits[0].score > hits[1].score

    async def test_upserting_the_same_id_overwrites(self, store: ChromaVectorStore) -> None:
        """Deterministic chunk ids mean re-indexing must replace, not duplicate."""
        await store.upsert(
            [VectorRecord(id="a", text="version one", embedding=vec(1, 0), metadata={})]
        )
        await store.upsert(
            [VectorRecord(id="a", text="version two", embedding=vec(1, 0), metadata={})]
        )

        assert await store.count() == 1
        hits = await store.query(vec(1, 0), top_k=1)
        assert hits[0].text == "version two"

    async def test_a_category_filter_narrows_the_results(self, store: ChromaVectorStore) -> None:
        await store.upsert(
            [
                VectorRecord(
                    id="a", text="t", embedding=vec(1, 0), metadata={"category": "billing"}
                ),
                VectorRecord(
                    id="b", text="t", embedding=vec(1, 0), metadata={"category": "security"}
                ),
            ]
        )
        hits = await store.query(vec(1, 0), top_k=5, where={"category": "billing"})
        assert [h.id for h in hits] == ["a"]

    async def test_metadata_round_trips(self, store: ChromaVectorStore) -> None:
        await store.upsert(
            [
                VectorRecord(
                    id="a",
                    text="t",
                    embedding=vec(1, 0),
                    metadata={"doc_id": "d1", "title": "T", "chunk_index": 2},
                )
            ]
        )
        hits = await store.query(vec(1, 0), top_k=1)
        assert hits[0].metadata["doc_id"] == "d1"
        assert hits[0].metadata["chunk_index"] == 2


class TestReset:
    async def test_reset_empties_the_collection(self, store: ChromaVectorStore) -> None:
        await store.upsert([VectorRecord(id="a", text="t", embedding=vec(1, 0), metadata={})])
        assert await store.count() == 1

        await store.reset()
        assert await store.count() == 0

    async def test_the_collection_is_usable_immediately_after_reset(
        self, store: ChromaVectorStore
    ) -> None:
        await store.reset()
        await store.upsert([VectorRecord(id="a", text="t", embedding=vec(1, 0), metadata={})])
        assert await store.count() == 1

    async def test_reset_before_any_connection_does_not_error(self, tmp_path: Path) -> None:
        fresh = ChromaVectorStore(str(tmp_path / "fresh"), "col")
        await fresh.reset()
        assert await fresh.count() == 0


class TestConcurrency:
    async def test_concurrent_first_access_connects_only_once(
        self, store: ChromaVectorStore
    ) -> None:
        import asyncio

        results = await asyncio.gather(*[store._get_collection() for _ in range(8)])
        assert len({id(r) for r in results}) == 1


class TestMetadataFlattening:
    def test_lists_are_joined_into_a_string(self) -> None:
        assert _flatten_metadata({"tags": ["a", "b"]}) == {"tags": "a,b"}

    def test_none_values_are_dropped(self) -> None:
        assert _flatten_metadata({"a": 1, "b": None}) == {"a": 1}

    def test_scalars_pass_through_unchanged(self) -> None:
        flat = _flatten_metadata({"i": 1, "f": 1.5, "s": "x", "b": True})
        assert flat == {"i": 1, "f": 1.5, "s": "x", "b": True}

    def test_other_types_are_stringified(self) -> None:
        assert _flatten_metadata({"x": {"nested": 1}}) == {"x": "{'nested': 1}"}


class TestFactory:
    def test_chroma_is_the_default_backend(self, tmp_path: Path) -> None:
        from support_common.config import Settings

        settings = Settings(
            environment="ci", vector_backend="chroma", chroma_persist_dir=tmp_path / "c"
        )
        store = build_vector_store(settings)
        assert store.backend == "chroma"
        assert (tmp_path / "c").exists()

    def test_pinecone_without_a_key_raises_immediately(self) -> None:
        from support_common.config import Settings
        from support_common.errors import IndexNotReady

        settings = Settings(environment="ci", vector_backend="pinecone", pinecone_api_key="")
        with pytest.raises(IndexNotReady, match="PINECONE_API_KEY"):
            build_vector_store(settings)
