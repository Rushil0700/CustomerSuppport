# Architecture

## The pipeline

```
ticket → normalise → store (NEW) → agent → confidence gate → resolve/escalate → dispatch → feedback
```

The receiver commits the ticket and returns before the agent runs. A customer
waiting on an HTTP response should not be held for the seconds a local model
takes to think; the agent runs as a background task and the dispatcher delivers
the answer when it is ready.

## Why four services and not one

Each boundary corresponds to something that scales, fails, or changes on its
own schedule:

- **Ticket Receiver** is I/O-bound and cheap. It scales on request volume.
- **RAG Engine** holds the vector index and the embedding model in memory. It
  scales on search volume and needs stable storage (a StatefulSet), not
  ephemeral pods.
- **Agent** does no I/O of its own beyond calling the other three services. It
  scales on concurrency, bounded by Ollama's real capacity, not CPU.
- **Dispatcher** is the one service with outbound side effects (Slack, SMTP)
  and therefore the one that needs dry-run protection and its own retry logic.

Splitting them means a knowledge base re-index does not require redeploying the
agent, and scaling ticket ingest for a traffic spike does not scale Ollama pods
that cost real GPU money.

## Why a confidence gate instead of trusting the model's own number

A local 7B model's self-reported confidence is not calibrated — asked "how sure
are you," it tends to answer "very," almost regardless of whether the retrieved
articles actually support the answer. Trusting that number directly would mean
the auto-resolution rate is really just "how often does the model feel
confident," which is not the same thing as "how often is the model right."

The gate in `agent_service/confidence.py` combines four signals:

1. **The model's claim** (40% weight) — it is evidence, just not sufficient evidence.
2. **Retrieval strength** (35%) — the top cosine similarity score, rescaled
   against what this embedding model actually produces on this corpus
   (calibrated empirically: ~0.55–0.85 for a genuine match, under ~0.28 is
   noise — not the textbook 0–1 range).
3. **Citation breadth** (15%) — how many distinct articles scored above a
   "genuinely relevant" floor.
4. **Surface grounding** (10%) — whether the answer's vocabulary overlaps with
   the cited articles' titles, which catches the specific failure mode of the
   model ignoring retrieval and writing a plausible-sounding generic reply.

Then multiplicative penalties override the weighted sum outright: no search at
all, no citations, an answer that hedges ("I think," "probably"), an answer
that asks a question (which can never be answered, since `resolve_ticket` ends
the conversation), or an answer under 25 words. Any of these should dominate
rather than average out — a confident-sounding hallucination with one weak
citation should not pass just because the model's own number was high.

**The gate's whole purpose** is that a model claiming 1.0 confidence with zero
supporting evidence must still fail it. `tests/unit/test_confidence.py::test_model_overconfidence_alone_cannot_pass_the_gate`
is the test that exists specifically to keep that property true.

## Why some tickets never reach the model

`agent_service/confidence.py::check_sensitive` pattern-matches the ticket text
*before* any inference: MFA lockouts without recovery codes, legal threats,
suspected account compromise, GDPR erasure requests, chargebacks, and anyone
asking for a human. These escalate in the time it takes to run a few regexes —
in the evaluation run, six of seven required escalations completed in 0.0
seconds.

This is not a performance optimisation. It is a policy decision: these
categories are not "the model wasn't confident enough," they are "a human must
handle this regardless of what any model would say," and encoding that as a
guard rail rather than a prompt instruction means it cannot be talked out of it
by a sufficiently persuasive ticket.

## Why retrieval treats the model's category guess as advisory

The `search_kb` tool lets the model optionally filter by category. Early
testing showed this actively hurting recall: given "I forgot my password," the
model would guess `category: troubleshooting`, which silently excluded the
`account/account-password-reset` article that actually answers the question —
and the agent escalated a ticket the knowledge base covered perfectly well.

The fix (`agent_service/tools.py::ToolRegistry._search_kb`) treats a
category-filtered search as a hint: if it returns nothing strong (top score
under 0.45), the tool silently retries without the filter and keeps whichever
result set scored higher. The model never sees the retry — from its
perspective, `search_kb` just returned good results.

## Why chunking is section-aware

`rag_engine/loader.py` splits on Markdown headings before splitting by size, so
a chunk boundary almost always falls at the start of a section rather than
mid-sentence. A retrieved chunk should read as a complete instruction, not a
fragment — "1. Go to Settings > Billing 2. Choose Request refund" is useful on
its own; "efund within 30 days of the initial purchase or the ren" is not.
Chunk ids are content hashes (`doc_id::index::sha1(content)[:8]`), so
re-indexing unchanged content overwrites the same vector rather than
accumulating duplicates — this matters because the knowledge base is
regenerated, not hand-edited, and every regeneration should leave the index
in the same state if nothing actually changed.

## Why per-document chunk diversity matters

A naive top-k search over chunks returns the 3-5 highest-scoring chunks, which
for a well-matched query are frequently 3-5 chunks of the *same* article. The
retriever caps this at two chunks per document
(`rag_engine/retriever.py::MAX_CHUNKS_PER_DOCUMENT`) so the agent's limited
context window is spent across distinct articles instead of restating one
article three times — this is what lets a single `search_kb` call surface both
the primary answer and a related edge case (e.g. the password-reset article and
the "cannot sign in for other reasons" article) instead of just the one
document the embedding happened to like most.

## Why tool calling has a text-JSON fallback

Ollama's native tool calling (`tools=` on `/api/chat`) only works with models
trained for it. `SupportAgent._chat` probes on the first call: if the response
contains no native tool call, it assumes the model does not support the
feature and switches the system prompt to instruct JSON-in-text
(`JSON_FALLBACK_INSTRUCTION`), then parses tool calls out of the response text
for the rest of the ticket (`ollama_client.py::extract_json`, which handles
fenced code blocks, bare objects, and objects embedded in prose with
brace-matching that respects string escapes). This is what lets the same agent
code run on `qwen3`, `mistral`, `llama3.1`, or a base model with no tool
training at all, with the same tool definitions.

## Why cost is modelled, not metered

Local inference has no per-token invoice. `support_common/cost.py` treats cost
as amortised compute: the GPU-hour rate divided across concurrent requests,
plus the always-on platform services' cost divided across ticket throughput.
This is the only honest way to report a "$X per ticket" figure for
self-hosted inference — it is directly comparable to what the same workload
would cost on a metered API, and it responds correctly to the levers that
actually change local-inference economics (concurrency, replica count,
instance choice) rather than to a number a vendor sets.

## What happens when things fail

- **Ollama is down or the model isn't pulled** → the LLM client raises
  `LLMError`, the agent escalates with reason `llm_error`, the customer still
  gets a holding message. Nothing is lost.
- **The RAG engine is unreachable** → `search_kb` reports the failure as a tool
  result rather than crashing the ticket; the model typically escalates with
  `no_kb_match` on the next turn.
- **The dispatcher can't deliver** (SMTP down, bad Slack token) → the
  resolution is already committed to Postgres before dispatch is attempted; a
  delivery failure logs a system message and returns `delivered: false` with a
  200, not a 500 — retrying would re-run work that already succeeded.
- **A webhook redelivers the same ticket** → `TicketRepository.create` uses
  `ON CONFLICT DO NOTHING` on `(channel, external_ref)` and returns the
  existing ticket, so Slack's or Zendesk's at-least-once delivery cannot create
  duplicate tickets or run the agent twice.
