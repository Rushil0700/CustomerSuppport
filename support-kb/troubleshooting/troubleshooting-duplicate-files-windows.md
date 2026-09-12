---
id: troubleshooting-duplicate-files-windows
title: Every file appears twice (the Windows desktop app)
category: troubleshooting
tags: [duplicates, import, sync, windows]
audience: customer
severity: normal
---

# Every file appears twice (the Windows desktop app)

## Symptom

The folder lists two copies of everything.

## Cause

Almost always a folder that was added to sync twice, or an import run a second time.

## Resolution

These steps are written for **the Windows desktop app**. Settings are stored in `%APPDATA%\AcmeCloud\config.json`.

1. Settings > Selective sync and check whether the same folder is mapped from two locations.
2. Check Settings > Import history for a repeated import.
3. Compare the two copies' Activity entries - the duplicate will show the import or sync that created it.
4. Delete one set. Trash holds them for 30 days if you get it wrong.

## Verify

A single copy of each file remains and the count matches the source.

## When to escalate

Escalate before deleting anything if the two copies have diverging content.
