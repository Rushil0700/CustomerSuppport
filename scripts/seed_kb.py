#!/usr/bin/env python
"""Index the knowledge base into the vector store.

    python scripts/seed_kb.py               # incremental index
    python scripts/seed_kb.py --reset       # drop the collection first
    python scripts/seed_kb.py --check "how do I reset my password"

Run this once before starting the RAG engine, and again after editing
``support-kb/``. The ``--check`` flag runs a search afterwards so you can see
what the index actually returns, which is the quickest way to tell whether a
knowledge base change had the effect you expected.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "rag-engine"))

from rag_engine.indexer import build_index  # noqa: E402
from rag_engine.retriever import Retriever  # noqa: E402
from support_common.config import get_settings  # noqa: E402
from support_common.logging import configure_logging, get_logger  # noqa: E402
from support_common.schemas import SearchRequest  # noqa: E402

log = get_logger("seed_kb")


async def run(reset: bool, check: str | None, top_k: int) -> int:
    settings = get_settings()
    configure_logging("seed-kb", level=settings.log_level, fmt="console")

    model_name = (
        settings.embedding_model
        if settings.embedding_provider == "sentence_transformers"
        else settings.ollama_embedding_model
    )
    print(
        f"Indexing {settings.kb_dir}\n"
        f"  backend:    {settings.vector_backend}\n"
        f"  embeddings: {settings.embedding_provider} / {model_name}\n"
        f"  chunking:   {settings.kb_chunk_size} chars, {settings.kb_chunk_overlap} overlap\n"
    )

    try:
        report = await build_index(reset=reset)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("Run `python scripts/generate_kb.py` first.", file=sys.stderr)
        return 1

    print(
        f"\nIndexed {report.chunks} chunks from {report.documents} documents "
        f"in {report.took_seconds}s"
    )

    if check:
        retriever = Retriever(settings=settings)
        response = await retriever.search(SearchRequest(query=check, top_k=top_k), use_cache=False)
        print(f'\nSearch: "{check}"  ({response.took_ms}ms)')
        if not response.results:
            print(
                "  no results above the score floor "
                f"({settings.rag_min_score}) - the index may be empty"
            )
            return 1
        for rank, doc in enumerate(response.results, start=1):
            preview = " ".join(doc.content.split())[:110]
            print(f"  {rank}. [{doc.score:.3f}] {doc.title}")
            print(f"      {doc.category}/{doc.doc_id}")
            print(f"      {preview}...")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="drop the collection before indexing")
    parser.add_argument("--check", metavar="QUERY", help="run a test search after indexing")
    parser.add_argument("--top-k", type=int, default=5, help="results to show for --check")
    args = parser.parse_args()
    return asyncio.run(run(args.reset, args.check, args.top_k))


if __name__ == "__main__":
    raise SystemExit(main())
