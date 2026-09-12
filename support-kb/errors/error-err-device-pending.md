---
id: error-err-device-pending
title: ERR_DEVICE_PENDING: Device awaiting approval
category: errors
tags: [err_device_pending, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_DEVICE_PENDING: Device awaiting approval

## What it means

Device approval is enabled and an admin has not yet approved this device.

## How to fix it

Ask a workspace admin to approve it under Settings > Security > Devices. You receive an email when it is approved.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
