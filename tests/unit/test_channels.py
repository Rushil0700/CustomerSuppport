"""Tests for outbound delivery formatting and channel selection."""

from __future__ import annotations

import pytest

from support_common.config import Settings
from support_common.enums import Channel
from support_common.errors import DispatchFailed
from support_common.schemas import Citation, DispatchRequest

from dispatcher.channels import (
    EmailChannel,
    LogChannel,
    SlackChannel,
    _citation_line,
    _email_body,
    _plain_text,
    _slack_blocks,
    _split_slack_ref,
    build_channels,
)


@pytest.fixture
def request_payload() -> DispatchRequest:
    return DispatchRequest(
        ticket_id="TKT-ABCDEF123456",
        channel=Channel.EMAIL,
        subject="Re: Cannot sign in",
        body="Open the login page and choose Forgot password.",
        recipient="dana@customer.example",
        citations=[
            Citation(
                doc_id="account-password-reset",
                title="Reset a forgotten password",
                source="account/account-password-reset.md",
                score=0.8,
            )
        ],
    )


class TestChannelSelection:
    def test_dry_run_routes_everything_to_the_log(self) -> None:
        """The default must never send a real message from a dev machine."""
        channels = build_channels(Settings(environment="ci", dispatch_dry_run=True))
        assert all(isinstance(c, LogChannel) for c in channels.values())

    def test_live_mode_wires_the_real_channels(self) -> None:
        channels = build_channels(Settings(environment="ci", dispatch_dry_run=False))
        assert isinstance(channels[Channel.SLACK], SlackChannel)
        assert isinstance(channels[Channel.EMAIL], EmailChannel)
        assert isinstance(channels[Channel.API], LogChannel)

    def test_every_channel_has_an_implementation(self) -> None:
        channels = build_channels(Settings(environment="ci", dispatch_dry_run=False))
        assert set(channels) == set(Channel)


class TestLogChannel:
    async def test_delivery_always_succeeds(self, request_payload: DispatchRequest) -> None:
        channel = LogChannel(Settings(environment="ci"), Channel.API)
        result = await channel.send(request_payload)
        assert result.delivered is True
        assert result.provider_message_id == "log:TKT-ABCDEF123456"

    async def test_it_is_always_healthy(self) -> None:
        assert await LogChannel(Settings(environment="ci")).healthy() is True


class TestEmailFormatting:
    def test_the_body_lists_related_articles_and_the_reference(
        self, request_payload: DispatchRequest
    ) -> None:
        body = _email_body(request_payload)
        assert "Reset a forgotten password" in body
        assert "TKT-ABCDEF123456" in body

    def test_an_escalation_adds_the_handover_notice(
        self, request_payload: DispatchRequest
    ) -> None:
        request_payload.escalated = True
        assert "support team has been notified" in _plain_text(request_payload)

    async def test_sending_without_a_recipient_fails_clearly(
        self, request_payload: DispatchRequest
    ) -> None:
        request_payload.recipient = None
        channel = EmailChannel(Settings(environment="ci", dispatch_dry_run=False))
        with pytest.raises(DispatchFailed, match="no recipient"):
            await channel.send(request_payload)


class TestSlackFormatting:
    def test_the_reference_splits_into_channel_and_thread(self) -> None:
        assert _split_slack_ref("C0111:1717171717.000100") == ("C0111", "1717171717.000100")

    def test_an_absent_reference_yields_empties(self) -> None:
        assert _split_slack_ref(None) == ("", "")

    def test_blocks_include_the_answer_and_the_ticket_id(
        self, request_payload: DispatchRequest
    ) -> None:
        blocks = _slack_blocks(request_payload)
        assert blocks[0]["text"]["text"].startswith("Open the login page")
        assert "TKT-ABCDEF123456" in blocks[-1]["elements"][0]["text"]

    def test_a_long_answer_is_truncated_to_slack_s_limit(
        self, request_payload: DispatchRequest
    ) -> None:
        request_payload.body = "x" * 5000
        assert len(_slack_blocks(request_payload)[0]["text"]["text"]) <= 2900

    def test_citations_render_as_a_context_line(self) -> None:
        line = _citation_line(
            [Citation(doc_id="d", title="Reset a forgotten password", source="s", score=0.8)]
        )
        assert line == "Based on: Reset a forgotten password"

    def test_no_citations_produces_no_line(self) -> None:
        assert _citation_line([]) == ""

    async def test_slack_without_a_token_fails_clearly(
        self, request_payload: DispatchRequest
    ) -> None:
        channel = SlackChannel(Settings(environment="ci", slack_bot_token=""))
        with pytest.raises(DispatchFailed, match="SLACK_BOT_TOKEN"):
            await channel.send(request_payload)

    async def test_slack_without_a_token_is_unhealthy(self) -> None:
        assert await SlackChannel(Settings(environment="ci", slack_bot_token="")).healthy() is False
