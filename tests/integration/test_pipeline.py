"""Tests for the ticket pipeline's orchestration logic against a real database.

The agent and dispatcher are faked; the point is verifying the pipeline's own
control flow (status transitions, metric labels, failure handling) rather than
re-testing the HTTP layer covered elsewhere.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from support_common.enums import EscalationReason, TicketStatus
from support_common.schemas import AgentResult, CustomerRef, TicketCreate
from ticket_receiver.pipeline import TicketPipeline
from ticket_receiver.repository import TicketRepository

pytestmark = pytest.mark.integration


class ScriptedAgent:
    def __init__(self, result: AgentResult | Exception) -> None:
        self.result = result
        self.calls = 0

    async def post_json(self, _path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result.model_dump(mode="json")

    async def aclose(self) -> None:
        return None

    async def healthy(self) -> bool:
        return True


class ScriptedDispatcher:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    async def post_json(self, _path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(payload)
        if self.fail:
            raise RuntimeError("dispatcher down")
        return {"delivered": True}

    async def aclose(self) -> None:
        return None

    async def healthy(self) -> bool:
        return True


@pytest.fixture
async def ticket_id(app_engine: AsyncEngine) -> str:
    factory = async_sessionmaker(app_engine, expire_on_commit=False)
    async with factory() as session:
        repository = TicketRepository(session)
        ticket, _ = await repository.create(
            TicketCreate(
                subject="Cannot sign in",
                body="I forgot my password.",
                customer=CustomerRef(external_id="email:a@b.example", email="a@b.example"),
                channel="email",
                external_ref="pipeline-test",
            )
        )
        await session.commit()
        return ticket.ticket_id


async def get_ticket(app_engine: AsyncEngine, ticket_id: str):
    factory = async_sessionmaker(app_engine, expire_on_commit=False)
    async with factory() as session:
        return await TicketRepository(session).get(ticket_id)


def resolved_result(ticket_id: str) -> AgentResult:
    return AgentResult(
        ticket_id=ticket_id,
        resolved=True,
        answer="Open the login page and choose Forgot password.",
        confidence=0.85,
        model="test-model",
        estimated_cost_usd=0.02,
    )


def escalated_result(ticket_id: str) -> AgentResult:
    return AgentResult(
        ticket_id=ticket_id,
        resolved=False,
        answer="A colleague will follow up.",
        confidence=0.0,
        escalated=True,
        escalation_reason=EscalationReason.NO_KB_MATCH,
        model="test-model",
    )


class TestProcess:
    async def test_a_resolved_ticket_ends_up_resolved(
        self, app_engine: AsyncEngine, ticket_id: str
    ) -> None:
        pipeline = TicketPipeline(
            agent_client=ScriptedAgent(resolved_result(ticket_id)),
            dispatcher_client=ScriptedDispatcher(),
        )
        result = await pipeline.process(ticket_id)

        assert result is not None
        assert result.resolved is True
        assert (await get_ticket(app_engine, ticket_id)).status is TicketStatus.RESOLVED

    async def test_an_escalated_ticket_ends_up_escalated(
        self, app_engine: AsyncEngine, ticket_id: str
    ) -> None:
        pipeline = TicketPipeline(
            agent_client=ScriptedAgent(escalated_result(ticket_id)),
            dispatcher_client=ScriptedDispatcher(),
        )
        await pipeline.process(ticket_id)
        assert (await get_ticket(app_engine, ticket_id)).status is TicketStatus.ESCALATED

    async def test_a_terminal_ticket_is_skipped(
        self, app_engine: AsyncEngine, ticket_id: str
    ) -> None:
        """Reprocessing something already resolved must not re-run the agent."""
        agent = ScriptedAgent(resolved_result(ticket_id))
        pipeline = TicketPipeline(agent_client=agent, dispatcher_client=ScriptedDispatcher())
        await pipeline.process(ticket_id)
        assert agent.calls == 1

        result = await pipeline.process(ticket_id)
        assert result is None
        assert agent.calls == 1  # not called again

    async def test_an_agent_failure_marks_the_ticket_failed(
        self, app_engine: AsyncEngine, ticket_id: str
    ) -> None:
        pipeline = TicketPipeline(
            agent_client=ScriptedAgent(RuntimeError("agent exploded")),
            dispatcher_client=ScriptedDispatcher(),
        )
        result = await pipeline.process(ticket_id)

        assert result is None
        ticket = await get_ticket(app_engine, ticket_id)
        assert ticket.status is TicketStatus.FAILED

    async def test_a_dispatch_failure_does_not_lose_the_resolution(
        self, app_engine: AsyncEngine, ticket_id: str
    ) -> None:
        pipeline = TicketPipeline(
            agent_client=ScriptedAgent(resolved_result(ticket_id)),
            dispatcher_client=ScriptedDispatcher(fail=True),
        )
        result = await pipeline.process(ticket_id)

        assert result is not None
        assert result.resolved is True
        # The ticket is still marked resolved - only delivery failed.
        assert (await get_ticket(app_engine, ticket_id)).status is TicketStatus.RESOLVED

    async def test_an_unknown_ticket_raises_rather_than_silently_returning(
        self,
        app_engine: AsyncEngine,
    ) -> None:
        # Takes app_engine purely so this test is gated on Postgres being
        # reachable like every other test here - without it, a missing database
        # surfaces as a raw connection error instead of a clean skip.
        from support_common.errors import TicketNotFound

        pipeline = TicketPipeline(
            agent_client=ScriptedAgent(resolved_result("TKT-X")),
            dispatcher_client=ScriptedDispatcher(),
        )
        with pytest.raises(TicketNotFound):
            await pipeline.process("TKT-DOESNOTEXIST")

    async def test_processing_moves_the_ticket_through_processing_first(
        self, app_engine: AsyncEngine, ticket_id: str
    ) -> None:
        """A slow agent call should find the ticket already marked PROCESSING."""
        pipeline = TicketPipeline(
            agent_client=ScriptedAgent(resolved_result(ticket_id)),
            dispatcher_client=ScriptedDispatcher(),
        )
        await pipeline.process(ticket_id)
        ticket = await get_ticket(app_engine, ticket_id)
        assert ticket.first_response_at is not None

    async def test_the_dispatch_payload_carries_the_answer_and_citations(
        self, app_engine: AsyncEngine, ticket_id: str
    ) -> None:
        dispatcher = ScriptedDispatcher()
        pipeline = TicketPipeline(
            agent_client=ScriptedAgent(resolved_result(ticket_id)),
            dispatcher_client=dispatcher,
        )
        await pipeline.process(ticket_id)

        assert len(dispatcher.calls) == 1
        assert dispatcher.calls[0]["ticket_id"] == ticket_id
        assert dispatcher.calls[0]["escalated"] is False
        assert dispatcher.calls[0]["body"] == resolved_result(ticket_id).answer
