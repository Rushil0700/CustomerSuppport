"""Confidence scoring and the escalation gate.

A local 7B model's self-reported confidence is optimistic and poorly calibrated,
so it is never trusted on its own. The final score combines what the model
claimed with evidence we can measure - how strong the retrieval was, how many
distinct articles were cited, whether the answer looks grounded - and a set of
hard rules that force escalation regardless of any score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from support_common.enums import EscalationReason
from support_common.schemas import Citation

# Phrases that mean the ticket must reach a human whatever the model decides.
# Matched against the customer's own words, before any inference runs, so a
# clearly sensitive ticket never costs a model call.
SENSITIVE_PATTERNS: list[tuple[re.Pattern[str], EscalationReason]] = [
    (
        re.compile(r"\b(lawyer|attorney|legal action|sue|lawsuit|court|subpoena)\b", re.I),
        EscalationReason.POLICY_REQUIRED,
    ),
    (
        re.compile(r"\b(gdpr|ccpa|right to (be forgotten|erasure)|erase (all )?my data)\b", re.I),
        EscalationReason.POLICY_REQUIRED,
    ),
    (
        re.compile(
            r"\b(hacked|compromised|breach|unauthori[sz]ed access|stolen account|phish)\w*\b", re.I
        ),
        EscalationReason.SENSITIVE_TOPIC,
    ),
    (
        re.compile(
            r"\b(lost|don'?t have|no).{0,25}\b(recovery cod|2fa|mfa|authenticator)\w*\b", re.I
        ),
        EscalationReason.POLICY_REQUIRED,
    ),
    (
        re.compile(r"\b(chargeback|dispute the charge|fraud(ulent)? charge)\b", re.I),
        EscalationReason.POLICY_REQUIRED,
    ),
    (
        re.compile(
            r"\b(speak|talk) to (a|an|someone|a real) ?(human|person|agent|manager)\b", re.I
        ),
        EscalationReason.CUSTOMER_REQUESTED,
    ),
    (
        re.compile(
            r"\b(cancel my (contract|account)|terminate (our|the) (contract|agreement))\b", re.I
        ),
        EscalationReason.POLICY_REQUIRED,
    ),
]

# Hedging language: when the answer itself is unsure, the score should be too.
HEDGE_RE = re.compile(
    r"\b(i think|probably|might be|may be|not sure|i believe|it seems|possibly|"
    r"i'?m not certain|cannot confirm|unclear)\b",
    re.I,
)
# An answer that asks a question cannot resolve a ticket - there is no follow-up.
QUESTION_RE = re.compile(r"\?\s*$|\?\s*\n")

# A citation at or above this score counts as genuine supporting evidence.
STRONG_MATCH_SCORE = 0.40
# Below this the retrieval is too weak to answer from at all.
NOISE_SCORE = 0.28


@dataclass
class ConfidenceBreakdown:
    """Why the final score came out where it did - logged for calibration."""

    model_confidence: float
    retrieval_score: float
    citation_score: float
    grounding_score: float
    final: float
    penalties: list[str]

    def as_dict(self) -> dict[str, float | list[str]]:
        return {
            "model_confidence": round(self.model_confidence, 3),
            "retrieval_score": round(self.retrieval_score, 3),
            "citation_score": round(self.citation_score, 3),
            "grounding_score": round(self.grounding_score, 3),
            "final": round(self.final, 3),
            "penalties": self.penalties,
        }


def check_sensitive(subject: str, body: str) -> EscalationReason | None:
    """Return a forced escalation reason if the ticket text demands a human."""
    text = f"{subject}\n{body}"
    for pattern, reason in SENSITIVE_PATTERNS:
        if pattern.search(text):
            return reason
    return None


def score_confidence(
    *,
    model_confidence: float,
    citations: list[Citation],
    answer: str,
    searches: int,
) -> ConfidenceBreakdown:
    """Blend the model's claim with measurable evidence.

    Weights: 40% the model's own number, 35% retrieval strength, 15% breadth of
    supporting articles, 10% surface grounding of the answer. Penalties then
    apply multiplicatively, because a single disqualifying signal - an ungrounded
    answer, a question, no search at all - should dominate rather than average out.
    """
    penalties: list[str] = []

    top_score = max((c.score for c in citations), default=0.0)
    # Calibrated against the real corpus with all-MiniLM-L6-v2: an on-topic
    # question scores 0.55-0.85 against its own article, and anything under
    # ~0.25 is noise. Mapping [0.25, 0.65] onto [0, 1] puts a genuine match near
    # the top of the range; the earlier [0.30, 0.80] scale was tuned for
    # similarity numbers this embedding model does not actually produce, and it
    # escalated tickets the knowledge base answered perfectly well.
    retrieval_score = _rescale(top_score, low=0.25, high=0.65)

    strong = [c for c in citations if c.score >= STRONG_MATCH_SCORE]
    citation_score = min(1.0, len(strong) / 3.0)

    grounding_score = _grounding(answer, citations)

    final = (
        0.40 * model_confidence
        + 0.35 * retrieval_score
        + 0.15 * citation_score
        + 0.10 * grounding_score
    )

    if searches == 0:
        final *= 0.25
        penalties.append("no_search")
    if not citations:
        final *= 0.30
        penalties.append("no_citations")
    if top_score < NOISE_SCORE:
        final *= 0.55
        penalties.append("weak_retrieval")
    if HEDGE_RE.search(answer):
        final *= 0.75
        penalties.append("hedging_language")
    if QUESTION_RE.search(answer.strip()):
        final *= 0.60
        penalties.append("answer_asks_a_question")
    if len(answer.split()) < 25:
        final *= 0.80
        penalties.append("answer_too_short")

    return ConfidenceBreakdown(
        model_confidence=model_confidence,
        retrieval_score=retrieval_score,
        citation_score=citation_score,
        grounding_score=grounding_score,
        final=max(0.0, min(1.0, final)),
        penalties=penalties,
    )


def _rescale(value: float, *, low: float, high: float) -> float:
    """Map ``value`` from [low, high] onto [0, 1], clamped."""
    if high <= low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _grounding(answer: str, citations: list[Citation]) -> float:
    """Rough check that the answer reuses vocabulary from the cited articles.

    Not a fact check - it catches the common failure where the model ignores
    retrieval entirely and writes a generic, plausible-sounding reply.
    """
    if not citations or not answer.strip():
        return 0.0

    answer_terms = _significant_terms(answer)
    if not answer_terms:
        return 0.0
    title_terms: set[str] = set()
    for citation in citations:
        title_terms |= _significant_terms(citation.title)
    if not title_terms:
        return 0.0

    overlap = len(answer_terms & title_terms) / len(title_terms)
    return min(1.0, overlap * 2.0)


_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "if",
    "then",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "your",
    "you",
    "we",
    "it",
    "is",
    "are",
    "be",
    "can",
    "will",
    "this",
    "that",
    "from",
    "at",
    "by",
    "as",
    "not",
    "do",
    "does",
    "how",
    "what",
    "when",
    "why",
    "please",
    "have",
    "has",
}


def _significant_terms(text: str) -> set[str]:
    """Lowercase content words of four characters or more."""
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", text.lower())
    return {w for w in words if w not in _STOPWORDS}
