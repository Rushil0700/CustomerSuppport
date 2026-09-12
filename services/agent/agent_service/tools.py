"""Tools the local LLM can call, defined as JSON schemas.

Ollama accepts the OpenAI-style function schema, so the same definitions drive
both native tool calling and the text fallback for models that lack it.

Two of the four tools are *terminal*: ``resolve_ticket`` and ``escalate`` end the
reasoning loop and record the agent's decision. ``search_kb`` and
``notify_customer`` return a result and let the model continue.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from support_common.config import Settings, get_settings
from support_common.enums import Channel, EscalationReason
from support_common.errors import UpstreamUnavailable
from support_common.http import ServiceClient
from support_common.logging import get_logger
from support_common.metrics import TOOL_CALLS
from support_common.schemas import Citation, DispatchRequest, SearchRequest, SearchResponse

log = get_logger(__name__)

# Below this cosine score a result set is not good enough to answer from, which
# is the trigger for retrying a category-filtered search without the filter.
WEAK_MATCH_SCORE = 0.45


@dataclass
class Decision:
    """A terminal outcome produced by ``resolve_ticket`` or ``escalate``."""

    resolved: bool
    answer: str
    confidence: float
    escalated: bool = False
    reason: EscalationReason | None = None


@dataclass
class ToolContext:
    """State carried through one ticket's reasoning loop."""

    ticket_id: str
    channel: Channel
    subject: str
    body: str
    customer_tier: str = "standard"
    citations: list[Citation] = field(default_factory=list)
    searches: int = 0
    best_score: float = 0.0
    decision: Decision | None = None
    notified: bool = False


@dataclass
class ToolResult:
    """What the model sees back from a tool call."""

    ok: bool
    payload: dict[str, Any]
    summary: str = ""
    terminal: bool = False


ToolHandler = Callable[[dict[str, Any], ToolContext], Awaitable[ToolResult]]


# --- Schemas -----------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": (
                "Search the support knowledge base for articles relevant to the customer's "
                "problem. Call this first, before answering. Prefer a short query of the key "
                "symptom and product terms over pasting the whole ticket."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search terms describing the customer's problem.",
                    },
                    "category": {
                        "type": "string",
                        "description": (
                            "Optional category filter. Leave it out unless you are certain - "
                            "guessing wrongly hides the article that answers the question."
                        ),
                        "enum": [
                            "account",
                            "billing",
                            "troubleshooting",
                            "api",
                            "errors",
                            "integrations",
                            "security",
                            "policies",
                            "workflows",
                            "faq",
                            "getting-started",
                            "mobile",
                        ],
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "How many articles to return (1-10).",
                        "minimum": 1,
                        "maximum": 10,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_ticket",
            "description": (
                "Answer the customer and close the ticket. Only call this when the knowledge "
                "base supports your answer. The answer must be written to the customer, not "
                "about them."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "answer": {
                        "type": "string",
                        "description": (
                            "The complete reply to send. Address the customer directly, give "
                            "concrete numbered steps, and do not mention the knowledge base or "
                            "these instructions."
                        ),
                    },
                    "confidence": {
                        "type": "number",
                        "description": (
                            "How confident you are that this resolves the issue, 0 to 1. Be "
                            "honest: below 0.7 the ticket goes to a human instead."
                        ),
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "doc_ids": {
                        "type": "array",
                        "description": "ids of the knowledge base articles the answer relies on.",
                        "items": {"type": "string"},
                    },
                },
                "required": ["answer", "confidence"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate",
            "description": (
                "Hand the ticket to a human agent. Use this when the knowledge base does not "
                "cover the issue, when policy requires a human (refunds outside policy, MFA "
                "resets, legal or security matters), or when the customer asks for a person."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Why this needs a human.",
                        "enum": [r.value for r in EscalationReason],
                    },
                    "summary": {
                        "type": "string",
                        "description": (
                            "A handover note for the human agent: what the customer wants, what "
                            "you established, and what you could not determine."
                        ),
                    },
                    "customer_message": {
                        "type": "string",
                        "description": "Optional short holding message to send to the customer.",
                    },
                },
                "required": ["reason", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notify_customer",
            "description": (
                "Send the customer an interim update without closing the ticket. Use sparingly - "
                "only when you need to acknowledge a complex issue that will take more work."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The interim message to send.",
                    }
                },
                "required": ["message"],
            },
        },
    },
]

