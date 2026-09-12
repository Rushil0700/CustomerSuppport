"""Dispatcher API tests against a real database, in dry-run mode."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from support_common.enums import Channel, TicketStatus
from support_common.errors import DispatchFailed
from support_common.models import Ticket, TicketFeedback, TicketMessage
from support_common.schemas import DispatchRequest, DispatchResult

from dispatcher import main as dispatcher_main
from dispatcher.channels import DeliveryChannel, LogChannel

pytestmark = pytest.mark.integration

API_KEY = "test-key"


class FailingChannel(DeliveryChannel):
    channel = Channel.EMAIL

    async def send(self, request: DispatchRequest) -> DispatchResult:
        raise DispatchFailed("smtp refused the connection")

    async def healthy(self) -> bool:
        return False


@pytest.fixture
async def seeded_ticket(app_engine: AsyncEngine) -> str:
    """Insert a resolved ticket for the dispatcher to act on."""
    factory = async_sessionmaker(app_engine, expire_on_commit=False)
    ticket_id = "TKT-ABCDEF123456"
    async with factory() as session:
        session.add(
            Ticket(
                ticket_id=ticket_id,
                subject="Cannot sign in",
                body="I forgot my password.",
                customer_external_id="email:dana@customer.example",
                customer_email="dana@customer.example",
                customer_tier="standard",
                channel=Channel.EMAIL,
                status=TicketStatus.RESOLVED,
                tags=[],
                metadata_json={},
            )
        )
        await session.commit()
    return ticket_id


@pytest.fixture
async def client(
    app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("API_KEY", API_KEY)
    from support_common.config import get_settings

    get_settings.cache_clear()

    from support_common.config import Settings

    settings = Settings(environment="ci", api_key=API_KEY, dispatch_dry_run=True)
    monkeypatch.setattr(
        dispatcher_main,
        "_channels",
        {channel: LogChannel(settings, channel) for channel in Channel},
    )

    transport = ASGITransport(app=dispatcher_main.app)
    async with AsyncClient(
        transport=transport, base_url="http://dispatcher", headers={"x-api-key": API_KEY}
    ) as http:
        yield http


async def rows(engine: AsyncEngine, model: Any) -> list[Any]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        return list((await session.execute(select(model))).scalars().all())


def dispatch_body(ticket_id: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "ticket_id": ticket_id,
        "channel": "email",
        "subject": "Re: Cannot sign in",
        "body": "Open the login page and choose Forgot password.",
        "recipient": "dana@customer.example",
        "escalated": False,
        "citations": [],
        "metadata": {},
    }
    body.update(overrides)
    return body


class TestDispatch:
    async def test_a_message_is_delivered_and_logged(
        self, client: AsyncClient, app_engine: AsyncEngine, seeded_ticket: str
    ) -> None:
        response = await client.post("/api/dispatch", json=dispatch_body(seeded_ticket))

        assert response.status_code == 200
        assert response.json()["delivered"] is True

        messages = await rows(app_engine, TicketMessage)
        assert len(messages) == 1
        assert messages[0].metadata_json["outbound"] is True
        assert messages[0].metadata_json["delivered"] is True

    async def test_a_failure_returns_200_with_delivered_false(
        self,
        client: AsyncClient,
        app_engine: AsyncEngine,
        seeded_ticket: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The caller has already committed the resolution; a 5xx would make it
        retry work that succeeded."""
        monkeypatch.setitem(dispatcher_main._channels, Channel.EMAIL, FailingChannel())

        response = await client.post("/api/dispatch", json=dispatch_body(seeded_ticket))

        assert response.status_code == 200
        payload = response.json()
        assert payload["delivered"] is False
        assert "smtp refused" in payload["error"]

        messages = await rows(app_engine, TicketMessage)
        assert messages[0].metadata_json["delivered"] is False

    async def test_an_unconfigured_channel_is_an_error(
        self, client: AsyncClient, seeded_ticket: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dispatcher_main, "_channels", {})
        response = await client.post("/api/dispatch", json=dispatch_body(seeded_ticket))
        assert response.status_code == 502
        assert response.json()["error"] == "dispatch_failed"

    async def test_an_escalation_is_attributed_to_the_system(
        self, client: AsyncClient, app_engine: AsyncEngine, seeded_ticket: str
    ) -> None:
        await client.post(
            "/api/dispatch", json=dispatch_body(seeded_ticket, escalated=True)
        )
        from support_common.enums import MessageSender

        messages = await rows(app_engine, TicketMessage)
        assert messages[0].sender is MessageSender.SYSTEM


