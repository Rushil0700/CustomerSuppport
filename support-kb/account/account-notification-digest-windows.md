---
id: account-notification-digest-windows
title: Reduce notification volume (the Windows desktop app)
category: account
tags: [email, notifications, preferences, windows]
audience: customer
severity: normal
---

# Reduce notification volume (the Windows desktop app)

## Symptom

A member is overwhelmed by notification email.

## Cause

Instant delivery is the default for every event type.

## Resolution

These steps are written for **the Windows desktop app**. Settings are stored in `%APPDATA%\AcmeCloud\config.json`.

1. Settings > **Notifications** and switch from Instant to **Daily digest**.
2. Turn off event types individually - most people keep mentions and direct shares, and disable the rest.
3. Mute a noisy project from its own menu without changing global settings.
4. Set do-not-disturb hours so nothing arrives overnight.

## Verify

A test event produces no immediate email, and appears in the next digest.

## When to escalate

Escalate when notifications continue after everything is disabled.
