"""Initial schema: tickets, messages, resolutions, feedback.

Revision ID: 0001
Revises:
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Enum types are created explicitly and then referenced with create_type=False,
# so a shared type is not emitted once per column that uses it.
CHANNEL = postgresql.ENUM(
    "slack", "email", "api", "zendesk", "web", name="channel", create_type=False
)
TICKET_STATUS = postgresql.ENUM(
    "new", "processing", "resolved", "escalated", "failed", "reopened", "closed",
    name="ticket_status", create_type=False,
)
TICKET_PRIORITY = postgresql.ENUM(
    "low", "normal", "high", "urgent", name="ticket_priority", create_type=False
)
MESSAGE_SENDER = postgresql.ENUM(
    "customer", "agent", "system", "human", name="message_sender", create_type=False
)
ESCALATION_REASON = postgresql.ENUM(
    "low_confidence", "no_kb_match", "max_turns_exceeded", "customer_requested",
    "policy_required", "sensitive_topic", "llm_error",
    name="escalation_reason", create_type=False,
)

ENUMS = (CHANNEL, TICKET_STATUS, TICKET_PRIORITY, MESSAGE_SENDER, ESCALATION_REASON)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in ENUMS:
        enum.create(bind, checkfirst=True)

    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("customer_external_id", sa.String(length=128), nullable=False),
        sa.Column("customer_email", sa.String(length=320), nullable=True),
        sa.Column("customer_name", sa.String(length=200), nullable=True),
        sa.Column("customer_tier", sa.String(length=32), nullable=False),
        sa.Column("channel", CHANNEL, nullable=False),
        sa.Column("status", TICKET_STATUS, nullable=False),
        sa.Column("priority", TICKET_PRIORITY, nullable=False),
        sa.Column("external_ref", sa.String(length=256), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("first_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_id", name="uq_tickets_ticket_id"),
        sa.UniqueConstraint("channel", "external_ref", name="uq_tickets_channel_external_ref"),
    )
    op.create_index("ix_tickets_created_at", "tickets", ["created_at"])
    op.create_index("ix_tickets_status", "tickets", ["status"])
    op.create_index("ix_tickets_customer_external_id", "tickets", ["customer_external_id"])
    op.create_index("ix_tickets_status_created_at", "tickets", ["status", "created_at"])
    op.create_index("ix_tickets_channel_created_at", "tickets", ["channel", "created_at"])

    op.create_table(
        "ticket_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.String(length=32), nullable=False),
        sa.Column("sender", MESSAGE_SENDER, nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.ticket_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticket_messages_ticket_id", "ticket_messages", ["ticket_id"])
    op.create_index(
        "ix_ticket_messages_ticket_created", "ticket_messages", ["ticket_id", "created_at"]
    )

    op.create_table(
        "ticket_resolutions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.String(length=32), nullable=False),
        sa.Column("solution", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("escalated", sa.Boolean(), nullable=False),
        sa.Column("escalation_reason", ESCALATION_REASON, nullable=True),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("turns_used", sa.Integer(), nullable=False),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tool_calls", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_resolution_confidence"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.ticket_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticket_resolutions_ticket_id", "ticket_resolutions", ["ticket_id"])
    op.create_index("ix_ticket_resolutions_resolved_at", "ticket_resolutions", ["resolved_at"])
    op.create_index(
        "ix_resolutions_escalated_resolved_at", "ticket_resolutions", ["escalated", "resolved_at"]
    )

    op.create_table(
        "ticket_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.String(length=32), nullable=False),
        sa.Column("satisfaction_score", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("resolved_issue", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("satisfaction_score BETWEEN 1 AND 5", name="ck_feedback_score_range"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.ticket_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_id", name="uq_feedback_ticket"),
    )
    op.create_index("ix_ticket_feedback_ticket_id", "ticket_feedback", ["ticket_id"])
    op.create_index("ix_ticket_feedback_created_at", "ticket_feedback", ["created_at"])


def downgrade() -> None:
    op.drop_table("ticket_feedback")
    op.drop_table("ticket_resolutions")
    op.drop_table("ticket_messages")
    op.drop_table("tickets")
    bind = op.get_bind()
    for enum in reversed(ENUMS):
        enum.drop(bind, checkfirst=True)