class TestFeedback:
    async def test_feedback_is_stored(
        self, client: AsyncClient, app_engine: AsyncEngine, seeded_ticket: str
    ) -> None:
        response = await client.post(
            "/api/feedback",
            json={
                "ticket_id": seeded_ticket,
                "satisfaction_score": 5,
                "comment": "Sorted it in one go, thanks.",
                "resolved_issue": True,
            },
        )
        assert response.status_code == 201
        assert response.json()["satisfaction_score"] == 5
        assert len(await rows(app_engine, TicketFeedback)) == 1

    async def test_resubmitting_replaces_the_previous_score(
        self, client: AsyncClient, app_engine: AsyncEngine, seeded_ticket: str
    ) -> None:
        """A customer changing their mind is an update, not a conflict."""
        await client.post(
            "/api/feedback", json={"ticket_id": seeded_ticket, "satisfaction_score": 2}
        )
        await client.post(
            "/api/feedback", json={"ticket_id": seeded_ticket, "satisfaction_score": 4}
        )

        feedback = await rows(app_engine, TicketFeedback)
        assert len(feedback) == 1
        assert feedback[0].satisfaction_score == 4

    async def test_a_low_score_reopens_a_resolved_ticket(
        self, client: AsyncClient, app_engine: AsyncEngine, seeded_ticket: str
    ) -> None:
        """A dissatisfied customer is the signal the automated answer was wrong."""
        await client.post(
            "/api/feedback",
            json={"ticket_id": seeded_ticket, "satisfaction_score": 1, "resolved_issue": False},
        )

        tickets = await rows(app_engine, Ticket)
        assert tickets[0].status is TicketStatus.REOPENED
        assert any("Reopened" in m.message for m in await rows(app_engine, TicketMessage))

    async def test_a_high_score_leaves_the_ticket_resolved(
        self, client: AsyncClient, app_engine: AsyncEngine, seeded_ticket: str
    ) -> None:
        await client.post(
            "/api/feedback", json={"ticket_id": seeded_ticket, "satisfaction_score": 5}
        )
        tickets = await rows(app_engine, Ticket)
        assert tickets[0].status is TicketStatus.RESOLVED

    async def test_feedback_for_an_unknown_ticket_is_a_404(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/feedback", json={"ticket_id": "TKT-DOESNOTEXIST", "satisfaction_score": 3}
        )
        assert response.status_code == 404

    async def test_an_out_of_range_score_is_rejected(
        self, client: AsyncClient, seeded_ticket: str
    ) -> None:
        response = await client.post(
            "/api/feedback", json={"ticket_id": seeded_ticket, "satisfaction_score": 9}
        )
        assert response.status_code == 422

    async def test_the_summary_aggregates_scores(
        self, client: AsyncClient, seeded_ticket: str
    ) -> None:
        await client.post(
            "/api/feedback", json={"ticket_id": seeded_ticket, "satisfaction_score": 4}
        )
        summary = (await client.get("/api/feedback/summary")).json()
        assert summary["responses"] == 1
        assert summary["average_score"] == pytest.approx(4.0)
        assert summary["distribution"] == {"4": 1}


class TestOps:
    async def test_channels_require_the_api_key(self, client: AsyncClient) -> None:
        response = await client.get("/api/channels", headers={"x-api-key": "wrong"})
        assert response.status_code == 401

    async def test_channels_report_their_implementation(self, client: AsyncClient) -> None:
        payload = (await client.get("/api/channels")).json()
        assert payload["email"]["implementation"] == "LogChannel"
        assert payload["email"]["healthy"] is True

    async def test_ready_reports_the_database(self, client: AsyncClient) -> None:
        payload = (await client.get("/ready")).json()
        assert payload["dependencies"]["database"] == "ok"

    async def test_dispatch_metrics_are_recorded(
        self, client: AsyncClient, seeded_ticket: str
    ) -> None:
        await client.post("/api/dispatch", json=dispatch_body(seeded_ticket))
        body = (await client.get("/metrics")).text
        assert "support_dispatches_total" in body
