"""Redis-backed cache with a no-op fallback.

Support traffic is extremely repetitive - "how do I reset my password" arrives
hundreds of times a day - so caching RAG results is the single cheapest way to
hold the per-ticket cost target. When Redis is unavailable the cache degrades to
a miss on every call rather than taking the service down.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from support_common.config import get_settings
from support_common.logging import get_logger

log = get_logger(__name__)

_client: Any = None
_unavailable = False


def cache_key(namespace: str, *parts: Any) -> str:
    """Stable key from arbitrary parts; long values are hashed."""
    raw = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"support:{namespace}:{digest}"


async def get_client() -> Any:
    """Return a connected Redis client, or ``None`` if Redis is unreachable."""
    global _client, _unavailable
    if _unavailable:
        return None
    if _client is not None:
        return _client
    try:
        from redis.asyncio import from_url

        settings = get_settings()
        client = from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        await client.ping()
        _client = client
        log.info("cache.connected")
        return _client
    except Exception as exc:
        log.warning("cache.unavailable", error=str(exc))
        _unavailable = True
        return None


async def get_json(key: str) -> Any | None:
    """Read and decode a cached value; ``None`` on miss or any failure."""
    client = await get_client()
    if client is None:
        return None
    try:
        raw = await client.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:
        log.warning("cache.get_failed", key=key, error=str(exc))
        return None


async def set_json(key: str, value: Any, ttl: int | None = None) -> None:
    """Write a value with a TTL. Failures are logged, never raised."""
    client = await get_client()
    if client is None:
        return
    try:
        ttl = ttl if ttl is not None else get_settings().cache_ttl_seconds
        await client.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception as exc:
        log.warning("cache.set_failed", key=key, error=str(exc))


async def invalidate(pattern: str) -> int:
    """Delete keys matching a glob, e.g. after re-indexing the knowledge base."""
    client = await get_client()
    if client is None:
        return 0
    deleted = 0
    try:
        async for key in client.scan_iter(match=pattern, count=500):
            await client.delete(key)
            deleted += 1
    except Exception as exc:
        log.warning("cache.invalidate_failed", pattern=pattern, error=str(exc))
    return deleted


async def healthy() -> bool:
    client = await get_client()
    if client is None:
        return False
    try:
        await client.ping()
        return True
    except Exception:
        return False


async def close() -> None:
    global _client, _unavailable
    if _client is not None:
        await _client.aclose()
        _client = None
    _unavailable = False
