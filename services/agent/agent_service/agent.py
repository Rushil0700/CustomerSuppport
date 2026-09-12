"""The multi-turn support agent.

One ticket, up to ``AGENT_MAX_TURNS`` reasoning turns. Each turn the model either
calls a tool or produces text; the loop ends when the model calls a terminal
tool, the turn budget runs out, or a guard rail fires.

The invariant worth stating: every path out of :meth:`SupportAgent.handle`
produces an ``AgentResult``. A ticket is never dropped, and anything the agent
cannot confidently answer becomes an escalation rather than a failure.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from support_common.config import Settings, get_settings
from support_common.cost import estimate_ticket_cost
from support_common.enums import EscalationReason
from support_common.errors import LLMError, UpstreamUnavailable
from support_common.logging import bind_ticket_id, get_logger
from support_common.metrics import AGENT_TURNS, RESOLUTION_CONFIDENCE, TICKET_COST
from support_common.schemas import AgentRequest, AgentResult, ToolCallRecord

from agent_service.confidence import ConfidenceBreakdown, check_sensitive, score_confidence
from agent_service.ollama_client import ChatResponse, OllamaClient, ToolCall, extract_json
from agent_service.prompts import (
    JSON_FALLBACK_INSTRUCTION,
    SYSTEM_PROMPT,
    build_nudge,
    build_ticket_prompt,
)
from agent_service.tools import TERMINAL_TOOLS, Decision, ToolContext, ToolRegistry

log = get_logger(__name__)

HOLDING_MESSAGE = (
    "Thanks for reaching out. I've passed this to our support team so a person can "
    "take a proper look - they'll get back to you on this thread shortly."
)


class SupportAgent:
    """Runs the reason-act loop over a single ticket."""

    def __init__(
        self,
        llm: OllamaClient | None = None,
        tools: ToolRegistry | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm = llm or OllamaClient(self.settings)
        self.tools = tools or ToolRegistry(self.settings)
        # Bounds concurrent inference: a local GPU serving more requests than it
        # has capacity for degrades every one of them rather than queuing.
        self._semaphore = asyncio.Semaphore(self.settings.agent_max_concurrency)
        self._supports_native_tools: bool | None = None

    async def aclose(self) -> None:
        await self.llm.aclose()
        await self.tools.aclose()

    @property
    def native_tool_calling(self) -> bool | None:
        """Whether the model answered with native tool calls; None until probed."""
        return self._supports_native_tools

    async def handle(self, request: AgentRequest) -> AgentResult:
        """Work a ticket to a resolution or an escalation."""
        bind_ticket_id(request.ticket_id)
        started = time.perf_counter()
        max_turns = request.max_turns or self.settings.agent_max_turns

        context = ToolContext(
            ticket_id=request.ticket_id,
            channel=request.channel,
            subject=request.subject,
            body=request.body,
            customer_tier=request.customer_tier,
        )

        # Guard rail before any inference: some tickets must reach a human, and
        # there is no point spending a model call to discover that.
        if (forced := check_sensitive(request.subject, request.body)) is not None:
            log.info("agent.forced_escalation", reason=forced.value)
            return self._escalation_result(
                request, context, forced, started, turns=0, inference_seconds=0.0
            )

        async with self._semaphore:
            return await self._run_loop(request, context, max_turns, started)

    async def _run_loop(
        self,
        request: AgentRequest,
        context: ToolContext,
        max_turns: int,
        started: float,
    ) -> AgentResult:
        messages: list[dict[str, Any]] = [{"role": "system", "content": self._system_prompt()}]
        for turn in request.history:
            messages.append(
                {
                    "role": "assistant" if turn.role.value == "agent" else "user",
                    "content": turn.content,
                }
            )
        messages.append(
            {
                "role": "user",
                "content": build_ticket_prompt(
                    subject=request.subject,
                    body=request.body,
                    channel=request.channel,
                    priority=request.priority,
                    customer_tier=request.customer_tier,
                ),
            }
        )

        records: list[ToolCallRecord] = []
        inference_seconds = 0.0
        turns_used = 0

        for turn in range(1, max_turns + 1):
            turns_used = turn
            try:
                response = await self._chat(messages)
            except (LLMError, UpstreamUnavailable) as exc:
                log.error("agent.llm_failed", turn=turn, error=str(exc))
                return self._escalation_result(
                    request,
                    context,
                    EscalationReason.LLM_ERROR,
                    started,
                    turns=turn,
                    inference_seconds=inference_seconds,
                )
            inference_seconds += response.duration_seconds

            calls = response.tool_calls or self._parse_text_tool_call(response)
            if not calls:
                # The model answered in prose. Accept it as a final answer only
                # if it did the research first; otherwise push it back on track.
                if context.searches > 0 and len(response.content) >= 40:
                    context.decision = Decision(
                        resolved=True, answer=response.content, confidence=0.6
                    )
                    break
                messages.append({"role": "assistant", "content": response.content})
                messages.append(
                    {
                        "role": "user",
                        "content": build_nudge("no_search" if not context.searches else "no_tool"),
                    }
                )
                continue

            messages.append(_assistant_message(response, calls))

            terminal = False
            for call in calls:
                result, took = await self.tools.execute(call.name, call.arguments, context)
                records.append(
                    ToolCallRecord(
                        turn=turn,
                        tool=call.name,
                        arguments=_redact(call.arguments),
                        ok=result.ok,
                        result_summary=result.summary[:500],
                        took_ms=round(took * 1000, 2),
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "name": call.name,
                        "content": json.dumps(result.payload, default=str)[:12_000],
                    }
                )
                if result.terminal and result.ok:
                    terminal = True
            if terminal:
                break

        AGENT_TURNS.observe(turns_used)

        if context.decision is None:
            log.info("agent.turn_budget_exhausted", turns=turns_used)
            return self._escalation_result(
                request,
                context,
                EscalationReason.MAX_TURNS_EXCEEDED,
                started,
                turns=turns_used,
                inference_seconds=inference_seconds,
                tool_calls=records,
            )

        return self._finalise(
            request, context, records, started, turns_used, inference_seconds
        )

    def _finalise(
        self,
        request: AgentRequest,
        context: ToolContext,
        records: list[ToolCallRecord],
        started: float,
        turns_used: int,
        inference_seconds: float,
    ) -> AgentResult:
        """Apply the confidence gate and build the result."""
        decision = context.decision
        assert decision is not None  # noqa: S101 - guaranteed by the caller

        if decision.escalated:
            return self._escalation_result(
                request,
                context,
                decision.reason or EscalationReason.LOW_CONFIDENCE,
                started,
                turns=turns_used,
                inference_seconds=inference_seconds,
                tool_calls=records,
                answer=decision.answer,
            )

        breakdown = score_confidence(
            model_confidence=decision.confidence,
            citations=context.citations,
            answer=decision.answer,
            searches=context.searches,
        )
        log.info("agent.confidence", **breakdown.as_dict())

        if breakdown.final < self.settings.agent_confidence_threshold:
            log.info(
                "agent.escalating_low_confidence",
                score=round(breakdown.final, 3),
                threshold=self.settings.agent_confidence_threshold,
            )
            reason = (
                EscalationReason.NO_KB_MATCH
                if not context.citations
                else EscalationReason.LOW_CONFIDENCE
            )
            return self._escalation_result(
                request,
                context,
                reason,
                started,
                turns=turns_used,
                inference_seconds=inference_seconds,
                tool_calls=records,
                confidence=breakdown,
            )

        elapsed = time.perf_counter() - started
        cost = estimate_ticket_cost(
            inference_seconds, concurrency=self.settings.agent_max_concurrency
        )
        RESOLUTION_CONFIDENCE.observe(breakdown.final)
        TICKET_COST.observe(cost)

        return AgentResult(
            ticket_id=request.ticket_id,
            resolved=True,
            answer=decision.answer,
            confidence=round(breakdown.final, 4),
            escalated=False,
            escalation_reason=None,
            citations=context.citations[:5],
            tool_calls=records,
            turns_used=turns_used,
            model=self.llm.model,
            took_ms=round(elapsed * 1000, 2),
            estimated_cost_usd=cost,
        )

    def _escalation_result(
        self,
        request: AgentRequest,
        context: ToolContext,
        reason: EscalationReason,
        started: float,
        *,
        turns: int,
        inference_seconds: float,
        tool_calls: list[ToolCallRecord] | None = None,
        answer: str | None = None,
        confidence: ConfidenceBreakdown | None = None,
    ) -> AgentResult:
        """Build the escalation result, which is always a valid outcome."""
        elapsed = time.perf_counter() - started
        cost = estimate_ticket_cost(
            inference_seconds, concurrency=self.settings.agent_max_concurrency
        )
        TICKET_COST.observe(cost)
        return AgentResult(
            ticket_id=request.ticket_id,
            resolved=False,
            answer=answer or HOLDING_MESSAGE,
            confidence=round(confidence.final, 4) if confidence else 0.0,
            escalated=True,
            escalation_reason=reason,
            citations=context.citations[:5],
            tool_calls=tool_calls or [],
            turns_used=turns,
            model=self.llm.model,
            took_ms=round(elapsed * 1000, 2),
            estimated_cost_usd=cost,
        )

    # --- model plumbing -----------------------------------------------------

    def _system_prompt(self) -> str:
        """Append JSON instructions only when the model lacks native tools."""
        if self._supports_native_tools is False:
            return f"{SYSTEM_PROMPT}\n\n{JSON_FALLBACK_INSTRUCTION}"
        return SYSTEM_PROMPT

    async def _chat(self, messages: list[dict[str, Any]]) -> ChatResponse:
        """One model call, with native tools unless we know they are unsupported."""
        if self._supports_native_tools is False:
            return await self.llm.chat(messages, json_mode=True)

        response = await self.llm.chat(messages, tools=self.tools.schemas)
        if self._supports_native_tools is None:
            # First call decides: a model that returns a tool call natively is
            # trusted from then on; one that returns only prose falls back.
            self._supports_native_tools = bool(response.tool_calls)
            if not response.tool_calls:
                log.info("agent.native_tools_unsupported", model=self.llm.model)
        return response

    @staticmethod
    def _parse_text_tool_call(response: ChatResponse) -> list[ToolCall]:
        """Recover a tool call from a JSON object embedded in text."""
        payload = extract_json(response.content)
        if not payload:
            return []
        name = payload.get("tool") or payload.get("name") or payload.get("function")
        if not isinstance(name, str):
            return []
        arguments = payload.get("arguments") or payload.get("parameters") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        # Some models inline the arguments at the top level instead of nesting.
        if not arguments:
            arguments = {k: v for k, v in payload.items() if k not in {"tool", "name", "function"}}
        return [ToolCall(name=name, arguments=arguments)]


def _assistant_message(response: ChatResponse, calls: list[ToolCall]) -> dict[str, Any]:
    """Echo the assistant turn back into the transcript in Ollama's format."""
    return {
        "role": "assistant",
        "content": response.content,
        "tool_calls": [
            {"function": {"name": call.name, "arguments": call.arguments}} for call in calls
        ],
    }


def _redact(arguments: dict[str, Any]) -> dict[str, Any]:
    """Truncate long tool arguments before they are persisted as an audit record."""
    return {
        key: (value[:1000] + "..." if isinstance(value, str) and len(value) > 1000 else value)
        for key, value in arguments.items()
    }


__all__ = ["SupportAgent", "TERMINAL_TOOLS"]
