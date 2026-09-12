---
id: error-err-clock-skew
title: ERR_CLOCK_SKEW: Device clock is out of sync
category: errors
tags: [err_clock_skew, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_CLOCK_SKEW: Device clock is out of sync

## What it means

The device clock differs from real time by more than 30 seconds, which breaks TOTP codes and request signing.

## How to fix it

Enable automatic time synchronisation in the operating system's date and time settings, then retry.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
