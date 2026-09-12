"""End-to-end tests against the real local model and the real vector index.

These are the only tests that exercise Ollama. They are slow (tens of seconds
per ticket on CPU) and are skipped unless both the daemon and an indexed
knowledge base are present, so the default test run never depends on them.

Run them explicitly::

    pytest tests/integration/test_agent_live.py -m slow -v

The assertions are deliberately about *behaviour that must hold for any model* -
that a ticket always reaches a decision, that sensitive tickets escalate, that
answers are grounded in retrieved articles - rather than about exact wording,
which would make the suite a flaky model regression test.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from support_common.config import get_settings
from support_common.enums import Channel, EscalationReason
from support_common.schemas import AgentRequest, SearchRequest, SearchResponse

from agent_service.agent import SupportAgent
from agent_service.ollama_client import OllamaClient
from agent_service.tools import ToolRegistry
from rag_engine.retriever import Retriever

pytestmark = [pytest.mark.integration, pytest.mark.slow]


class InProcessRAG:
    """Lets the tool registry reach the retriever without an HTTP hop."""

    def __init__(self, retriever: Retriever) -> None:
        self.retriever = retriever
        self.queries: list[str] = []

    async def post_json(self, _path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = SearchRequest.model_validate(payload)
        self.queries.append(request.query)
        response: SearchResponse = await self.retriever.search(request)
        return response.model_dump(mode="json")

    async def aclose(self) -> None:
        return None

    async def healthy(self) -> bool:
        return True


class NullDispatcher:
    async def post_json(self, _path: str, _payload: dict[str, Any]) -> dict[str, Any]:
        return {"delivered": True, "dry_run": True}

    async def aclose(self) -> None:
        return None

    async def healthy(self) -> bool:
        return True


@pytest.fixture(scope="module")
async def live_retriever() -> AsyncIterator[Retriever]:
    retriever = Retriever()
    try:
        count = await retriever.vector_store.count()
    except Exception as exc:
        pytest.skip(f"vector store unavailable: {exc}")
    if count == 0:
        pytest.skip("vector index is empty - run `python scripts/seed_kb.py`")
    yield retriever


@pytest.fixture
async def live_agent(live_retriever: Retriever) -> AsyncIterator[SupportAgent]:
    settings = get_settings()
    client = OllamaClient(settings)
    if not await client.healthy():
        await client.aclose()
        pytest.skip(f"ollama unavailable or model {settings.ollama_model!r} not pulled")

    tools = ToolRegistry(
        settings=settings,
        rag_client=InProcessRAG(live_retriever),  # type: ignore[arg-type]
        dispatcher_client=NullDispatcher(),  # type: ignore[arg-type]
    )
    agent = SupportAgent(llm=client, tools=tools, settings=settings)
    yield agent
    await agent.aclose()


def request(subject: str, body: str, channel: Channel = Channel.EMAIL) -> AgentRequest:
    # The id alphabet excludes I, L, O and U.
    return AgentRequest(
        ticket_id="TKT-VE" + f"{abs(hash(subject)) % 10**10:010d}",
        subject=subject,
        body=body,
        channel=channel,
    )


class TestLiveResolution:
    async def test_a_well_covered_ticket_is_answered_and_grounded(
        self, live_agent: SupportAgent
    ) -> None:
        result = await live_agent.handle(
            request(
                "Files stuck syncing",
                "Three files have been showing the syncing spinner for two hours. "
                "Everything else in the workspace works fine.",
            )
        )

        assert result.resolved is True, f"escalated: {result.escalation_reason}"
        assert result.confidence >= get_settings().agent_confidence_threshold
        assert result.citations, "a resolved ticket must cite the articles it used"
        assert len(result.answer.split()) >= 25
        # The prompt forbids leaking the machinery to the customer.
        lowered = result.answer.lower()
        for forbidden in ("knowledge base", "search_kb", "as an ai", "article id"):
            assert forbidden not in lowered

    async def test_the_agent_searches_before_answering(
        self, live_agent: SupportAgent
    ) -> None:
        await live_agent.handle(
            request(
                "How do I download an invoice",
                "Our finance team needs a PDF invoice for last month for expenses.",
            )
        )
        rag: InProcessRAG = live_agent.tools.rag  # type: ignore[assignment]
        assert rag.queries, "the agent answered without consulting the knowledge base"


class TestLiveEscalation:
    async def test_an_mfa_lockout_always_escalates(self, live_agent: SupportAgent) -> None:
        """Policy, not model judgement: this must never be auto-answered."""
        result = await live_agent.handle(
            request(
                "Lost my 2FA device",
                "My phone was stolen and I do not have my recovery codes. "
                "I need access to my account immediately.",
            )
        )
        assert result.resolved is False
        assert result.escalated is True

    async def test_a_request_for_a_human_escalates(self, live_agent: SupportAgent) -> None:
        result = await live_agent.handle(
            request(
                "Speak to a person",
                "I do not want to talk to a bot. Please put me through to a real human.",
            )
        )
        assert result.escalation_reason is EscalationReason.CUSTOMER_REQUESTED
        # Guard rails run before inference, so this costs nothing.
        assert result.turns_used == 0

    async def test_a_question_outside_the_knowledge_base_escalates(
        self, live_agent: SupportAgent
    ) -> None:
        result = await live_agent.handle(
            request(
                "Quantum tunnelling in our deployment",
                "Can your platform model the quantum tunnelling probability of an "
                "electron through a potential barrier in our physics simulation?",
            )
        )
        assert result.resolved is False


class TestLiveInvariants:
    async def test_every_ticket_reaches_a_decision(
        self, live_agent: SupportAgent
    ) -> None:
        """The core invariant, against the real model: nothing is ever dropped."""
        tickets = [
            ("Cannot sign in", "I forgot my password and the reset email never arrives."),
            ("", "just some text with no subject to speak of at all"),
            ("???", "???"),
            ("Very long", "please help " * 400),
        ]
        for subject, body in tickets:
            result = await live_agent.handle(
                request(subject or "No subject", body)
            )
            assert result.resolved != result.escalated
            assert result.answer.strip()
            assert 0.0 <= result.confidence <= 1.0
            assert result.turns_used <= get_settings().agent_max_turns

    async def test_cost_stays_under_the_target(self, live_agent: SupportAgent) -> None:
        result = await live_agent.handle(
            request(
                "How many seats on the Team plan",
                "We are on the Team plan. How many seats does that include?",
            )
        )
        assert result.estimated_cost_usd <= 0.08, (
            f"cost ${result.estimated_cost_usd:.4f} exceeds the $0.08 target"
        )
