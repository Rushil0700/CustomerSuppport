"""Tests for confidence scoring and the escalation guard rails.

These are the tests that matter most for the auto-resolution target: the gate
decides which tickets a customer sees an automated answer to.
"""

from __future__ import annotations

import pytest
from agent_service.confidence import check_sensitive, score_confidence
from support_common.enums import EscalationReason
from support_common.schemas import Citation

GOOD_ANSWER = (
    "To reset your password, go to the login page and choose Forgot password. "
    "Enter the email address on your account and open the reset link, which is "
    "valid for 60 minutes. If you signed up with Google or Microsoft SSO there is "
    "no password to reset - use Continue with Google instead."
)


class TestSensitiveTopics:
    @pytest.mark.parametrize(
        ("text", "reason"),
        [
            ("I want to speak to a human please", EscalationReason.CUSTOMER_REQUESTED),
            ("Can I talk to a real person?", EscalationReason.CUSTOMER_REQUESTED),
            ("I think our account was hacked", EscalationReason.SENSITIVE_TOPIC),
            ("There was unauthorized access last night", EscalationReason.SENSITIVE_TOPIC),
            ("I lost my recovery codes and my authenticator", EscalationReason.POLICY_REQUIRED),
            ("Please erase all my data under GDPR", EscalationReason.POLICY_REQUIRED),
            ("Our lawyer will be in touch", EscalationReason.POLICY_REQUIRED),
            ("I am filing a chargeback", EscalationReason.POLICY_REQUIRED),
            ("We want to terminate our contract", EscalationReason.POLICY_REQUIRED),
        ],
    )
    def test_sensitive_text_forces_escalation(self, text: str, reason: EscalationReason) -> None:
        assert check_sensitive("", text) is reason

    @pytest.mark.parametrize(
        "text",
        [
            "How do I reset my password?",
            "My files are stuck syncing",
            "Where do I download an invoice?",
            "What file types can I upload?",
        ],
    )
    def test_ordinary_tickets_are_not_flagged(self, text: str) -> None:
        assert check_sensitive("", text) is None

    def test_the_subject_is_searched_too(self) -> None:
        assert check_sensitive("Account compromised", "please advise") is not None

    def test_matching_is_case_insensitive(self) -> None:
        assert check_sensitive("", "PLEASE LET ME SPEAK TO A HUMAN") is not None


class TestConfidenceScoring:
    def test_strong_evidence_scores_above_the_threshold(
        self, strong_citations: list[Citation]
    ) -> None:
        result = score_confidence(
            model_confidence=0.9,
            citations=strong_citations,
            answer=GOOD_ANSWER,
            searches=1,
        )
        assert result.final >= 0.70
        assert result.penalties == []

    def test_no_search_collapses_the_score(self, strong_citations: list[Citation]) -> None:
        """A confident answer with no retrieval behind it is a hallucination."""
        result = score_confidence(
            model_confidence=1.0, citations=strong_citations, answer=GOOD_ANSWER, searches=0
        )
        assert result.final < 0.30
        assert "no_search" in result.penalties

    def test_no_citations_collapses_the_score(self) -> None:
        result = score_confidence(
            model_confidence=1.0, citations=[], answer=GOOD_ANSWER, searches=1
        )
        assert result.final < 0.30
        assert "no_citations" in result.penalties

    def test_weak_retrieval_is_penalised(self) -> None:
        weak = [Citation(doc_id="d", title="Something unrelated", source="s", score=0.12)]
        result = score_confidence(
            model_confidence=0.95, citations=weak, answer=GOOD_ANSWER, searches=1
        )
        assert "weak_retrieval" in result.penalties
        assert result.final < 0.70

    def test_hedging_language_is_penalised(self, strong_citations: list[Citation]) -> None:
        hedged = "I think you might be able to reset it, but I'm not certain how that works here."
        result = score_confidence(
            model_confidence=0.9, citations=strong_citations, answer=hedged, searches=1
        )
        assert "hedging_language" in result.penalties

    def test_an_answer_that_asks_a_question_is_penalised(
        self, strong_citations: list[Citation]
    ) -> None:
        """resolve_ticket ends the conversation, so a question never gets answered."""
        asking = (
            "I can help with that once I know a little more about your setup. "
            "Which email address did you use when you signed up?"
        )
        result = score_confidence(
            model_confidence=0.9, citations=strong_citations, answer=asking, searches=1
        )
        assert "answer_asks_a_question" in result.penalties
        assert result.final < 0.70

    def test_a_very_short_answer_is_penalised(self, strong_citations: list[Citation]) -> None:
        result = score_confidence(
            model_confidence=0.9, citations=strong_citations, answer="Reset it.", searches=1
        )
        assert "answer_too_short" in result.penalties

    def test_the_score_is_always_within_bounds(self, strong_citations: list[Citation]) -> None:
        for model_confidence in (0.0, 0.5, 1.0):
            result = score_confidence(
                model_confidence=model_confidence,
                citations=strong_citations,
                answer=GOOD_ANSWER,
                searches=1,
            )
            assert 0.0 <= result.final <= 1.0

    def test_model_overconfidence_alone_cannot_pass_the_gate(self) -> None:
        """The whole point: a 1.0 claim with nothing behind it still escalates."""
        result = score_confidence(
            model_confidence=1.0,
            citations=[],
            answer="Just restart the app and it will be fine.",
            searches=0,
        )
        assert result.final < 0.70

    def test_breakdown_is_serialisable(self, strong_citations: list[Citation]) -> None:
        result = score_confidence(
            model_confidence=0.8, citations=strong_citations, answer=GOOD_ANSWER, searches=1
        )
        payload = result.as_dict()
        assert set(payload) == {
            "model_confidence",
            "retrieval_score",
            "citation_score",
            "grounding_score",
            "final",
            "penalties",
        }

    def test_grounding_rewards_reusing_article_vocabulary(self) -> None:
        citations = [
            Citation(doc_id="d", title="Reset a forgotten password", source="s", score=0.7)
        ]
        grounded = score_confidence(
            model_confidence=0.8,
            citations=citations,
            answer=GOOD_ANSWER,
            searches=1,
        )
        ungrounded = score_confidence(
            model_confidence=0.8,
            citations=citations,
            answer=(
                "Please turn the device off and on again, then wait a while before "
                "trying whatever it was you were doing once more."
            ),
            searches=1,
        )
        assert grounded.grounding_score > ungrounded.grounding_score
