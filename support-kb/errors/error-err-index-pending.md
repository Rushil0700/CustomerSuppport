---
id: error-err-index-pending
title: ERR_INDEX_PENDING: File not yet searchable
category: errors
tags: [err_index_pending, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_INDEX_PENDING: File not yet searchable

## What it means

Indexing runs a few minutes behind upload, and longer for very large files.

## How to fix it

Wait five minutes and search again. Search by filename works immediately.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
