"""Load test for the support automation platform.

Two workloads, selected by tag:

    # Ingest throughput - how many tickets can the front door absorb?
    locust -f tests/load/locustfile.py --host http://localhost:8001 \
           --tags ingest --users 500 --spawn-rate 50 --run-time 5m

    # Retrieval throughput - the RAG engine on its own.
    locust -f tests/load/locustfile.py --host http://localhost:8002 \
           --tags search --users 200 --spawn-rate 20 --run-time 5m

Ingest returns as soon as the ticket is committed, so it measures the receiver
and Postgres rather than the model. End-to-end resolution throughput is bounded
by Ollama, which is measured separately by scripts/evaluate.py - loading it with
Locust would only ever show the GPU saturating.

Headless with a pass/fail gate for CI:

    locust -f tests/load/locustfile.py --host http://localhost:8001 \
           --tags ingest --users 500 --spawn-rate 50 --run-time 3m \
           --headless --only-summary
"""

from __future__ import annotations

import os
import random
import uuid

from locust import HttpUser, between, events, tag, task
from locust.env import Environment
from locust.runners import MasterRunner

API_KEY = os.environ.get("API_KEY", "dev-local-key")

# Thresholds the run is judged against in headless mode.
MAX_P95_MS = float(os.environ.get("LOAD_MAX_P95_MS", "500"))
MAX_FAILURE_RATIO = float(os.environ.get("LOAD_MAX_FAILURE_RATIO", "0.01"))
MIN_RPS = float(os.environ.get("LOAD_MIN_RPS", "300"))

SUBJECTS = [
    "Cannot sign in", "Files stuck syncing", "Where is my invoice",
    "API returning 429", "Slack integration broken", "How many seats do we get",
    "Invite email never arrived", "How do I enable 2FA", "Storage is full",
    "Share link says not available", "Payment was declined",
    "Which file types can you preview", "How far back is version history",
    "Desktop app will not start", "Notifications stopped arriving",
]

BODIES = [
    "I forgot my password and the reset email never arrives. I have checked spam.",
    "Three files have shown the syncing spinner for two hours. Everything else works.",
    "Our finance team needs a PDF invoice for last month for expense reporting.",
    "Our integration started returning 429 rate_limited this morning.",
    "The Slack integration card shows 'Needs attention' and nothing comes through.",
    "We are on the Team plan - how many seats does that include and how are they counted?",
    "I invited a colleague three days ago and they never received the email.",
    "Our security team wants two-factor authentication enforced for everyone.",
    "We are getting 'storage limit reached' and sync has paused for the whole team.",
    "I sent a share link to a client and they see 'not available'. It worked yesterday.",
]

QUERIES = [
    "how do I reset my password",
    "files stuck syncing for hours",
    "refund policy for annual plans",
    "api rate limit 429 error",
    "slack integration stopped working",
    "how many seats are in the team plan",
    "invite email not received",
    "enable two factor authentication",
    "workspace out of storage",
    "share link expired",
    "download an invoice",
    "supported file types for preview",
]

CHANNELS = ["api", "email", "slack", "web"]


class TicketIngestUser(HttpUser):
    """Submits tickets through the public ingest API."""

    weight = 3
    wait_time = between(0.1, 0.5)

    @tag("ingest")
    @task(10)
    def submit_ticket(self) -> None:
        index = random.randrange(len(SUBJECTS))
        payload = {
            "subject": SUBJECTS[index],
            "body": BODIES[index % len(BODIES)],
            "customer": {
                "external_id": f"load:{uuid.uuid4().hex[:12]}",
                "email": f"user{random.randrange(100000)}@customer.example",
                "name": "Load Test",
                "tier": random.choice(["standard", "standard", "standard", "enterprise"]),
            },
            "channel": random.choice(CHANNELS),
            "priority": random.choice(["low", "normal", "normal", "high"]),
            # A unique ref per request, so deduplication does not mask throughput.
            "external_ref": f"load-{uuid.uuid4().hex}",
            "tags": ["load-test"],
            "metadata": {},
        }
        with self.client.post(
            "/api/tickets",
            json=payload,
            headers={"x-api-key": API_KEY},
            name="POST /api/tickets",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 201):
                response.success()
            else:
                response.failure(f"{response.status_code}: {response.text[:200]}")

    @tag("ingest")
    @task(1)
    def read_stats(self) -> None:
        self.client.get("/api/stats", name="GET /api/stats")

    @tag("ingest")
    @task(1)
    def health(self) -> None:
        self.client.get("/health", name="GET /health")


class SlackWebhookUser(HttpUser):
    """Simulates Slack event traffic.

    Only meaningful when SLACK_SIGNING_SECRET is empty, which disables signature
    checking - signing every request here would measure our HMAC, not the service.
    """

    weight = 1
    wait_time = between(0.2, 1.0)

    @tag("ingest", "slack")
    @task
    def slack_event(self) -> None:
        payload = {
            "team_id": "T_LOAD",
            "event": {
                "type": "message",
                "text": random.choice(BODIES),
                "user": f"U{random.randrange(100000):05d}",
                "channel": "C_LOAD",
                "ts": f"{random.random() * 1e9:.6f}",
            },
        }
        self.client.post(
            "/api/webhooks/slack", json=payload, name="POST /api/webhooks/slack"
        )


class SearchUser(HttpUser):
    """Hammers the RAG engine directly."""

    wait_time = between(0.05, 0.2)

    @tag("search")
    @task(9)
    def search(self) -> None:
        with self.client.post(
            "/api/search",
            json={"query": random.choice(QUERIES), "top_k": 5},
            name="POST /api/search",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"{response.status_code}")
            elif not response.json().get("results"):
                # A 200 with nothing in it is a failure for our purposes: it
                # means the index is empty or the score floor is too high.
                response.failure("no results returned")
            else:
                response.success()

    @tag("search")
    @task(1)
    def uncached_search(self) -> None:
        """Bypass Redis so the numbers reflect real vector search, not the cache."""
        self.client.post(
            "/api/search",
            params={"use_cache": "false"},
            json={"query": f"{random.choice(QUERIES)} {uuid.uuid4().hex[:6]}", "top_k": 5},
            name="POST /api/search (uncached)",
        )


@events.quitting.add_listener
def _assert_thresholds(environment: Environment, **_: object) -> None:
    """Fail the process when a headless run misses its targets."""
    if isinstance(environment.runner, MasterRunner) or environment.runner is None:
        return

    stats = environment.stats.total
    failures = stats.fail_ratio
    p95 = stats.get_response_time_percentile(0.95) or 0
    rps = stats.total_rps

    print(
        f"\nThresholds: failure ratio {failures:.2%} (max {MAX_FAILURE_RATIO:.2%}), "
        f"p95 {p95:.0f}ms (max {MAX_P95_MS:.0f}ms), rps {rps:.1f} (min {MIN_RPS:.0f})"
    )

    if failures > MAX_FAILURE_RATIO:
        print(f"FAIL: failure ratio {failures:.2%}")
        environment.process_exit_code = 1
    elif p95 > MAX_P95_MS:
        print(f"FAIL: p95 {p95:.0f}ms")
        environment.process_exit_code = 1
    elif rps < MIN_RPS:
        print(f"FAIL: throughput {rps:.1f} rps")
        environment.process_exit_code = 1
    else:
        print("PASS")
        environment.process_exit_code = 0
