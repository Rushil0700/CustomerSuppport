"""Tests for inbound signature verification and the cost model."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

import pytest
from support_common.cost import CostModel, estimate_ticket_cost
from support_common.errors import InvalidSignature
from support_common.security import (
    SLACK_MAX_SKEW_SECONDS,
    verify_slack_signature,
    verify_zendesk_signature,
)

SECRET = "8f742231b10e8888abcd99yyyzzz85a5"
BODY = b"token=xyz&team_id=T1&event=message"


def slack_signature(body: bytes, timestamp: str, secret: str = SECRET) -> str:
    base = b"v0:" + timestamp.encode() + b":" + body
    return "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()


class TestSlackSignature:
    def test_a_valid_signature_passes(self) -> None:
        now = time.time()
        timestamp = str(int(now))
        verify_slack_signature(
            BODY, timestamp, slack_signature(BODY, timestamp), signing_secret=SECRET, now=now
        )

    def test_a_wrong_secret_is_rejected(self) -> None:
        now = time.time()
        timestamp = str(int(now))
        forged = slack_signature(BODY, timestamp, secret="attacker-secret")
        with pytest.raises(InvalidSignature, match="mismatch"):
            verify_slack_signature(BODY, timestamp, forged, signing_secret=SECRET, now=now)

    def test_a_tampered_body_is_rejected(self) -> None:
        now = time.time()
        timestamp = str(int(now))
        signature = slack_signature(BODY, timestamp)
        with pytest.raises(InvalidSignature):
            verify_slack_signature(
                BODY + b"&evil=1", timestamp, signature, signing_secret=SECRET, now=now
            )

    def test_an_old_timestamp_is_rejected_as_a_replay(self) -> None:
        now = time.time()
        old = str(int(now - SLACK_MAX_SKEW_SECONDS - 60))
        with pytest.raises(InvalidSignature, match="replay window"):
            verify_slack_signature(
                BODY, old, slack_signature(BODY, old), signing_secret=SECRET, now=now
            )

    def test_a_future_timestamp_is_also_rejected(self) -> None:
        now = time.time()
        future = str(int(now + SLACK_MAX_SKEW_SECONDS + 60))
        with pytest.raises(InvalidSignature, match="replay window"):
            verify_slack_signature(
                BODY, future, slack_signature(BODY, future), signing_secret=SECRET, now=now
            )

    @pytest.mark.parametrize("timestamp", ["", "not-a-number", "12.34.56"])
    def test_a_malformed_timestamp_is_rejected(self, timestamp: str) -> None:
        with pytest.raises(InvalidSignature, match="malformed"):
            verify_slack_signature(BODY, timestamp, "v0=abc", signing_secret=SECRET)

    def test_an_empty_secret_disables_checking(self) -> None:
        """Local development runs without a Slack app configured."""
        verify_slack_signature(BODY, "0", "anything", signing_secret="")


class TestZendeskSignature:
    def test_a_valid_signature_passes(self) -> None:
        timestamp = "2026-09-12T10:00:00Z"
        body = b'{"ticket": {"id": 1}}'
        signature = base64.b64encode(
            hmac.new(SECRET.encode(), (timestamp + body.decode()).encode(), hashlib.sha256).digest()
        ).decode()
        verify_zendesk_signature(body, signature, timestamp, secret=SECRET)

    def test_a_wrong_signature_is_rejected(self) -> None:
        with pytest.raises(InvalidSignature, match="zendesk"):
            verify_zendesk_signature(b"{}", "bogus", "2026-09-12T10:00:00Z", secret=SECRET)

    def test_an_empty_secret_disables_checking(self) -> None:
        verify_zendesk_signature(b"{}", "", "", secret="")


class TestCostModel:
    def test_cost_grows_with_inference_time(self) -> None:
        cheap = estimate_ticket_cost(2.0)
        expensive = estimate_ticket_cost(20.0)
        assert expensive > cheap

    def test_concurrency_divides_the_inference_cost(self) -> None:
        """A GPU serving eight tickets at once bills each second eight ways."""
        serial = estimate_ticket_cost(16.0, concurrency=1)
        parallel = estimate_ticket_cost(16.0, concurrency=8)
        assert parallel < serial

    def test_a_typical_ticket_lands_under_the_eight_cent_target(self) -> None:
        # 25s of model time at a concurrency of 8 is a realistic 7B-model ticket.
        assert estimate_ticket_cost(25.0, concurrency=8) < 0.08

    def test_the_platform_overhead_is_always_charged(self) -> None:
        assert estimate_ticket_cost(0.0) > 0

    def test_zero_throughput_does_not_divide_by_zero(self) -> None:
        model = CostModel(tickets_per_hour=0)
        assert model.platform_usd_per_ticket == 0.0
        assert model.estimate(5.0) > 0

    def test_concurrency_below_one_is_treated_as_one(self) -> None:
        assert estimate_ticket_cost(10.0, concurrency=0) == estimate_ticket_cost(
            10.0, concurrency=1
        )

    def test_a_custom_model_changes_the_result(self) -> None:
        pricey = CostModel(inference_hourly_usd=5.0, platform_hourly_usd=1.0)
        assert pricey.estimate(10.0) > estimate_ticket_cost(10.0)
