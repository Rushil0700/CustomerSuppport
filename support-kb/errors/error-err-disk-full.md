---
id: error-err-disk-full
title: ERR_DISK_FULL: Not enough local disk space
category: errors
tags: [err_disk_full, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_DISK_FULL: Not enough local disk space

## What it means

The sync folder's drive has less free space than the pending download needs.

## How to fix it

Free space, move the sync folder to a larger drive, or use selective sync to exclude folders you do not need locally.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
