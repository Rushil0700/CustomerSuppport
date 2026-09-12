"""Tests for the agent reasoning loop.

The LLM and the RAG engine are both replaced by scripted fakes, so these tests
are deterministic and need no Ollama. What they verify is the control flow that
decides a customer's outcome: when the agent resolves, when it escalates, and
that it always does one or the other.
"""

from __future__ import annotations

from typing import Any

import pytest

from support_common.config import Settings
from support_common.enums import Channel, EscalationReason
from support_common.schemas import AgentRequest, SearchResponse

from agent_service.agent import SupportAgent
from agent_service.ollama_client import ChatResponse, ToolCall
from agent_service.tools import ToolRegistry

GOOD_ANSWER = (
    "To reset your password, open the login page and choose Forgot password. "
    "Enter the email address on your account, then open the reset link we send - "
    "it is valid for 60 minutes. If you signed up with Google or Microsoft SSO "
    "there is no password to reset, so use Continue with Google instead. Reply "
    "here if that does not get you back in."
)


class FakeLLM:
    """Returns a scripted sequence of responses, recording what it was asked."""

    def __init__(self, responses: list[ChatResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict[str, Any]]] = []
        self.model = "fake-model"

    async def chat(self, messages: list[dict[str, Any]], **_: Any) -> ChatResponse:
        self.calls.append(messages)
        if not self.responses:
            # Runaway loop: the test wanted fewer turns than the agent took.
            return ChatResponse(content="(no more scripted responses)", model=self.model)
        return self.responses.pop(0)

    async def aclose(self) -> None:
        return None

    async def healthy(self) -> bool:
        return True


