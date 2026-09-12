"""Enumerations shared across services and persisted in PostgreSQL.

These are plain ``str`` enums so they serialise transparently to JSON and map
onto native PostgreSQL enum types via SQLAlchemy.
"""

from __future__ import annotations

from enum import StrEnum


class Channel(StrEnum):
    """Where a ticket came from, and where the reply should go back to."""

    SLACK = "slack"
    EMAIL = "email"
    API = "api"
    ZENDESK = "zendesk"
    WEB = "web"


class TicketStatus(StrEnum):
    """Lifecycle of a ticket.

    ``NEW`` -> ``PROCESSING`` -> (``RESOLVED`` | ``ESCALATED`` | ``FAILED``)
    ``RESOLVED`` may later become ``REOPENED`` if the customer is unsatisfied.
    """

    NEW = "new"
    PROCESSING = "processing"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    FAILED = "failed"
    REOPENED = "reopened"
    CLOSED = "closed"

    @property
    def is_terminal(self) -> bool:
        """True when no further automated work is expected on the ticket."""
        return self in {TicketStatus.RESOLVED, TicketStatus.ESCALATED, TicketStatus.CLOSED}


class TicketPriority(StrEnum):
    """Customer-visible urgency, used for queue ordering and SLA targets."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class MessageSender(StrEnum):
    """Author of an entry in the ticket conversation log."""

    CUSTOMER = "customer"
    AGENT = "agent"
    SYSTEM = "system"
    HUMAN = "human"


class EscalationReason(StrEnum):
    """Why the agent handed a ticket to a human.

    Recorded on every escalation so the auto-resolution rate can be broken down
    by cause rather than being a single opaque number.
    """

    LOW_CONFIDENCE = "low_confidence"
    NO_KB_MATCH = "no_kb_match"
    MAX_TURNS_EXCEEDED = "max_turns_exceeded"
    CUSTOMER_REQUESTED = "customer_requested"
    POLICY_REQUIRED = "policy_required"
    SENSITIVE_TOPIC = "sensitive_topic"
    LLM_ERROR = "llm_error"
