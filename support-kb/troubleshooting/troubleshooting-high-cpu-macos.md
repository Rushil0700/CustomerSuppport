---
id: troubleshooting-high-cpu-macos
title: The app uses a lot of CPU or battery (the macOS desktop app)
category: troubleshooting
tags: [battery, cpu, macos, performance]
audience: customer
severity: normal
---

# The app uses a lot of CPU or battery (the macOS desktop app)

## Symptom

Fans spin up and the process sits at high CPU for long stretches.

## Cause

An initial index, an antivirus scanning every synced file, or a pathological folder.

## Resolution

These steps are written for **the macOS desktop app**. Settings are stored in `~/Library/Application Support/AcmeCloud/config.json`.

1. First sync of a large workspace is genuinely CPU-heavy and settles within a few hours - check Activity to see if it is still indexing.
2. Add the Acme Cloud data folder to your antivirus exclusions; real-time scanners re-scan every file we touch.
3. Exclude build output and dependency folders (`node_modules`, `target`, `.venv`) with selective sync - they churn constantly.
4. Cap bandwidth and set **Power saver** under Settings > Network on laptops.

## Verify

CPU settles to near zero when sync is idle.

## When to escalate

Escalate when high CPU persists with sync idle and no antivirus involved.
