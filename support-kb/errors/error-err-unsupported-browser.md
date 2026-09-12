---
id: error-err-unsupported-browser
title: ERR_UNSUPPORTED_BROWSER: This browser is not supported
category: errors
tags: [err_unsupported_browser, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_UNSUPPORTED_BROWSER: This browser is not supported

## What it means

The web app needs a browser released within roughly the last two years.

## How to fix it

Update to a current Chrome, Edge, Firefox or Safari. Internet Explorer is not supported at all.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
