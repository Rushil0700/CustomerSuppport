---
id: troubleshooting-slow-performance-android
title: The app feels slow (the Android app)
category: troubleshooting
tags: [android, performance, slow, troubleshooting]
audience: customer
severity: normal
---

# The app feels slow (the Android app)

## Symptom

Navigation and file listings take several seconds.

## Cause

Large folders, an outdated client, or a saturated local link.

## Resolution

These steps are written for **the Android app**. Use Settings > Apps > Acme Cloud > Storage > Clear cache (not Clear data).

1. Check the status page before anything else - a regional incident presents exactly like this.
2. Folders over 20,000 items render slowly by design; split them.
3. Update to the current client version; performance fixes ship most weeks.
4. Run a speed test - sync saturating the uplink starves the UI. Cap bandwidth in Settings > Network.

## Verify

Listing a folder of a few hundred items returns in under a second.

## When to escalate

Escalate with a HAR file when the workspace is small, the client is current, and the network is healthy.
