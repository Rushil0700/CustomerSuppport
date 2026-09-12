"""Knowledge base loading and chunking.

Every file in ``support-kb/`` is a Markdown document with YAML front matter::

    ---
    id: billing-refund-policy
    title: Refund policy for annual plans
    category: billing
    tags: [refund, billing, annual]
    ---

    # Refund policy ...

Documents are split on Markdown headings first and only then by size, so a
retrieved chunk almost always begins at a section boundary and reads as a
complete instruction rather than a sentence fragment.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from support_common.logging import get_logger

log = get_logger(__name__)

FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


@dataclass
class KBDocument:
    """One knowledge base article."""

    doc_id: str
    title: str
    category: str
    source: str
    content: str
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KBChunk:
    """An indexable slice of a document."""

    chunk_id: str
    doc_id: str
    title: str
    category: str
    source: str
    section: str
    content: str
    chunk_index: int
    tags: list[str] = field(default_factory=list)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "category": self.category,
            "source": self.source,
            "section": self.section,
            "chunk_index": self.chunk_index,
            "tags": self.tags,
        }

    @property
    def embedding_text(self) -> str:
        """Prefixing the title and section measurably improves recall on short
        chunks, which would otherwise lack the vocabulary of their own heading."""
        header = f"{self.title} - {self.section}" if self.section else self.title
        return f"{header}\n\n{self.content}"


def parse_front_matter(raw: str) -> tuple[dict[str, Any], str]:
    """Split a minimal YAML front-matter block from the body.

    Deliberately hand-rolled rather than pulling in PyYAML: the KB uses only
    ``key: value`` and ``key: [a, b]`` lines, and this keeps the indexer's
    dependency surface small.
    """
    match = FRONT_MATTER_RE.match(raw)
    if not match:
        return {}, raw

    meta: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key] = [v.strip().strip("\"'") for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key] = value.strip("\"'")
    return meta, raw[match.end() :]


def load_documents(kb_dir: Path) -> list[KBDocument]:
    """Read every ``.md`` file under ``kb_dir`` into a document."""
    if not kb_dir.exists():
        raise FileNotFoundError(f"knowledge base directory not found: {kb_dir}")

    documents: list[KBDocument] = []
    for path in sorted(kb_dir.rglob("*.md")):
        if path.name.lower() in {"readme.md", "index.md"}:
            continue
        raw = path.read_text(encoding="utf-8")
        meta, body = parse_front_matter(raw)
        if not body.strip():
            log.warning("kb.empty_document", path=str(path))
            continue

        relative = path.relative_to(kb_dir).as_posix()
        tags = meta.get("tags", [])
        documents.append(
            KBDocument(
                doc_id=str(meta.get("id") or path.stem),
                title=str(meta.get("title") or _first_heading(body) or path.stem),
                category=str(meta.get("category") or path.parent.name or "general"),
                source=relative,
                content=body.strip(),
                tags=[t for t in tags] if isinstance(tags, list) else [str(tags)],
                metadata={
                    k: v for k, v in meta.items() if k not in {"id", "title", "category", "tags"}
                },
            )
        )
    log.info("kb.documents_loaded", count=len(documents), path=str(kb_dir))
    return documents


def _first_heading(body: str) -> str | None:
    match = HEADING_RE.search(body)
    return match.group(2).strip() if match else None


def split_sections(content: str) -> list[tuple[str, str]]:
    """Split Markdown into ``(heading, text)`` pairs, preserving order."""
    matches = list(HEADING_RE.finditer(content))
    if not matches:
        return [("", content.strip())]

    sections: list[tuple[str, str]] = []
    preamble = content[: matches[0].start()].strip()
    if preamble:
        sections.append(("", preamble))

    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        text = content[match.end() : end].strip()
        if text:
            sections.append((match.group(2).strip(), text))
    return sections


def chunk_document(
    document: KBDocument, *, chunk_size: int = 900, overlap: int = 150
) -> list[KBChunk]:
    """Split one document into overlapping, section-aware chunks."""
    chunks: list[KBChunk] = []
    for section, text in split_sections(document.content):
        for piece in _split_text(text, chunk_size, overlap):
            index = len(chunks)
            chunks.append(
                KBChunk(
                    chunk_id=_chunk_id(document.doc_id, index, piece),
                    doc_id=document.doc_id,
                    title=document.title,
                    category=document.category,
                    source=document.source,
                    section=section,
                    content=piece,
                    chunk_index=index,
                    tags=document.tags,
                )
            )
    return chunks


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Greedy paragraph packing with a character overlap between chunks."""
    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if text else []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        # A single oversized paragraph (a long table or code block) is hard-split.
        if len(paragraph) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            step = chunk_size - overlap
            for start in range(0, len(paragraph), step):
                chunks.append(paragraph[start : start + chunk_size])
            continue

        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            current = f"{tail}\n\n{paragraph}".strip() if tail else paragraph

    if current:
        chunks.append(current)
    return chunks


def _chunk_id(doc_id: str, index: int, content: str) -> str:
    """Deterministic id: re-indexing unchanged content overwrites in place
    rather than accumulating duplicate vectors."""
    digest = hashlib.sha1(content.encode("utf-8")).hexdigest()[:8]
    return f"{doc_id}::{index}::{digest}"


def chunk_documents(
    documents: list[KBDocument], *, chunk_size: int = 900, overlap: int = 150
) -> list[KBChunk]:
    """Chunk a whole knowledge base."""
    chunks: list[KBChunk] = []
    for document in documents:
        chunks.extend(chunk_document(document, chunk_size=chunk_size, overlap=overlap))
    log.info("kb.documents_chunked", documents=len(documents), chunks=len(chunks))
    return chunks
