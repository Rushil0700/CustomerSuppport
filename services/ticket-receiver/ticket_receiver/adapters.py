"""Channel adapters: turn each provider's payload into a ``TicketCreate``.

Every inbound format converges on one normalised ticket here, so nothing
downstream - persistence, the agent, the dispatcher - needs to know or care
whether a ticket arrived from Slack, an email, Zendesk or the API.
"""

from __future__ import annotations

import email
import re
from email.header import decode_header, make_header
from email.message import Message
from typing import Any

from support_common.enums import Channel, TicketPriority
from support_common.logging import get_logger
from support_common.schemas import CustomerRef, TicketCreate

log = get_logger(__name__)

# <@U01ABC> and <#C01ABC|general> mentions, and <https://x|label> links.
SLACK_USER_RE = re.compile(r"<@([UW][A-Z0-9]+)(?:\|[^>]*)?>")
SLACK_CHANNEL_RE = re.compile(r"<#([C][A-Z0-9]+)(?:\|([^>]*))?>")
SLACK_LINK_RE = re.compile(r"<(https?://[^|>]+)(?:\|([^>]*))?>")

# Quoted-reply boundaries, so an email thread does not re-send its own history
# to the model as if it were new information.
QUOTE_MARKERS = (
    re.compile(r"^On .{5,80} wrote:$", re.MULTILINE),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^_{10,}$", re.MULTILINE),
    re.compile(r"^From:\s.+$", re.MULTILINE),
)

URGENT_WORDS = re.compile(
    r"\b(urgent|asap|emergency|critical|outage|down|broken|blocked|immediately)\b", re.I
)
HIGH_WORDS = re.compile(r"\b(important|priority|soon|escalate|deadline)\b", re.I)


def infer_priority(subject: str, body: str, default: TicketPriority) -> TicketPriority:
    """Guess urgency from the customer's own language.

    Only ever raises the priority above the default - a customer calling
    something urgent is evidence; their silence is not evidence of the opposite.
    """
    text = f"{subject} {body}"
    if URGENT_WORDS.search(text):
        return TicketPriority.URGENT
    if HIGH_WORDS.search(text) and default is TicketPriority.NORMAL:
        return TicketPriority.HIGH
    return default


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _subject_from_body(body: str, fallback: str = "Support request") -> str:
    """Derive a subject from the first meaningful line of a message."""
    for line in body.splitlines():
        line = line.strip()
        if len(line) >= 8:
            return _truncate(line, 200)
    return fallback


# --- Slack -------------------------------------------------------------------


def clean_slack_text(text: str) -> str:
    """Replace Slack's markup with something the model can read."""
    text = SLACK_LINK_RE.sub(lambda m: m.group(2) or m.group(1), text)
    text = SLACK_CHANNEL_RE.sub(lambda m: f"#{m.group(2) or m.group(1)}", text)
    text = SLACK_USER_RE.sub("@user", text)
    return text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()


def from_slack_event(payload: dict[str, Any]) -> TicketCreate:
    """Build a ticket from a Slack Events API ``message`` or ``app_mention``.

    The ``event_ts`` becomes the external reference, which both deduplicates
    Slack's at-least-once redelivery and threads our reply onto the original.
    """
    event = payload.get("event") or payload
    raw_text = str(event.get("text") or "")
    body = clean_slack_text(raw_text)
    if not body:
        raise ValueError("slack event carried no text")

    user_id = str(event.get("user") or event.get("bot_id") or "unknown")
    channel_id = str(event.get("channel") or "")
    # thread_ts when the message is already in a thread, ts otherwise: replying
    # to the parent keeps the whole exchange in one Slack thread.
    thread_ts = str(event.get("thread_ts") or event.get("ts") or "")

    profile = (payload.get("user_profile") or event.get("user_profile") or {}) or {}

    return TicketCreate(
        subject=_subject_from_body(body, "Slack support request"),
        body=_truncate(body, 20_000),
        customer=CustomerRef(
            external_id=f"slack:{user_id}",
            email=profile.get("email") or None,
            name=profile.get("real_name") or profile.get("display_name") or None,
        ),
        channel=Channel.SLACK,
        priority=infer_priority("", body, TicketPriority.NORMAL),
        external_ref=f"{channel_id}:{thread_ts}" if channel_id else thread_ts,
        tags=["slack"],
        metadata={
            "slack_channel": channel_id,
            "slack_thread_ts": thread_ts,
            "slack_user": user_id,
            "team": payload.get("team_id", ""),
        },
    )


