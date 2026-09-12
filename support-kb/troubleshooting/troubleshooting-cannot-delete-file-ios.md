---
id: troubleshooting-cannot-delete-file-ios
title: A file will not delete (the iOS app)
category: troubleshooting
tags: [delete, files, ios, locks]
audience: customer
severity: normal
---

# A file will not delete (the iOS app)

## Symptom

Deleting returns an error or the file reappears.

## Cause

A retention hold, an active lock, or a second device re-uploading it.

## Resolution

These steps are written for **the iOS app**. Force-quit by swiping up from the app switcher before retrying.

1. Check whether the file is locked - unlock it first from the right-click menu.
2. Projects under legal hold (Enterprise) refuse deletion by design; an admin must lift the hold.
3. If it reappears, another device still has the old copy and is re-uploading it. Delete on the web app and let every device sync before retrying.
4. Archived projects are read-only; unarchive before deleting.

## Verify

The file is in Trash and does not return after all devices have synced.

## When to escalate

Escalate when no lock, hold or archive applies and deletion still errors.
