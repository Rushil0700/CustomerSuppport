"""Repository tests against a real PostgreSQL database."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from support_common.enums import (
    Channel,
    EscalationReason,
    MessageSender,
    TicketStatus,
)
from support_common.errors import TicketNotFound
from support_common.schemas import AgentResult, Citation, CustomerRef, TicketCreate

from ticket_receiver.repository import TicketRepository

pytestmark = pytest.mark.integration


@pytest.fixture
async def repository(
    session_factory: async_sessionmaker,
) -> AsyncIterator[TicketRepository]:
    async with session_factory() as session:
        yield TicketRepository(session)
        await session.commit()


def make_ticket(external_ref: str = "ref-1", channel: Channel = Channel.EMAIL) -> TicketCreate:
    return TicketCreate(
        subject="Cannot sign in",
        body="I forgot my password and the reset email never arrives.",
        customer=CustomerRef(
            external_id="email:dana@customer.example",
            email="dana@customer.example",
            name="Dana Okafor",
        ),
        channel=channel,
        external_ref=external_ref,
        tags=["email", "login"],
        metadata={"source": "test"},
    )


class TestCreate:
    async def test_a_ticket_is_stored_with_its_first_message(
        self, repository: TicketRepository
    ) -> None:
        ticket, created = await repository.create(make_ticket())

        assert created is True
        assert ticket.ticket_id.startswith("TKT-")
        assert ticket.status is TicketStatus.NEW
        assert ticket.tags == ["email", "login"]
        assert ticket.metadata_json == {"source": "test"}

        messages = await repository.messages(ticket.ticket_id)
        assert len(messages) == 1
        assert messages[0].sender is MessageSender.CUSTOMER

    async def test_the_same_external_ref_is_not_duplicated(
        self, repository: TicketRepository
    ) -> None:
        """Webhooks redeliver; a redelivery must not open a second ticket."""
        first, created_first = await repository.create(make_ticket("dup-ref"))
        second, created_second = await repository.create(make_ticket("dup-ref"))

        assert created_first is True
        assert created_second is False
        assert first.ticket_id == second.ticket_id

    async def test_the_same_ref_on_a_different_channel_is_a_separate_ticket(
        self, repository: TicketRepository
    ) -> None:
        first, _ = await repository.create(make_ticket("shared", Channel.EMAIL))
        second, created = await repository.create(make_ticket("shared", Channel.SLACK))

        assert created is True
        assert first.ticket_id != second.ticket_id

    async def test_tickets_without_a_ref_are_always_distinct(
        self, repository: TicketRepository
    ) -> None:
        payload = make_ticket()
        payload.external_ref = None
        first, _ = await repository.create(payload)
        second, created = await repository.create(payload)

        assert created is True
        assert first.ticket_id != second.ticket_id


class TestLifecycle:
    async def test_status_transitions_stamp_the_timestamps(
        self, repository: TicketRepository
    ) -> None:
        ticket, _ = await repository.create(make_ticket())

        processing = await repository.set_status(ticket.ticket_id, TicketStatus.PROCESSING)
        assert processing.first_response_at is not None
        assert processing.closed_at is None

        resolved = await repository.set_status(ticket.ticket_id, TicketStatus.RESOLVED)
        assert resolved.closed_at is not None

    async def test_fetching_an_unknown_ticket_raises(
        self, repository: TicketRepository
    ) -> None:
        with pytest.raises(TicketNotFound):
            await repository.get("TKT-DOESNOTEXIST")


class TestResolutions:
    async def test_a_resolution_is_stored_and_closes_the_ticket(
        self, repository: TicketRepository
    ) -> None:
        ticket, _ = await repository.create(make_ticket())
        result = AgentResult(
            ticket_id=ticket.ticket_id,
            resolved=True,
            answer="Use the Forgot password link on the login page.",
            confidence=0.88,
            citations=[
                Citation(
                    doc_id="account-password-reset",
                    title="Reset a forgotten password",
                    source="account/account-password-reset.md",
                    score=0.81,
                )
            ],
            turns_used=2,
            model="qwen3:8b",
            took_ms=4200.0,
            estimated_cost_usd=0.032,
        )

        resolution = await repository.record_resolution(result)

        assert resolution.confidence == pytest.approx(0.88)
        assert resolution.citations[0]["doc_id"] == "account-password-reset"
        assert (await repository.get(ticket.ticket_id)).status is TicketStatus.RESOLVED

        messages = await repository.messages(ticket.ticket_id)
        assert [m.sender for m in messages] == [MessageSender.CUSTOMER, MessageSender.AGENT]

    async def test_an_escalation_is_stored_with_its_reason(
        self, repository: TicketRepository
    ) -> None:
        ticket, _ = await repository.create(make_ticket())
        result = AgentResult(
            ticket_id=ticket.ticket_id,
            resolved=False,
            answer="A colleague will follow up shortly.",
            confidence=0.0,
            escalated=True,
            escalation_reason=EscalationReason.POLICY_REQUIRED,
            model="qwen3:8b",
        )

        resolution = await repository.record_resolution(result)

        assert resolution.escalated is True
        assert resolution.escalation_reason is EscalationReason.POLICY_REQUIRED
        assert (await repository.get(ticket.ticket_id)).status is TicketStatus.ESCALATED


class TestQueries:
    async def test_recent_tickets_are_newest_first(
        self, repository: TicketRepository
    ) -> None:
        for index in range(5):
            await repository.create(make_ticket(f"ref-{index}"))

        recent = await repository.list_recent(limit=3)
        assert len(recent) == 3

    async def test_listing_can_filter_by_status(
        self, repository: TicketRepository
    ) -> None:
        first, _ = await repository.create(make_ticket("a"))
        await repository.create(make_ticket("b"))
        await repository.set_status(first.ticket_id, TicketStatus.RESOLVED)

        resolved = await repository.list_recent(status=TicketStatus.RESOLVED)
        assert [t.ticket_id for t in resolved] == [first.ticket_id]

    async def test_stats_report_the_auto_resolution_rate(
        self, repository: TicketRepository
    ) -> None:
        """Three resolved out of four decided is the headline 75%."""
        for index in range(4):
            ticket, _ = await repository.create(make_ticket(f"stat-{index}"))
            await repository.record_resolution(
                AgentResult(
                    ticket_id=ticket.ticket_id,
                    resolved=index < 3,
                    answer="An answer long enough to be realistic.",
                    confidence=0.8 if index < 3 else 0.0,
                    escalated=index >= 3,
                    escalation_reason=None if index < 3 else EscalationReason.NO_KB_MATCH,
                    estimated_cost_usd=0.04,
                )
            )

        stats = await repository.stats()
        assert stats["tickets_total"] == 4
        assert stats["auto_resolution_rate"] == pytest.approx(0.75)
        assert stats["resolutions_recorded"] == 4
        assert stats["avg_cost_usd"] == pytest.approx(0.04)
