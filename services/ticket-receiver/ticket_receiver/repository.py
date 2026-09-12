"""Database access for tickets, messages and resolutions.

All ticket writes go through here so the status transitions and the
deduplication rule live in one place rather than being re-implemented per route.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from support_common.enums import MessageSender, TicketStatus
from support_common.errors import TicketNotFound
from support_common.logging import get_logger
from support_common.models import Ticket, TicketMessage, TicketResolution
from support_common.schemas import AgentResult, TicketCreate, new_ticket_id

log = get_logger(__name__)


class TicketRepository:
    """Persistence for the ticket aggregate."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_external_ref(self, channel: str, external_ref: str) -> Ticket | None:
        """Look up a ticket by its channel-native id, for idempotency."""
        result = await self.session.execute(
            select(Ticket).where(Ticket.channel == channel, Ticket.external_ref == external_ref)
        )
        return result.scalar_one_or_none()

    async def get(self, ticket_id: str) -> Ticket:
        result = await self.session.execute(select(Ticket).where(Ticket.ticket_id == ticket_id))
        ticket = result.scalar_one_or_none()
        if ticket is None:
            raise TicketNotFound(f"no ticket with id {ticket_id}")
        return ticket

    async def create(self, payload: TicketCreate) -> tuple[Ticket, bool]:
        """Insert a ticket, returning ``(ticket, created)``.

        Webhooks redeliver, so a repeat of the same ``external_ref`` on the same
        channel returns the original ticket instead of creating a second one.
        ``ON CONFLICT DO NOTHING`` makes that safe even when two replicas race.
        """
        if (
            payload.external_ref
            and (
                existing := await self.find_by_external_ref(
                    payload.channel.value, payload.external_ref
                )
            )
            is not None
        ):
            log.info("ticket.duplicate_ignored", ticket_id=existing.ticket_id)
            return existing, False

        ticket_id = new_ticket_id()
        values: dict[str, Any] = {
            "ticket_id": ticket_id,
            "subject": payload.subject,
            "body": payload.body,
            "customer_external_id": payload.customer.external_id,
            "customer_email": payload.customer.email,
            "customer_name": payload.customer.name,
            "customer_tier": payload.customer.tier,
            "channel": payload.channel,
            "status": TicketStatus.NEW,
            "priority": payload.priority,
            "external_ref": payload.external_ref,
            "tags": payload.tags,
            # The ORM attribute name, not the column name: ``Ticket.metadata`` is
            # SQLAlchemy's own MetaData object, so keying on "metadata" here
            # silently resolves to the wrong thing.
            "metadata_json": payload.metadata,
        }

        statement = (
            pg_insert(Ticket)
            .values(**values)
            .on_conflict_do_nothing(constraint="uq_tickets_channel_external_ref")
            .returning(Ticket.ticket_id)
        )
        result = await self.session.execute(statement)
        inserted = result.scalar_one_or_none()

        if inserted is None:
            # Lost the race; the winner's row is the one to use.
            await self.session.flush()
            existing = await self.find_by_external_ref(
                payload.channel.value, payload.external_ref or ""
            )
            if existing is not None:
                return existing, False
            raise RuntimeError("ticket insert conflicted but no existing row was found")

        await self.session.flush()
        ticket = await self.get(ticket_id)
        await self.add_message(
            ticket_id, MessageSender.CUSTOMER, payload.body, metadata={"initial": True}
        )
        log.info("ticket.created", ticket_id=ticket_id, channel=payload.channel.value)
        return ticket, True

    async def add_message(
        self,
        ticket_id: str,
        sender: MessageSender,
        message: str,
        *,
        turn: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TicketMessage:
        """Append to the conversation log."""
        record = TicketMessage(
            ticket_id=ticket_id,
            sender=sender,
            message=message,
            turn=turn,
            metadata_json=metadata or {},
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def set_status(self, ticket_id: str, status: TicketStatus) -> Ticket:
        """Move a ticket to a new status, stamping the lifecycle timestamps."""
        ticket = await self.get(ticket_id)
        ticket.status = status
        now = datetime.now(UTC)
        if status is TicketStatus.PROCESSING and ticket.first_response_at is None:
            ticket.first_response_at = now
        if status.is_terminal:
            ticket.closed_at = now
        await self.session.flush()
        return ticket

    async def record_resolution(self, result: AgentResult) -> TicketResolution:
        """Store the agent's decision and move the ticket to its final status."""
        resolution = TicketResolution(
            ticket_id=result.ticket_id,
            solution=result.answer,
            confidence=result.confidence,
            escalated=result.escalated,
            escalation_reason=result.escalation_reason,
            model=result.model,
            turns_used=result.turns_used,
            citations=[c.model_dump(mode="json") for c in result.citations],
            tool_calls=[t.model_dump(mode="json") for t in result.tool_calls],
            latency_ms=result.took_ms,
            estimated_cost_usd=result.estimated_cost_usd,
        )
        self.session.add(resolution)

        await self.add_message(
            result.ticket_id,
            MessageSender.AGENT,
            result.answer,
            turn=result.turns_used,
            metadata={
                "confidence": result.confidence,
                "escalated": result.escalated,
                "citations": [c.doc_id for c in result.citations],
            },
        )
        await self.set_status(
            result.ticket_id,
            TicketStatus.ESCALATED if result.escalated else TicketStatus.RESOLVED,
        )
        await self.session.flush()
        return resolution

    async def list_recent(
        self, *, limit: int = 50, status: TicketStatus | None = None
    ) -> list[Ticket]:
        query = select(Ticket).order_by(Ticket.created_at.desc()).limit(limit)
        if status is not None:
            query = query.where(Ticket.status == status)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def messages(self, ticket_id: str) -> list[TicketMessage]:
        result = await self.session.execute(
            select(TicketMessage)
            .where(TicketMessage.ticket_id == ticket_id)
            .order_by(TicketMessage.id)
        )
        return list(result.scalars().all())

    async def stats(self) -> dict[str, Any]:
        """Headline numbers for the ops dashboard: volume, auto-resolution, cost."""
        status_rows = await self.session.execute(
            select(Ticket.status, func.count()).group_by(Ticket.status)
        )
        by_status: dict[TicketStatus, int] = dict(status_rows.all())  # type: ignore[arg-type]
        total = sum(by_status.values())
        resolved = by_status.get(TicketStatus.RESOLVED, 0)
        escalated = by_status.get(TicketStatus.ESCALATED, 0)
        decided = resolved + escalated

        aggregates = (
            await self.session.execute(
                select(
                    func.avg(TicketResolution.confidence),
                    func.avg(TicketResolution.latency_ms),
                    func.avg(TicketResolution.estimated_cost_usd),
                    func.count(),
                )
            )
        ).one()

        return {
            "tickets_total": total,
            "by_status": {str(k): v for k, v in by_status.items()},
            "auto_resolution_rate": round(resolved / decided, 4) if decided else 0.0,
            "resolutions_recorded": aggregates[3] or 0,
            "avg_confidence": round(float(aggregates[0] or 0), 4),
            "avg_resolution_ms": round(float(aggregates[1] or 0), 2),
            "avg_cost_usd": round(float(aggregates[2] or 0), 6),
        }
