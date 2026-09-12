---
id: error-err-path-too-long
title: ERR_PATH_TOO_LONG: Path exceeds the operating system limit
category: errors
tags: [err_path_too_long, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_PATH_TOO_LONG: Path exceeds the operating system limit

## What it means

The full path is longer than 260 characters, which Windows rejects.

## How to fix it

Shorten a parent folder name, or move the folder closer to the drive root. Enabling long path support in Windows also works but needs a policy change.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
