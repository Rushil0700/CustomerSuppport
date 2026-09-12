"""End-to-end tests for the Ticket Receiver API against a real database.

The agent and dispatcher are faked so the test is deterministic, but everything
between the HTTP request and the committed rows is the real code path, including
the background pipeline.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from support_common.enums import EscalationReason, MessageSender, TicketStatus
from support_common.models import Ticket, TicketMessage, TicketResolution
from support_common.schemas import AgentResult
from ticket_receiver import main as receiver_main
from ticket_receiver.pipeline import TicketPipeline

pytestmark = pytest.mark.integration

API_KEY = "test-key"
SLACK_SECRET = "test-slack-secret"

RESOLVED_ANSWER = (
    "To reset your password, open the login page and choose Forgot password. "
    "The emailed link is valid for 60 minutes."
)


class StubAgent:
    """Returns a scripted AgentResult for whatever ticket it is given."""

    def __init__(self, *, escalate: bool = False) -> None:
        self.escalate = escalate
        self.requests: list[dict[str, Any]] = []

    async def post_json(self, _path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(payload)
        result = AgentResult(
            ticket_id=payload["ticket_id"],
            resolved=not self.escalate,
            answer=RESOLVED_ANSWER,
            confidence=0.0 if self.escalate else 0.87,
            escalated=self.escalate,
            escalation_reason=EscalationReason.NO_KB_MATCH if self.escalate else None,
            turns_used=2,
            model="stub-model",
            took_ms=1500.0,
            estimated_cost_usd=0.031,
        )
        return result.model_dump(mode="json")

    async def aclose(self) -> None:
        return None

    async def healthy(self) -> bool:
        return True


class StubDispatcher:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[dict[str, Any]] = []

    async def post_json(self, _path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.fail:
            raise RuntimeError("dispatcher unreachable")
        self.sent.append(payload)
        return {"delivered": True}

    async def aclose(self) -> None:
        return None

    async def healthy(self) -> bool:
        return True


@pytest.fixture
def stub_agent() -> StubAgent:
    return StubAgent()


@pytest.fixture
def stub_dispatcher() -> StubDispatcher:
    return StubDispatcher()


@pytest.fixture
async def client(
    app_engine: AsyncEngine,
    stub_agent: StubAgent,
    stub_dispatcher: StubDispatcher,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("API_KEY", API_KEY)
    monkeypatch.setenv("SLACK_SIGNING_SECRET", SLACK_SECRET)
    from support_common.config import get_settings

    get_settings.cache_clear()

    pipeline = TicketPipeline(agent_client=stub_agent, dispatcher_client=stub_dispatcher)
    monkeypatch.setattr(receiver_main, "_pipeline", pipeline)

    transport = ASGITransport(app=receiver_main.app)
    async with AsyncClient(
        transport=transport, base_url="http://receiver", headers={"x-api-key": API_KEY}
    ) as http:
        yield http


def ticket_body(**overrides: Any) -> dict[str, Any]:
    body = {
        "subject": "Cannot sign in",
        "body": "I forgot my password and the reset email never arrives.",
        "customer": {
            "external_id": "email:dana@customer.example",
            "email": "dana@customer.example",
            "name": "Dana Okafor",
            "tier": "standard",
        },
        "channel": "email",
        "priority": "normal",
        "external_ref": "msg-001@customer.example",
        "tags": ["email"],
        "metadata": {},
    }
    body.update(overrides)
    return body


async def rows(engine: AsyncEngine, model: Any) -> list[Any]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        return list((await session.execute(select(model))).scalars().all())


class TestApiIngest:
    async def test_a_ticket_is_accepted_and_processed(
        self,
        client: AsyncClient,
        app_engine: AsyncEngine,
        stub_agent: StubAgent,
        stub_dispatcher: StubDispatcher,
    ) -> None:
        response = await client.post("/api/tickets", json=ticket_body())

        assert response.status_code == 201
        payload = response.json()
        assert payload["created"] is True
        ticket_id = payload["ticket_id"]

        # BackgroundTasks run after the response is produced, so by the time the
        # client has the body the pipeline has finished.
        assert stub_agent.requests[0]["ticket_id"] == ticket_id
        assert len(stub_dispatcher.sent) == 1

        tickets = await rows(app_engine, Ticket)
        assert tickets[0].status is TicketStatus.RESOLVED
        assert tickets[0].first_response_at is not None
        assert tickets[0].closed_at is not None

        resolutions = await rows(app_engine, TicketResolution)
        assert resolutions[0].confidence == pytest.approx(0.87)
        assert resolutions[0].escalated is False
        assert resolutions[0].model == "stub-model"

        messages = await rows(app_engine, TicketMessage)
        senders = [m.sender for m in messages]
        assert MessageSender.CUSTOMER in senders
        assert MessageSender.AGENT in senders

    async def test_a_redelivered_ticket_is_not_duplicated(
        self, client: AsyncClient, app_engine: AsyncEngine, stub_agent: StubAgent
    ) -> None:
        first = await client.post("/api/tickets", json=ticket_body())
        second = await client.post("/api/tickets", json=ticket_body())

        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json()["created"] is False
        assert first.json()["ticket_id"] == second.json()["ticket_id"]
        assert len(await rows(app_engine, Ticket)) == 1
        assert len(stub_agent.requests) == 1  # processed once, not twice

    async def test_the_api_key_is_required(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/tickets", json=ticket_body(), headers={"x-api-key": "wrong"}
        )
        assert response.status_code == 401
        assert response.json()["error"] == "invalid_signature"

    async def test_a_malformed_body_is_rejected(self, client: AsyncClient) -> None:
        response = await client.post("/api/tickets", json={"subject": "only a subject"})
        assert response.status_code == 422


class TestEscalationPath:
    async def test_an_escalated_ticket_is_recorded_and_delivered(
        self,
        app_engine: AsyncEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        agent, dispatcher = StubAgent(escalate=True), StubDispatcher()
        pipeline = TicketPipeline(agent_client=agent, dispatcher_client=dispatcher)
        monkeypatch.setattr(receiver_main, "_pipeline", pipeline)
        monkeypatch.setenv("API_KEY", API_KEY)
        from support_common.config import get_settings

        get_settings.cache_clear()

        transport = ASGITransport(app=receiver_main.app)
        async with AsyncClient(
            transport=transport, base_url="http://receiver", headers={"x-api-key": API_KEY}
        ) as client:
            await client.post("/api/tickets", json=ticket_body())

        tickets = await rows(app_engine, Ticket)
        assert tickets[0].status is TicketStatus.ESCALATED

        resolutions = await rows(app_engine, TicketResolution)
        assert resolutions[0].escalated is True
        assert resolutions[0].escalation_reason is EscalationReason.NO_KB_MATCH
        # The customer is still told something, even on an escalation.
        assert dispatcher.sent[0]["escalated"] is True


class TestDispatchFailure:
    async def test_the_resolution_survives_a_delivery_failure(
        self, app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Losing the delivery must not lose the answer."""
        pipeline = TicketPipeline(
            agent_client=StubAgent(), dispatcher_client=StubDispatcher(fail=True)
        )
        monkeypatch.setattr(receiver_main, "_pipeline", pipeline)
        monkeypatch.setenv("API_KEY", API_KEY)
        from support_common.config import get_settings

        get_settings.cache_clear()

        transport = ASGITransport(app=receiver_main.app)
        async with AsyncClient(
            transport=transport, base_url="http://receiver", headers={"x-api-key": API_KEY}
        ) as client:
            response = await client.post("/api/tickets", json=ticket_body())
        assert response.status_code == 201

        assert len(await rows(app_engine, TicketResolution)) == 1
        assert (await rows(app_engine, Ticket))[0].status is TicketStatus.RESOLVED
        system_messages = [
            m for m in await rows(app_engine, TicketMessage) if m.sender is MessageSender.SYSTEM
        ]
        assert any("Delivery failed" in m.message for m in system_messages)


