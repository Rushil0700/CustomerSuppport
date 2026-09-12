"""Shared pytest fixtures.

Unit tests run with no infrastructure: no Postgres, no Redis, no Ollama, no
embedding model. Anything that needs those is marked ``integration`` and skipped
unless the dependency is actually reachable.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest

# Set before any application import so the settings singleton picks them up.
os.environ.setdefault("ENVIRONMENT", "ci")
os.environ.setdefault("LOG_FORMAT", "console")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("DISPATCH_DRY_RUN", "true")
os.environ.setdefault("METRICS_ENABLED", "true")

from support_common.config import Settings, get_settings  # noqa: E402
from support_common.enums import Channel, TicketPriority  # noqa: E402
from support_common.schemas import (  # noqa: E402
    AgentRequest,
    Citation,
    CustomerRef,
    RetrievedDocument,
    SearchResponse,
    TicketCreate,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    """Stop a test that patches the environment from leaking into the next."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="ci",
        api_key="test-key",
        agent_confidence_threshold=0.70,
        agent_max_turns=5,
        dispatch_dry_run=True,
    )


@pytest.fixture
def ticket_payload() -> TicketCreate:
    return TicketCreate(
        subject="Cannot sign in",
        body="I forgot my password and the reset email never arrives.",
        customer=CustomerRef(
            external_id="email:dana@customer.example",
            email="dana@customer.example",
            name="Dana Okafor",
        ),
        channel=Channel.EMAIL,
        priority=TicketPriority.NORMAL,
        external_ref="<msg-001@customer.example>",
        tags=["email"],
    )


@pytest.fixture
def agent_request() -> AgentRequest:
    return AgentRequest(
        ticket_id="TKT-ABCDEF123456",
        subject="Cannot sign in",
        body="I forgot my password and the reset email never arrives. I checked spam.",
        channel=Channel.EMAIL,
    )


@pytest.fixture
def search_response() -> SearchResponse:
    """A realistic strong retrieval result."""
    return SearchResponse(
        query="password reset",
        results=[
            RetrievedDocument(
                doc_id="account-password-reset",
                title="Reset a forgotten password",
                source="account/account-password-reset.md",
                category="account",
                content=(
                    "Go to https://app.acme.example/login and choose Forgot password. "
                    "The link is valid for 60 minutes. If you signed up with SSO there "
                    "is no password to reset."
                ),
                score=0.78,
            ),
            RetrievedDocument(
                doc_id="troubleshooting-cannot-login",
                title="Cannot sign in although the password is correct",
                source="troubleshooting/troubleshooting-cannot-login.md",
                category="troubleshooting",
                content="Ten failed attempts locks sign-in for 15 minutes.",
                score=0.61,
            ),
        ],
        took_ms=12.0,
    )


@pytest.fixture
def strong_citations() -> list[Citation]:
    return [
        Citation(
            doc_id="account-password-reset",
            title="Reset a forgotten password",
            source="account/account-password-reset.md",
            score=0.78,
        ),
        Citation(
            doc_id="troubleshooting-cannot-login",
            title="Cannot sign in although the password is correct",
            source="troubleshooting/troubleshooting-cannot-login.md",
            score=0.61,
        ),
        Citation(
            doc_id="account-session-expired",
            title="Signed out repeatedly during the day",
            source="account/account-session-expired.md",
            score=0.52,
        ),
    ]


# --- Integration gating ------------------------------------------------------


async def _reachable(url: str) -> bool:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.get(url)
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def postgres_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL", "postgresql+asyncpg://support:support@localhost:5433/support"
    )


@pytest.fixture
async def db_session(postgres_url: str) -> AsyncIterator[Any]:
    """A session against a real Postgres, rolled back after the test.

    Skips when Postgres is not reachable, so ``pytest`` still passes on a
    machine with nothing running.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from support_common.models import Base

    engine = create_async_engine(postgres_url, poolclass=None)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"postgres unavailable: {exc}")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: requires Postgres/Redis/Ollama")
    config.addinivalue_line("markers", "slow: takes more than a few seconds")
