"""Prometheus metrics shared by all services.

The counters here are the ones the project is judged on: auto-resolution rate,
end-to-end resolution latency, and cost per ticket. Defining them once means the
Grafana dashboards work regardless of which service reports the sample.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# --- Request-level -----------------------------------------------------------
REQUEST_COUNT = Counter(
    "support_http_requests_total",
    "HTTP requests handled.",
    ["service", "method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "support_http_request_duration_seconds",
    "HTTP request latency.",
    ["service", "method", "path"],
    buckets=(0.005, 0.025, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)

# --- Ticket pipeline ---------------------------------------------------------
TICKETS_RECEIVED = Counter(
    "support_tickets_received_total",
    "Tickets accepted by the receiver.",
    ["channel", "priority"],
)
TICKETS_RESOLVED = Counter(
    "support_tickets_resolved_total",
    "Tickets auto-resolved by the agent.",
    ["channel"],
)
TICKETS_ESCALATED = Counter(
    "support_tickets_escalated_total",
    "Tickets handed to a human.",
    ["channel", "reason"],
)
RESOLUTION_LATENCY = Histogram(
    "support_ticket_resolution_seconds",
    "Time from ticket receipt to resolution or escalation.",
    ["outcome"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800),
)
RESOLUTION_CONFIDENCE = Histogram(
    "support_resolution_confidence",
    "Agent confidence score at the moment of resolution.",
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0),
)

# --- LLM / RAG ---------------------------------------------------------------
LLM_CALLS = Counter(
    "support_llm_calls_total",
    "Calls to the local Ollama model.",
    ["model", "outcome"],
)
LLM_LATENCY = Histogram(
    "support_llm_call_duration_seconds",
    "Latency of a single Ollama chat completion.",
    ["model"],
    buckets=(0.25, 0.5, 1, 2, 5, 10, 20, 40, 80, 160),
)
LLM_TOKENS = Counter(
    "support_llm_tokens_total",
    "Tokens processed by the local model.",
    ["model", "kind"],  # kind: prompt | completion
)
AGENT_TURNS = Histogram(
    "support_agent_turns",
    "Reasoning turns used before the agent reached a decision.",
    buckets=(1, 2, 3, 4, 5, 6),
)
TOOL_CALLS = Counter(
    "support_agent_tool_calls_total",
    "Tool invocations made by the agent.",
    ["tool", "outcome"],
)
RAG_QUERIES = Counter(
    "support_rag_queries_total",
    "Knowledge base searches.",
    ["cache"],  # cache: hit | miss
)
RAG_LATENCY = Histogram(
    "support_rag_query_duration_seconds",
    "Vector search latency.",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2),
)
RAG_TOP_SCORE = Histogram(
    "support_rag_top_score",
    "Similarity score of the best matching document per query.",
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)
KB_DOCUMENTS = Gauge(
    "support_kb_documents",
    "Chunks currently indexed in the vector store.",
)

# --- Dispatch / feedback -----------------------------------------------------
DISPATCHES = Counter(
    "support_dispatches_total",
    "Outbound customer messages.",
    ["channel", "outcome"],
)
FEEDBACK_SCORE = Histogram(
    "support_feedback_score",
    "Customer satisfaction score (1-5).",
    buckets=(1, 2, 3, 4, 5),
)

# --- Cost --------------------------------------------------------------------
TICKET_COST = Histogram(
    "support_ticket_cost_usd",
    "Estimated compute cost of handling one ticket.",
    buckets=(0.01, 0.025, 0.05, 0.08, 0.1, 0.15, 0.25, 0.5),
)
