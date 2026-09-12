---
id: mobile-mobile-storage-ios
title: The mobile app is using too much device storage (the iOS app)
category: mobile
tags: [cache, ios, mobile, storage]
audience: customer
severity: normal
---

# The mobile app is using too much device storage (the iOS app)

## Symptom

The phone reports several gigabytes used by Acme Cloud.

## Cause

Offline pins and the preview cache both live on the device.

## Resolution

These steps are written for **the iOS app**. Force-quit by swiping up from the app switcher before retrying.

1. Settings > Storage shows pinned files and cache separately.
2. Unpin folders you no longer need offline.
3. Choose **Clear cache**; previews are re-downloaded on demand and nothing is lost.
4. Set a cache cap - 1 GB is a sensible default on a phone.

## Verify

The OS storage figure drops to roughly the size of the pinned content.

## When to escalate

Escalate when clearing the cache does not reduce usage.
