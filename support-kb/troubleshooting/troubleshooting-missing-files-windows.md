---
id: troubleshooting-missing-files-windows
title: Files have disappeared (the Windows desktop app)
category: troubleshooting
tags: [files, missing, recovery, trash, windows]
audience: customer
severity: high
---

# Files have disappeared (the Windows desktop app)

## Symptom

A folder that had content now looks empty.

## Cause

Deleted by a collaborator, moved, filtered by selective sync, or the wrong workspace is open.

## Resolution

These steps are written for **the Windows desktop app**. Settings are stored in `%APPDATA%\AcmeCloud\config.json`.

1. Check the workspace switcher first - the same folder name often exists in two workspaces.
2. Open **Trash**; deletions are recoverable for 30 days with one click.
3. Open **Activity** and filter by the folder to see who moved or deleted what, and when.
4. Check Settings > Selective sync; an excluded folder is present on the server but hidden locally.

## Verify

The files are visible again in the expected folder on the web app, which is the source of truth.

## When to escalate

Escalate when Activity shows no deletion event and the files are absent from both Trash and the web app.
