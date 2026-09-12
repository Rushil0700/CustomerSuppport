"""Async client for the local Ollama daemon.

Ollama exposes native tool calling on ``/api/chat`` for models trained for it
(qwen3, llama3.1, mistral-nemo and others). Models without that training simply
ignore the ``tools`` field, so the client detects an empty tool-call list and
falls back to parsing a JSON object out of the text response. That fallback is
what lets the same agent code run on whatever model the operator has pulled.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from support_common.config import Settings, get_settings
from support_common.errors import LLMError, UpstreamUnavailable
from support_common.logging import get_logger
from support_common.metrics import LLM_CALLS, LLM_LATENCY, LLM_TOKENS

log = get_logger(__name__)

# Matches a fenced ```json block or the first balanced top-level object.
JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
# Models with visible reasoning wrap it in <think> tags that must not reach the customer.
THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


@dataclass
class ToolCall:
    """A tool invocation requested by the model."""

    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResponse:
    """One completion from the model."""

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_seconds: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class OllamaClient:
    """Talks to ``http://localhost:11434`` (or wherever Ollama is running)."""

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self.model = self.settings.ollama_model
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self.settings.ollama_host.rstrip("/"),
            timeout=httpx.Timeout(self.settings.ollama_timeout_seconds, connect=10.0),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
    ) -> ChatResponse:
        """Send a chat completion request and normalise the response.

        ``json_mode`` asks Ollama to constrain output to valid JSON, which is
        how the final structured answer is extracted reliably.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": self.settings.ollama_keep_alive,
            "options": {
                "temperature": (
                    temperature if temperature is not None else self.settings.ollama_temperature
                ),
                "num_ctx": self.settings.ollama_num_ctx,
            },
        }
        if tools:
            payload["tools"] = tools
        if json_mode:
            payload["format"] = "json"

        started = time.perf_counter()
        try:
            response = await self._client.post("/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            LLM_CALLS.labels(self.model, "timeout").inc()
            raise LLMError(f"ollama timed out after {self.settings.ollama_timeout_seconds}s") from exc
        except httpx.HTTPError as exc:
            LLM_CALLS.labels(self.model, "transport_error").inc()
            raise UpstreamUnavailable(f"cannot reach ollama at {self.settings.ollama_host}: {exc}") from exc

        elapsed = time.perf_counter() - started
        if response.status_code == 404:
            LLM_CALLS.labels(self.model, "model_missing").inc()
            raise LLMError(
                f"model {self.model!r} is not available - run `ollama pull {self.model}`"
            )
        if response.status_code >= 400:
            LLM_CALLS.labels(self.model, "http_error").inc()
            raise LLMError(f"ollama returned {response.status_code}: {response.text[:500]}")

        body = response.json()
        message = body.get("message") or {}
        content = strip_reasoning(message.get("content") or "")

        tool_calls = [
            ToolCall(
                name=call["function"]["name"],
                arguments=_coerce_arguments(call["function"].get("arguments")),
            )
            for call in (message.get("tool_calls") or [])
            if call.get("function", {}).get("name")
        ]

        prompt_tokens = int(body.get("prompt_eval_count") or 0)
        completion_tokens = int(body.get("eval_count") or 0)

        LLM_CALLS.labels(self.model, "ok").inc()
        LLM_LATENCY.labels(self.model).observe(elapsed)
        LLM_TOKENS.labels(self.model, "prompt").inc(prompt_tokens)
        LLM_TOKENS.labels(self.model, "completion").inc(completion_tokens)
        log.info(
            "llm.chat",
            model=self.model,
            duration_ms=round(elapsed * 1000, 2),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            tool_calls=[t.name for t in tool_calls],
        )

        return ChatResponse(
            content=content,
            tool_calls=tool_calls,
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_seconds=elapsed,
            raw=body,
        )

    async def available_models(self) -> list[str]:
        """Names of the models Ollama currently has pulled."""
        try:
            response = await self._client.get("/api/tags", timeout=5.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable(f"cannot list ollama models: {exc}") from exc
        return [m["name"] for m in response.json().get("models", [])]

    async def healthy(self) -> bool:
        """True when the daemon responds and the configured model is present."""
        try:
            models = await self.available_models()
        except Exception:
            return False
        # Ollama reports "qwen3:8b"; a config of "qwen3" should still match.
        return any(m == self.model or m.split(":")[0] == self.model.split(":")[0] for m in models)


def strip_reasoning(text: str) -> str:
    """Remove ``<think>`` blocks that reasoning models emit before the answer."""
    return THINK_RE.sub("", text).strip()


def _coerce_arguments(arguments: Any) -> dict[str, Any]:
    """Ollama returns arguments as an object, but some models emit a JSON string."""
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            return {"value": arguments}
    return {}


def extract_json(text: str) -> dict[str, Any] | None:
    """Pull the first JSON object out of a model response.

    Used by the non-native-tool-calling fallback and by the final-answer parser,
    both of which face models that wrap valid JSON in prose or code fences.
    """
    text = strip_reasoning(text).strip()
    if not text:
        return None

    if (fenced := JSON_BLOCK_RE.search(text)) is not None:
        try:
            parsed = json.loads(fenced.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Last resort: scan for the first balanced object, respecting string escapes.
    start = text.find("{")
    while start != -1:
        depth, in_string, escaped = 0, False, False
        for index in range(start, len(text)):
            char = text[index]
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
            elif char == '"':
                in_string = not in_string
            elif not in_string:
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            parsed = json.loads(text[start : index + 1])
                            if isinstance(parsed, dict):
                                return parsed
                        except json.JSONDecodeError:
                            break
        start = text.find("{", start + 1)
    return None