class TestSlackWebhook:
    @staticmethod
    def signed(body: bytes) -> dict[str, str]:
        timestamp = str(int(time.time()))
        base = b"v0:" + timestamp.encode() + b":" + body
        signature = "v0=" + hmac.new(SLACK_SECRET.encode(), base, hashlib.sha256).hexdigest()
        return {
            "x-slack-request-timestamp": timestamp,
            "x-slack-signature": signature,
            "content-type": "application/json",
        }

    async def test_the_url_verification_challenge_is_echoed(self, client: AsyncClient) -> None:
        body = b'{"type": "url_verification", "challenge": "abc123"}'
        response = await client.post("/api/webhooks/slack", content=body, headers=self.signed(body))
        assert response.json() == {"challenge": "abc123"}

    async def test_a_message_event_creates_a_ticket(
        self, client: AsyncClient, app_engine: AsyncEngine
    ) -> None:
        body = (
            b'{"team_id": "T1", "event": {"type": "message", '
            b'"text": "our files are stuck syncing", "user": "U1", '
            b'"channel": "C1", "ts": "1717171717.000100"}}'
        )
        response = await client.post("/api/webhooks/slack", content=body, headers=self.signed(body))
        assert response.status_code == 201

        tickets = await rows(app_engine, Ticket)
        assert tickets[0].external_ref == "C1:1717171717.000100"
        assert tickets[0].customer_external_id == "slack:U1"

    async def test_a_bot_message_is_ignored(
        self, client: AsyncClient, app_engine: AsyncEngine
    ) -> None:
        """Otherwise the bot answers its own replies, forever."""
        body = (
            b'{"event": {"type": "message", "text": "an automated reply", '
            b'"bot_id": "B1", "channel": "C1", "ts": "1.0"}}'
        )
        response = await client.post("/api/webhooks/slack", content=body, headers=self.signed(body))
        assert response.json()["ignored"] == "bot_or_edit"
        assert await rows(app_engine, Ticket) == []

    async def test_an_invalid_signature_is_rejected(self, client: AsyncClient) -> None:
        body = b'{"event": {"type": "message", "text": "hi", "user": "U1"}}'
        response = await client.post(
            "/api/webhooks/slack",
            content=body,
            headers={
                "x-slack-request-timestamp": str(int(time.time())),
                "x-slack-signature": "v0=deadbeef",
                "content-type": "application/json",
            },
        )
        assert response.status_code == 401


