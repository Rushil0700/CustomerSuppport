"""Contract tests for the shared wire schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from support_common.enums import Channel, EscalationReason, TicketStatus
from support_common.schemas import (
    AgentResult,
    Citation,
    CustomerRef,
    FeedbackCreate,
    SearchRequest,
    SearchResponse,
    TicketCreate,
    new_ticket_id,
)


class TestTicketId:
    def test_generated_ids_are_unique_and_well_formed(self) -> None:
        ids = {new_ticket_id() for _ in range(500)}
        assert len(ids) == 500
        assert all(i.startswith("TKT-") for i in ids)

    def test_generated_ids_avoid_ambiguous_characters(self) -> None:
        """I, L, O and U are excluded so a ticket id can be read aloud."""
        joined = "".join(new_ticket_id()[4:] for _ in range(200))
        assert not set(joined) & set("ILOU")


class TestTicketCreate:
    def test_tags_are_deduplicated_lowercased_and_sorted(self) -> None:
        ticket = TicketCreate(
            subject="s",
            body="b",
            customer=CustomerRef(external_id="c1"),
            channel=Channel.API,
            tags=["Billing", "billing", " URGENT ", ""],
        )
        assert ticket.tags == ["billing", "urgent"]

    def test_search_text_joins_subject_and_body(self) -> None:
        ticket = TicketCreate(
            subject="Login broken",
            body="Cannot sign in",
            customer=CustomerRef(external_id="c1"),
            channel=Channel.API,
        )
        assert ticket.search_text == "Login broken\n\nCannot sign in"

    def test_unknown_fields_are_rejected(self) -> None:
        """Extra fields fail loudly rather than being silently dropped."""
        with pytest.raises(ValidationError):
            TicketCreate(
                subject="s",
                body="b",
                customer=CustomerRef(external_id="c1"),
                channel=Channel.API,
                surprise="field",
            )

    def test_empty_body_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TicketCreate(
                subject="s",
                body="",
                customer=CustomerRef(external_id="c1"),
                channel=Channel.API,
            )

    def test_invalid_email_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CustomerRef(external_id="c1", email="not-an-email")


class TestAgentResult:
    def test_escalation_requires_a_reason(self) -> None:
        with pytest.raises(ValidationError, match="escalation_reason"):
            AgentResult(
                ticket_id="TKT-ABCDEF123456",
                resolved=False,
                answer="handing over",
                confidence=0.1,
                escalated=True,
            )

    def test_cannot_be_both_resolved_and_escalated(self) -> None:
        with pytest.raises(ValidationError, match="both resolved and escalated"):
            AgentResult(
                ticket_id="TKT-ABCDEF123456",
                resolved=True,
                answer="done",
                confidence=0.9,
                escalated=True,
                escalation_reason=EscalationReason.LOW_CONFIDENCE,
            )

    def test_confidence_is_bounded(self) -> None:
        with pytest.raises(ValidationError):
            AgentResult(
                ticket_id="TKT-ABCDEF123456", resolved=True, answer="a", confidence=1.5
            )

    def test_valid_escalation_round_trips(self) -> None:
        result = AgentResult(
            ticket_id="TKT-ABCDEF123456",
            resolved=False,
            answer="A colleague will follow up.",
            confidence=0.0,
            escalated=True,
            escalation_reason=EscalationReason.NO_KB_MATCH,
        )
        assert AgentResult.model_validate(result.model_dump()) == result

    def test_malformed_ticket_id_is_rejected_on_requests(self) -> None:
        from support_common.schemas import AgentRequest

        with pytest.raises(ValidationError, match="malformed ticket id"):
            AgentRequest(
                ticket_id="not-a-ticket", subject="s", body="b", channel=Channel.API
            )


class TestSearchSchemas:
    def test_top_score_is_the_first_result(self, search_response: SearchResponse) -> None:
        assert search_response.top_score == 0.78

    def test_top_score_of_empty_results_is_zero(self) -> None:
        assert SearchResponse(query="q", results=[], took_ms=1.0).top_score == 0.0

    def test_query_has_a_minimum_length(self) -> None:
        with pytest.raises(ValidationError):
            SearchRequest(query="hi")

    def test_top_k_is_capped(self) -> None:
        with pytest.raises(ValidationError):
            SearchRequest(query="a real query", top_k=99)


class TestFeedback:
    @pytest.mark.parametrize("score", [0, 6, -1])
    def test_scores_outside_one_to_five_are_rejected(self, score: int) -> None:
        with pytest.raises(ValidationError):
            FeedbackCreate(ticket_id="TKT-ABCDEF123456", satisfaction_score=score)

    @pytest.mark.parametrize("score", [1, 3, 5])
    def test_valid_scores_are_accepted(self, score: int) -> None:
        assert FeedbackCreate(
            ticket_id="TKT-ABCDEF123456", satisfaction_score=score
        ).satisfaction_score == score


class TestEnums:
    @pytest.mark.parametrize(
        ("status", "terminal"),
        [
            (TicketStatus.NEW, False),
            (TicketStatus.PROCESSING, False),
            (TicketStatus.RESOLVED, True),
            (TicketStatus.ESCALATED, True),
            (TicketStatus.CLOSED, True),
            (TicketStatus.FAILED, False),
            (TicketStatus.REOPENED, False),
        ],
    )
    def test_terminal_statuses(self, status: TicketStatus, terminal: bool) -> None:
        assert status.is_terminal is terminal

    def test_citation_score_is_bounded(self) -> None:
        with pytest.raises(ValidationError):
            Citation(doc_id="d", title="t", source="s", score=2.0)
