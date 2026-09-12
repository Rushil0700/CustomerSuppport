---
id: integration-webhooks-troubleshoot
title: Outgoing Webhooks integration has stopped working
category: integrations
tags: [integration, troubleshooting, webhooks]
audience: customer
severity: normal
---

# Outgoing Webhooks integration has stopped working

## Symptom

Events stop flowing, or the integration card shows **Needs attention**.

## Cause

In order of likelihood: the authorising user lost access in Outgoing Webhooks or left the
company, the OAuth grant was revoked by an administrator, the token expired
after a password change, or a permission scope changed on the Outgoing Webhooks side.

## Resolution

1. Open Settings > Integrations > Outgoing Webhooks and read the error on the card - it
   names the failing scope where Outgoing Webhooks tells us.
2. Choose **Reconnect** and re-authorise. This fixes expired and revoked tokens,
   which is the large majority of cases.
3. Confirm the authorising account still exists and retains access in Outgoing Webhooks.
   Prefer a service account over a person's account so staff turnover cannot
   break the integration.
4. Check Outgoing Webhooks's own status page - an outage there presents identically.
5. Re-select the projects in scope; a deleted project leaves a dangling mapping.

## Verify

The card returns to **Connected** and a test event appears in Activity within a
minute.

## When to escalate

Escalate when a reconnect by a confirmed-admin account fails twice, or when
events flow one way but not the other.
