---
id: integration-webhooks-limits
title: Outgoing Webhooks integration: sync behaviour and limits
category: integrations
tags: [integration, limits, sync, webhooks]
audience: customer
severity: normal
---

# Outgoing Webhooks integration: sync behaviour and limits

## How often it syncs

Events flow within a minute in normal operation. After a reconnect or an outage
at either end, the integration replays from its last cursor, so nothing is lost -
but a large backlog can take an hour to drain.

## Rate limits

Outgoing Webhooks enforces its own API limits. When we are throttled the integration backs
off exponentially and retries; the card shows **Catching up** rather than an
error. This is expected and needs no action unless it persists for hours.

## What is not synced

- Items in the trash on either side.
- Content the authorising account cannot itself see - the integration never has
  more access than the person who connected it.
- Files above your plan's single-file size limit.
- Revisions older than the current one, unless the integration's card says otherwise.

## Deletions

Deletions propagate as deletions, not as permanent removals: the item lands in
trash on the receiving side and stays recoverable for 30 days. This is deliberate -
a misconfigured integration should not be able to destroy data irreversibly.

## Conflicts

When the same item changes on both sides between syncs, we keep both and mark
one as a conflicted copy. We never silently discard an edit.

## When to escalate

Escalate when the card has shown **Catching up** for more than four hours, or
when items that satisfy all the conditions above are still not syncing.
