---
id: troubleshooting-webhook-not-firing
title: Webhooks are not being delivered
category: troubleshooting
tags: [api, integrations, webhooks]
audience: customer
severity: normal
---

# Webhooks are not being delivered

## Symptom

The receiving endpoint gets nothing, or only some events.

## Cause

A non-2xx response disables an endpoint after repeated failures; a filter may also exclude the event type.

## Resolution

1. Settings > Developers > Webhooks shows the last delivery status and response code per endpoint.
2. An endpoint is disabled automatically after 100 consecutive failures - re-enable it once your receiver is fixed.
3. Confirm the event types you expect are selected; the default selection is narrow.
4. Your endpoint must answer within 10 seconds with a 2xx. Acknowledge first, process asynchronously.
5. Use **Replay** to re-send a stored delivery after fixing the receiver.

## Verify

A test delivery returns 200 and appears in your logs.

## When to escalate

Escalate when deliveries show as sent on our side but never reach a verified-reachable endpoint.