class FakeRAG:
    """Stands in for the RAG engine's HTTP client."""

    def __init__(self, response: SearchResponse) -> None:
        self.response = response
        self.queries: list[str] = []

    async def post_json(self, _path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.queries.append(payload["query"])
        return self.response.model_dump(mode="json")

    async def aclose(self) -> None:
        return None

    async def healthy(self) -> bool:
        return True


class FakeDispatcher:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def post_json(self, _path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.sent.append(payload)
        return {"delivered": True}

    async def aclose(self) -> None:
        return None

    async def healthy(self) -> bool:
        return True


def tool_response(name: str, **arguments: Any) -> ChatResponse:
    return ChatResponse(
        content="", tool_calls=[ToolCall(name=name, arguments=arguments)], model="fake-model"
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="ci",
        agent_max_turns=5,
        agent_confidence_threshold=0.70,
        agent_max_concurrency=2,
    )


def build_agent(
    responses: list[ChatResponse],
    search_response: SearchResponse,
    settings: Settings,
) -> tuple[SupportAgent, FakeRAG, FakeDispatcher]:
    rag, dispatcher = FakeRAG(search_response), FakeDispatcher()
    registry = ToolRegistry(settings=settings, rag_client=rag, dispatcher_client=dispatcher)
    agent = SupportAgent(llm=FakeLLM(responses), tools=registry, settings=settings)
    return agent, rag, dispatcher


class TestHappyPath:
    async def test_search_then_resolve(
        self, agent_request: AgentRequest, search_response: SearchResponse, settings: Settings
    ) -> None:
        agent, rag, _ = build_agent(
            [
                tool_response("search_kb", query="password reset email not arriving"),
                tool_response("resolve_ticket", answer=GOOD_ANSWER, confidence=0.92),
            ],
            search_response,
            settings,
        )
        result = await agent.handle(agent_request)

        assert result.resolved is True
        assert result.escalated is False
        assert result.confidence >= 0.70
        assert result.turns_used == 2
        assert rag.queries == ["password reset email not arriving"]
        assert [c.doc_id for c in result.citations] == [
            "account-password-reset",
            "troubleshooting-cannot-login",
        ]

    async def test_tool_calls_are_recorded_for_audit(
        self, agent_request: AgentRequest, search_response: SearchResponse, settings: Settings
    ) -> None:
        agent, _, _ = build_agent(
            [
                tool_response("search_kb", query="password reset"),
                tool_response("resolve_ticket", answer=GOOD_ANSWER, confidence=0.9),
            ],
            search_response,
            settings,
        )
        result = await agent.handle(agent_request)
        assert [t.tool for t in result.tool_calls] == ["search_kb", "resolve_ticket"]
        assert all(t.ok for t in result.tool_calls)
        assert result.tool_calls[0].turn == 1

    async def test_cost_and_model_are_reported(
        self, agent_request: AgentRequest, search_response: SearchResponse, settings: Settings
    ) -> None:
        agent, _, _ = build_agent(
            [
                tool_response("search_kb", query="password"),
                tool_response("resolve_ticket", answer=GOOD_ANSWER, confidence=0.9),
            ],
            search_response,
            settings,
        )
        result = await agent.handle(agent_request)
        assert result.model == "fake-model"
        assert result.estimated_cost_usd > 0
        assert result.took_ms >= 0


class TestEscalation:
    async def test_the_model_can_escalate_explicitly(
        self, agent_request: AgentRequest, search_response: SearchResponse, settings: Settings
    ) -> None:
        agent, _, _ = build_agent(
            [
                tool_response("search_kb", query="password"),
                tool_response(
                    "escalate", reason="no_kb_match", summary="Nothing covers this case."
                ),
            ],
            search_response,
            settings,
        )
        result = await agent.handle(agent_request)

        assert result.escalated is True
        assert result.resolved is False
        assert result.escalation_reason is EscalationReason.NO_KB_MATCH

    async def test_low_confidence_is_converted_to_an_escalation(
        self, agent_request: AgentRequest, search_response: SearchResponse, settings: Settings
    ) -> None:
        """The gate overrides the model even when it called resolve_ticket."""
        agent, _, _ = build_agent(
            [
                tool_response("search_kb", query="password"),
                tool_response("resolve_ticket", answer=GOOD_ANSWER, confidence=0.2),
            ],
            search_response,
            settings,
        )
        result = await agent.handle(agent_request)

        assert result.escalated is True
        assert result.escalation_reason is EscalationReason.LOW_CONFIDENCE

    async def test_answering_without_searching_escalates(
        self, agent_request: AgentRequest, search_response: SearchResponse, settings: Settings
    ) -> None:
        """No retrieval means no grounding, whatever confidence is claimed."""
        agent, rag, _ = build_agent(
            [tool_response("resolve_ticket", answer=GOOD_ANSWER, confidence=1.0)],
            search_response,
            settings,
        )
        result = await agent.handle(agent_request)

        assert result.escalated is True
        assert rag.queries == []

    async def test_running_out_of_turns_escalates(
        self, agent_request: AgentRequest, search_response: SearchResponse, settings: Settings
    ) -> None:
        agent, _, _ = build_agent(
            [tool_response("search_kb", query=f"attempt {i}") for i in range(5)],
            search_response,
            settings,
        )
        result = await agent.handle(agent_request)

        assert result.escalated is True
        assert result.escalation_reason is EscalationReason.MAX_TURNS_EXCEEDED
        assert result.turns_used == 5

    async def test_a_sensitive_ticket_escalates_without_calling_the_model(
        self, search_response: SearchResponse, settings: Settings
    ) -> None:
        agent, rag, _ = build_agent([], search_response, settings)
        request = AgentRequest(
            ticket_id="TKT-ABCDEF123456",
            subject="Security incident",
            body="I think our workspace was hacked - there are share links nobody recognises.",
            channel=Channel.SLACK,
        )
        result = await agent.handle(request)

        assert result.escalated is True
        assert result.escalation_reason is EscalationReason.SENSITIVE_TOPIC
        assert result.turns_used == 0
        assert agent.llm.calls == []  # type: ignore[attr-defined]
        assert rag.queries == []

    async def test_a_request_for_a_human_escalates_immediately(
        self, search_response: SearchResponse, settings: Settings
    ) -> None:
        agent, _, _ = build_agent([], search_response, settings)
        result = await agent.handle(
            AgentRequest(
                ticket_id="TKT-ABCDEF123456",
                subject="Help",
                body="Please let me speak to a human, the bot is not helping.",
                channel=Channel.EMAIL,
            )
        )
        assert result.escalation_reason is EscalationReason.CUSTOMER_REQUESTED

    async def test_an_llm_failure_escalates_rather_than_erroring(
        self, agent_request: AgentRequest, search_response: SearchResponse, settings: Settings
    ) -> None:
        from support_common.errors import LLMError

        class BrokenLLM(FakeLLM):
            async def chat(self, messages: list[dict[str, Any]], **_: Any) -> ChatResponse:
                raise LLMError("ollama is down")

        registry = ToolRegistry(
            settings=settings,
            rag_client=FakeRAG(search_response),
            dispatcher_client=FakeDispatcher(),
        )
        agent = SupportAgent(llm=BrokenLLM([]), tools=registry, settings=settings)
        result = await agent.handle(agent_request)

        assert result.escalated is True
        assert result.escalation_reason is EscalationReason.LLM_ERROR
        assert result.answer  # the customer still gets a holding message


class TestProtocolRecovery:
    async def test_prose_before_searching_is_nudged_back_on_track(
        self, agent_request: AgentRequest, search_response: SearchResponse, settings: Settings
    ) -> None:
        agent, rag, _ = build_agent(
            [
                ChatResponse(content="Sure, I can help with that!", model="fake-model"),
                tool_response("search_kb", query="password reset"),
                tool_response("resolve_ticket", answer=GOOD_ANSWER, confidence=0.9),
            ],
            search_response,
            settings,
        )
        result = await agent.handle(agent_request)

        assert result.resolved is True
        assert rag.queries == ["password reset"]

    async def test_a_json_tool_call_in_text_is_parsed(
        self, agent_request: AgentRequest, search_response: SearchResponse, settings: Settings
    ) -> None:
        """Models without native tool calling emit JSON in the content field."""
        agent, rag, _ = build_agent(
            [
                ChatResponse(
                    content='```json\n{"tool": "search_kb", "arguments": {"query": "password reset"}}\n```',
                    model="fake-model",
                ),
                ChatResponse(
                    content=(
                        '{"tool": "resolve_ticket", "arguments": '
                        f'{{"answer": {GOOD_ANSWER!r}, "confidence": 0.9}}}}'
                    ).replace("'", '"'),
                    model="fake-model",
                ),
            ],
            search_response,
            settings,
        )
        result = await agent.handle(agent_request)

        assert rag.queries == ["password reset"]
        assert result.resolved is True

    async def test_an_unknown_tool_does_not_end_the_ticket(
        self, agent_request: AgentRequest, search_response: SearchResponse, settings: Settings
    ) -> None:
        agent, _, _ = build_agent(
            [
                tool_response("refund_customer", amount=100),
                tool_response("search_kb", query="password"),
                tool_response("resolve_ticket", answer=GOOD_ANSWER, confidence=0.9),
            ],
            search_response,
            settings,
        )
        result = await agent.handle(agent_request)

        assert result.resolved is True
        assert result.tool_calls[0].ok is False

    async def test_a_confidence_given_as_a_percentage_is_normalised(
        self, agent_request: AgentRequest, search_response: SearchResponse, settings: Settings
    ) -> None:
        agent, _, _ = build_agent(
            [
                tool_response("search_kb", query="password"),
                tool_response("resolve_ticket", answer=GOOD_ANSWER, confidence=90),
            ],
            search_response,
            settings,
        )
        result = await agent.handle(agent_request)
        assert result.resolved is True
        assert result.confidence <= 1.0

    async def test_a_truncated_answer_is_rejected_and_retried(
        self, agent_request: AgentRequest, search_response: SearchResponse, settings: Settings
    ) -> None:
        agent, _, _ = build_agent(
            [
                tool_response("search_kb", query="password"),
                tool_response("resolve_ticket", answer="ok", confidence=0.9),
                tool_response("resolve_ticket", answer=GOOD_ANSWER, confidence=0.9),
            ],
            search_response,
            settings,
        )
        result = await agent.handle(agent_request)

        assert result.resolved is True
        assert result.tool_calls[1].ok is False


class TestInvariants:
    async def test_every_path_produces_a_decision(
        self, agent_request: AgentRequest, search_response: SearchResponse, settings: Settings
    ) -> None:
        """A ticket is never dropped: it is always resolved or escalated."""
        scripts: list[list[ChatResponse]] = [
            [],
            [ChatResponse(content="hello", model="m")],
            [tool_response("search_kb", query="a query")],
            [tool_response("escalate", reason="bogus_reason", summary="s")],
            [tool_response("resolve_ticket", answer="", confidence=0.9)],
        ]
        for script in scripts:
            agent, _, _ = build_agent(script, search_response, settings)
            result = await agent.handle(agent_request)
            assert result.resolved != result.escalated
            assert result.answer
            assert result.ticket_id == agent_request.ticket_id

    async def test_an_unrecognised_escalation_reason_falls_back(
        self, agent_request: AgentRequest, search_response: SearchResponse, settings: Settings
    ) -> None:
        agent, _, _ = build_agent(
            [tool_response("escalate", reason="because_i_said_so", summary="note")],
            search_response,
            settings,
        )
        result = await agent.handle(agent_request)
        assert result.escalation_reason is EscalationReason.LOW_CONFIDENCE

    async def test_max_turns_can_be_overridden_per_request(
        self, search_response: SearchResponse, settings: Settings
    ) -> None:
        agent, _, _ = build_agent(
            [tool_response("search_kb", query=f"q{i}") for i in range(5)],
            search_response,
            settings,
        )
        request = AgentRequest(
            ticket_id="TKT-ABCDEF123456",
            subject="s",
            body="a body that is long enough to be processed normally",
            channel=Channel.API,
            max_turns=2,
        )
        result = await agent.handle(request)
        assert result.turns_used == 2


class TestNotifyCustomer:
    async def test_an_interim_update_is_dispatched(
        self, agent_request: AgentRequest, search_response: SearchResponse, settings: Settings
    ) -> None:
        agent, _, dispatcher = build_agent(
            [
                tool_response("search_kb", query="password"),
                tool_response(
                    "notify_customer",
                    message="Looking into this now, I'll follow up shortly.",
                ),
                tool_response("resolve_ticket", answer=GOOD_ANSWER, confidence=0.9),
            ],
            search_response,
            settings,
        )
        result = await agent.handle(agent_request)

        assert len(dispatcher.sent) == 1
        assert dispatcher.sent[0]["metadata"]["interim"] is True
        assert result.resolved is True

    async def test_a_second_interim_update_is_suppressed(
        self, agent_request: AgentRequest, search_response: SearchResponse, settings: Settings
    ) -> None:
        agent, _, dispatcher = build_agent(
            [
                tool_response("search_kb", query="password"),
                tool_response("notify_customer", message="First update on your ticket."),
                tool_response("notify_customer", message="Second update on your ticket."),
                tool_response("resolve_ticket", answer=GOOD_ANSWER, confidence=0.9),
            ],
            search_response,
            settings,
        )
        await agent.handle(agent_request)
        assert len(dispatcher.sent) == 1
