---
id: integration-quickbooks-connect
title: Connect QuickBooks to Acme Cloud
category: integrations
tags: [integration, quickbooks, setup]
audience: customer
severity: normal
---

# Connect QuickBooks to Acme Cloud

## Before you start

You need the **admin** role in the Acme Cloud workspace, and permission to
install apps in QuickBooks. On the Free plan integrations are limited to one; Team
and above are unlimited.

## Steps

1. Settings > **Integrations** and find QuickBooks.
2. Choose **Connect**. You are redirected to QuickBooks to authorise access.
3. Review the requested permissions and approve.
4. Pick the Acme Cloud projects the integration may access. Start narrow - you
   can widen the scope later without reconnecting.
5. Choose **Save**. The first sync starts immediately and takes a few minutes.

## Verify

The integration card shows **Connected** with a recent 'Last synced' timestamp,
and a test event appears in Activity.

## When to escalate

Escalate if the authorisation redirect returns an error from QuickBooks, or if the
card stays on "Connecting" for more than ten minutes.
