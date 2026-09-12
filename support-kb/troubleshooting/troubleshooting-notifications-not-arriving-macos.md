---
id: troubleshooting-notifications-not-arriving-macos
title: Notifications are not arriving (the macOS desktop app)
category: troubleshooting
tags: [email, macos, notifications, push]
audience: customer
severity: normal
---

# Notifications are not arriving (the macOS desktop app)

## Symptom

No email or push notification for comments and shares.

## Cause

Per-user notification settings, OS-level permission, or digest mode batching them.

## Resolution

These steps are written for **the macOS desktop app**. Settings are stored in `~/Library/Application Support/AcmeCloud/config.json`.

1. Settings > Notifications: confirm the event type is enabled and the mode is Instant rather than Daily digest.
2. Check the operating system's own notification permission for Acme Cloud.
3. For email, search for 'acme.example' and mark a message as not spam - a single spam report suppresses the whole category for that address.
4. Do not disturb hours, if configured, suppress push silently.

## Verify

A test comment produces a notification within a minute.

## When to escalate

Escalate if instant mode is on, permissions are granted, and no notification arrives for two different event types.
