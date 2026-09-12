---
id: troubleshooting-offline-access-windows
title: Access files without a connection (the Windows desktop app)
category: troubleshooting
tags: [mobile, offline, sync, windows]
audience: customer
severity: normal
---

# Access files without a connection (the Windows desktop app)

## Symptom

Files are unavailable on a plane or in a dead spot.

## Cause

By default files are streamed on demand to save disk space.

## Resolution

These steps are written for **the Windows desktop app**. Settings are stored in `%APPDATA%\AcmeCloud\config.json`.

1. Right-click a file or folder and choose **Make available offline** before you lose connectivity.
2. On mobile, open the file once and tap the pin icon.
3. Offline copies sync their changes when you reconnect; conflicts are handled as conflicted copies.
4. Settings > Storage shows how much space offline content is using.

## Verify

The item shows a solid green dot rather than a cloud icon.

## When to escalate

Escalate when a pinned file is still unavailable offline.
