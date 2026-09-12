"""Tests for the agent's tool layer."""

from __future__ import annotations

from typing import Any

import pytest

from support_common.config import Settings
from support_common.enums import Channel, EscalationReason
from support_common.errors import UpstreamUnavailable
from support_common.schemas import SearchResponse

from agent_service.tools import TOOL_SCHEMAS, ToolContext, ToolRegistry, _clamp


class StubClient:
    """Minimal stand-in for ServiceClient."""

    def __init__(self, response: dict[str, Any] | None = None, error: Exception | None = None):
        self.response = response or {}
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((path, payload))
        if self.error:
            raise self.error
        return self.response

    async def aclose(self) -> None:
        return None

    async def healthy(self) -> bool:
        return True


@pytest.fixture
def settings() -> Settings:
    return Settings(environment="ci", rag_top_k=5)


@pytest.fixture
def context() -> ToolContext:
    return ToolContext(
        ticket_id="TKT-ABCDEF123456",
        channel=Channel.EMAIL,
        subject="Cannot sign in",
        body="I forgot my password.",
    )


def registry(
    settings: Settings,
    search_response: SearchResponse | None = None,
    rag_error: Exception | None = None,
) -> tuple[ToolRegistry, StubClient, StubClient]:
    rag = StubClient(
        search_response.model_dump(mode="json") if search_response else {"query": "q", "results": [], "took_ms": 1.0},
        rag_error,
    )
    dispatcher = StubClient({"delivered": True})
    return (
        ToolRegistry(settings=settings, rag_client=rag, dispatcher_client=dispatcher),
        rag,
        dispatcher,
    )


class TestSchemas:
    def test_the_four_required_tools_are_defined(self) -> None:
        names = {s["function"]["name"] for s in TOOL_SCHEMAS}
        assert names == {"search_kb", "resolve_ticket", "escalate", "notify_customer"}

    def test_every_schema_is_shaped_for_ollama(self) -> None:
        for schema in TOOL_SCHEMAS:
            assert schema["type"] == "function"
            function = schema["function"]
            assert function["description"]
            assert function["parameters"]["type"] == "object"
            assert function["parameters"]["required"]

    def test_escalation_reasons_match_the_enum(self) -> None:
        escalate = next(s for s in TOOL_SCHEMAS if s["function"]["name"] == "escalate")
        allowed = escalate["function"]["parameters"]["properties"]["reason"]["enum"]
        assert set(allowed) == {r.value for r in EscalationReason}


class TestSearchKb:
    async def test_results_become_citations(
        self, settings: Settings, context: ToolContext, search_response: SearchResponse
    ) -> None:
        tools, rag, _ = registry(settings, search_response)
        result, _ = await tools.execute("search_kb", {"query": "password reset"}, context)

        assert result.ok
        assert len(result.payload["results"]) == 2
        assert [c.doc_id for c in context.citations] == [
            "account-password-reset",
            "troubleshooting-cannot-login",
        ]
        assert context.searches == 1
        assert context.best_score == pytest.approx(0.78)
        assert rag.calls[0][0] == "/api/search"

    async def test_repeated_searches_do_not_duplicate_citations(
        self, settings: Settings, context: ToolContext, search_response: SearchResponse
    ) -> None:
        tools, _, _ = registry(settings, search_response)
        await tools.execute("search_kb", {"query": "password"}, context)
        await tools.execute("search_kb", {"query": "password again"}, context)
        assert len(context.citations) == 2
        assert context.searches == 2

    async def test_a_category_filter_is_forwarded(
        self, settings: Settings, context: ToolContext, search_response: SearchResponse
    ) -> None:
        tools, rag, _ = registry(settings, search_response)
        await tools.execute("search_kb", {"query": "refund", "category": "billing"}, context)
        assert rag.calls[0][1]["categories"] == ["billing"]

    async def test_an_empty_query_is_rejected(
        self, settings: Settings, context: ToolContext
    ) -> None:
        tools, rag, _ = registry(settings)
        result, _ = await tools.execute("search_kb", {"query": "ab"}, context)
        assert result.ok is False
        assert rag.calls == []

    async def test_no_results_suggests_escalating(
        self, settings: Settings, context: ToolContext
    ) -> None:
        tools, _, _ = registry(settings)
        result, _ = await tools.execute("search_kb", {"query": "an obscure query"}, context)
        assert result.ok
        assert "escalating" in result.payload["note"].lower()

    async def test_an_unreachable_rag_engine_is_reported_not_raised(
        self, settings: Settings, context: ToolContext
    ) -> None:
        """A dependency failure must degrade into an escalation, not a crash."""
        tools, _, _ = registry(settings, rag_error=UpstreamUnavailable("rag is down"))
        result, _ = await tools.execute("search_kb", {"query": "password reset"}, context)
        assert result.ok is False
        assert "rag is down" in result.payload["error"]


