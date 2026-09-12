"""Inbound authentication helpers.

Public ingest endpoints are internet-facing, so each one verifies either a
shared API key or the signing scheme of the platform that calls it.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import Header

from support_common.config import get_settings
from support_common.errors import InvalidSignature

# Slack replays older than this are rejected outright.
SLACK_MAX_SKEW_SECONDS = 60 * 5


async def require_api_key(x_api_key: str = Header(default="")) -> None:
    """FastAPI dependency enforcing the shared ingest key.

    Uses a constant-time comparison so the endpoint does not leak the key one
    byte at a time under timing analysis.
    """
    expected = get_settings().api_key
    if not expected:
        # An empty configured key means auth is deliberately disabled (tests).
        return
    if not hmac.compare_digest(x_api_key, expected):
        raise InvalidSignature("invalid or missing X-API-Key header")


def verify_slack_signature(
    body: bytes,
    timestamp: str,
    signature: str,
    *,
    signing_secret: str | None = None,
    now: float | None = None,
) -> None:
    """Validate Slack's ``v0`` request signature.

    Raises :class:`InvalidSignature` on a bad secret, a malformed header, or a
    timestamp outside the replay window.
    """
    secret = signing_secret if signing_secret is not None else get_settings().slack_signing_secret
    if not secret:
        return  # Signature checking disabled in local development.

    try:
        ts = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise InvalidSignature("missing or malformed X-Slack-Request-Timestamp") from exc

    current = now if now is not None else time.time()
    if abs(current - ts) > SLACK_MAX_SKEW_SECONDS:
        raise InvalidSignature("slack request timestamp outside the replay window")

    basestring = b"v0:" + timestamp.encode() + b":" + body
    expected = "v0=" + hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature or ""):
        raise InvalidSignature("slack signature mismatch")


def verify_zendesk_signature(
    body: bytes,
    signature: str,
    timestamp: str,
    *,
    secret: str | None = None,
) -> None:
    """Validate a Zendesk webhook HMAC-SHA256 (base64) signature."""
    import base64

    key = secret if secret is not None else get_settings().zendesk_webhook_secret
    if not key:
        return

    expected = base64.b64encode(
        hmac.new(key.encode(), (timestamp + body.decode("utf-8")).encode(), hashlib.sha256).digest()
    ).decode()
    if not hmac.compare_digest(expected, signature or ""):
        raise InvalidSignature("zendesk signature mismatch")
