---
id: troubleshooting-desktop-app-wont-start-windows
title: The desktop app will not start (the Windows desktop app)
category: troubleshooting
tags: [crash, desktop, startup, windows]
audience: customer
severity: normal
---

# The desktop app will not start (the Windows desktop app)

## Symptom

The app icon bounces or the window never appears.

## Cause

A corrupt local database, an OS permission that was revoked, or a half-completed update.

## Resolution

These steps are written for **the Windows desktop app**. Settings are stored in `%APPDATA%\AcmeCloud\config.json`.

1. Quit the app fully, including any tray or menu bar icon.
2. Rename the local database folder (do not delete it) so a fresh one is built: the path is in the platform note below.
3. Start the app and sign in. Your files are re-linked from the server; nothing local is lost.
4. If it still fails, reinstall the current version over the top - your data folder is untouched.

## Verify

The app opens to the file list and the sync badge turns green.

## When to escalate

Escalate with the application log when a clean reinstall does not help.
