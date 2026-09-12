"""Domain exceptions mapped to HTTP responses by the shared app factory."""

from __future__ import annotations


class SupportError(Exception):
    """Base class for expected, reportable failures."""

    status_code = 500
    error_code = "internal_error"

    def __init__(self, detail: str = "", *, status_code: int | None = None) -> None:
        super().__init__(detail or self.error_code)
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code


class TicketNotFound(SupportError):
    status_code = 404
    error_code = "ticket_not_found"


class DuplicateTicket(SupportError):
    """A webhook redelivery for a ticket we already have."""

    status_code = 409
    error_code = "duplicate_ticket"

    def __init__(self, detail: str = "", *, ticket_id: str = "") -> None:
        super().__init__(detail)
        self.ticket_id = ticket_id


class InvalidSignature(SupportError):
    status_code = 401
    error_code = "invalid_signature"


class UpstreamUnavailable(SupportError):
    """A dependency (RAG engine, Ollama, SMTP) could not be reached."""

    status_code = 503
    error_code = "upstream_unavailable"


class LLMError(SupportError):
    """The local model failed or returned something unusable."""

    status_code = 502
    error_code = "llm_error"


class IndexNotReady(SupportError):
    """The vector store has no documents yet; run ``make kb`` first."""

    status_code = 503
    error_code = "index_not_ready"


class DispatchFailed(SupportError):
    status_code = 502
    error_code = "dispatch_failed"
