# Customer Support Automation (local LLM)

Auto-resolves support tickets using retrieval-augmented generation over a
knowledge base and a **locally hosted** LLM. No paid APIs: inference runs on
Ollama, embeddings run on `sentence-transformers`, and the vector store is
embedded Chroma. The whole stack runs on a laptop.

```
                 Slack / Email / Zendesk / API
                              │
                   ┌──────────▼──────────┐
                   │  Ticket Receiver    │  :8001  normalise, store, orchestrate
                   └──────────┬──────────┘
                              │  POST /api/process
                   ┌──────────▼──────────┐        ┌──────────────────┐
                   │      Agent          │ :8003 ─▶│  Ollama (local)  │
                   │  reason + tool call │        └──────────────────┘
                   └──────┬───────┬──────┘
              search_kb   │       │  resolve / escalate
                   ┌──────▼────┐  │
                   │ RAG Engine│  │ :8002  Chroma + MiniLM over 504 articles
                   └───────────┘  │
                                  ▼
                   ┌─────────────────────┐
                   │ Response Dispatcher │  :8004  Slack / email / API + feedback
                   └─────────────────────┘

            PostgreSQL (tickets, messages, resolutions, feedback)
            Redis (search cache)          Prometheus + Grafana
```

## What it actually does

A ticket arrives on any channel and is normalised to one shape. The agent is
given four tools — `search_kb`, `resolve_ticket`, `escalate`, `notify_customer` —
and reasons for up to five turns. It must search before it answers. When it
proposes an answer, a **confidence gate** re-scores it against measurable
evidence (retrieval strength, number of supporting articles, whether the answer
reuses the vocabulary of what was retrieved) and escalates anything below
threshold. Certain tickets — MFA lockouts, refunds outside policy, suspected
compromise, legal and erasure requests, anyone asking for a human — escalate
*before* the model is invoked at all.

The design assumption throughout: **an escalation is a correct outcome, a wrong
confident answer is not.** Every path through the agent produces a decision; a
ticket is never dropped.

## Quick start

