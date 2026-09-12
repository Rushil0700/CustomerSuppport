---
id: error-err-invalid-chars
title: ERR_INVALID_CHARS: File name contains unsupported characters
category: errors
tags: [err_invalid_chars, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_INVALID_CHARS: File name contains unsupported characters

## What it means

The name contains one of \\ / : * ? " < > |, which at least one supported platform refuses.

## How to fix it

Rename the file. Until you do, the rest of that folder's queue stays blocked behind it.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
