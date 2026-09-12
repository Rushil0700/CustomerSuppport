"""SQLAlchemy ORM models backing the PostgreSQL schema.

Four tables mirror the ticket lifecycle:

``tickets``              the ticket itself and its current status
``ticket_messages``      the append-only conversation log
``ticket_resolutions``   what the agent decided, with confidence and citations
``ticket_feedback``      customer satisfaction after the fact

The raw DDL in ``database/schema.sql`` is generated from these models, so the
models are the single source of truth.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from support_common.enums import (
    Channel,
    EscalationReason,
    MessageSender,
    TicketPriority,
    TicketStatus,
)


def _pg_enum(enum_cls: type, name: str) -> SAEnum:
    """Native PostgreSQL enum that stores the lowercase *values*, not the names."""
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda e: [member.value for member in e],
        native_enum=True,
        create_constraint=False,
    )


class Base(DeclarativeBase):
    """Declarative base for all support tables."""

    type_annotation_map = {dict[str, Any]: JSONB, list[str]: JSONB}


class TimestampMixin:
    """``created_at``/``updated_at`` maintained by the database clock."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Ticket(TimestampMixin, Base):
    """A support request, normalised across every inbound channel."""

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)

    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    customer_external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    customer_email: Mapped[str | None] = mapped_column(String(320))
    customer_name: Mapped[str | None] = mapped_column(String(200))
    customer_tier: Mapped[str] = mapped_column(String(32), nullable=False, default="standard")

    channel: Mapped[Channel] = mapped_column(_pg_enum(Channel, "channel"), nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        _pg_enum(TicketStatus, "ticket_status"),
        nullable=False,
        default=TicketStatus.NEW,
        index=True,
    )
    priority: Mapped[TicketPriority] = mapped_column(
        _pg_enum(TicketPriority, "ticket_priority"),
        nullable=False,
        default=TicketPriority.NORMAL,
    )

    # Channel-native id (Slack ts, email Message-ID, Zendesk ticket id). Unique
    # per channel so a webhook redelivery cannot create a duplicate ticket.
    external_ref: Mapped[str | None] = mapped_column(String(256))
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list[TicketMessage]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="TicketMessage.id"
    )
    resolutions: Mapped[list[TicketResolution]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="TicketResolution.id"
    )
    feedback: Mapped[list[TicketFeedback]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("channel", "external_ref", name="uq_tickets_channel_external_ref"),
        Index("ix_tickets_status_created_at", "status", "created_at"),
        Index("ix_tickets_channel_created_at", "channel", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Ticket {self.ticket_id} {self.status}>"


class TicketMessage(Base):
    """Append-only conversation log for a ticket."""

    __tablename__ = "ticket_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("tickets.ticket_id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender: Mapped[MessageSender] = mapped_column(
        _pg_enum(MessageSender, "message_sender"), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # Agent reasoning turn this message belongs to; NULL for customer messages.
    turn: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    ticket: Mapped[Ticket] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_ticket_messages_ticket_created", "ticket_id", "created_at"),)


class TicketResolution(Base):
    """What the agent decided, and how sure it was."""

    __tablename__ = "ticket_resolutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("tickets.ticket_id", ondelete="CASCADE"), nullable=False, index=True
    )
    solution: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    escalated: Mapped[bool] = mapped_column(nullable=False, default=False)
    escalation_reason: Mapped[EscalationReason | None] = mapped_column(
        _pg_enum(EscalationReason, "escalation_reason")
    )

    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    turns_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # [{doc_id, title, source, score}, ...] - lets us audit which KB article
    # produced an answer and retire documents that never get cited.
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    ticket: Mapped[Ticket] = relationship(back_populates="resolutions")

    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_resolution_confidence"),
        Index("ix_resolutions_escalated_resolved_at", "escalated", "resolved_at"),
    )


class TicketFeedback(Base):
    """Customer satisfaction for a resolved ticket."""

    __tablename__ = "ticket_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("tickets.ticket_id", ondelete="CASCADE"), nullable=False, index=True
    )
    satisfaction_score: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    resolved_issue: Mapped[bool | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    ticket: Mapped[Ticket] = relationship(back_populates="feedback")

    __table_args__ = (
        CheckConstraint(
            "satisfaction_score BETWEEN 1 AND 5", name="ck_feedback_score_range"
        ),
        UniqueConstraint("ticket_id", name="uq_feedback_ticket"),
    )


__all__ = [
    "Base",
    "Ticket",
    "TicketFeedback",
    "TicketMessage",
    "TicketResolution",
]
