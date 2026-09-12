---
id: error-err-sync-locked
title: ERR_SYNC_LOCKED: Sync paused: file locked by another application
category: errors
tags: [err_sync_locked, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_SYNC_LOCKED: Sync paused: file locked by another application

## What it means

Another program holds an exclusive lock on the file - Office and Adobe applications do this while a document is open.

## How to fix it

Close the application holding the file. The transfer resumes within a minute without any further action.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
