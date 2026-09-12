---
id: troubleshooting-wrong-timezone-android
title: Timestamps show the wrong time (the Android app)
category: troubleshooting
tags: [android, profile, timestamps, timezone]
audience: customer
severity: normal
---

# Timestamps show the wrong time (the Android app)

## Symptom

Activity and comment timestamps are hours off.

## Cause

The display timezone comes from your profile, not from the device, and defaults to the workspace's region.

## Resolution

These steps are written for **the Android app**. Use Settings > Apps > Acme Cloud > Storage > Clear cache (not Clear data).

1. Settings > Profile > **Timezone** and set your own.
2. Choose between 12 and 24 hour display in the same place.
3. Exports and the API always use UTC in ISO 8601 - that is deliberate and not configurable.
4. The audit log shows UTC regardless of profile settings, for evidential consistency.

## Verify

A newly posted comment shows your local time.

## When to escalate

Rarely needed; escalate only if the profile timezone is correct and display is still wrong.
