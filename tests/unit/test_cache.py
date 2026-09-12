"""Tests for the cache module's degrade-to-miss behaviour.

Redis is not running in unit tests, so every one of these exercises the real
"Redis unreachable" path rather than mocking a client - which is exactly the
path that matters: the cache must never take a service down.
"""

from __future__ import annotations

import pytest
from support_common import cache


@pytest.fixture(autouse=True)
def _reset_cache_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point at a port nothing listens on, so these exercise the real
    connection-failure path rather than actually reaching a Redis that may be
    running locally on the default port."""
    monkeypatch.setenv("REDIS_URL", "redis://localhost:1/0")
    from support_common.config import get_settings

    get_settings.cache_clear()
    cache._client = None
    cache._unavailable = False
    yield
    cache._client = None
    cache._unavailable = False
    get_settings.cache_clear()


class TestUnavailableRedis:
    async def test_get_client_returns_none_when_unreachable(self) -> None:
        assert await cache.get_client() is None

    async def test_unavailability_is_remembered_across_calls(self) -> None:
        """A second call must not retry the connection - that would add latency
        to every request for the lifetime of an outage."""
        await cache.get_client()
        assert cache._unavailable is True
        assert await cache.get_client() is None

    async def test_get_json_returns_none_rather_than_raising(self) -> None:
        assert await cache.get_json("some:key") is None

    async def test_set_json_does_not_raise(self) -> None:
        await cache.set_json("some:key", {"a": 1})  # must not raise

    async def test_invalidate_returns_zero_rather_than_raising(self) -> None:
        assert await cache.invalidate("some:*") == 0

    async def test_healthy_is_false(self) -> None:
        assert await cache.healthy() is False

    async def test_close_is_safe_when_never_connected(self) -> None:
        await cache.close()  # must not raise


class TestCacheKey:
    def test_the_same_parts_produce_the_same_key(self) -> None:
        assert cache.cache_key("ns", "a", 1) == cache.cache_key("ns", "a", 1)

    def test_different_parts_produce_different_keys(self) -> None:
        assert cache.cache_key("ns", "a") != cache.cache_key("ns", "b")

    def test_the_namespace_is_part_of_the_key(self) -> None:
        assert cache.cache_key("ns1", "a") != cache.cache_key("ns2", "a")

    def test_the_key_has_the_expected_shape(self) -> None:
        key = cache.cache_key("rag:search", "query text", 5)
        assert key.startswith("support:rag:search:")
        assert len(key.split(":")[-1]) == 32