# --- Email -------------------------------------------------------------------


def _decode(value: str | None) -> str:
    """Decode RFC 2047 encoded headers ("=?utf-8?B?...?=")."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _body_from_message(message: Message) -> str:
    """Prefer text/plain; fall back to stripping tags from text/html."""
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(
                part.get("Content-Disposition", "")
            ):
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", "replace")
        for part in message.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    html = payload.decode(part.get_content_charset() or "utf-8", "replace")
                    return re.sub(r"<[^>]+>", " ", html)
        return ""

    payload = message.get_payload(decode=True)
    if payload is None:
        return str(message.get_payload() or "")
    return payload.decode(message.get_content_charset() or "utf-8", "replace")


def strip_quoted_reply(body: str) -> str:
    """Drop quoted history so only the customer's new message is processed."""
    earliest = len(body)
    for marker in QUOTE_MARKERS:
        if (match := marker.search(body)) is not None:
            earliest = min(earliest, match.start())
    trimmed = body[:earliest].strip()
    # Guard against an over-eager match swallowing the entire message.
    return trimmed if len(trimmed) >= 20 else body.strip()


def from_email(raw_message: str | bytes) -> TicketCreate:
    """Parse an RFC 822 message into a ticket."""
    if isinstance(raw_message, bytes):
        message = email.message_from_bytes(raw_message)
    else:
        message = email.message_from_string(raw_message)

    subject = _decode(message.get("Subject")) or "Email support request"
    from_header = _decode(message.get("From"))
    name, address = email.utils.parseaddr(from_header)
    if not address:
        raise ValueError("email has no parseable From address")

    body = strip_quoted_reply(re.sub(r"\r\n", "\n", _body_from_message(message)).strip())
    if not body:
        body = subject

    # In-Reply-To threads a follow-up onto the original conversation.
    message_id = message.get("Message-ID", "").strip("<> ")
    in_reply_to = (message.get("In-Reply-To") or "").strip("<> ")

    return TicketCreate(
        subject=_truncate(subject, 500),
        body=_truncate(body, 20_000),
        customer=CustomerRef(
            external_id=f"email:{address.lower()}",
            email=address.lower(),
            name=name or None,
        ),
        channel=Channel.EMAIL,
        priority=infer_priority(subject, body, TicketPriority.NORMAL),
        external_ref=message_id or None,
        tags=["email"],
        metadata={
            "message_id": message_id,
            "in_reply_to": in_reply_to,
            "to": _decode(message.get("To")),
            "date": _decode(message.get("Date")),
        },
    )


# --- Zendesk -----------------------------------------------------------------

ZENDESK_PRIORITY = {
    "low": TicketPriority.LOW,
    "normal": TicketPriority.NORMAL,
    "high": TicketPriority.HIGH,
    "urgent": TicketPriority.URGENT,
}


def from_zendesk(payload: dict[str, Any]) -> TicketCreate:
    """Build a ticket from a Zendesk webhook payload."""
    ticket = payload.get("ticket") or payload
    requester = ticket.get("requester") or ticket.get("via", {}).get("source", {}) or {}

    subject = str(ticket.get("subject") or "Zendesk ticket")
    body = str(ticket.get("description") or ticket.get("comment", {}).get("body") or "").strip()
    if not body:
        raise ValueError("zendesk payload carried no description")

    zendesk_id = str(ticket.get("id") or "")
    requester_id = str(requester.get("id") or requester.get("email") or "unknown")

    return TicketCreate(
        subject=_truncate(subject, 500),
        body=_truncate(body, 20_000),
        customer=CustomerRef(
            external_id=f"zendesk:{requester_id}",
            email=requester.get("email") or None,
            name=requester.get("name") or None,
        ),
        channel=Channel.ZENDESK,
        priority=ZENDESK_PRIORITY.get(
            str(ticket.get("priority") or "").lower(), TicketPriority.NORMAL
        ),
        external_ref=zendesk_id or None,
        tags=["zendesk", *[str(t) for t in (ticket.get("tags") or [])][:10]],
        metadata={
            "zendesk_id": zendesk_id,
            "zendesk_status": ticket.get("status", ""),
            "organization": (ticket.get("organization") or {}).get("name", ""),
        },
    )
