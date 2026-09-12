---
id: error-err-integration-token
title: ERR_INTEGRATION_TOKEN: Integration credentials expired
category: errors
tags: [err_integration_token, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_INTEGRATION_TOKEN: Integration credentials expired

## What it means

The OAuth grant was revoked, or the authorising user lost access in the third-party tool.

## How to fix it

Reconnect the integration under Settings > Integrations. Use a service account so staff turnover does not break it again.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
