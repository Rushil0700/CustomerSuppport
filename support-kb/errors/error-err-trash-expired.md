---
id: error-err-trash-expired
title: ERR_TRASH_EXPIRED: Item is no longer recoverable
category: errors
tags: [err_trash_expired, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_TRASH_EXPIRED: Item is no longer recoverable

## What it means

The file has been in trash for more than 30 days and has been purged.

## How to fix it

Check whether an earlier version survives elsewhere, or whether the file exists on a device that was offline. Beyond 35 days it is gone from backups too.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
