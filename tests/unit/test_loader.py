"""Tests for knowledge base loading and chunking."""

from __future__ import annotations

from pathlib import Path

import pytest

from rag_engine.loader import (
    KBDocument,
    chunk_document,
    chunk_documents,
    load_documents,
    parse_front_matter,
    split_sections,
)

SAMPLE = """\
---
id: billing-refund-policy
title: Refund policy
category: billing
tags: [refund, billing, policy]
audience: customer
---

# Refund policy

Intro paragraph explaining the scope.

## Monthly plans

Monthly subscriptions can be cancelled at any time.

## Annual plans

Annual plans are refundable within 30 days.
"""


class TestFrontMatter:
    def test_scalar_and_list_values_are_parsed(self) -> None:
        meta, body = parse_front_matter(SAMPLE)
        assert meta["id"] == "billing-refund-policy"
        assert meta["title"] == "Refund policy"
        assert meta["tags"] == ["refund", "billing", "policy"]
        assert body.lstrip().startswith("# Refund policy")

    def test_a_document_without_front_matter_is_returned_whole(self) -> None:
        meta, body = parse_front_matter("# Just a heading\n\ntext")
        assert meta == {}
        assert body == "# Just a heading\n\ntext"

    def test_quoted_values_are_unwrapped(self) -> None:
        meta, _ = parse_front_matter('---\ntitle: "Quoted title"\n---\n\nbody')
        assert meta["title"] == "Quoted title"


class TestSectionSplitting:
    def test_headings_become_sections(self) -> None:
        _, body = parse_front_matter(SAMPLE)
        sections = split_sections(body)
        names = [name for name, _ in sections]
        assert "Refund policy" in names
        assert "Monthly plans" in names
        assert "Annual plans" in names

    def test_text_before_the_first_heading_is_kept(self) -> None:
        sections = split_sections("preamble text\n\n# Heading\n\nbody")
        assert sections[0] == ("", "preamble text")

    def test_content_without_headings_is_one_section(self) -> None:
        assert split_sections("just some text") == [("", "just some text")]


class TestChunking:
    def _doc(self, content: str) -> KBDocument:
        return KBDocument(
            doc_id="d1", title="T", category="c", source="c/d1.md", content=content
        )

    def test_a_short_document_is_one_chunk_per_section(self) -> None:
        chunks = chunk_document(self._doc("# A\n\nshort body"), chunk_size=900)
        assert len(chunks) == 1
        assert chunks[0].content == "short body"

    def test_long_content_is_split(self) -> None:
        paragraphs = "\n\n".join(f"Paragraph {i} " + "word " * 40 for i in range(12))
        chunks = chunk_document(self._doc(paragraphs), chunk_size=500, overlap=50)
        assert len(chunks) > 1
        assert all(len(c.content) <= 600 for c in chunks)

    def test_an_oversized_paragraph_is_hard_split(self) -> None:
        chunks = chunk_document(self._doc("x" * 2500), chunk_size=500, overlap=50)
        assert len(chunks) >= 5

    def test_chunk_ids_are_deterministic(self) -> None:
        """Re-indexing unchanged content must overwrite, not duplicate."""
        document = self._doc("# A\n\n" + "text " * 200)
        first = [c.chunk_id for c in chunk_document(document)]
        second = [c.chunk_id for c in chunk_document(document)]
        assert first == second

    def test_changed_content_produces_different_ids(self) -> None:
        a = chunk_document(self._doc("# A\n\noriginal text here"))[0]
        b = chunk_document(self._doc("# A\n\nrevised text here"))[0]
        assert a.chunk_id != b.chunk_id

    def test_embedding_text_includes_the_title_and_section(self) -> None:
        chunk = chunk_document(self._doc("# Monthly plans\n\nbody text"))[0]
        assert chunk.embedding_text.startswith("T - Monthly plans")
        assert "body text" in chunk.embedding_text

    def test_metadata_carries_the_fields_search_filters_on(self) -> None:
        metadata = chunk_document(self._doc("# A\n\nbody"))[0].to_metadata()
        assert metadata["doc_id"] == "d1"
        assert metadata["category"] == "c"
        assert metadata["source"] == "c/d1.md"


class TestLoading:
    def test_documents_are_loaded_from_disk(self, tmp_path: Path) -> None:
        (tmp_path / "billing").mkdir()
        (tmp_path / "billing" / "refund.md").write_text(SAMPLE, encoding="utf-8")

        documents = load_documents(tmp_path)
        assert len(documents) == 1
        assert documents[0].doc_id == "billing-refund-policy"
        assert documents[0].category == "billing"
        assert documents[0].source == "billing/refund.md"

    def test_readme_files_are_excluded(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Index\n\nnot an article", encoding="utf-8")
        (tmp_path / "real.md").write_text(SAMPLE, encoding="utf-8")
        assert len(load_documents(tmp_path)) == 1

    def test_the_category_falls_back_to_the_folder_name(self, tmp_path: Path) -> None:
        (tmp_path / "security").mkdir()
        (tmp_path / "security" / "a.md").write_text("# Encryption\n\nbody", encoding="utf-8")
        assert load_documents(tmp_path)[0].category == "security"

    def test_a_missing_directory_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_documents(tmp_path / "nope")

    def test_chunking_a_corpus_returns_chunks_for_every_document(
        self, tmp_path: Path
    ) -> None:
        for i in range(3):
            (tmp_path / f"doc{i}.md").write_text(
                f"---\nid: d{i}\ntitle: T{i}\ncategory: c\n---\n\n# H\n\nbody text",
                encoding="utf-8",
            )
        chunks = chunk_documents(load_documents(tmp_path))
        assert {c.doc_id for c in chunks} == {"d0", "d1", "d2"}


class TestRealCorpus:
    """Guards on the generated knowledge base itself."""

    @pytest.fixture(scope="class")
    def kb_dir(self) -> Path:
        path = Path(__file__).resolve().parents[2] / "support-kb"
        if not path.exists():
            pytest.skip("support-kb not generated; run scripts/generate_kb.py")
        return path

    def test_the_corpus_meets_the_500_document_target(self, kb_dir: Path) -> None:
        assert len(load_documents(kb_dir)) >= 500

    def test_every_document_has_an_id_title_and_category(self, kb_dir: Path) -> None:
        for document in load_documents(kb_dir):
            assert document.doc_id and document.title and document.category

    def test_document_ids_are_unique(self, kb_dir: Path) -> None:
        ids = [d.doc_id for d in load_documents(kb_dir)]
        assert len(ids) == len(set(ids))

    def test_chunks_stay_within_the_configured_size(self, kb_dir: Path) -> None:
        chunks = chunk_documents(load_documents(kb_dir), chunk_size=900, overlap=150)
        oversized = [c for c in chunks if len(c.content) > 1100]
        assert not oversized, f"{len(oversized)} chunks exceed the size budget"
