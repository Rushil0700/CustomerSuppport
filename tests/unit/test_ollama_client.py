"""Tests for the Ollama client, with the daemon mocked at the HTTP layer."""

from __future__ import annotations

import httpx
import pytest
import respx

from support_common.config import Settings
from support_common.errors import LLMError, UpstreamUnavailable

from agent_service.ollama_client import OllamaClient, extract_json, strip_reasoning

HOST = "http://localhost:11434"


@pytest.fixture
def settings() -> Settings:
    return Settings(environment="ci", ollama_host=HOST, ollama_model="test-model")


@pytest.fixture
def client(settings: Settings) -> OllamaClient:
    return OllamaClient(settings=settings)


def chat_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "model": "test-model",
        "message": {"role": "assistant", "content": "Here is your answer."},
        "done": True,
        "prompt_eval_count": 120,
        "eval_count": 45,
    }
    body.update(overrides)
    return body


class TestChat:
    @respx.mock
    async def test_a_plain_completion_is_parsed(self, client: OllamaClient) -> None:
        respx.post(f"{HOST}/api/chat").mock(return_value=httpx.Response(200, json=chat_body()))

        response = await client.chat([{"role": "user", "content": "hello"}])

        assert response.content == "Here is your answer."
        assert response.tool_calls == []
        assert response.prompt_tokens == 120
        assert response.completion_tokens == 45
        assert response.duration_seconds > 0

    @respx.mock
    async def test_native_tool_calls_are_extracted(self, client: OllamaClient) -> None:
        respx.post(f"{HOST}/api/chat").mock(
            return_value=httpx.Response(
                200,
                json=chat_body(
                    message={
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "search_kb",
                                    "arguments": {"query": "password reset"},
                                }
                            }
                        ],
                    }
                ),
            )
        )

        response = await client.chat([{"role": "user", "content": "help"}], tools=[{"x": 1}])

        assert response.wants_tools
        assert response.tool_calls[0].name == "search_kb"
        assert response.tool_calls[0].arguments == {"query": "password reset"}

    @respx.mock
    async def test_arguments_sent_as_a_json_string_are_coerced(
        self, client: OllamaClient
    ) -> None:
        """Some models serialise the arguments object as a string."""
        respx.post(f"{HOST}/api/chat").mock(
            return_value=httpx.Response(
                200,
                json=chat_body(
                    message={
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {"function": {"name": "search_kb", "arguments": '{"query": "sync"}'}}
                        ],
                    }
                ),
            )
        )
        response = await client.chat([{"role": "user", "content": "help"}])
        assert response.tool_calls[0].arguments == {"query": "sync"}

    @respx.mock
    async def test_reasoning_blocks_are_stripped(self, client: OllamaClient) -> None:
        """A <think> block must never reach the customer."""
        respx.post(f"{HOST}/api/chat").mock(
            return_value=httpx.Response(
                200,
                json=chat_body(
                    message={
                        "role": "assistant",
                        "content": "<think>The user wants X, so I should...</think>\nThe answer.",
                    }
                ),
            )
        )
        response = await client.chat([{"role": "user", "content": "hi"}])
        assert response.content == "The answer."

    @respx.mock
    async def test_a_missing_model_gives_an_actionable_error(
        self, client: OllamaClient
    ) -> None:
        respx.post(f"{HOST}/api/chat").mock(return_value=httpx.Response(404, text="not found"))
        with pytest.raises(LLMError, match="ollama pull test-model"):
            await client.chat([{"role": "user", "content": "hi"}])

    @respx.mock
    async def test_a_server_error_raises_llm_error(self, client: OllamaClient) -> None:
        respx.post(f"{HOST}/api/chat").mock(return_value=httpx.Response(500, text="boom"))
        with pytest.raises(LLMError, match="500"):
            await client.chat([{"role": "user", "content": "hi"}])

    @respx.mock
    async def test_a_connection_failure_raises_upstream_unavailable(
        self, client: OllamaClient
    ) -> None:
        respx.post(f"{HOST}/api/chat").mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(UpstreamUnavailable, match="cannot reach ollama"):
            await client.chat([{"role": "user", "content": "hi"}])

    @respx.mock
    async def test_a_timeout_raises_llm_error(self, client: OllamaClient) -> None:
        respx.post(f"{HOST}/api/chat").mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(LLMError, match="timed out"):
            await client.chat([{"role": "user", "content": "hi"}])

    @respx.mock
    async def test_json_mode_sets_the_format_field(self, client: OllamaClient) -> None:
        route = respx.post(f"{HOST}/api/chat").mock(
            return_value=httpx.Response(200, json=chat_body())
        )
        await client.chat([{"role": "user", "content": "hi"}], json_mode=True)
        assert route.calls.last.request.read().decode().count('"format":"json"') == 1


class TestHealth:
    @respx.mock
    async def test_the_configured_model_is_detected(self, client: OllamaClient) -> None:
        respx.get(f"{HOST}/api/tags").mock(
            return_value=httpx.Response(200, json={"models": [{"name": "test-model:latest"}]})
        )
        assert await client.healthy() is True

    @respx.mock
    async def test_a_missing_model_is_unhealthy(self, client: OllamaClient) -> None:
        respx.get(f"{HOST}/api/tags").mock(
            return_value=httpx.Response(200, json={"models": [{"name": "something-else"}]})
        )
        assert await client.healthy() is False

    @respx.mock
    async def test_an_unreachable_daemon_is_unhealthy(self, client: OllamaClient) -> None:
        respx.get(f"{HOST}/api/tags").mock(side_effect=httpx.ConnectError("refused"))
        assert await client.healthy() is False


class TestJsonExtraction:
    def test_a_bare_object_is_parsed(self) -> None:
        assert extract_json('{"tool": "search_kb"}') == {"tool": "search_kb"}

    def test_a_fenced_block_is_parsed(self) -> None:
        assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_an_object_embedded_in_prose_is_found(self) -> None:
        text = 'Sure, here you go: {"tool": "escalate", "arguments": {"reason": "x"}} - hope that helps'
        assert extract_json(text) == {"tool": "escalate", "arguments": {"reason": "x"}}

    def test_braces_inside_strings_do_not_confuse_the_scanner(self) -> None:
        assert extract_json('prefix {"answer": "use {braces} carefully"} suffix') == {
            "answer": "use {braces} carefully"
        }

    def test_escaped_quotes_are_handled(self) -> None:
        assert extract_json(r'{"answer": "she said \"hello\""}') == {
            "answer": 'she said "hello"'
        }

    @pytest.mark.parametrize("text", ["", "no json at all", "{unclosed: ", "[1, 2, 3]"])
    def test_unparseable_input_returns_none(self, text: str) -> None:
        assert extract_json(text) is None

    def test_reasoning_is_stripped_before_parsing(self) -> None:
        assert extract_json('<think>hmm</think>{"a": 1}') == {"a": 1}


class TestStripReasoning:
    def test_multiline_blocks_are_removed(self) -> None:
        assert strip_reasoning("<think>\nline one\nline two\n</think>\nAnswer") == "Answer"

    def test_text_without_a_block_is_untouched(self) -> None:
        assert strip_reasoning("Just an answer") == "Just an answer"
