"""Typed configuration loaded from the environment (and ``.env`` in dev).

A single ``Settings`` object is shared by all four services; each service simply
ignores the fields it does not use. Keeping one class means a value like
``AGENT_CONFIDENCE_THRESHOLD`` cannot drift between the agent and the dashboards
that report on it.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Application settings, populated from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- General ------------------------------------------------------------
    environment: Literal["local", "ci", "staging", "production"] = "local"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    # --- Database -----------------------------------------------------------
    database_url: str = "postgresql+asyncpg://support:support@localhost:5433/support"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # --- Cache --------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 3600

    # --- Ollama -------------------------------------------------------------
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    ollama_timeout_seconds: float = 120.0
    ollama_num_ctx: int = 8192
    ollama_temperature: float = 0.1
    ollama_keep_alive: str = "30m"

    # --- Embeddings ---------------------------------------------------------
    embedding_provider: Literal["sentence_transformers", "ollama"] = "sentence_transformers"
    embedding_model: str = "all-MiniLM-L6-v2"
    ollama_embedding_model: str = "nomic-embed-text"
    embedding_batch_size: int = 64

    # --- Vector store -------------------------------------------------------
    vector_backend: Literal["chroma", "pinecone"] = "chroma"
    chroma_persist_dir: Path = REPO_ROOT / "data" / "chroma"
    chroma_collection: str = "support_kb"
    pinecone_api_key: str = ""
    pinecone_index: str = "support-kb"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"

    # --- Knowledge base -----------------------------------------------------
    kb_dir: Path = REPO_ROOT / "support-kb"
    kb_chunk_size: int = 900
    kb_chunk_overlap: int = 150
    rag_top_k: int = 5
    rag_min_score: float = 0.25

    # --- Service discovery --------------------------------------------------
    ticket_receiver_url: str = "http://localhost:8001"
    rag_engine_url: str = "http://localhost:8002"
    agent_url: str = "http://localhost:8003"
    dispatcher_url: str = "http://localhost:8004"
    http_timeout_seconds: float = 30.0
    http_max_retries: int = 3

    # --- Agent --------------------------------------------------------------
    agent_max_turns: int = 5
    agent_confidence_threshold: float = 0.70
    agent_max_concurrency: int = 8

    # --- Dispatcher ---------------------------------------------------------
    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    slack_default_channel: str = "#support"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False
    smtp_from_email: str = "support@example.com"
    smtp_from_name: str = "Acme Support"
    dispatch_dry_run: bool = True

    # --- Inbound auth -------------------------------------------------------
    api_key: str = "dev-local-key"
    zendesk_webhook_secret: str = ""

    # --- Observability ------------------------------------------------------
    metrics_enabled: bool = True

    @field_validator("database_url")
    @classmethod
    def _require_async_driver(cls, value: str) -> str:
        """Guard against the classic footgun of handing a sync DSN to asyncpg."""
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @field_validator("agent_confidence_threshold")
    @classmethod
    def _confidence_in_range(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("agent_confidence_threshold must be between 0 and 1")
        return value

    @property
    def sync_database_url(self) -> str:
        """Sync DSN for Alembic, which does not run under an event loop."""
        return self.database_url.replace("+asyncpg", "+psycopg2")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def embedding_dimensions(self) -> int:
        """Vector width, needed up front when creating a Pinecone index."""
        known = {
            "all-MiniLM-L6-v2": 384,
            "all-mpnet-base-v2": 768,
            "nomic-embed-text": 768,
            "bge-small-en-v1.5": 384,
        }
        model = (
            self.ollama_embedding_model
            if self.embedding_provider == "ollama"
            else self.embedding_model
        )
        return known.get(model, 384)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached so that importing modules and FastAPI dependencies all observe the
    same object; call ``get_settings.cache_clear()`` in tests that patch env.
    """
    return Settings()
