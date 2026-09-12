"""Structured logging with request correlation.

Every log line carries the ``ticket_id`` and ``request_id`` of the work in
flight, which is what makes a ticket traceable across the four services.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_ticket_id: ContextVar[str | None] = ContextVar("ticket_id", default=None)

_configured = False


def bind_request_id(request_id: str | None) -> None:
    """Attach a request id to the current async context."""
    _request_id.set(request_id)


def bind_ticket_id(ticket_id: str | None) -> None:
    """Attach a ticket id to the current async context."""
    _ticket_id.set(ticket_id)


def current_request_id() -> str | None:
    return _request_id.get()


def _inject_context(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor copying the context vars onto every event."""
    if (request_id := _request_id.get()) is not None:
        event_dict.setdefault("request_id", request_id)
    if (ticket_id := _ticket_id.get()) is not None:
        event_dict.setdefault("ticket_id", ticket_id)
    return event_dict


def configure_logging(service: str, level: str = "INFO", fmt: str = "json") -> None:
    """Configure structlog and the stdlib root logger for a service.

    Safe to call more than once; only the first call takes effect so that test
    fixtures and app startup do not fight over the handler list.
    """
    global _configured
    if _configured:
        return

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _inject_context,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if fmt == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper(), force=True)
    # uvicorn's access log duplicates our own request middleware line.
    logging.getLogger("uvicorn.access").disabled = True
    for noisy in ("httpx", "httpcore", "chromadb", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    structlog.contextvars.bind_contextvars(service=service)
    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
