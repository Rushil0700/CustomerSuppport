"""Fixtures for tests that need real infrastructure.

Every fixture skips rather than fails when its dependency is missing, so
``pytest`` still passes on a machine with nothing running. CI starts Postgres
and Redis as services, so these do run there.

The schema is created once per session over a *synchronous* connection, while
the async engine is built per test. pytest-asyncio gives each test its own event
loop, and an asyncpg connection pool cannot outlive the loop it was created on.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from support_common import database
from support_common.models import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://support:support@localhost:5433/support"
)
SYNC_DATABASE_URL = TEST_DATABASE_URL.replace("+asyncpg", "+psycopg2")

TABLES = "tickets, ticket_messages, ticket_resolutions, ticket_feedback"


@pytest.fixture(scope="session")
def schema() -> Iterator[None]:
    """Create the tables once, over a plain synchronous connection."""
    engine = create_engine(SYNC_DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT 1"))
            Base.metadata.create_all(connection)
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"postgres unavailable at {SYNC_DATABASE_URL}: {exc}")
    engine.dispose()
    yield


@pytest.fixture
def truncate(schema: None) -> Iterator[None]:
    """Empty the ticket tables before each test.

    Truncating is far quicker than recreating, and CASCADE deals with the
    foreign keys in a single statement.
    """
    engine = create_engine(SYNC_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    engine.dispose()
    yield


@pytest.fixture
async def engine(truncate: None) -> AsyncIterator[AsyncEngine]:
    """A fresh async engine bound to this test's event loop."""
    engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@pytest.fixture
async def app_engine(engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    """Point the services' module-level engine at the test database.

    The service code reaches the database through ``support_common.database``
    globals, so an app-level test has to replace them rather than pass a session.
    """
    await database.dispose_engine()
    database._engine = engine
    database._session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    yield engine
    database._engine = None
    database._session_factory = None


@pytest.fixture
async def redis_available() -> bool:
    """Skip a test when Redis is not reachable."""
    from support_common import cache

    if not await cache.healthy():
        pytest.skip("redis unavailable")
    return True
