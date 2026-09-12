---
id: error-err-file-too-large
title: ERR_FILE_TOO_LARGE: File exceeds the maximum size for this plan
category: errors
tags: [err_file_too_large, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_FILE_TOO_LARGE: File exceeds the maximum size for this plan

## What it means

The single-file limit is a hard per-plan ceiling checked before the upload starts.

## How to fix it

Split the file, compress it, or upgrade. Nothing is uploaded partially - the file is refused outright.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
