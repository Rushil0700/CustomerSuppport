---
id: mobile-camera-upload-ios
title: Set up automatic camera upload (the iOS app)
category: mobile
tags: [backup, ios, mobile, photos]
audience: customer
severity: normal
---

# Set up automatic camera upload (the iOS app)

## Symptom

Photos are not backing up from the phone.

## Cause

Camera upload is opt-in and is suspended by the OS under low power or on cellular.

## Resolution

These steps are written for **the iOS app**. Force-quit by swiping up from the app switcher before retrying.

1. Open the app, go to Settings > **Camera upload** and turn it on.
2. Grant full photo library access - 'selected photos only' silently limits the backup.
3. Decide whether to allow cellular upload; the default is Wi-Fi only.
4. Disable battery optimisation for Acme Cloud so the OS stops suspending background transfers.

## Verify

The Camera Uploads folder fills and shows a recent timestamp.

## When to escalate

Escalate when permissions are full, the device is on Wi-Fi and charging, and nothing uploads for an hour.
