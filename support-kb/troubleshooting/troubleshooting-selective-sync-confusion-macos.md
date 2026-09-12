---
id: troubleshooting-selective-sync-confusion-macos
title: Files exist on the web app but not on this device (the macOS desktop app)
category: troubleshooting
tags: [desktop, files, macos, selective-sync]
audience: customer
severity: normal
---

# Files exist on the web app but not on this device (the macOS desktop app)

## Symptom

A folder is visible in the browser but missing from the local sync folder.

## Cause

Selective sync excludes it, or the folder is set to online-only.

## Resolution

These steps are written for **the macOS desktop app**. Settings are stored in `~/Library/Application Support/AcmeCloud/config.json`.

1. Settings > **Selective sync** and tick the folder.
2. Check the folder's icon: a cloud means online-only, a solid dot means downloaded.
3. Right-click and choose **Make available offline** to force a download.
4. Confirm there is enough local disk space; an excluded folder is sometimes the result of an earlier out-of-space event.

## Verify

The folder appears locally with a solid green dot.

## When to escalate

Escalate when the folder is ticked, disk space is ample, and it still does not appear after a restart.
