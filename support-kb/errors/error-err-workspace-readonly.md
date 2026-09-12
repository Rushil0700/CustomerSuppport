---
id: error-err-workspace-readonly
title: ERR_WORKSPACE_READONLY: Workspace is read-only
category: errors
tags: [err_workspace_readonly, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_WORKSPACE_READONLY: Workspace is read-only

## What it means

Billing lapsed past the 14 day grace period, or an admin suspended writes deliberately.

## How to fix it

Settle the outstanding invoice under Settings > Billing. Write access returns within a minute of a successful charge.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
