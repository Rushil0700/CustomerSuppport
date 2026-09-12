"""FastAPI application factory shared by all four services.

Gives every service the same middleware stack, error envelope, ``/health``,
``/ready`` and ``/metrics`` endpoints, so an operator can probe any pod the same
way and Prometheus needs only one scrape config.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.cors import CORSMiddleware

from support_common.config import get_settings
from support_common.errors import SupportError
from support_common.logging import (
    bind_request_id,
    configure_logging,
    current_request_id,
    get_logger,
)
from support_common.metrics import REQUEST_COUNT, REQUEST_LATENCY

log = get_logger(__name__)

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_app(
    *,
    service: str,
    title: str,
    description: str = "",
    version: str = "0.1.0",
    lifespan: Lifespan | None = None,
) -> FastAPI:
    """Build a configured FastAPI app for one microservice."""
    settings = get_settings()
    configure_logging(service, level=settings.log_level, fmt=settings.log_format)

    app = FastAPI(
        title=title,
        description=description,
        version=version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    app.state.service = service
    app.state.version = version

    # Services are reached through an ingress in production; CORS is only here
    # so the local dashboard and Swagger UI can call across ports.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not settings.is_production else [],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Assign a request id, time the call, and record metrics."""
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        bind_request_id(request_id)
        # Route template ("/api/tickets/{ticket_id}") keeps metric cardinality
        # bounded; the raw path would create one series per ticket.
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed = time.perf_counter() - started
            log.exception(
                "http.unhandled_error",
                method=request.method,
                path=request.url.path,
                duration_ms=round(elapsed * 1000, 2),
            )
            raise
        elapsed = time.perf_counter() - started
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)

        if settings.metrics_enabled:
            REQUEST_COUNT.labels(service, request.method, path, str(response.status_code)).inc()
            REQUEST_LATENCY.labels(service, request.method, path).observe(elapsed)

        response.headers["x-request-id"] = request_id
        if path not in {"/health", "/ready", "/metrics"}:
            log.info(
                "http.request",
                method=request.method,
                path=path,
                status=response.status_code,
                duration_ms=round(elapsed * 1000, 2),
            )
        return response

    @app.exception_handler(SupportError)
    async def support_error_handler(_request: Request, exc: SupportError) -> JSONResponse:
        log.warning("error.domain", code=exc.error_code, detail=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.error_code,
                "detail": exc.detail or None,
                "request_id": current_request_id(),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "detail": str(exc.errors()),
                "request_id": current_request_id(),
            },
        )

    @app.get("/health", tags=["ops"], include_in_schema=False)
    async def health() -> dict[str, str]:
        """Liveness: the process is up. Never touches dependencies."""
        return {"status": "ok", "service": service, "version": version}

    if settings.metrics_enabled:

        @app.get("/metrics", tags=["ops"], include_in_schema=False)
        async def metrics() -> Response:
            return PlainTextResponse(
                generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST
            )

    return app
