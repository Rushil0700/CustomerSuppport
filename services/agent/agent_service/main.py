"""Agent service (port 8003).

Stateless by design: it takes a ticket in, reasons over the knowledge base with
the local model, and returns a decision. It owns no database tables, so it scales
horizontally with nothing but the Ollama capacity behind it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import JSONResponse

from support_common.app import create_app
from support_common.config import get_settings
from support_common.errors import UpstreamUnavailable
from support_common.logging import get_logger
from support_common.schemas import AgentRequest, AgentResult

from agent_service.agent import SupportAgent
from agent_service.tools import TOOL_SCHEMAS

log = get_logger(__name__)

SERVICE = "agent"
VERSION = "0.1.0"

_agent: SupportAgent | None = None


def get_agent() -> SupportAgent:
    if _agent is None:  # pragma: no cover - guarded by lifespan
        raise UpstreamUnavailable("agent not initialised")
    return _agent


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Check the model is present and warm it into memory."""
    global _agent
    settings = get_settings()
    _agent = SupportAgent(settings=settings)
    try:
        models = await _agent.llm.available_models()
        if not await _agent.llm.healthy():
            log.error(
                "agent.model_missing",
                configured=settings.ollama_model,
                available=models,
                hint=f"run `ollama pull {settings.ollama_model}`",
            )
        else:
            # A short generation loads the weights so the first real ticket does
            # not pay the model load time.
            await _agent.llm.chat([{"role": "user", "content": "Reply with: ready"}])
            log.info("agent.ready", model=settings.ollama_model)
    except Exception as exc:
        log.error("agent.warmup_failed", error=str(exc))
    yield
    if _agent is not None:
        await _agent.aclose()


app = create_app(
    service=SERVICE,
    title="Support Agent",
    description="Local LLM agent (Ollama) that resolves or escalates support tickets.",
    version=VERSION,
    lifespan=lifespan,
)

router = APIRouter(prefix="/api", tags=["agent"])


@router.post("/process", response_model=AgentResult, summary="Work a ticket to a decision")
async def process(request: AgentRequest, agent: SupportAgent = Depends(get_agent)) -> AgentResult:
    """Resolve or escalate one ticket.

    Always returns 200 with a decision - an escalation is a successful outcome,
    not an error, and the caller should treat it as such.
    """
    return await agent.handle(request)


@router.get("/tools", summary="Tool schemas exposed to the model")
async def tools() -> dict[str, object]:
    """Useful when debugging why a model is or is not calling a tool."""
    return {
        "tools": [schema["function"]["name"] for schema in TOOL_SCHEMAS],
        "schemas": TOOL_SCHEMAS,
    }


@router.get("/model", summary="Model configuration and availability")
async def model_info(agent: SupportAgent = Depends(get_agent)) -> dict[str, object]:
    settings = get_settings()
    try:
        available = await agent.llm.available_models()
    except Exception as exc:
        return {"configured": settings.ollama_model, "available": [], "error": str(exc)}
    return {
        "configured": settings.ollama_model,
        "available": available,
        "present": await agent.llm.healthy(),
        "host": settings.ollama_host,
        "max_turns": settings.agent_max_turns,
        "confidence_threshold": settings.agent_confidence_threshold,
        "native_tool_calling": agent.native_tool_calling,
    }


app.include_router(router)


@app.get("/ready", include_in_schema=False)
async def ready() -> JSONResponse:
    """Readiness: Ollama is reachable and the configured model is pulled."""
    agent = _agent
    llm_ok = await agent.llm.healthy() if agent else False
    rag_ok = await agent.tools.rag.healthy() if agent else False
    # The RAG engine is a hard dependency: without it the agent can only escalate.
    ok = llm_ok and rag_ok
    return JSONResponse(
        status_code=200 if ok else 503,
        content={
            "status": "ok" if ok else "degraded",
            "service": SERVICE,
            "version": VERSION,
            "dependencies": {
                "ollama": "ok" if llm_ok else "unavailable_or_model_missing",
                "rag-engine": "ok" if rag_ok else "unavailable",
            },
        },
    )
