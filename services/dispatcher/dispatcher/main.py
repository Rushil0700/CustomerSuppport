"""Response Dispatcher service (port 8004).

Delivers agent answers back to the customer on the channel the ticket arrived
on, and records the satisfaction feedback that tells us whether the automated
answers were actually any good.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from support_common.app import create_app
from support_common.database import check_database, dispose_engine, get_session, init_engine
from support_common.enums import Channel, MessageSender, TicketStatus
from support_common.errors import DispatchFailed, TicketNotFound
from support_common.logging import bind_ticket_id, get_logger
from support_common.metrics import DISPATCHES, FEEDBACK_SCORE
from support_common.models import Ticket, TicketFeedback, TicketMessage
from support_common.schemas import (
    DispatchRequest,
    DispatchResult,
    FeedbackCreate,
    FeedbackRead,
)
from support_common.security import require_api_key

from dispatcher.channels import DeliveryChannel, build_channels

log = get_logger(__name__)

SERVICE = "dispatcher"
VERSION = "0.1.0"

_channels: dict[Channel, DeliveryChannel] = {}


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    global _channels
    init_engine()
    _channels = build_channels()
    log.info("dispatcher.ready", channels=[c.value for c in _channels])
    yield
    await dispose_engine()


app = create_app(
    service=SERVICE,
    title="Response Dispatcher",
    description="Delivers resolutions to customers and records satisfaction feedback.",
    version=VERSION,
    lifespan=lifespan,
)

router = APIRouter(prefix="/api", tags=["dispatch"])


@router.post("/dispatch", response_model=DispatchResult, summary="Deliver a response")
async def dispatch(
    request: DispatchRequest,
    session: AsyncSession = Depends(get_session),
) -> DispatchResult:
    """Send one message on the ticket's original channel.

    Delivery failures are recorded and returned as ``delivered: false`` with a
    200 status - the caller has already committed the resolution, and a 5xx here
    would only make it retry work that succeeded.
    """
    bind_ticket_id(request.ticket_id)
    channel = _channels.get(request.channel)
    if channel is None:
        raise DispatchFailed(f"no delivery channel configured for {request.channel.value}")

    try:
        result = await channel.send(request)
    except DispatchFailed as exc:
        DISPATCHES.labels(request.channel.value, "failed").inc()
        log.error("dispatch.failed", channel=request.channel.value, error=exc.detail)
        await _record_outbound(session, request, delivered=False, error=exc.detail)
        return DispatchResult(
            ticket_id=request.ticket_id,
            channel=request.channel,
            delivered=False,
            error=exc.detail,
        )

    DISPATCHES.labels(request.channel.value, "delivered").inc()
    await _record_outbound(session, request, delivered=True, error=None)
    log.info(
        "dispatch.delivered",
        channel=request.channel.value,
        provider_message_id=result.provider_message_id,
    )
    return result


@router.post(
    "/feedback",
    response_model=FeedbackRead,
    summary="Record customer satisfaction",
    status_code=201,
)
async def submit_feedback(
    payload: FeedbackCreate,
    session: AsyncSession = Depends(get_session),
) -> FeedbackRead:
    """Store a 1-5 satisfaction score for a resolved ticket.

    Resubmitting replaces the previous score rather than erroring: a customer
    changing their mind is a legitimate update, not a conflict.
    """
    bind_ticket_id(payload.ticket_id)
    exists = await session.scalar(
        select(Ticket.ticket_id).where(Ticket.ticket_id == payload.ticket_id)
    )
    if exists is None:
        raise TicketNotFound(f"no ticket with id {payload.ticket_id}")

    statement = (
        pg_insert(TicketFeedback)
        .values(
            ticket_id=payload.ticket_id,
            satisfaction_score=payload.satisfaction_score,
            comment=payload.comment,
            resolved_issue=payload.resolved_issue,
        )
        .on_conflict_do_update(
            constraint="uq_feedback_ticket",
            set_={
                "satisfaction_score": payload.satisfaction_score,
                "comment": payload.comment,
                "resolved_issue": payload.resolved_issue,
            },
        )
        .returning(TicketFeedback)
    )
    record = (await session.execute(statement)).scalar_one()
    FEEDBACK_SCORE.observe(payload.satisfaction_score)

    # A dissatisfied customer on an auto-resolved ticket is the signal that the
    # answer was wrong; reopening puts it back in front of a human.
    if payload.satisfaction_score <= 2 or payload.resolved_issue is False:
        ticket = await session.scalar(select(Ticket).where(Ticket.ticket_id == payload.ticket_id))
        if ticket is not None and ticket.status is TicketStatus.RESOLVED:
            ticket.status = TicketStatus.REOPENED
            session.add(
                TicketMessage(
                    ticket_id=payload.ticket_id,
                    sender=MessageSender.SYSTEM,
                    message=(
                        f"Reopened after a satisfaction score of {payload.satisfaction_score}/5."
                    ),
                    metadata_json={"reopened_by": "feedback"},
                )
            )
            log.info("feedback.reopened_ticket", score=payload.satisfaction_score)

    await session.flush()
    return FeedbackRead.model_validate(record)


@router.get("/feedback/summary", summary="Satisfaction summary")
async def feedback_summary(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Average score, response count and distribution."""
    average, count = (
        await session.execute(select(func.avg(TicketFeedback.satisfaction_score), func.count()))
    ).one()
    distribution_rows = await session.execute(
        select(TicketFeedback.satisfaction_score, func.count()).group_by(
            TicketFeedback.satisfaction_score
        )
    )
    distribution: dict[int, int] = dict(distribution_rows.all())  # type: ignore[arg-type]
    return {
        "responses": count or 0,
        "average_score": round(float(average or 0), 3),
        "distribution": {str(score): n for score, n in sorted(distribution.items())},
    }


@router.get("/channels", summary="Channel configuration", dependencies=[Depends(require_api_key)])
async def channels() -> dict[str, Any]:
    """Which channels are wired up and whether each is currently reachable."""
    return {
        channel.value: {
            "implementation": type(impl).__name__,
            "healthy": await impl.healthy(),
        }
        for channel, impl in _channels.items()
    }


async def _record_outbound(
    session: AsyncSession,
    request: DispatchRequest,
    *,
    delivered: bool,
    error: str | None,
) -> None:
    """Log the outbound message against the ticket's conversation."""
    session.add(
        TicketMessage(
            ticket_id=request.ticket_id,
            sender=MessageSender.AGENT if not request.escalated else MessageSender.SYSTEM,
            message=request.body,
            metadata_json={
                "outbound": True,
                "channel": request.channel.value,
                "delivered": delivered,
                "error": error,
                **request.metadata,
            },
        )
    )
    await session.flush()


app.include_router(router)


@app.get("/ready", include_in_schema=False)
async def ready() -> JSONResponse:
    """Readiness: the database must be reachable to log deliveries."""
    database_ok = await check_database()
    return JSONResponse(
        status_code=200 if database_ok else 503,
        content={
            "status": "ok" if database_ok else "degraded",
            "service": SERVICE,
            "version": VERSION,
            "dependencies": {
                "database": "ok" if database_ok else "unavailable",
                "channels": sorted(c.value for c in _channels),
            },
        },
    )
