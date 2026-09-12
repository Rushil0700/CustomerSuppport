---
id: error-err-sync-quota
title: ERR_SYNC_QUOTA: Sync paused: storage limit reached
category: errors
tags: [err_sync_quota, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_SYNC_QUOTA: Sync paused: storage limit reached

## What it means

The workspace used every byte of its plan allowance, including trash and version history.

## How to fix it

Empty trash, reduce version retention, archive finished projects, or upgrade. Sync resumes on its own within minutes of dropping below the limit.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
