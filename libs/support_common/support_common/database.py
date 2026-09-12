"""Async SQLAlchemy engine and session management.

Services call :func:`init_engine` on startup, depend on :func:`get_session` in
their routes, and call :func:`dispose_engine` on shutdown.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from support_common.config import Settings, get_settings
from support_common.logging import get_logger

log = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(settings: Settings | None = None) -> AsyncEngine:
    """Create the process-wide engine. Idempotent."""
    global _engine, _session_factory
    if _engine is not None:
        return _engine

    settings = settings or get_settings()
    # NullPool would be right for serverless; we run long-lived pods, so a real
    # pool with pre-ping survives Postgres restarts and idle-connection reaping.
    _engine = create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
        echo=False,
        future=True,
    )
    _session_factory = async_sessionmaker(
        _engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    log.info("database.engine_initialised", pool_size=settings.db_pool_size)
    return _engine


def get_engine() -> AsyncEngine:
    """Return the engine, creating it on first use."""
    return _engine or init_engine()


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        init_engine()
    assert _session_factory is not None  # noqa: S101 - set by init_engine
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a session that commits on success.

    A route that raises leaves the transaction rolled back, so a failed write
    never half-applies across the several tables a ticket touches.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Same semantics as :func:`get_session`, for use outside request handlers."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_database() -> bool:
    """Cheap readiness probe."""
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # pragma: no cover - exercised in integration tests
        log.warning("database.healthcheck_failed", error=str(exc))
        return False


async def dispose_engine() -> None:
    """Close pooled connections on shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
