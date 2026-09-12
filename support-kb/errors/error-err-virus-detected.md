---
id: error-err-virus-detected
title: ERR_VIRUS_DETECTED: Upload blocked by malware scanning
category: errors
tags: [err_virus_detected, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_VIRUS_DETECTED: Upload blocked by malware scanning

## What it means

Our scanner matched a known malware signature in the file.

## How to fix it

The upload is refused and the file quarantined. If you believe it is a false positive, contact support with the file name and the time - do not retry, the result will be identical.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