Prerequisites: Python 3.11, Docker, and [Ollama](https://ollama.ai).

```bash
make setup            # virtualenv + dependencies + .env
make ollama           # verify Ollama and pull the configured model
make infra            # Postgres + Redis
make kb               # generate 504 KB articles and index them (~90s first run)
make up               # build and start all four services
make demo             # submit one ticket and watch it get answered
```

Then:

| | |
|---|---|
| Ticket Receiver | http://localhost:8001/docs |
| RAG Engine | http://localhost:8002/docs |
| Agent | http://localhost:8003/docs |
| Dispatcher | http://localhost:8004/docs |

> **macOS note.** Docker has no GPU passthrough, so run Ollama natively
> (`ollama serve`) rather than in a container; the compose file already points
> the services at `host.docker.internal:11434`. Postgres is published on
> **5433** so it does not collide with a Postgres installed on the host.

### Without Docker

```bash
make infra            # you still want Postgres and Redis
make migrate
make run-rag          # terminal 1
make run-agent        # terminal 2
make run-receiver     # terminal 3
make run-dispatcher   # terminal 4
```

## Measuring it

`scripts/evaluate.py` runs a labelled set of 20 tickets — 13 answerable from the
knowledge base, 7 that must reach a human — through the real agent, the real
index and the real model, and reports the numbers the project is judged on:

```bash
make eval             # the whole set (~15-20 min on CPU)
make eval-quick       # first five tickets
```

It reports auto-resolution rate, decision accuracy, **false-resolution rate**
(a must-escalate ticket answered automatically — the expensive mistake),
retrieval hit rate, latency, and cost per ticket.

Measured on `qwen3:8b`, CPU only, on an Apple Silicon laptop:

| Metric | Result | Target |
|---|---|---|
| Auto-resolution rate | **65.0%** (13/20) | 60–65% |
| Decision accuracy | **100%** (20/20) | — |
| Recall on answerable tickets | **100%** (13/13) | — |
| False-resolution rate | **0%** (0/7) | as low as possible |
| Mean confidence when resolving | 0.86 | ≥ 0.70 gate |
| Resolution time (mean / max) | 43s / 95s | ≤ 120s |
| Cost per ticket (mean / max) | $0.0012 / $0.0022 | ≤ $0.08 |
| Reasoning turns (mean) | 1.45 | ≤ 5 |

The 65% is the ceiling this set allows — the other 35% are the seven tickets
that *must* reach a human, and all seven did. Six of them escalated in **0.0s**
without invoking the model at all, because the pre-inference guard rails caught
them. Cost lands far under target because local inference costs only the compute
it occupies, and the model averages 1.45 turns per ticket.

The labelled set is deliberately harder than production traffic: it contains no
duplicate questions, whereas real support volume is extremely repetitive and
benefits from the Redis cache and from easy repeat questions.

## The knowledge base

504 Markdown articles across 12 categories describing a fictional SaaS, generated
deterministically by `scripts/generate_kb.py` from a curated catalogue of real
support scenarios (symptom → cause → numbered steps → escalation criteria).

```
account 64 · api 56 · billing 35 · errors 25 · faq 36 · getting-started 21
integrations 125 · mobile 6 · policies 17 · security 21 · troubleshooting 88
workflows 10
```

Edit `scripts/generate_kb.py`, not the files — regeneration overwrites them.
Re-index with `make kb`. Chunk ids are content hashes, so re-indexing unchanged
articles overwrites in place instead of accumulating duplicate vectors.

## Configuration

Everything is environment-driven; see [.env.example](.env.example) for the full
list. The settings that matter most:

| Variable | Default | Why you would change it |
|---|---|---|
| `OLLAMA_MODEL` | `qwen3:8b` | Any tool-calling model: `mistral`, `llama3.1:8b`. Models without native tool calling fall back to JSON-in-text automatically. |
| `AGENT_CONFIDENCE_THRESHOLD` | `0.70` | Raise it to escalate more and answer fewer tickets wrongly. Production overlay uses 0.75. |
| `AGENT_MAX_TURNS` | `5` | Reasoning budget per ticket. |
| `AGENT_MAX_CONCURRENCY` | `8` | In-flight inference per replica. Should match Ollama's `OLLAMA_NUM_PARALLEL`. |
| `EMBEDDING_PROVIDER` | `sentence_transformers` | `ollama` uses `nomic-embed-text` (768-dim, slightly better recall, needs the daemon). |
| `VECTOR_BACKEND` | `chroma` | `pinecone` for the cloud deployment; same interface. |
| `DISPATCH_DRY_RUN` | `true` | **Nothing is sent while this is true.** Set false to actually deliver. |

## Testing

```bash
make test             # everything
make test-unit        # no infrastructure required
make test-integration # needs Postgres
make cov              # coverage report
make lint             # ruff + mypy
```

Unit tests replace Ollama, Postgres, Redis and the embedding model with fakes,
so they run in under a second and need nothing installed. Integration tests use
a real Postgres and skip themselves when it is absent. The live model tests in
`tests/integration/test_agent_live.py` are marked `slow` and skip unless Ollama
is running with the configured model.

Load testing:

```bash
make load             # 500 concurrent users against ticket ingest
make load-search      # 200 users against the RAG engine
```

## Deployment

```bash
kubectl apply -k kubernetes/overlays/prod
```

The receiver, agent and dispatcher are Deployments with HPAs; the RAG engine is
a StatefulSet (each replica keeps its own Chroma index, rebuilt from
`support-kb` by an init container); Ollama is a StatefulSet pinned to GPU nodes
and is the real capacity constraint on the system. Only the receiver is exposed
publicly — it is the only service that needs to accept webhooks — and a
default-deny NetworkPolicy enforces the rest.

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) lints, type-checks,
runs the suite against real Postgres and Redis with an 80% coverage floor,
verifies the knowledge base and `database/schema.sql` are not stale, builds and
health-checks all four images, and validates the rendered manifests.
[deploy.yml](.github/workflows/deploy.yml) publishes images, runs migrations as
a Job, applies the overlay pinned to the commit SHA, smoke-tests, and rolls back
on failure.

## Monitoring

```bash
make monitoring       # Prometheus :9090, Grafana :3000
```

Every service exposes `/metrics`. The alert rules in
[kubernetes/monitoring/alerts.yml](kubernetes/monitoring/alerts.yml) encode the
project's own targets — auto-resolution rate, p95 resolution time, cost per
ticket, and the single most damaging silent failure, an empty vector index.

## Layout

```
services/
  ticket-receiver/   FastAPI ingest, channel adapters, orchestration pipeline
  rag-engine/        embeddings, vector store, chunking, retrieval
  agent/             Ollama client, tools, reasoning loop, confidence gate
  dispatcher/        Slack/email/API delivery, satisfaction feedback
libs/support_common/ config, ORM models, wire schemas, logging, metrics, cost
database/            generated schema.sql + Alembic migrations
support-kb/          504 generated Markdown articles
scripts/             generate_kb, seed_kb, seed_db, export_schema, evaluate, demo
kubernetes/          base manifests, prod overlay, monitoring config
tests/               unit (no infra), integration (Postgres), load (Locust)
docs/                architecture notes and the production runbook
```

## Documentation

- [docs/architecture.md](docs/architecture.md) — why the pieces are split the way they are, and the decisions behind the confidence gate
- [docs/runbook.md](docs/runbook.md) — what to do when it breaks