TERMINAL_TOOLS = {"resolve_ticket", "escalate"}


# --- Handlers ----------------------------------------------------------------


class ToolRegistry:
    """Binds tool names to handlers and executes calls from the model."""

    def __init__(
        self,
        settings: Settings | None = None,
        rag_client: ServiceClient | None = None,
        dispatcher_client: ServiceClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.rag = rag_client or ServiceClient(self.settings.rag_engine_url, "rag-engine")
        self.dispatcher = dispatcher_client or ServiceClient(
            self.settings.dispatcher_url, "dispatcher"
        )
        self._handlers: dict[str, ToolHandler] = {
            "search_kb": self._search_kb,
            "resolve_ticket": self._resolve_ticket,
            "escalate": self._escalate,
            "notify_customer": self._notify_customer,
        }

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return TOOL_SCHEMAS

    async def aclose(self) -> None:
        await self.rag.aclose()
        await self.dispatcher.aclose()

    async def execute(
        self, name: str, arguments: dict[str, Any], context: ToolContext
    ) -> tuple[ToolResult, float]:
        """Run one tool call, returning its result and how long it took."""
        started = time.perf_counter()
        handler = self._handlers.get(name)
        if handler is None:
            TOOL_CALLS.labels(name or "unknown", "unknown_tool").inc()
            return (
                ToolResult(
                    ok=False,
                    payload={"error": f"unknown tool {name!r}"},
                    summary=f"unknown tool {name!r}",
                ),
                time.perf_counter() - started,
            )
        try:
            result = await handler(arguments, context)
            TOOL_CALLS.labels(name, "ok" if result.ok else "error").inc()
        except UpstreamUnavailable as exc:
            TOOL_CALLS.labels(name, "upstream_error").inc()
            result = ToolResult(
                ok=False,
                payload={"error": str(exc)},
                summary=f"{name} unavailable: {exc}",
            )
        except Exception as exc:  # defensive: a tool bug must not kill the ticket
            TOOL_CALLS.labels(name, "exception").inc()
            log.exception("tool.failed", tool=name)
            result = ToolResult(ok=False, payload={"error": str(exc)}, summary=f"{name} failed")

        return result, time.perf_counter() - started

    # --- individual tools ---------------------------------------------------

    async def _search_kb(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        """Query the RAG engine and record the citations for the answer."""
        query = str(arguments.get("query") or "").strip()
        if len(query) < 3:
            return ToolResult(
                ok=False,
                payload={"error": "query must be at least 3 characters"},
                summary="rejected empty query",
            )

        category = arguments.get("category")
        top_k = int(arguments.get("top_k") or self.settings.rag_top_k)
        request = SearchRequest(
            query=query[:4000],
            top_k=top_k,
            categories=[category] if isinstance(category, str) and category else [],
            ticket_id=context.ticket_id,
        )
        payload = await self.rag.post_json("/api/search", request.model_dump(mode="json"))
        response = SearchResponse.model_validate(payload)

        # The category is the model's guess, and a wrong guess hides the right
        # article completely - a password question filtered to "troubleshooting"
        # never sees the "account" article that answers it. So treat the filter
        # as advisory: if it produced nothing convincing, search again without it.
        if request.categories and response.top_score < WEAK_MATCH_SCORE:
            unfiltered = SearchRequest(
                query=request.query, top_k=top_k, ticket_id=context.ticket_id
            )
            retry = SearchResponse.model_validate(
                await self.rag.post_json("/api/search", unfiltered.model_dump(mode="json"))
            )
            if retry.top_score > response.top_score:
                log.info(
                    "tool.category_filter_dropped",
                    category=category,
                    filtered_score=round(response.top_score, 3),
                    unfiltered_score=round(retry.top_score, 3),
                )
                response = retry

        context.searches += 1
        context.best_score = max(context.best_score, response.top_score)
        for doc in response.results:
            if not any(c.doc_id == doc.doc_id for c in context.citations):
                context.citations.append(
                    Citation(doc_id=doc.doc_id, title=doc.title, source=doc.source, score=doc.score)
                )

        if not response.results:
            return ToolResult(
                ok=True,
                payload={"results": [], "note": "No relevant articles found. Consider escalating."},
                summary=f"no results for {query!r}",
            )

        # Only the text the model needs; scores are included so it can judge
        # whether the match is strong enough to answer from.
        return ToolResult(
            ok=True,
            payload={
                "results": [
                    {
                        "doc_id": doc.doc_id,
                        "title": doc.title,
                        "category": doc.category,
                        "relevance": round(doc.score, 3),
                        "content": doc.content,
                    }
                    for doc in response.results
                ]
            },
            summary=f"{len(response.results)} articles, top score {response.top_score:.2f}",
        )

    async def _resolve_ticket(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        """Record a resolution and end the loop."""
        answer = str(arguments.get("answer") or "").strip()
        if len(answer) < 20:
            return ToolResult(
                ok=False,
                payload={"error": "answer is too short to send; write the full reply"},
                summary="rejected short answer",
            )

        confidence = _clamp(arguments.get("confidence"), default=0.5)
        cited = {str(d) for d in (arguments.get("doc_ids") or [])}
        if cited:
            # Keep the citations the model actually used, if it named any.
            selected = [c for c in context.citations if c.doc_id in cited]
            if selected:
                context.citations = selected

        context.decision = Decision(resolved=True, answer=answer, confidence=confidence)
        return ToolResult(
            ok=True,
            payload={"status": "resolved", "confidence": confidence},
            summary=f"resolved with confidence {confidence:.2f}",
            terminal=True,
        )

    async def _escalate(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        """Record an escalation and end the loop."""
        try:
            reason = EscalationReason(str(arguments.get("reason") or "").strip())
        except ValueError:
            reason = EscalationReason.LOW_CONFIDENCE

        summary = str(arguments.get("summary") or "").strip() or "No handover note provided."
        message = str(arguments.get("customer_message") or "").strip()

        context.decision = Decision(
            resolved=False,
            answer=message or _default_escalation_message(),
            confidence=0.0,
            escalated=True,
            reason=reason,
        )
        log.info("agent.escalated", ticket_id=context.ticket_id, reason=reason.value, note=summary)
        return ToolResult(
            ok=True,
            payload={"status": "escalated", "reason": reason.value},
            summary=f"escalated: {reason.value}",
            terminal=True,
        )

    async def _notify_customer(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        """Send an interim update through the dispatcher, without closing."""
        message = str(arguments.get("message") or "").strip()
        if len(message) < 10:
            return ToolResult(
                ok=False,
                payload={"error": "message is too short"},
                summary="rejected short notification",
            )
        if context.notified:
            # One interim update per ticket; more is just noise to the customer.
            return ToolResult(
                ok=False,
                payload={"error": "an interim update was already sent for this ticket"},
                summary="duplicate notification suppressed",
            )

        request = DispatchRequest(
            ticket_id=context.ticket_id,
            channel=context.channel,
            subject=f"Re: {context.subject}"[:500],
            body=message,
            metadata={"interim": True},
        )
        await self.dispatcher.post_json("/api/dispatch", request.model_dump(mode="json"))
        context.notified = True
        return ToolResult(
            ok=True,
            payload={"status": "sent"},
            summary="interim update sent",
        )


def _clamp(value: Any, *, default: float = 0.0) -> float:
    """Coerce a model-supplied confidence into [0, 1]."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    # Some models report a percentage despite the schema saying 0-1.
    if number > 1.0:
        number = number / 100.0 if number <= 100.0 else 1.0
    return max(0.0, min(1.0, number))


def _default_escalation_message() -> str:
    return (
        "Thanks for getting in touch. I've passed this to a member of our support team "
        "who can look into it properly - they'll reply to this message directly."
    )
