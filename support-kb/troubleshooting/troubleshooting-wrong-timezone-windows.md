---
id: troubleshooting-wrong-timezone-windows
title: Timestamps show the wrong time (the Windows desktop app)
category: troubleshooting
tags: [profile, timestamps, timezone, windows]
audience: customer
severity: normal
---

# Timestamps show the wrong time (the Windows desktop app)

## Symptom

Activity and comment timestamps are hours off.

## Cause

The display timezone comes from your profile, not from the device, and defaults to the workspace's region.

## Resolution

These steps are written for **the Windows desktop app**. Settings are stored in `%APPDATA%\AcmeCloud\config.json`.

1. Settings > Profile > **Timezone** and set your own.
2. Choose between 12 and 24 hour display in the same place.
3. Exports and the API always use UTC in ISO 8601 - that is deliberate and not configurable.
4. The audit log shows UTC regardless of profile settings, for evidential consistency.

## Verify

A newly posted comment shows your local time.

## When to escalate

Rarely needed; escalate only if the profile timezone is correct and display is still wrong.
