"""Outbound delivery channels.

Each channel implements :class:`DeliveryChannel`. ``DISPATCH_DRY_RUN`` short-
circuits every one of them and logs instead, which is the default locally so a
test run cannot email a real customer.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from email.message import EmailMessage
from typing import Any

from support_common.config import Settings, get_settings
from support_common.enums import Channel
from support_common.errors import DispatchFailed
from support_common.logging import get_logger
from support_common.schemas import Citation, DispatchRequest, DispatchResult

log = get_logger(__name__)

ESCALATION_FOOTER = "A member of our support team has been notified and will follow up here."


class DeliveryChannel(ABC):
    """Sends one message to one customer."""

    channel: Channel

    @abstractmethod
    async def send(self, request: DispatchRequest) -> DispatchResult:
        """Deliver the message, or raise :class:`DispatchFailed`."""

    @abstractmethod
    async def healthy(self) -> bool:
        """Whether the channel is currently configured and reachable."""


class SlackChannel(DeliveryChannel):
    """Posts back into the Slack thread the ticket came from."""

    channel = Channel.SLACK

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            from slack_sdk.web.async_client import AsyncWebClient

            self._client = AsyncWebClient(token=self.settings.slack_bot_token)
        return self._client

    async def send(self, request: DispatchRequest) -> DispatchResult:
        started = time.perf_counter()
        if not self.settings.slack_bot_token:
            raise DispatchFailed("SLACK_BOT_TOKEN is not configured")

        channel_id, thread_ts = _split_slack_ref(request.external_ref)
        target = channel_id or self.settings.slack_default_channel

        try:
            response = await self._get_client().chat_postMessage(
                channel=target,
                thread_ts=thread_ts or None,
                text=_plain_text(request),
                blocks=_slack_blocks(request),
                unfurl_links=False,
            )
        except Exception as exc:
            raise DispatchFailed(f"slack delivery failed: {exc}") from exc

        return DispatchResult(
            ticket_id=request.ticket_id,
            channel=self.channel,
            delivered=True,
            provider_message_id=str(response.get("ts", "")),
            took_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    async def healthy(self) -> bool:
        if not self.settings.slack_bot_token:
            return False
        try:
            return bool((await self._get_client().auth_test()).get("ok"))
        except Exception:
            return False


class EmailChannel(DeliveryChannel):
    """Sends the reply over SMTP."""

    channel = Channel.EMAIL

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send(self, request: DispatchRequest) -> DispatchResult:
        import aiosmtplib

        started = time.perf_counter()
        if not request.recipient:
            raise DispatchFailed("no recipient email address on the ticket")

        message = EmailMessage()
        message["From"] = f"{self.settings.smtp_from_name} <{self.settings.smtp_from_email}>"
        message["To"] = request.recipient
        message["Subject"] = request.subject or f"Re: your support request {request.ticket_id}"
        # Threading headers so the reply lands in the customer's existing thread
        # rather than starting a new one in their client.
        if request.external_ref:
            message["In-Reply-To"] = f"<{request.external_ref}>"
            message["References"] = f"<{request.external_ref}>"
        message["X-Ticket-ID"] = request.ticket_id
        message.set_content(_email_body(request))

        try:
            await aiosmtplib.send(
                message,
                hostname=self.settings.smtp_host,
                port=self.settings.smtp_port,
                username=self.settings.smtp_username or None,
                password=self.settings.smtp_password or None,
                start_tls=self.settings.smtp_use_tls,
                timeout=30,
            )
        except Exception as exc:
            raise DispatchFailed(f"smtp delivery failed: {exc}") from exc

        return DispatchResult(
            ticket_id=request.ticket_id,
            channel=self.channel,
            delivered=True,
            provider_message_id=message.get("Message-ID"),
            took_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    async def healthy(self) -> bool:
        import aiosmtplib

        try:
            client = aiosmtplib.SMTP(
                hostname=self.settings.smtp_host, port=self.settings.smtp_port, timeout=5
            )
            await client.connect()
            await client.quit()
            return True
        except Exception:
            return False


class LogChannel(DeliveryChannel):
    """Terminal channel for API and web tickets, and the dry-run fallback.

    The caller polls the ticket for its resolution, so "delivery" is simply
    making the answer durable and recording that it was made available.
    """

    channel = Channel.API

    def __init__(self, settings: Settings, channel: Channel = Channel.API) -> None:
        self.settings = settings
        self.channel = channel

    async def send(self, request: DispatchRequest) -> DispatchResult:
        log.info(
            "dispatch.logged",
            ticket_id=request.ticket_id,
            channel=self.channel.value,
            escalated=request.escalated,
            body_chars=len(request.body),
        )
        return DispatchResult(
            ticket_id=request.ticket_id,
            channel=self.channel,
            delivered=True,
            provider_message_id=f"log:{request.ticket_id}",
            took_ms=0.0,
        )

    async def healthy(self) -> bool:
        return True


# --- Formatting --------------------------------------------------------------


def _split_slack_ref(external_ref: str | None) -> tuple[str, str]:
    """Split the stored ``"<channel>:<thread_ts>"`` reference."""
    if not external_ref:
        return "", ""
    channel_id, _, thread_ts = external_ref.partition(":")
    return channel_id, thread_ts


def _plain_text(request: DispatchRequest) -> str:
    """Body plus escalation notice - also the Slack notification preview text."""
    body = request.body
    if request.escalated:
        body = f"{body}\n\n{ESCALATION_FOOTER}"
    return body


def _email_body(request: DispatchRequest) -> str:
    """Email body with a citation footer and the ticket reference."""
    parts = [_plain_text(request)]
    if request.citations:
        parts.append("\nRelated help articles:")
        parts.extend(f"  - {c.title}" for c in request.citations[:3])
    parts.append(f"\nTicket reference: {request.ticket_id}")
    return "\n".join(parts)


def _slack_blocks(request: DispatchRequest) -> list[dict[str, Any]]:
    """Block Kit payload: the answer, then a compact context line."""
    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": _plain_text(request)[:2900]}}
    ]
    context = _citation_line(request.citations)
    if context:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": context}]})
    blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Ticket `{request.ticket_id}`"}],
        }
    )
    return blocks


def _citation_line(citations: list[Citation]) -> str:
    if not citations:
        return ""
    titles = ", ".join(c.title for c in citations[:3])
    return f"Based on: {titles}"


def build_channels(settings: Settings | None = None) -> dict[Channel, DeliveryChannel]:
    """Map each channel to its delivery implementation.

    In dry-run mode every channel resolves to :class:`LogChannel`, so no message
    can leave the machine.
    """
    settings = settings or get_settings()
    if settings.dispatch_dry_run:
        log.warning("dispatch.dry_run_enabled", hint="set DISPATCH_DRY_RUN=false to send for real")
        return {channel: LogChannel(settings, channel) for channel in Channel}

    return {
        Channel.SLACK: SlackChannel(settings),
        Channel.EMAIL: EmailChannel(settings),
        # Zendesk replies are written back through its API by the same webhook
        # integration that delivered the ticket; logging is the honest behaviour
        # until that credential is configured.
        Channel.ZENDESK: LogChannel(settings, Channel.ZENDESK),
        Channel.API: LogChannel(settings, Channel.API),
        Channel.WEB: LogChannel(settings, Channel.WEB),
    }
