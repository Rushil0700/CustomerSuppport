# Production runbook

## Health checks

Every service exposes `/health` (liveness, no dependency checks) and `/ready`
(readiness, checks dependencies). Kubernetes uses both; a human debugging should
start with `/ready` since it names what's actually wrong:

```bash
curl -s http://ticket-receiver:8001/ready | python3 -m json.tool
curl -s http://rag-engine:8002/ready | python3 -m json.tool
curl -s http://agent:8003/ready | python3 -m json.tool
curl -s http://dispatcher:8004/ready | python3 -m json.tool
```

## Alerts and what to do about them

Definitions in [kubernetes/monitoring/alerts.yml](../kubernetes/monitoring/alerts.yml).

### `AutoResolutionRateBelowTarget`

Auto-resolution has dropped under half the 65% target for an hour.

1. Check `GET /api/stats` on the rag-engine — if `chunks` is near zero, the
   index is empty (see `KnowledgeBaseEmpty` below).
2. Check `GET /api/model` on the agent — if `present: false`, the configured
   model isn't pulled on the Ollama pods (`ollama pull <model>` there).
3. Check recent knowledge base changes — a bad regeneration or a bug in
   `scripts/generate_kb.py` can silently drop coverage. `make eval` catches this
   locally before it reaches production.

### `KnowledgeBaseEmpty`

The single most damaging silent failure: retrieval returns nothing and every
ticket escalates, at the model call's cost with none of its benefit.

```bash
kubectl -n support exec -it rag-engine-0 -- python -c \
  "import asyncio; from rag_engine.indexer import build_index; asyncio.run(build_index(reset=True))"
```

Or re-run the init container by deleting the pod (`kubectl -n support delete
pod rag-engine-0`) — it rebuilds the index before the pod is marked ready.

### `EscalationSpike` (reason=`llm_error`)

Ollama is failing. Every affected ticket still reaches a human — this is
degradation, not an outage — but check immediately:

```bash
kubectl -n support get pods -l app=ollama
kubectl -n support logs -l app=ollama --tail=100
kubectl -n support exec -it ollama-0 -- ollama list   # is the model still there?
```

Common causes: GPU OOM (model too large for the node's VRAM — check
`OLLAMA_MODEL` against the node's GPU memory), the model was never pulled after
a node replacement, or the daemon is up but overloaded (`OLLAMA_NUM_PARALLEL`
too high for the hardware).

### `ResolutionLatencyHigh`

p95 resolution time over 120s.

1. `GET /metrics` on the agent, look at `support_llm_call_duration_seconds` — if
   this is the bottleneck, Ollama is saturated. Check GPU utilization; consider
   adding an Ollama replica or reducing `AGENT_MAX_CONCURRENCY` so requests queue
   client-side instead of degrading every in-flight one.
2. Check `support_rag_query_duration_seconds` — a slow vector search usually
   means the Redis cache is down (`GET /ready` on rag-engine) and every query is
   hitting Chroma cold.

### `CostPerTicketAboveTarget`

Either inference got slower (see latency above) or throughput dropped so the
fixed platform cost is spread over fewer tickets — check
`support_tickets_received_total` for a volume drop before assuming a regression.

### `DispatchFailures`

Answers are being generated but not reaching customers.

```bash
curl -s http://dispatcher:8004/api/channels -H "x-api-key: $API_KEY" | python3 -m json.tool
```

- Slack: `healthy: false` usually means the bot token was revoked. Re-issue and
  update the `support-secrets` Secret.
- Email: check the SMTP relay is reachable from the cluster and credentials are
  current.

Delivery failures do **not** lose the resolution — it's committed to Postgres
before dispatch is attempted. Once the channel is fixed, resend from the stored
resolution rather than re-running the agent:

```bash
curl -X POST http://dispatcher:8004/api/dispatch -H "x-api-key: $API_KEY" \
  -d '{"ticket_id": "TKT-...", "channel": "email", "body": "...", ...}'
```

### `SatisfactionDropping`

Automated answers are landing badly on tickets the agent was confident about.
This is a knowledge base quality problem, not an infrastructure one. As an
immediate mitigation, raise `AGENT_CONFIDENCE_THRESHOLD` (the prod overlay
default is 0.75) while the underlying articles are fixed — a higher threshold
trades auto-resolution rate for accuracy.

## Common operational tasks

### Re-index after a knowledge base change

```bash
make kb                          # local
kubectl -n support exec rag-engine-0 -- \
  python -c "import asyncio; from rag_engine.indexer import build_index; asyncio.run(build_index(reset=False))"
```

`reset=False` is an incremental upsert — safe to run anytime. Use `reset=True`
only after removing or renaming articles, so stale chunks don't linger.

### Roll back a bad deploy

```bash
kubectl -n support rollout undo deployment/agent
kubectl -n support rollout undo deployment/ticket-receiver
kubectl -n support rollout undo deployment/dispatcher
kubectl -n support rollout undo statefulset/rag-engine
```

`deploy.yml` does this automatically on a failed smoke test.

### Change the model without downtime

1. `ollama pull <new-model>` on every Ollama pod (or bake it into the image via
   the StatefulSet's `postStart` hook).
2. Update `OLLAMA_MODEL` in the ConfigMap.
3. Rolling-restart the agent deployment: `kubectl -n support rollout restart
   deployment/agent`. The RAG engine and receiver are unaffected — only the
   agent talks to Ollama.
4. Run `make eval` against the new model before rolling it to 100% of traffic,
   since the confidence gate's retrieval-score calibration
   (`agent_service/confidence.py`) was tuned against `all-MiniLM-L6-v2`
   embeddings, not against the chat model — changing the chat model needs no
   recalibration, but changing `EMBEDDING_MODEL` does.

### Investigate one ticket

```bash
curl -s http://ticket-receiver:8001/api/tickets/TKT-XXXX | python3 -m json.tool
curl -s http://ticket-receiver:8001/api/tickets/TKT-XXXX/messages | python3 -m json.tool
```

The messages endpoint shows the full conversation including system messages for
dispatch failures, and each agent message's metadata carries the confidence
score and cited article ids.

### Force a ticket to be reprocessed

```bash
curl -X POST http://ticket-receiver:8001/api/tickets/TKT-XXXX/reprocess \
  -H "x-api-key: $API_KEY"
```

Resets status to `NEW` and re-queues it. Useful after fixing the knowledge base
article that should have answered it, or after an `llm_error` escalation once
Ollama recovers.
