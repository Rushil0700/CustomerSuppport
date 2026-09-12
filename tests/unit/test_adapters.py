"""Tests for the inbound channel adapters."""

from __future__ import annotations

import pytest

from support_common.enums import Channel, TicketPriority

from ticket_receiver.adapters import (
    clean_slack_text,
    from_email,
    from_slack_event,
    from_zendesk,
    infer_priority,
    strip_quoted_reply,
)


class TestSlack:
    def test_mentions_channels_and_links_are_cleaned(self) -> None:
        raw = "Hey <@U012AB3CD>, see <#C0111|general> and <https://acme.example/docs|the docs>"
        assert clean_slack_text(raw) == "Hey @user, see #general and the docs"

    def test_html_entities_are_decoded(self) -> None:
        assert clean_slack_text("a &lt;b&gt; &amp; c") == "a <b> & c"

    def test_event_becomes_a_ticket(self) -> None:
        ticket = from_slack_event(
            {
                "team_id": "T001",
                "event": {
                    "type": "message",
                    "text": "Our files have been stuck syncing for two hours",
                    "user": "U012AB3CD",
                    "channel": "C0111",
                    "ts": "1717171717.000100",
                },
            }
        )
        assert ticket.channel is Channel.SLACK
        assert ticket.customer.external_id == "slack:U012AB3CD"
        assert ticket.external_ref == "C0111:1717171717.000100"
        assert "stuck syncing" in ticket.body

    def test_a_threaded_reply_references_the_thread_parent(self) -> None:
        """Replies must thread onto the original, not spawn a new conversation."""
        ticket = from_slack_event(
            {
                "event": {
                    "type": "message",
                    "text": "Still not working, any update?",
                    "user": "U1",
                    "channel": "C1",
                    "ts": "200.0002",
                    "thread_ts": "100.0001",
                }
            }
        )
        assert ticket.external_ref == "C1:100.0001"

    def test_an_empty_message_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="no text"):
            from_slack_event({"event": {"type": "message", "text": "", "user": "U1"}})

    def test_the_profile_email_is_captured_when_present(self) -> None:
        ticket = from_slack_event(
            {
                "event": {"type": "message", "text": "help with billing", "user": "U1", "channel": "C1", "ts": "1.0"},
                "user_profile": {"email": "sam@customer.example", "real_name": "Sam Rossi"},
            }
        )
        assert ticket.customer.email == "sam@customer.example"
        assert ticket.customer.name == "Sam Rossi"


class TestEmail:
    RAW = """\
From: Dana Okafor <dana@customer.example>
To: support@acme.example
Subject: Files stuck syncing
Message-ID: <abc123@customer.example>
Date: Thu, 12 Sep 2026 10:00:00 +0000
Content-Type: text/plain; charset=utf-8

Three files have been showing the sync spinner for two hours.

Everything else in the workspace works fine.
"""

    def test_headers_and_body_are_parsed(self) -> None:
        ticket = from_email(self.RAW)
        assert ticket.channel is Channel.EMAIL
        assert ticket.subject == "Files stuck syncing"
        assert ticket.customer.email == "dana@customer.example"
        assert ticket.customer.name == "Dana Okafor"
        assert ticket.external_ref == "abc123@customer.example"
        assert "sync spinner" in ticket.body

    def test_bytes_input_is_accepted(self) -> None:
        assert from_email(self.RAW.encode()).subject == "Files stuck syncing"

    def test_encoded_subject_headers_are_decoded(self) -> None:
        raw = self.RAW.replace(
            "Subject: Files stuck syncing", "Subject: =?utf-8?B?w4ljaGVjIGRlIHN5bmM=?="
        )
        assert from_email(raw).subject == "Échec de sync"

    def test_quoted_history_is_stripped(self) -> None:
        raw = self.RAW + """
On Wed, 11 Sep 2026 at 09:00, Acme Support wrote:
> Have you tried pausing and resuming sync?
"""
        body = from_email(raw).body
        assert "pausing and resuming" not in body
        assert "sync spinner" in body

    def test_stripping_never_empties_the_message(self) -> None:
        """An over-eager quote match must not swallow the whole body."""
        body = "From: someone\nshort note"
        assert strip_quoted_reply(body) == body.strip()

    def test_multipart_prefers_the_plain_text_part(self) -> None:
        raw = """\
From: a@b.example
Subject: Multipart
Content-Type: multipart/alternative; boundary="BOUND"

--BOUND
Content-Type: text/plain; charset=utf-8

This is the plain text body of the message.
--BOUND
Content-Type: text/html; charset=utf-8

<p>This is the HTML body</p>
--BOUND--
"""
        assert "plain text body" in from_email(raw).body

    def test_a_missing_from_address_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="From address"):
            from_email("Subject: no sender\n\nbody text here")


class TestZendesk:
    def test_webhook_payload_becomes_a_ticket(self) -> None:
        ticket = from_zendesk(
            {
                "ticket": {
                    "id": 90210,
                    "subject": "API returning 429",
                    "description": "Our integration started returning 429 rate_limited.",
                    "priority": "high",
                    "status": "new",
                    "tags": ["api", "rate-limit"],
                    "requester": {
                        "id": 55,
                        "email": "dev@customer.example",
                        "name": "Mei Kim",
                    },
                }
            }
        )
        assert ticket.channel is Channel.ZENDESK
        assert ticket.priority is TicketPriority.HIGH
        assert ticket.external_ref == "90210"
        assert ticket.customer.external_id == "zendesk:55"
        assert "api" in ticket.tags

    def test_a_payload_without_a_description_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="no description"):
            from_zendesk({"ticket": {"id": 1, "subject": "empty"}})


class TestPriorityInference:
    @pytest.mark.parametrize(
        "text", ["This is URGENT", "our workspace is down", "everything is broken", "need this asap"]
    )
    def test_urgent_language_raises_priority(self, text: str) -> None:
        assert infer_priority("", text, TicketPriority.NORMAL) is TicketPriority.URGENT

    def test_important_language_raises_to_high(self) -> None:
        assert (
            infer_priority("", "this is important for our deadline", TicketPriority.NORMAL)
            is TicketPriority.HIGH
        )

    def test_neutral_language_keeps_the_default(self) -> None:
        assert (
            infer_priority("", "how do I download an invoice", TicketPriority.NORMAL)
            is TicketPriority.NORMAL
        )

    def test_an_explicit_high_priority_is_never_lowered(self) -> None:
        """Inference only ever raises: the sender's own setting is evidence."""
        assert (
            infer_priority("", "just a quick question", TicketPriority.HIGH)
            is TicketPriority.HIGH
        )
