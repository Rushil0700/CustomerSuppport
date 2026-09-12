---
id: troubleshooting-permission-denied-ios
title: 'You do not have permission' on a file you should own (the iOS app)
category: troubleshooting
tags: [access, ios, permissions, roles]
audience: customer
severity: normal
---

# 'You do not have permission' on a file you should own (the iOS app)

## Symptom

An action is refused despite the user believing they have access.

## Cause

Permissions are inherited from the project; a guest role or a project-level override usually explains it.

## Resolution

These steps are written for **the iOS app**. Force-quit by swiping up from the app switcher before retrying.

1. Open the project and check your role in the header - guests cannot edit unless explicitly granted.
2. Ask a project admin to review **Project settings > Access**; a project override beats the workspace role.
3. Files in an archived project are read-only for everyone until it is unarchived.
4. If the workspace is in read-only mode for non-payment, every write is refused regardless of role.

## Verify

The action succeeds after the role or project access is corrected.

## When to escalate

Escalate when the role and project access both look correct and writes are still refused.
