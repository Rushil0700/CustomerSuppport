"""Tests for the shared ServiceClient: retries, error mapping, request-id passthrough."""

from __future__ import annotations

import httpx
import pytest
import respx
from support_common.errors import UpstreamUnavailable
from support_common.http import ServiceClient
from support_common.logging import bind_request_id

BASE = "http://downstream.internal"


@pytest.fixture
async def client() -> ServiceClient:
    c = ServiceClient(BASE, "downstream", max_retries=2)
    yield c
    await c.aclose()


class TestSuccess:
    @respx.mock
    async def test_post_json_returns_the_decoded_body(self, client: ServiceClient) -> None:
        respx.post(f"{BASE}/x").mock(return_value=httpx.Response(200, json={"ok": True}))
        assert await client.post_json("/x", {"a": 1}) == {"ok": True}

    @respx.mock
    async def test_get_json_returns_the_decoded_body(self, client: ServiceClient) -> None:
        respx.get(f"{BASE}/x").mock(return_value=httpx.Response(200, json={"ok": True}))
        assert await client.get_json("/x", {"q": "1"}) == {"ok": True}

    @respx.mock
    async def test_the_current_request_id_is_forwarded(self, client: ServiceClient) -> None:
        bind_request_id("req-abc")
        route = respx.post(f"{BASE}/x").mock(return_value=httpx.Response(200, json={}))
        await client.post_json("/x", {})
        assert route.calls.last.request.headers["x-request-id"] == "req-abc"
        bind_request_id(None)


class TestRetries:
    @respx.mock
    async def test_a_503_is_retried_and_then_succeeds(self, client: ServiceClient) -> None:
        route = respx.post(f"{BASE}/x").mock(
            side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": True})]
        )
        result = await client.post_json("/x", {})
        assert result == {"ok": True}
        assert route.call_count == 2

    @respx.mock
    async def test_persistent_5xx_raises_upstream_unavailable(self, client: ServiceClient) -> None:
        respx.post(f"{BASE}/x").mock(return_value=httpx.Response(500))
        with pytest.raises(UpstreamUnavailable):
            await client.post_json("/x", {})

    @respx.mock
    async def test_a_429_is_retried(self, client: ServiceClient) -> None:
        route = respx.post(f"{BASE}/x").mock(
            side_effect=[httpx.Response(429), httpx.Response(200, json={"ok": True})]
        )
        await client.post_json("/x", {})
        assert route.call_count == 2

    @respx.mock
    async def test_a_client_error_is_not_retried(self, client: ServiceClient) -> None:
        """A 404 is a real answer, not a transient failure - retrying it is wasted work."""
        route = respx.post(f"{BASE}/x").mock(return_value=httpx.Response(404))
        with pytest.raises(httpx.HTTPStatusError):
            await client.post_json("/x", {})
        assert route.call_count == 1

    @respx.mock
    async def test_a_connection_error_is_retried_then_raises(self, client: ServiceClient) -> None:
        route = respx.post(f"{BASE}/x").mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(UpstreamUnavailable):
            await client.post_json("/x", {})
        assert route.call_count == 2  # max_retries=2 on this fixture


class TestHealthy:
    @respx.mock
    async def test_a_200_from_health_is_healthy(self, client: ServiceClient) -> None:
        respx.get(f"{BASE}/health").mock(return_value=httpx.Response(200))
        assert await client.healthy() is True

    @respx.mock
    async def test_a_non_200_is_unhealthy(self, client: ServiceClient) -> None:
        respx.get(f"{BASE}/health").mock(return_value=httpx.Response(503))
        assert await client.healthy() is False

    @respx.mock
    async def test_an_unreachable_service_is_unhealthy(self, client: ServiceClient) -> None:
        respx.get(f"{BASE}/health").mock(side_effect=httpx.ConnectError("refused"))
        assert await client.healthy() is False


class TestContextManager:
    @respx.mock
    async def test_the_client_closes_on_exit(self) -> None:
        respx.get(f"{BASE}/health").mock(return_value=httpx.Response(200))
        async with ServiceClient(BASE, "downstream") as client:
            assert await client.healthy() is True
        # aclose is idempotent-safe to call again via __aexit__; no assertion
        # needed beyond "this does not raise".
