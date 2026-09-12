---
id: troubleshooting-upload-fails-android
title: Uploads fail part-way through (the Android app)
category: troubleshooting
tags: [android, files, network, upload]
audience: customer
severity: normal
---

# Uploads fail part-way through (the Android app)

## Symptom

An upload reaches a percentage and then restarts or errors.

## Cause

Almost always the network path: a proxy that buffers the whole body, an idle timeout, or a genuinely unstable link.

## Resolution

These steps are written for **the Android app**. Use Settings > Apps > Acme Cloud > Storage > Clear cache (not Clear data).

1. Retry on a different network to separate a local problem from an account one.
2. Files above the plan's single-file limit are rejected; check Settings > Usage.
3. On a corporate network, ask IT to allow `*.acme.example` on 443 and to exempt uploads from body inspection.
4. Large files resume automatically for 24 hours - reopen the app rather than starting over.

## Verify

The file appears with a green check and the size matches the source.

## When to escalate

Escalate when the same file fails on two different networks and is inside the plan limit.
