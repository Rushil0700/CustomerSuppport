---
id: troubleshooting-update-failing-macos
title: The app will not update (the macOS desktop app)
category: troubleshooting
tags: [desktop, macos, update, version]
audience: customer
severity: normal
---

# The app will not update (the macOS desktop app)

## Symptom

The updater errors, or the version never changes.

## Cause

Insufficient permissions to write to the install directory, or a managed deployment that blocks self-update.

## Resolution

These steps are written for **the macOS desktop app**. Settings are stored in `~/Library/Application Support/AcmeCloud/config.json`.

1. Quit the app completely, including tray or menu bar icons.
2. Run the installer for the current version manually from acme.example/download - installing over the top preserves your data.
3. On a managed device, self-update is often disabled by policy; ask IT to push the new version.
4. Check available disk space; updates need roughly twice the app size.

## Verify

Help > About shows the current version number.

## When to escalate

Escalate with the updater log when a manual install also fails.