class TestResolveTicket:
    ANSWER = "Open the login page, choose Forgot password, and follow the emailed link."

    async def test_a_valid_answer_sets_the_decision(
        self, settings: Settings, context: ToolContext
    ) -> None:
        tools, _, _ = registry(settings)
        result, _ = await tools.execute(
            "resolve_ticket", {"answer": self.ANSWER, "confidence": 0.9}, context
        )
        assert result.terminal is True
        assert context.decision is not None
        assert context.decision.resolved is True
        assert context.decision.confidence == 0.9

    async def test_a_too_short_answer_is_rejected(
        self, settings: Settings, context: ToolContext
    ) -> None:
        tools, _, _ = registry(settings)
        result, _ = await tools.execute(
            "resolve_ticket", {"answer": "Done.", "confidence": 0.9}, context
        )
        assert result.ok is False
        assert result.terminal is False
        assert context.decision is None

    async def test_named_doc_ids_narrow_the_citations(
        self, settings: Settings, context: ToolContext, search_response: SearchResponse
    ) -> None:
        tools, _, _ = registry(settings, search_response)
        await tools.execute("search_kb", {"query": "password"}, context)
        await tools.execute(
            "resolve_ticket",
            {
                "answer": self.ANSWER,
                "confidence": 0.9,
                "doc_ids": ["account-password-reset"],
            },
            context,
        )
        assert [c.doc_id for c in context.citations] == ["account-password-reset"]

    async def test_unknown_doc_ids_leave_the_citations_alone(
        self, settings: Settings, context: ToolContext, search_response: SearchResponse
    ) -> None:
        tools, _, _ = registry(settings, search_response)
        await tools.execute("search_kb", {"query": "password"}, context)
        await tools.execute(
            "resolve_ticket",
            {"answer": self.ANSWER, "confidence": 0.9, "doc_ids": ["invented-id"]},
            context,
        )
        assert len(context.citations) == 2


class TestEscalate:
    async def test_escalating_records_the_reason(
        self, settings: Settings, context: ToolContext
    ) -> None:
        tools, _, _ = registry(settings)
        result, _ = await tools.execute(
            "escalate", {"reason": "policy_required", "summary": "Refund outside policy."}, context
        )
        assert result.terminal is True
        assert context.decision is not None
        assert context.decision.escalated is True
        assert context.decision.reason is EscalationReason.POLICY_REQUIRED

    async def test_a_holding_message_is_supplied_by_default(
        self, settings: Settings, context: ToolContext
    ) -> None:
        tools, _, _ = registry(settings)
        await tools.execute("escalate", {"reason": "no_kb_match", "summary": "n/a"}, context)
        assert context.decision is not None
        assert "support team" in context.decision.answer

    async def test_a_custom_customer_message_is_used(
        self, settings: Settings, context: ToolContext
    ) -> None:
        tools, _, _ = registry(settings)
        await tools.execute(
            "escalate",
            {
                "reason": "customer_requested",
                "summary": "wants a person",
                "customer_message": "Putting you through to a colleague now.",
            },
            context,
        )
        assert context.decision is not None
        assert context.decision.answer == "Putting you through to a colleague now."


class TestNotifyCustomer:
    async def test_a_message_is_sent_to_the_dispatcher(
        self, settings: Settings, context: ToolContext
    ) -> None:
        tools, _, dispatcher = registry(settings)
        result, _ = await tools.execute(
            "notify_customer", {"message": "Still looking into this for you."}, context
        )
        assert result.ok
        assert dispatcher.calls[0][0] == "/api/dispatch"
        assert context.notified is True

    async def test_a_second_notification_is_suppressed(
        self, settings: Settings, context: ToolContext
    ) -> None:
        tools, _, dispatcher = registry(settings)
        await tools.execute("notify_customer", {"message": "First update here."}, context)
        result, _ = await tools.execute("notify_customer", {"message": "Second update."}, context)
        assert result.ok is False
        assert len(dispatcher.calls) == 1

    async def test_a_short_message_is_rejected(
        self, settings: Settings, context: ToolContext
    ) -> None:
        tools, _, dispatcher = registry(settings)
        result, _ = await tools.execute("notify_customer", {"message": "ok"}, context)
        assert result.ok is False
        assert dispatcher.calls == []


class TestRegistry:
    async def test_an_unknown_tool_is_reported(
        self, settings: Settings, context: ToolContext
    ) -> None:
        tools, _, _ = registry(settings)
        result, _ = await tools.execute("delete_everything", {}, context)
        assert result.ok is False
        assert "unknown tool" in result.payload["error"]

    async def test_execution_time_is_measured(
        self, settings: Settings, context: ToolContext
    ) -> None:
        tools, _, _ = registry(settings)
        _, took = await tools.execute("search_kb", {"query": "a query"}, context)
        assert took >= 0


class TestConfidenceClamp:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (0.9, 0.9),
            (1.0, 1.0),
            (0.0, 0.0),
            (90, 0.9),          # percentage despite the schema
            (150, 1.0),         # nonsense, clamped
            (-0.5, 0.0),
            ("0.8", 0.8),       # string from a sloppy model
            (None, 0.5),        # default
            ("not a number", 0.5),
        ],
    )
    def test_values_are_coerced_into_range(self, raw: object, expected: float) -> None:
        assert _clamp(raw, default=0.5) == pytest.approx(expected)
