---
id: integration-figma-connect
title: Connect Figma to Acme Cloud
category: integrations
tags: [figma, integration, setup]
audience: customer
severity: normal
---

# Connect Figma to Acme Cloud

## Before you start

You need the **admin** role in the Acme Cloud workspace, and permission to
install apps in Figma. On the Free plan integrations are limited to one; Team
and above are unlimited.

## Steps

1. Settings > **Integrations** and find Figma.
2. Choose **Connect**. You are redirected to Figma to authorise access.
3. Review the requested permissions and approve.
4. Pick the Acme Cloud projects the integration may access. Start narrow - you
   can widen the scope later without reconnecting.
5. Choose **Save**. The first sync starts immediately and takes a few minutes.

## Verify

The integration card shows **Connected** with a recent 'Last synced' timestamp,
and a test event appears in Activity.

## When to escalate

Escalate if the authorisation redirect returns an error from Figma, or if the
card stays on "Connecting" for more than ten minutes.