class TestEmailWebhook:
    RAW = (
        "From: Dana Okafor <dana@customer.example>\n"
        "To: support@acme.example\n"
        "Subject: Files stuck syncing\n"
        "Message-ID: <email-001@customer.example>\n\n"
        "Three files have been showing the sync spinner for two hours.\n"
    )

    async def test_a_raw_message_creates_a_ticket(
        self, client: AsyncClient, app_engine: AsyncEngine
    ) -> None:
        response = await client.post(
            "/api/webhooks/email",
            content=self.RAW,
            headers={"content-type": "text/plain", "x-api-key": API_KEY},
        )
        assert response.status_code == 201
        tickets = await rows(app_engine, Ticket)
        assert tickets[0].subject == "Files stuck syncing"
        assert tickets[0].customer_email == "dana@customer.example"

    async def test_a_json_wrapped_message_is_accepted(
        self, client: AsyncClient, app_engine: AsyncEngine
    ) -> None:
        response = await client.post("/api/webhooks/email", json={"raw": self.RAW})
        assert response.status_code == 201
        assert len(await rows(app_engine, Ticket)) == 1

    async def test_an_empty_payload_is_rejected(self, client: AsyncClient) -> None:
        response = await client.post("/api/webhooks/email", json={"raw": "   "})
        assert response.status_code == 400


class TestZendeskWebhook:
    async def test_a_webhook_creates_a_ticket(
        self, client: AsyncClient, app_engine: AsyncEngine
    ) -> None:
        response = await client.post(
            "/api/webhooks/zendesk",
            json={
                "ticket": {
                    "id": 90210,
                    "subject": "API returning 429",
                    "description": "Our integration started returning 429 rate_limited.",
                    "priority": "high",
                    "requester": {"id": 55, "email": "dev@customer.example"},
                }
            },
        )
        assert response.status_code == 201
        tickets = await rows(app_engine, Ticket)
        assert tickets[0].external_ref == "90210"


class TestReadEndpoints:
    async def test_a_ticket_and_its_messages_can_be_fetched(self, client: AsyncClient) -> None:
        ticket_id = (await client.post("/api/tickets", json=ticket_body())).json()["ticket_id"]

        ticket = await client.get(f"/api/tickets/{ticket_id}")
        assert ticket.status_code == 200
        assert ticket.json()["ticket_id"] == ticket_id

        messages = await client.get(f"/api/tickets/{ticket_id}/messages")
        assert messages.status_code == 200
        assert len(messages.json()) >= 2

    async def test_an_unknown_ticket_is_a_404(self, client: AsyncClient) -> None:
        response = await client.get("/api/tickets/TKT-DOESNOTEXIST")
        assert response.status_code == 404
        assert response.json()["error"] == "ticket_not_found"

    async def test_tickets_can_be_listed_and_filtered(self, client: AsyncClient) -> None:
        for index in range(3):
            await client.post("/api/tickets", json=ticket_body(external_ref=f"list-{index}"))

        listed = await client.get("/api/tickets", params={"limit": 10})
        assert len(listed.json()) == 3

        resolved = await client.get("/api/tickets", params={"status": "resolved"})
        assert len(resolved.json()) == 3

    async def test_stats_report_the_auto_resolution_rate(self, client: AsyncClient) -> None:
        await client.post("/api/tickets", json=ticket_body())
        stats = (await client.get("/api/stats")).json()
        assert stats["tickets_total"] == 1
        assert stats["auto_resolution_rate"] == 1.0
        assert stats["avg_cost_usd"] == pytest.approx(0.031)

    async def test_reprocessing_requeues_a_ticket(
        self, client: AsyncClient, stub_agent: StubAgent
    ) -> None:
        ticket_id = (await client.post("/api/tickets", json=ticket_body())).json()["ticket_id"]
        response = await client.post(f"/api/tickets/{ticket_id}/reprocess")

        assert response.status_code == 200
        assert len(stub_agent.requests) == 2


class TestOps:
    async def test_health_is_dependency_free(self, client: AsyncClient) -> None:
        assert (await client.get("/health")).status_code == 200

    async def test_ready_reports_the_database(self, client: AsyncClient) -> None:
        payload = (await client.get("/ready")).json()
        assert payload["dependencies"]["database"] == "ok"

    async def test_pipeline_metrics_are_recorded(self, client: AsyncClient) -> None:
        await client.post("/api/tickets", json=ticket_body())
        body = (await client.get("/metrics")).text
        assert "support_tickets_received_total" in body
        assert "support_tickets_resolved_total" in body
        assert "support_ticket_resolution_seconds" in body
