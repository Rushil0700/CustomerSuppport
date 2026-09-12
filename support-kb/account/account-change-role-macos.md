---
id: account-change-role-macos
title: Change a member's role (the macOS desktop app)
category: account
tags: [macos, members, permissions, roles]
audience: customer
severity: normal
---

# Change a member's role (the macOS desktop app)

## Symptom

Someone has too much or too little access.

## Cause

Roles are assigned per workspace: owner, admin, member, guest.

## Resolution

These steps are written for **the macOS desktop app**. Settings are stored in `~/Library/Application Support/AcmeCloud/config.json`.

1. Settings > Members and open the person's row.
2. Pick the new role. Guests see only projects they are explicitly added to; members see all projects in the workspace.
3. Save. The change applies on the member's next request - no sign-out needed.

## Verify

The Members list shows the new role and the audit log records who changed it.

## When to escalate

Escalate when a role change does not take effect after five minutes.
