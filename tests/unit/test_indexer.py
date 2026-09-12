"""Tests for the indexing pipeline: loader + embedder + vector store wired together."""

from __future__ import annotations

from pathlib import Path

import pytest
from rag_engine.indexer import build_index
from rag_engine.vector_store import ChromaVectorStore
from support_common.config import Settings


class FakeEmbedder:
    model_name = "fake"
    dimensions = 4

    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(texts)
        # Distinct-ish vectors so ordering isn't accidentally identical.
        return [[float(i % 4 == j) for j in range(4)] for i, _ in enumerate(texts)]

    async def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0, 0.0]


@pytest.fixture
def kb_dir(tmp_path: Path) -> Path:
    docs = tmp_path / "kb"
    (docs / "billing").mkdir(parents=True)
    (docs / "account").mkdir()
    (docs / "billing" / "refund.md").write_text(
        "---\nid: refund\ntitle: Refund policy\ncategory: billing\n---\n\n"
        "# Refund policy\n\nRefunds are available within 30 days.",
        encoding="utf-8",
    )
    (docs / "account" / "reset.md").write_text(
        "---\nid: reset\ntitle: Reset password\ncategory: account\n---\n\n"
        "# Reset password\n\nUse the forgot password link on the login page.",
        encoding="utf-8",
    )
    return docs


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(environment="ci", chroma_persist_dir=tmp_path / "chroma")


class TestBuildIndex:
    async def test_indexing_writes_every_document(self, kb_dir: Path, settings: Settings) -> None:
        store = ChromaVectorStore(str(settings.chroma_persist_dir), "test")
        embedder = FakeEmbedder()

        report = await build_index(
            kb_dir=kb_dir, vector_store=store, embedder=embedder, settings=settings
        )

        assert report.documents == 2
        assert report.chunks >= 2
        assert await store.count() == report.chunks

    async def test_a_missing_directory_raises(self, tmp_path: Path, settings: Settings) -> None:
        store = ChromaVectorStore(str(settings.chroma_persist_dir), "test")
        with pytest.raises(FileNotFoundError):
            await build_index(
                kb_dir=tmp_path / "nope",
                vector_store=store,
                embedder=FakeEmbedder(),
                settings=settings,
            )

    async def test_reset_clears_before_reindexing(self, kb_dir: Path, settings: Settings) -> None:
        store = ChromaVectorStore(str(settings.chroma_persist_dir), "test")
        await build_index(
            kb_dir=kb_dir, vector_store=store, embedder=FakeEmbedder(), settings=settings
        )
        before = await store.count()

        report = await build_index(
            kb_dir=kb_dir,
            vector_store=store,
            embedder=FakeEmbedder(),
            settings=settings,
            reset=True,
        )
        assert report.reset is True
        assert await store.count() == before  # same corpus, freshly written

    async def test_batching_respects_the_batch_size(self, kb_dir: Path, settings: Settings) -> None:
        store = ChromaVectorStore(str(settings.chroma_persist_dir), "test")
        embedder = FakeEmbedder()
        await build_index(
            kb_dir=kb_dir,
            vector_store=store,
            embedder=embedder,
            settings=settings,
            batch_size=1,
        )
        assert all(len(batch) == 1 for batch in embedder.batches)
        assert len(embedder.batches) >= 2

    def test_report_serialises_to_a_dict(self) -> None:
        from rag_engine.indexer import IndexReport

        report = IndexReport(documents=2, chunks=5, took_seconds=1.234, reset=False)
        assert report.as_dict() == {
            "documents": 2,
            "chunks": 5,
            "took_seconds": 1.23,
            "reset": False,
        }
