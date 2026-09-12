---
id: troubleshooting-search-missing-results-macos
title: Search does not find a file that exists (the macOS desktop app)
category: troubleshooting
tags: [files, index, macos, search]
audience: customer
severity: normal
---

# Search does not find a file that exists (the macOS desktop app)

## Symptom

A file is visible in the folder but does not appear in search.

## Cause

Indexing lag, an unindexed file type, or a filter left applied.

## Resolution

These steps are written for **the macOS desktop app**. Settings are stored in `~/Library/Application Support/AcmeCloud/config.json`.

1. Clear any active filters - a date or type filter persists between searches.
2. New and just-modified files are indexed within about five minutes; very large files take longer.
3. Only the file types in the supported-formats article are full-text searchable; everything else matches on filename only.
4. Search by filename to confirm the file is indexed at all.

## Verify

Searching a distinctive phrase from inside the file returns it.

## When to escalate

Escalate when a supported file type is still missing from search after an hour.
