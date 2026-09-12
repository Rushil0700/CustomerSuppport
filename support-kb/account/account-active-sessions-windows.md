---
id: account-active-sessions-windows
title: Review and end active sessions (the Windows desktop app)
category: account
tags: [account, security, sessions, windows]
audience: customer
severity: high
---

# Review and end active sessions (the Windows desktop app)

## Symptom

A user wants to check where their account is signed in.

## Cause

Sessions persist for up to 30 days per device.

## Resolution

These steps are written for **the Windows desktop app**. Settings are stored in `%APPDATA%\AcmeCloud\config.json`.

1. Settings > Security > **Active sessions**.
2. Each row shows the device, approximate location from the IP address, and last activity.
3. Choose **Sign out** on any session you do not recognise.
4. **Sign out everywhere** ends every session including the current one - the right first move if compromise is suspected.

## Verify

Only expected devices remain listed.

## When to escalate

Escalate to security@acme.example when an unrecognised session is found - do not stop at signing it out.
