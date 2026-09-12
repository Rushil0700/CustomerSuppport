"""Wire schemas exchanged between the services.

These are the contract: the receiver produces ``TicketCreate``/``TicketRead``,
the RAG engine answers ``SearchRequest`` with ``SearchResponse``, the agent turns
an ``AgentRequest`` into an ``AgentResult``, and the dispatcher consumes
``DispatchRequest``. Anything not in this module is service-private.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from support_common.enums import (
    Channel,
    EscalationReason,
    MessageSender,
    TicketPriority,
    TicketStatus,
)

TICKET_ID_PATTERN = re.compile(r"^TKT-[0-9A-HJKMNP-TV-Z]{10,26}$")


def new_ticket_id() -> str:
    """Generate a human-quotable, sortable ticket id (``TKT-<ULID-ish>``)."""
    return f"TKT-{uuid.uuid4().hex[:12].upper().translate(str.maketrans('ILOU', '2345'))}"


class Base(BaseModel):
    """Base model: reject unknown fields so contract drift fails loudly."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --- Tickets -----------------------------------------------------------------


class CustomerRef(Base):
    """Identity of the person who filed the ticket."""

    external_id: str = Field(min_length=1, max_length=128)
    email: EmailStr | None = None
    name: str | None = Field(default=None, max_length=200)
    tier: str = Field(default="standard", max_length=32)


class TicketCreate(Base):
    """A normalised inbound ticket, whatever channel it arrived on."""

    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=20_000)
    customer: CustomerRef
    channel: Channel
    priority: TicketPriority = TicketPriority.NORMAL
    # Channel-native identifier (Slack ts, RFC-822 Message-ID, Zendesk id) used
    # for idempotency and for threading the reply back to the right place.
    external_ref: str | None = Field(default=None, max_length=256)
    tags: list[str] = Field(default_factory=list, max_length=20)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tags")
    @classmethod
    def _normalise_tags(cls, value: list[str]) -> list[str]:
        return sorted({t.strip().lower() for t in value if t.strip()})

    @property
    def search_text(self) -> str:
        """Subject plus body, which is what gets embedded for retrieval."""
        return f"{self.subject}\n\n{self.body}"


class TicketRead(Base):
    """A ticket as stored, returned by the receiver's read endpoints."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    ticket_id: str
    subject: str
    body: str
    customer_external_id: str
    customer_email: str | None
    customer_name: str | None
    customer_tier: str
    channel: Channel
    status: TicketStatus
    priority: TicketPriority
    external_ref: str | None
    tags: list[str]
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class TicketMessageRead(Base):
    """One entry in a ticket's conversation log."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    ticket_id: str
    sender: MessageSender
    message: str
    turn: int | None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


# --- RAG ---------------------------------------------------------------------


class SearchRequest(Base):
    """A knowledge base query."""

    query: str = Field(min_length=3, max_length=4_000)
    top_k: int = Field(default=5, ge=1, le=20)
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    # Restrict to a KB category such as "billing" or "troubleshooting".
    categories: list[str] = Field(default_factory=list, max_length=10)
    ticket_id: str | None = None


class RetrievedDocument(Base):
    """One chunk returned by the vector store."""

    doc_id: str
    title: str
    source: str
    category: str
    content: str
    score: float = Field(ge=0.0, le=1.0)
    chunk_index: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(Base):
    """Ranked knowledge base hits for a query."""

    query: str
    results: list[RetrievedDocument]
    took_ms: float
    cached: bool = False

    @property
    def top_score(self) -> float:
        return self.results[0].score if self.results else 0.0


class IndexStats(Base):
    """Size and shape of the current vector index."""

    collection: str
    backend: str
    documents: int
    chunks: int
    embedding_model: str
    dimensions: int


# --- Agent -------------------------------------------------------------------


class AgentRequest(Base):
    """Ask the agent to work a ticket."""

    ticket_id: str
    subject: str
    body: str
    channel: Channel
    customer_tier: str = "standard"
    priority: TicketPriority = TicketPriority.NORMAL
    # Prior turns, when a customer replies to an existing thread.
    history: list[ConversationTurn] = Field(default_factory=list, max_length=50)
    max_turns: int | None = Field(default=None, ge=1, le=10)

    @field_validator("ticket_id")
    @classmethod
    def _valid_ticket_id(cls, value: str) -> str:
        if not TICKET_ID_PATTERN.match(value):
            raise ValueError(f"malformed ticket id: {value!r}")
        return value


class ConversationTurn(Base):
    """A single message in the agent's working conversation."""

    role: MessageSender
    content: str


class ToolCallRecord(Base):
    """Audit record of one tool invocation during agent reasoning."""

    turn: int
    tool: str
    arguments: dict[str, Any]
    ok: bool
    result_summary: str = ""
    took_ms: float = 0.0


class Citation(Base):
    """A knowledge base document the answer was grounded in."""

    doc_id: str
    title: str
    source: str
    score: float = Field(ge=0.0, le=1.0)


class AgentResult(Base):
    """The agent's decision on a ticket."""

    ticket_id: str
    resolved: bool
    answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    escalated: bool = False
    escalation_reason: EscalationReason | None = None
    citations: list[Citation] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    turns_used: int = 0
    model: str = ""
    took_ms: float = 0.0
    estimated_cost_usd: float = 0.0

    @model_validator(mode="after")
    def _escalation_has_reason(self) -> AgentResult:
        if self.escalated and self.escalation_reason is None:
            raise ValueError("escalated results must carry an escalation_reason")
        if self.resolved and self.escalated:
            raise ValueError("a ticket cannot be both resolved and escalated")
        return self


# --- Dispatch ----------------------------------------------------------------


class DispatchRequest(Base):
    """Deliver a resolution (or an escalation notice) to the customer."""

    ticket_id: str
    channel: Channel
    body: str = Field(min_length=1, max_length=40_000)
    subject: str | None = Field(default=None, max_length=500)
    recipient: str | None = Field(default=None, max_length=320)
    external_ref: str | None = None
    escalated: bool = False
    citations: list[Citation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DispatchResult(Base):
    """Outcome of an outbound delivery attempt."""

    ticket_id: str
    channel: Channel
    delivered: bool
    provider_message_id: str | None = None
    dry_run: bool = False
    error: str | None = None
    took_ms: float = 0.0


# --- Feedback ----------------------------------------------------------------


class FeedbackCreate(Base):
    """Customer satisfaction signal for a resolved ticket."""

    ticket_id: str
    satisfaction_score: Annotated[int, Field(ge=1, le=5)]
    comment: str | None = Field(default=None, max_length=4_000)
    resolved_issue: bool | None = None


class FeedbackRead(FeedbackCreate):
    """Stored feedback."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    created_at: datetime


# --- Operational -------------------------------------------------------------


class HealthResponse(Base):
    """Liveness/readiness payload returned by every service."""

    status: str
    service: str
    version: str
    environment: str
    dependencies: dict[str, str] = Field(default_factory=dict)


class ErrorResponse(Base):
    """Uniform error body."""

    error: str
    detail: str | None = None
    request_id: str | None = None


# Resolve the forward reference used by AgentRequest.history.
AgentRequest.model_rebuild()
