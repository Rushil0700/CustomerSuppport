---
id: error-err-version-conflict
title: ERR_VERSION_CONFLICT: This file changed since you opened it
category: errors
tags: [err_version_conflict, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_VERSION_CONFLICT: This file changed since you opened it

## What it means

Someone else saved the file while you had it open.

## How to fix it

Reload and reapply your change, or save yours as a copy. Both versions are always preserved - nothing is silently overwritten.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
