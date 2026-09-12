#!/usr/bin/env python
"""Measure the agent against a labelled ticket set.

Runs tickets through the real agent, the real RAG engine and the real local
model, in-process, and reports the numbers the project is judged on:
auto-resolution rate, latency, cost per ticket, and - most importantly -
whether the agent's resolve/escalate decision agreed with the label.

    python scripts/evaluate.py                    # the whole set
    python scripts/evaluate.py --limit 5          # a quick smoke run
    python scripts/evaluate.py --json out.json    # machine-readable output

Requires Ollama running with the configured model, and an indexed knowledge base
(``python scripts/seed_kb.py``). Nothing is written to Postgres: the agent is
stateless, so this needs no database.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "agent"))
sys.path.insert(0, str(REPO_ROOT / "services" / "rag-engine"))

from support_common.config import get_settings  # noqa: E402
from support_common.enums import Channel  # noqa: E402
from support_common.logging import configure_logging  # noqa: E402
from support_common.schemas import (  # noqa: E402
    AgentRequest,
    AgentResult,
    SearchRequest,
    SearchResponse,
)

from agent_service.agent import SupportAgent  # noqa: E402
from agent_service.tools import ToolRegistry  # noqa: E402
from rag_engine.retriever import Retriever  # noqa: E402


@dataclass
class Case:
    """A labelled ticket. ``should_resolve=False`` means a human is required."""

    subject: str
    body: str
    channel: Channel
    should_resolve: bool
    expect_docs: list[str] = field(default_factory=list)
    note: str = ""


# Twenty cases: thirteen answerable from the knowledge base, seven that must
# reach a human. The mix is deliberately harder than real traffic - it has no
# duplicate questions, which is where caching and easy wins come from.
CASES: list[Case] = [
    Case("Forgot my password", "I can't log in. I forgot my password and the reset email never arrives, I checked spam.", Channel.EMAIL, True, ["account-password-reset"]),
    Case("Files stuck syncing", "Three files have been showing the syncing spinner for two hours. Everything else works.", Channel.SLACK, True, ["troubleshooting-sync-stuck"]),
    Case("Where is my invoice", "Our finance team needs a PDF invoice for last month for expenses. Where do I download it?", Channel.EMAIL, True, ["billing-invoice-copy"]),
    Case("Getting 429 from your API", "Our integration started returning 429 rate_limited this morning. What are the limits and how should we handle it?", Channel.API, True, ["api-error-429-rate_limited"]),
    Case("Slack integration broken", "Our Slack integration shows 'Needs attention' and no messages come through any more.", Channel.SLACK, True, ["integration-slack-troubleshoot"]),
    Case("How many seats on Team", "We're on the Team plan. How many seats does that include, and how are they counted?", Channel.WEB, True, ["plan-team", "billing-seat-count-team"]),
    Case("Invite email not received", "I invited a colleague three days ago and they say they never got the email.", Channel.EMAIL, True, ["account-invite-not-received"]),
    Case("How do I turn on 2FA", "Our security team wants two-factor authentication enabled for everyone. How do we do that?", Channel.WEB, True, ["account-enable-mfa"]),
    Case("Storage is full", "We're getting 'storage limit reached' and sync has paused for the whole team.", Channel.SLACK, True, ["troubleshooting-storage-full"]),
    Case("Share link not working", "I sent a share link to a client and they see 'not available'. It worked yesterday.", Channel.EMAIL, True, ["troubleshooting-share-link-not-working"]),
    Case("Payment failed", "Our card was declined and I got an email about it. What happens to our workspace now?", Channel.EMAIL, True, ["billing-failed-payment"]),
    Case("Which file types preview", "Can your app preview PSD files and ZIP archives, or only documents?", Channel.WEB, True, ["faq-supported-file-types"]),
    Case("How long is version history", "How far back can I restore an earlier version of a spreadsheet?", Channel.WEB, True, ["faq-version-history"]),
    # Must escalate.
    Case("Lost my 2FA device", "My phone was stolen and I don't have my recovery codes. I need access to my account immediately.", Channel.EMAIL, False, note="MFA reset requires identity verification"),
    Case("Refund for our annual plan", "We paid for a year back in March and want a full refund now. Please process it today.", Channel.EMAIL, False, note="outside the 30 day refund window"),
    Case("I think we've been hacked", "There are share links in our workspace that nobody recognises. Please help urgently.", Channel.SLACK, False, note="suspected compromise"),
    Case("Delete all my data", "Under GDPR I am requesting that you erase all of my personal data immediately.", Channel.EMAIL, False, note="erasure request"),
    Case("Speak to a person", "I don't want to talk to a bot. Please put me through to a real human being.", Channel.SLACK, False, note="customer asked for a human"),
    Case("Our lawyer will contact you", "We are considering legal action over last week's outage. Our lawyer will be in touch.", Channel.EMAIL, False, note="legal matter"),
    Case("Dispute this charge", "I'm filing a chargeback with my bank for the payment you took in error.", Channel.EMAIL, False, note="payment dispute"),
]


class LocalRetrieverClient:
    """Adapter letting the tool registry call the retriever in-process.

    Keeps the evaluation honest about retrieval quality while avoiding the need
    to have the RAG engine running as a separate service.
    """

    def __init__(self, retriever: Retriever) -> None:
        self.retriever = retriever

    async def post_json(self, _path: str, payload: dict) -> dict:
        request = SearchRequest.model_validate(payload)
        response: SearchResponse = await self.retriever.search(request)
        return response.model_dump(mode="json")

    async def aclose(self) -> None:
        return None

    async def healthy(self) -> bool:
        return True


class NullDispatcher:
    """Swallows interim notifications; nothing is sent during evaluation."""

    async def post_json(self, _path: str, _payload: dict) -> dict:
        return {"delivered": True, "dry_run": True}

    async def aclose(self) -> None:
        return None

    async def healthy(self) -> bool:
        return True


@dataclass
class Outcome:
    case: Case
    result: AgentResult
    correct: bool
    retrieval_hit: bool


async def evaluate(limit: int | None, verbose: bool) -> tuple[list[Outcome], dict]:
    settings = get_settings()
    configure_logging("evaluate", level="WARNING", fmt="console")

    retriever = Retriever(settings=settings)
    indexed = await retriever.vector_store.count()
    if indexed == 0:
        raise RuntimeError("the vector index is empty - run `python scripts/seed_kb.py` first")

    tools = ToolRegistry(
        settings=settings,
        rag_client=LocalRetrieverClient(retriever),  # type: ignore[arg-type]
        dispatcher_client=NullDispatcher(),  # type: ignore[arg-type]
    )
    agent = SupportAgent(tools=tools, settings=settings)

    if not await agent.llm.healthy():
        raise RuntimeError(
            f"model {settings.ollama_model!r} is not available - "
            f"run `ollama pull {settings.ollama_model}`"
        )

    cases = CASES[:limit] if limit else CASES
    print(
        f"Evaluating {len(cases)} tickets\n"
        f"  model:      {settings.ollama_model}\n"
        f"  index:      {indexed} chunks\n"
        f"  threshold:  {settings.agent_confidence_threshold}\n"
        f"  max turns:  {settings.agent_max_turns}\n"
    )

    outcomes: list[Outcome] = []
    started = time.perf_counter()

    for index, case in enumerate(cases, start=1):
        request = AgentRequest(
            # The ticket id alphabet excludes I, L, O and U, so "EVAL" is not a
            # legal prefix - "EVA" is.
            ticket_id=f"TKT-EVA{index:09d}",
            subject=case.subject,
            body=case.body,
            channel=case.channel,
        )
        result = await agent.handle(request)
        correct = result.resolved == case.should_resolve
        cited = {c.doc_id for c in result.citations}
        retrieval_hit = not case.expect_docs or bool(cited & set(case.expect_docs))

        outcomes.append(Outcome(case, result, correct, retrieval_hit))

        mark = "ok  " if correct else "MISS"
        decision = "resolved " if result.resolved else "escalated"
        print(
            f"  [{mark}] {index:2d}. {case.subject[:38]:38s} {decision} "
            f"conf={result.confidence:.2f} turns={result.turns_used} "
            f"{result.took_ms / 1000:5.1f}s"
        )
        if not correct or verbose:
            expected = "resolve" if case.should_resolve else "escalate"
            print(f"          expected {expected}" + (f" ({case.note})" if case.note else ""))
            if result.escalation_reason:
                print(f"          reason: {result.escalation_reason.value}")
            if verbose:
                print(f"          answer: {' '.join(result.answer.split())[:160]}")

    await agent.aclose()
    wall = time.perf_counter() - started
    return outcomes, summarise(outcomes, wall)


def summarise(outcomes: list[Outcome], wall_seconds: float) -> dict:
    total = len(outcomes)
    resolvable = [o for o in outcomes if o.case.should_resolve]
    must_escalate = [o for o in outcomes if not o.case.should_resolve]

    resolved = [o for o in outcomes if o.result.resolved]
    latencies = [o.result.took_ms / 1000 for o in outcomes]
    costs = [o.result.estimated_cost_usd for o in outcomes]

    return {
        "tickets": total,
        "auto_resolution_rate": round(len(resolved) / total, 4) if total else 0.0,
        "decision_accuracy": round(sum(o.correct for o in outcomes) / total, 4) if total else 0.0,
        # Recall on answerable tickets: of what it could have answered, how much did it?
        "recall_on_answerable": round(
            sum(o.result.resolved for o in resolvable) / len(resolvable), 4
        )
        if resolvable
        else None,
        # The safety number: an escalation-required ticket answered automatically
        # is the expensive kind of mistake.
        "false_resolution_rate": round(
            sum(o.result.resolved for o in must_escalate) / len(must_escalate), 4
        )
        if must_escalate
        else None,
        "retrieval_hit_rate": round(
            sum(o.retrieval_hit for o in resolvable) / len(resolvable), 4
        )
        if resolvable
        else None,
        "mean_confidence_when_resolved": round(
            statistics.mean([o.result.confidence for o in resolved]), 4
        )
        if resolved
        else None,
        "latency_seconds": {
            "mean": round(statistics.mean(latencies), 2) if latencies else 0.0,
            "median": round(statistics.median(latencies), 2) if latencies else 0.0,
            "max": round(max(latencies), 2) if latencies else 0.0,
        },
        "mean_turns": round(statistics.mean([o.result.turns_used for o in outcomes]), 2)
        if outcomes
        else 0.0,
        "cost_usd": {
            "mean": round(statistics.mean(costs), 5) if costs else 0.0,
            "max": round(max(costs), 5) if costs else 0.0,
        },
        "wall_seconds": round(wall_seconds, 1),
        "escalation_reasons": _count_reasons(outcomes),
    }


def _count_reasons(outcomes: list[Outcome]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for outcome in outcomes:
        if outcome.result.escalation_reason is not None:
            key = outcome.result.escalation_reason.value
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def report(summary: dict) -> None:
    latency, cost = summary["latency_seconds"], summary["cost_usd"]
    print(
        f"""
{'=' * 62}
  Auto-resolution rate      {summary['auto_resolution_rate']:.1%}   (target 60-65%)
  Decision accuracy         {summary['decision_accuracy']:.1%}
  Recall on answerable      {_pct(summary['recall_on_answerable'])}
  False-resolution rate     {_pct(summary['false_resolution_rate'])}   (lower is better)
  Retrieval hit rate        {_pct(summary['retrieval_hit_rate'])}
  Mean confidence           {_num(summary['mean_confidence_when_resolved'])}
  Latency  mean/median/max  {latency['mean']}s / {latency['median']}s / {latency['max']}s
  Mean turns                {summary['mean_turns']}
  Cost per ticket  mean/max ${cost['mean']:.4f} / ${cost['max']:.4f}   (target <= $0.08)
  Total wall time           {summary['wall_seconds']}s
{'=' * 62}"""
    )
    if summary["escalation_reasons"]:
        print("  Escalations by reason:")
        for reason, count in summary["escalation_reasons"].items():
            print(f"    {reason:24s} {count}")


def _pct(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "n/a"


def _num(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "n/a"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="evaluate only the first N cases")
    parser.add_argument("--json", type=Path, help="write the summary to this file")
    parser.add_argument("-v", "--verbose", action="store_true", help="print every answer")
    args = parser.parse_args()

    try:
        _, summary = asyncio.run(evaluate(args.limit, args.verbose))
    except (RuntimeError, KeyboardInterrupt) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    report(summary)
    if args.json:
        args.json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nSummary written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
