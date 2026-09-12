"""Ticket Receiver service (port 8001).

The front door: accepts tickets from the API, Slack, email and Zendesk,
normalises them, stores them, and hands them to the agent in the background.
Also the read side - ticket lookup, conversation history and headline stats.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from support_common import cache
from support_common.app import create_app
from support_common.config import get_settings
from support_common.database import check_database, dispose_engine, get_session, init_engine
from support_common.enums import TicketStatus
from support_common.errors import SupportError
from support_common.logging import get_logger
from support_common.metrics import TICKETS_RECEIVED
from support_common.schemas import (
    TicketCreate,
    TicketMessageRead,
    TicketRead,
)
from support_common.security import (
    require_api_key,
    verify_slack_signature,
    verify_zendesk_signature,
)

from ticket_receiver.adapters import from_email, from_slack_event, from_zendesk
from ticket_receiver.pipeline import TicketPipeline
from ticket_receiver.repository import TicketRepository

log = get_logger(__name__)

SERVICE = "ticket-receiver"
VERSION = "0.1.0"

_pipeline: TicketPipeline | None = None


def get_pipeline() -> TicketPipeline:
    if _pipeline is None:  # pragma: no cover - guarded by lifespan
        raise SupportError("pipeline not initialised")
    return _pipeline


def get_repository(session: AsyncSession = Depends(get_session)) -> TicketRepository:
    return TicketRepository(session)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    global _pipeline
    init_engine()
    _pipeline = TicketPipeline()
    log.info("receiver.ready")
    yield
    if _pipeline is not None:
        await _pipeline.aclose()
    await cache.close()
    await dispose_engine()


app = create_app(
    service=SERVICE,
    title="Ticket Receiver",
    description="Accepts support tickets from every channel and routes them to the agent.",
    version=VERSION,
    lifespan=lifespan,
)

router = APIRouter(prefix="/api", tags=["tickets"])


async def _accept(
    payload: TicketCreate,
    repository: TicketRepository,
    background: BackgroundTasks,
    pipeline: TicketPipeline,
) -> JSONResponse:
    """Store a normalised ticket and queue it for the agent."""
    ticket, created = await repository.create(payload)

    if created:
        TICKETS_RECEIVED.labels(payload.channel.value, payload.priority.value).inc()
        # Committed by the session dependency before the background task runs,
        # so the pipeline always finds the row it is asked to process.
        background.add_task(pipeline.process, ticket.ticket_id)

    return JSONResponse(
        status_code=201 if created else 200,
        content={
            "ticket_id": ticket.ticket_id,
            "status": ticket.status.value,
            "created": created,
            "message": (
                "Ticket accepted and queued for processing."
                if created
                else "Ticket already exists for this reference."
            ),
        },
    )


@router.post(
    "/tickets",
    summary="Submit a ticket",
    dependencies=[Depends(require_api_key)],
    status_code=201,
)
async def create_ticket(
    payload: TicketCreate,
    background: BackgroundTasks,
    repository: TicketRepository = Depends(get_repository),
    pipeline: TicketPipeline = Depends(get_pipeline),
) -> JSONResponse:
    """Direct API ingest for an already-normalised ticket."""
    return await _accept(payload, repository, background, pipeline)


@router.post("/webhooks/slack", summary="Slack Events API webhook")
async def slack_webhook(
    request: Request,
    background: BackgroundTasks,
    x_slack_request_timestamp: Annotated[str, Header()] = "",
    x_slack_signature: Annotated[str, Header()] = "",
    repository: TicketRepository = Depends(get_repository),
    pipeline: TicketPipeline = Depends(get_pipeline),
) -> Any:
    """Receive Slack messages and app mentions."""
    body = await request.body()
    verify_slack_signature(body, x_slack_request_timestamp, x_slack_signature)
    payload = await request.json()

    # Slack verifies a new endpoint by posting a challenge it expects echoed back.
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    event = payload.get("event") or {}
    # Ignore our own replies and edits, or the bot would answer itself forever.
    if event.get("bot_id") or event.get("subtype") in {"bot_message", "message_changed"}:
        return {"ok": True, "ignored": "bot_or_edit"}
    if event.get("type") not in {"message", "app_mention"}:
        return {"ok": True, "ignored": event.get("type")}

    try:
        ticket = from_slack_event(payload)
    except ValueError as exc:
        log.info("slack.unparseable", error=str(exc))
        return {"ok": True, "ignored": str(exc)}

    return await _accept(ticket, repository, background, pipeline)


@router.post("/webhooks/email", summary="Inbound email webhook")
async def email_webhook(
    request: Request,
    background: BackgroundTasks,
    repository: TicketRepository = Depends(get_repository),
    pipeline: TicketPipeline = Depends(get_pipeline),
    _: None = Depends(require_api_key),
) -> JSONResponse:
    """Accept a raw RFC 822 message from the mail gateway.

    Takes either ``text/plain`` (the raw message) or a JSON body with a ``raw``
    field, which is what most inbound-parse providers send.
    """
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        payload = await request.json()
        raw = payload.get("raw") or payload.get("message") or ""
    else:
        raw = (await request.body()).decode("utf-8", "replace")

    if not raw.strip():
        raise SupportError("empty email payload", status_code=400)

    ticket = from_email(raw)
    return await _accept(ticket, repository, background, pipeline)


@router.post("/webhooks/zendesk", summary="Zendesk webhook")
async def zendesk_webhook(
    request: Request,
    background: BackgroundTasks,
    x_zendesk_webhook_signature: Annotated[str, Header()] = "",
    x_zendesk_webhook_signature_timestamp: Annotated[str, Header()] = "",
    repository: TicketRepository = Depends(get_repository),
    pipeline: TicketPipeline = Depends(get_pipeline),
) -> JSONResponse:
    """Receive newly created Zendesk tickets."""
    body = await request.body()
    verify_zendesk_signature(
        body, x_zendesk_webhook_signature, x_zendesk_webhook_signature_timestamp
    )
    ticket = from_zendesk(await request.json())
    return await _accept(ticket, repository, background, pipeline)


@router.get("/tickets/{ticket_id}", response_model=TicketRead, summary="Fetch a ticket")
async def get_ticket(
    ticket_id: str, repository: TicketRepository = Depends(get_repository)
) -> TicketRead:
    return TicketRead.model_validate(await repository.get(ticket_id))


@router.get(
    "/tickets/{ticket_id}/messages",
    response_model=list[TicketMessageRead],
    summary="Conversation history",
)
async def get_messages(
    ticket_id: str, repository: TicketRepository = Depends(get_repository)
) -> list[TicketMessageRead]:
    await repository.get(ticket_id)  # 404 rather than an empty list for an unknown id
    return [TicketMessageRead.model_validate(m) for m in await repository.messages(ticket_id)]


@router.get("/tickets", response_model=list[TicketRead], summary="List recent tickets")
async def list_tickets(
    limit: int = Query(default=50, ge=1, le=200),
    status: TicketStatus | None = None,
    repository: TicketRepository = Depends(get_repository),
) -> list[TicketRead]:
    tickets = await repository.list_recent(limit=limit, status=status)
    return [TicketRead.model_validate(t) for t in tickets]


@router.post(
    "/tickets/{ticket_id}/reprocess",
    summary="Re-run the agent on a ticket",
    dependencies=[Depends(require_api_key)],
)
async def reprocess(
    ticket_id: str,
    background: BackgroundTasks,
    repository: TicketRepository = Depends(get_repository),
    pipeline: TicketPipeline = Depends(get_pipeline),
) -> dict[str, str]:
    """Retry a ticket that failed, or re-run one after a knowledge base fix."""
    await repository.get(ticket_id)
    await repository.set_status(ticket_id, TicketStatus.NEW)
    background.add_task(pipeline.process, ticket_id)
    return {"ticket_id": ticket_id, "status": "queued"}


@router.get("/stats", summary="Auto-resolution rate, latency and cost")
async def stats(repository: TicketRepository = Depends(get_repository)) -> dict[str, Any]:
    """The numbers the project is measured on."""
    return await repository.stats()


app.include_router(router)


@app.get("/ready", include_in_schema=False)
async def ready() -> JSONResponse:
    """Readiness: the database must be reachable; the agent need not be."""
    settings = get_settings()
    database_ok = await check_database()
    agent_ok = await _pipeline.agent.healthy() if _pipeline else False
    return JSONResponse(
        status_code=200 if database_ok else 503,
        content={
            "status": "ok" if database_ok else "degraded",
            "service": SERVICE,
            "version": VERSION,
            "environment": settings.environment,
            "dependencies": {
                "database": "ok" if database_ok else "unavailable",
                "agent": "ok" if agent_ok else "unavailable",
                "cache": "ok" if await cache.healthy() else "unavailable",
            },
        },
    )
