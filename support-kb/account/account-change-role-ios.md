---
id: account-change-role-ios
title: Change a member's role (the iOS app)
category: account
tags: [ios, members, permissions, roles]
audience: customer
severity: normal
---

# Change a member's role (the iOS app)

## Symptom

Someone has too much or too little access.

## Cause

Roles are assigned per workspace: owner, admin, member, guest.

## Resolution

These steps are written for **the iOS app**. Force-quit by swiping up from the app switcher before retrying.

1. Settings > Members and open the person's row.
2. Pick the new role. Guests see only projects they are explicitly added to; members see all projects in the workspace.
3. Save. The change applies on the member's next request - no sign-out needed.

## Verify

The Members list shows the new role and the audit log records who changed it.

## When to escalate

Escalate when a role change does not take effect after five minutes.
