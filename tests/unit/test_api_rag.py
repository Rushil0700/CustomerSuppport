"""API tests for the RAG engine, with the vector store and embedder faked."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from support_common.config import Settings
from support_common.schemas import SearchRequest

from rag_engine import main as rag_main
from rag_engine.retriever import Retriever
from rag_engine.vector_store import VectorHit, VectorRecord, VectorStore


class FakeEmbedder:
    """Deterministic vectors, no model download."""

    model_name = "fake-embedder"
    dimensions = 4

    def __init__(self) -> None:
        self.calls = 0

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        self.calls += 1
        return [1.0, 0.0, 0.0, 0.0]


class FakeVectorStore(VectorStore):
    """In-memory store returning a fixed, ordered hit list."""

    backend = "fake"

    def __init__(self, hits: list[VectorHit] | None = None) -> None:
        self.hits = hits if hits is not None else _default_hits()
        self.written: list[VectorRecord] = []
        self.reset_called = False
        self.last_where: dict[str, Any] | None = None

    async def upsert(self, records: list[VectorRecord]) -> int:
        self.written.extend(records)
        return len(records)

    async def query(
        self, embedding: list[float], top_k: int, *, where: dict[str, Any] | None = None
    ) -> list[VectorHit]:
        self.last_where = where
        hits = self.hits
        if where and "category" in where and isinstance(where["category"], str):
            hits = [h for h in hits if h.metadata.get("category") == where["category"]]
        return hits[:top_k]

    async def count(self) -> int:
        return len(self.hits)

    async def reset(self) -> None:
        self.reset_called = True
        self.hits = []


def _default_hits() -> list[VectorHit]:
    def hit(doc_id: str, title: str, category: str, score: float, chunk: int = 0) -> VectorHit:
        return VectorHit(
            id=f"{doc_id}::{chunk}",
            text=f"Content of {title}, chunk {chunk}.",
            score=score,
            metadata={
                "doc_id": doc_id,
                "title": title,
                "category": category,
                "source": f"{category}/{doc_id}.md",
                "chunk_index": chunk,
                "section": "Steps",
            },
        )

    return [
        hit("account-password-reset", "Reset a forgotten password", "account", 0.81, 0),
        hit("account-password-reset", "Reset a forgotten password", "account", 0.76, 1),
        hit("account-password-reset", "Reset a forgotten password", "account", 0.71, 2),
        hit("troubleshooting-cannot-login", "Cannot sign in", "troubleshooting", 0.64, 0),
        hit("billing-refund-policy", "Refund policy", "billing", 0.42, 0),
        hit("faq-trial-length", "How long is the free trial?", "faq", 0.11, 0),
    ]


@pytest.fixture
def rag_settings() -> Settings:
    return Settings(environment="ci", api_key="test-key", rag_top_k=5, rag_min_score=0.25)


@pytest.fixture
def store() -> FakeVectorStore:
    return FakeVectorStore()


@pytest.fixture
async def client(
    store: FakeVectorStore, rag_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> Any:
    """Drive the real app object with fakes injected behind the dependency."""
    retriever = Retriever(vector_store=store, embedder=FakeEmbedder(), settings=rag_settings)
    monkeypatch.setattr(rag_main, "_retriever", retriever)
    # Redis is not running in unit tests; make the cache a guaranteed miss.
    monkeypatch.setattr("support_common.cache.get_client", _no_cache)

    transport = ASGITransport(app=rag_main.app)
    async with AsyncClient(transport=transport, base_url="http://rag") as http:
        yield http


async def _no_cache() -> None:
    return None


class TestSearch:
    async def test_search_returns_ranked_results(self, client: AsyncClient) -> None:
        response = await client.post("/api/search", json={"query": "how do I reset my password"})
        assert response.status_code == 200

        payload = response.json()
        assert payload["results"][0]["doc_id"] == "account-password-reset"
        assert payload["results"][0]["score"] >= payload["results"][-1]["score"]
        assert payload["cached"] is False

    async def test_results_below_the_score_floor_are_dropped(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/search", json={"query": "an unrelated question entirely", "min_score": 0.5}
        )
        scores = [r["score"] for r in response.json()["results"]]
        assert scores and all(s >= 0.5 for s in scores)

    async def test_no_more_than_two_chunks_per_document(self, client: AsyncClient) -> None:
        """Otherwise one verbose article crowds out every other answer."""
        response = await client.post("/api/search", json={"query": "password reset help"})
        doc_ids = [r["doc_id"] for r in response.json()["results"]]
        assert doc_ids.count("account-password-reset") <= 2

    async def test_top_k_is_respected(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/search", json={"query": "password reset help", "top_k": 2}
        )
        assert len(response.json()["results"]) == 2

    async def test_a_category_filter_is_passed_to_the_store(
        self, client: AsyncClient, store: FakeVectorStore
    ) -> None:
        response = await client.post(
            "/api/search", json={"query": "refund for annual plan", "categories": ["billing"]}
        )
        assert store.last_where == {"category": "billing"}
        assert {r["category"] for r in response.json()["results"]} == {"billing"}

    async def test_a_short_query_is_rejected(self, client: AsyncClient) -> None:
        response = await client.post("/api/search", json={"query": "hi"})
        assert response.status_code == 422
        assert response.json()["error"] == "validation_error"

    async def test_an_unknown_field_is_rejected(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/search", json={"query": "a valid query", "unexpected": 1}
        )
        assert response.status_code == 422


class TestOps:
    async def test_health_never_touches_dependencies(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "rag-engine"

    async def test_ready_reports_the_index_size(self, client: AsyncClient) -> None:
        response = await client.get("/ready")
        assert response.status_code == 200
        assert response.json()["dependencies"]["vector_store"] == "ok"

    async def test_ready_is_503_when_the_index_is_empty(
        self, client: AsyncClient, store: FakeVectorStore
    ) -> None:
        store.hits = []
        response = await client.get("/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "degraded"

    async def test_stats_describes_the_index(self, client: AsyncClient) -> None:
        payload = (await client.get("/api/stats")).json()
        assert payload["backend"] == "fake"
        assert payload["embedding_model"] == "fake-embedder"
        assert payload["chunks"] == 6

    async def test_metrics_are_exposed_for_prometheus(self, client: AsyncClient) -> None:
        await client.post("/api/search", json={"query": "a query for the counter"})
        body = (await client.get("/metrics")).text
        assert "support_rag_queries_total" in body
        assert "support_http_requests_total" in body

    async def test_every_response_carries_a_request_id(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.headers["x-request-id"]

    async def test_an_inbound_request_id_is_propagated(self, client: AsyncClient) -> None:
        response = await client.get("/health", headers={"x-request-id": "abc-123"})
        assert response.headers["x-request-id"] == "abc-123"


class TestRebuildEndpoint:
    async def test_rebuilding_requires_the_api_key(self, client: AsyncClient) -> None:
        response = await client.post("/api/index/rebuild")
        assert response.status_code == 401
        assert response.json()["error"] == "invalid_signature"


class TestRetrieverDirectly:
    async def test_caching_is_bypassed_when_asked(self, rag_settings: Settings) -> None:
        embedder = FakeEmbedder()
        retriever = Retriever(
            vector_store=FakeVectorStore(), embedder=embedder, settings=rag_settings
        )
        await retriever.search(SearchRequest(query="a repeated query"), use_cache=False)
        await retriever.search(SearchRequest(query="a repeated query"), use_cache=False)
        assert embedder.calls == 2
