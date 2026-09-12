---
id: error-err-rate-limited-ui
title: ERR_RATE_LIMITED_UI: Too many requests - slow down
category: errors
tags: [err_rate_limited_ui, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_RATE_LIMITED_UI: Too many requests - slow down

## What it means

An unusual burst of actions from one session tripped the abuse protection.

## How to fix it

Wait 60 seconds. If a script is driving the web app, move it to the API, which has documented, higher limits.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
