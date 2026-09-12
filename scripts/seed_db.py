#!/usr/bin/env python
"""Create the database schema and optionally load sample tickets.

    python scripts/seed_db.py                 # create tables only
    python scripts/seed_db.py --tickets 25    # also insert sample tickets
    python scripts/seed_db.py --drop          # drop everything first

The sample tickets span every channel and a mix of easy, ambiguous and
must-escalate cases, which makes them a reasonable smoke test for the whole
pipeline rather than just the database.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "ticket-receiver"))

from support_common.config import get_settings  # noqa: E402
from support_common.database import dispose_engine, get_engine, session_scope  # noqa: E402
from support_common.enums import Channel, TicketPriority  # noqa: E402
from support_common.logging import configure_logging  # noqa: E402
from support_common.models import Base  # noqa: E402
from support_common.schemas import CustomerRef, TicketCreate  # noqa: E402

from ticket_receiver.repository import TicketRepository  # noqa: E402

# (subject, body, channel, priority) - the first six should be auto-resolvable
# from the knowledge base, the last three must escalate.
SAMPLE_TICKETS: list[tuple[str, str, Channel, TicketPriority]] = [
    ("Can't log in", "I forgot my password and the reset email never arrives. I've checked spam.",
     Channel.EMAIL, TicketPriority.NORMAL),
    ("Files stuck syncing", "Three files have been showing the syncing spinner for two hours. Everything else works.",
     Channel.SLACK, TicketPriority.HIGH),
    ("How do I add teammates?", "We just signed up on the Team plan. How do I invite the rest of my team?",
     Channel.WEB, TicketPriority.LOW),
    ("Getting 429 from the API", "Our integration started returning 429 rate_limited this morning. What are the limits?",
     Channel.API, TicketPriority.HIGH),
    ("Invoice for accounting", "Finance needs a PDF invoice for last month. Where do I download it?",
     Channel.EMAIL, TicketPriority.LOW),
    ("Slack integration stopped", "Our Slack integration shows 'Needs attention' and no messages are coming through.",
     Channel.SLACK, TicketPriority.NORMAL),
    ("Refund for annual plan", "We paid for a year in March and want a full refund now. Please process it today.",
     Channel.EMAIL, TicketPriority.URGENT),
    ("Lost my 2FA device", "My phone was stolen and I don't have my recovery codes. I need access immediately.",
     Channel.EMAIL, TicketPriority.URGENT),
    ("I think we've been hacked", "There are share links in our workspace nobody recognises. Please help urgently.",
     Channel.SLACK, TicketPriority.URGENT),
]

FIRST_NAMES = ["Alex", "Sam", "Priya", "Jordan", "Mei", "Tomas", "Aisha", "Noah", "Lena", "Kofi"]
LAST_NAMES = ["Patel", "Nguyen", "Silva", "Okafor", "Kim", "Rossi", "Dubois", "Haddad", "Novak"]


async def create_schema(drop: bool) -> None:
    engine = get_engine()
    async with engine.begin() as connection:
        if drop:
            await connection.run_sync(Base.metadata.drop_all)
            print("Dropped existing tables.")
        await connection.run_sync(Base.metadata.create_all)
    print("Schema created.")


async def insert_tickets(count: int, seed: int) -> list[str]:
    """Insert ``count`` sample tickets, cycling through the catalogue."""
    rng = random.Random(seed)
    created: list[str] = []

    async with session_scope() as session:
        repository = TicketRepository(session)
        for index in range(count):
            subject, body, channel, priority = SAMPLE_TICKETS[index % len(SAMPLE_TICKETS)]
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
            handle = name.lower().replace(" ", ".")
            payload = TicketCreate(
                subject=subject,
                body=body,
                customer=CustomerRef(
                    external_id=f"seed:{handle}:{index}",
                    email=f"{handle}@customer.example",
                    name=name,
                    tier=rng.choice(["standard", "standard", "standard", "enterprise"]),
                ),
                channel=channel,
                priority=priority,
                external_ref=f"seed-{seed}-{index}",
                tags=["seed"],
                metadata={"seeded": True},
            )
            ticket, was_created = await repository.create(payload)
            if was_created:
                created.append(ticket.ticket_id)
    return created


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    configure_logging("seed-db", level="WARNING", fmt="console")
    print(f"Database: {settings.database_url.split('@')[-1]}")

    try:
        await create_schema(args.drop)
        if args.tickets:
            created = await insert_tickets(args.tickets, args.seed)
            print(f"Inserted {len(created)} tickets.")
            for ticket_id in created[:10]:
                print(f"  {ticket_id}")
            if len(created) > 10:
                print(f"  ... and {len(created) - 10} more")
            print(
                "\nThese are stored but not processed. To run them through the agent:\n"
                "  curl -XPOST -H 'X-API-Key: dev-local-key' "
                "http://localhost:8001/api/tickets/<TICKET_ID>/reprocess"
            )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "Is Postgres running? Try `docker compose up -d postgres`.",
            file=sys.stderr,
        )
        return 1
    finally:
        await dispose_engine()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drop", action="store_true", help="drop all tables first")
    parser.add_argument("--tickets", type=int, default=0, help="how many sample tickets to insert")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducible data")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
