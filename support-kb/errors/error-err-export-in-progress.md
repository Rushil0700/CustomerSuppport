---
id: error-err-export-in-progress
title: ERR_EXPORT_IN_PROGRESS: An export is already running
category: errors
tags: [err_export_in_progress, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_EXPORT_IN_PROGRESS: An export is already running

## What it means

Only one export job runs per workspace at a time.

## How to fix it

Wait for the running export to finish; you receive an email with the download link. Large workspaces take several hours.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
