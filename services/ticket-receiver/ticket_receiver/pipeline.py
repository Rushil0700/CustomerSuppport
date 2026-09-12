"""Orchestration: ticket -> agent -> persistence -> dispatch.

Ingest endpoints return as soon as the ticket is durably stored; the pipeline
then runs in the background. A customer waiting on an HTTP response should not
be held for the seconds a local model takes to think.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from support_common.config import Settings, get_settings
from support_common.database import session_scope
from support_common.enums import Channel, MessageSender, TicketStatus
from support_common.errors import SupportError
from support_common.http import ServiceClient
from support_common.logging import bind_ticket_id, get_logger
from support_common.metrics import (
    RESOLUTION_LATENCY,
    TICKETS_ESCALATED,
    TICKETS_RESOLVED,
)
from support_common.models import Ticket
from support_common.schemas import AgentRequest, AgentResult, DispatchRequest

from ticket_receiver.repository import TicketRepository

log = get_logger(__name__)


class TicketPipeline:
    """Drives one ticket from ``NEW`` to a terminal status."""

    def __init__(
        self,
        settings: Settings | None = None,
        agent_client: ServiceClient | None = None,
        dispatcher_client: ServiceClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.agent = agent_client or ServiceClient(
            self.settings.agent_url,
            "agent",
            # The agent's own budget is turns x model latency; allow for it
            # rather than timing out a ticket that was about to succeed.
            timeout=self.settings.ollama_timeout_seconds * 2,
        )
        self.dispatcher = dispatcher_client or ServiceClient(
            self.settings.dispatcher_url, "dispatcher"
        )
        # FastAPI's BackgroundTasks run in this same process, sharing its event
        # loop and its one Postgres connection pool with every foreground
        # request. A burst of ticket submissions used to schedule one
        # process() coroutine per ticket with nothing bounding how many ran at
        # once - under load, hundreds of concurrent background runs starved
        # the pool of connections that foreground POST /api/tickets requests
        # also needed, so ingest latency degraded even though ingest itself
        # does none of the slow work. Capping concurrency here means excess
        # tickets simply wait their turn on this semaphore (holding no
        # connection while they do) instead of everyone grabbing a connection
        # at once and congesting the pool.
        self._semaphore = asyncio.Semaphore(self.settings.pipeline_max_concurrency)

    async def aclose(self) -> None:
        await self.agent.aclose()
        await self.dispatcher.aclose()

    async def process(self, ticket_id: str) -> AgentResult | None:
        """Run the full pipeline for one ticket.

        Returns the agent's decision, or ``None`` if the ticket could not be
        processed - in which case it is left in ``FAILED`` for the retry sweep.
        """
        async with self._semaphore:
            return await self._process_locked(ticket_id)

    async def _process_locked(self, ticket_id: str) -> AgentResult | None:
        bind_ticket_id(ticket_id)
        started = time.perf_counter()

        try:
            async with session_scope() as session:
                repository = TicketRepository(session)
                ticket = await repository.get(ticket_id)
                if ticket.status.is_terminal:
                    log.info("pipeline.skipped_terminal", status=ticket.status.value)
                    return None
                await repository.set_status(ticket_id, TicketStatus.PROCESSING)
                request = _to_agent_request(ticket)
                channel = ticket.channel
                subject = ticket.subject
                recipient = ticket.customer_email
                external_ref = ticket.external_ref
        except SupportError:
            raise
        except Exception:
            log.exception("pipeline.load_failed")
            return None

        try:
            payload = await self.agent.post_json("/api/process", request.model_dump(mode="json"))
            result = AgentResult.model_validate(payload)
        except Exception as exc:
            log.error("pipeline.agent_failed", error=str(exc))
            await self._mark_failed(ticket_id, str(exc))
            return None

        async with session_scope() as session:
            await TicketRepository(session).record_resolution(result)

        outcome = "escalated" if result.escalated else "resolved"
        if result.escalated:
            TICKETS_ESCALATED.labels(
                channel.value,
                result.escalation_reason.value if result.escalation_reason else "unknown",
            ).inc()
        else:
            TICKETS_RESOLVED.labels(channel.value).inc()

        await self._dispatch(
            result,
            channel=channel,
            subject=subject,
            recipient=recipient,
            external_ref=external_ref,
        )

        elapsed = time.perf_counter() - started
        RESOLUTION_LATENCY.labels(outcome).observe(elapsed)
        log.info(
            "pipeline.complete",
            outcome=outcome,
            confidence=result.confidence,
            turns=result.turns_used,
            cost_usd=result.estimated_cost_usd,
            duration_ms=round(elapsed * 1000, 2),
        )
        return result

    async def _dispatch(
        self,
        result: AgentResult,
        *,
        channel: Channel,
        subject: str,
        recipient: str | None,
        external_ref: str | None,
    ) -> None:
        """Send the reply. A delivery failure must not lose the resolution."""
        request = DispatchRequest(
            ticket_id=result.ticket_id,
            channel=channel,
            subject=f"Re: {subject}"[:500],
            body=result.answer,
            recipient=recipient,
            external_ref=external_ref,
            escalated=result.escalated,
            citations=result.citations,
            metadata={"confidence": result.confidence},
        )
        try:
            await self.dispatcher.post_json("/api/dispatch", request.model_dump(mode="json"))
        except Exception as exc:
            # The resolution is already committed, so the customer's answer is
            # not lost - only its delivery. The dispatcher's own retry queue and
            # the ops dashboard surface it.
            log.error("pipeline.dispatch_failed", error=str(exc))
            async with session_scope() as session:
                await TicketRepository(session).add_message(
                    result.ticket_id,
                    MessageSender.SYSTEM,
                    f"Delivery failed: {exc}",
                    metadata={"dispatch_error": True},
                )

    async def _mark_failed(self, ticket_id: str, error: str) -> None:
        async with session_scope() as session:
            repository = TicketRepository(session)
            await repository.add_message(
                ticket_id,
                MessageSender.SYSTEM,
                f"Processing failed: {error}",
                metadata={"error": True, "at": datetime.now(UTC).isoformat()},
            )
            await repository.set_status(ticket_id, TicketStatus.FAILED)


def _to_agent_request(ticket: Ticket) -> AgentRequest:
    """Project the stored ticket onto the agent's request contract."""
    return AgentRequest(
        ticket_id=ticket.ticket_id,
        subject=ticket.subject,
        body=ticket.body,
        channel=ticket.channel,
        customer_tier=ticket.customer_tier,
        priority=ticket.priority,
    )
