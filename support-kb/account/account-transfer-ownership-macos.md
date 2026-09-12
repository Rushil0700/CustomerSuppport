---
id: account-transfer-ownership-macos
title: Transfer workspace ownership (the macOS desktop app)
category: account
tags: [admin, macos, ownership, workspace]
audience: customer
severity: normal
---

# Transfer workspace ownership (the macOS desktop app)

## Symptom

The current owner is leaving and someone else must take over billing and administration.

## Cause

Exactly one member holds the owner role, which alone can change billing and delete the workspace.

## Resolution

These steps are written for **the macOS desktop app**. Settings are stored in `~/Library/Application Support/AcmeCloud/config.json`.

1. Sign in as the current owner.
2. Settings > Members, open the row of the new owner.
3. Choose **Make owner** and confirm. The new owner must already be an admin.
4. The previous owner is demoted to admin automatically.

## Verify

Settings > Members shows the owner badge against the new person.

## When to escalate

Escalate when the only owner has already left the company and cannot sign in; staff must verify domain control before reassigning.
