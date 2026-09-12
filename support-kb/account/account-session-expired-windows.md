---
id: account-session-expired-windows
title: Signed out repeatedly during the day (the Windows desktop app)
category: account
tags: [cookies, login, session, windows]
audience: customer
severity: normal
---

# Signed out repeatedly during the day (the Windows desktop app)

## Symptom

The session ends every few hours even though 'stay signed in' was selected.

## Cause

Sessions last 30 days, but are cut short by privacy settings that clear cookies, by an admin-set shorter session policy, or by an IP address that keeps changing.

## Resolution

These steps are written for **the Windows desktop app**. Settings are stored in `%APPDATA%\AcmeCloud\config.json`.

1. Check Settings > Security for an admin-enforced session length; Business and Enterprise admins can set it as low as one hour.
2. Disable any browser extension or setting that clears cookies on close for app.acme.example.
3. If you are on a corporate VPN that rotates egress IPs, ask IT to pin the egress range - we re-authenticate when the IP changes networks mid-session.
4. Sign out everywhere from Settings > Security > Active sessions, then sign in once more.

## Verify

The session survives a browser restart.

## When to escalate

Escalate when the workspace has no session policy, cookies persist, and the user is still signed out within an hour.
