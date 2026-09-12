---
id: troubleshooting-file-conflict-macos
title: Conflicted copies keep appearing (the macOS desktop app)
category: troubleshooting
tags: [conflict, files, macos, sync]
audience: customer
severity: normal
---

# Conflicted copies keep appearing (the macOS desktop app)

## Symptom

Files named 'report (conflicted copy 2024-05-02)' multiply.

## Cause

Two devices edited the same file before either finished syncing - common with always-open documents and with folders shared into a second sync tool.

## Resolution

These steps are written for **the macOS desktop app**. Settings are stored in `~/Library/Application Support/AcmeCloud/config.json`.

1. Open both versions and merge by hand; we never discard either side.
2. Never point a second sync tool (OneDrive, iCloud Drive, Dropbox) at an Acme Cloud folder. This is the single largest cause.
3. Close documents when you finish rather than leaving them open overnight.
4. For files edited by several people at once, use a shared project and in-app editing, which locks per paragraph.

## Verify

No new conflicted copies appear over 24 hours of normal use.

## When to escalate

Escalate if conflicts appear on a file only ever edited on one device.
