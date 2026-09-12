"""Shared async HTTP client for service-to-service calls.

Wraps httpx with retries on transient failures and propagates the request id so
one ticket can be followed through the receiver, agent, RAG engine and
dispatcher in the logs.
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from support_common.config import get_settings
from support_common.errors import UpstreamUnavailable
from support_common.logging import current_request_id, get_logger

log = get_logger(__name__)

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class RetryableHTTPError(Exception):
    """Marker so tenacity retries only the statuses worth retrying."""


class ServiceClient:
    """Thin JSON client for one downstream service.

    Usage::

        async with ServiceClient(settings.rag_engine_url, "rag-engine") as client:
            payload = await client.post_json("/api/search", {"query": "..."})
    """

    def __init__(
        self,
        base_url: str,
        name: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries if max_retries is not None else settings.http_max_retries
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout or settings.http_timeout_seconds,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )

    async def __aenter__(self) -> ServiceClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if (request_id := current_request_id()) is not None:
            headers["x-request-id"] = request_id
        return headers

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential_jitter(initial=0.25, max=4.0),
            retry=retry_if_exception_type((RetryableHTTPError, httpx.TransportError)),
            reraise=True,
        )
        async def _attempt() -> httpx.Response:
            response = await self._client.request(
                method, path, headers=self._headers(), **kwargs
            )
            if response.status_code in RETRYABLE_STATUS:
                raise RetryableHTTPError(f"{self.name} returned {response.status_code}")
            return response

        try:
            return await _attempt()
        except (RetryableHTTPError, httpx.TransportError) as exc:
            log.warning("http.upstream_failed", upstream=self.name, path=path, error=str(exc))
            raise UpstreamUnavailable(f"{self.name} unavailable: {exc}") from exc

    async def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST JSON and return the decoded body, raising on 4xx."""
        response = await self._request("POST", path, json=payload)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = await self._request("GET", path, params=params)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def healthy(self) -> bool:
        """Best-effort dependency check used by readiness probes."""
        try:
            response = await self._client.get("/health", timeout=3.0)
            return response.status_code == 200
        except Exception:
            return False
