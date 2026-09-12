---
id: error-err-link-password
title: ERR_LINK_PASSWORD: Incorrect share link password
category: errors
tags: [err_link_password, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_LINK_PASSWORD: Incorrect share link password

## What it means

The password on the share link does not match.

## How to fix it

Passwords are case-sensitive and are not recoverable - the sender must reset it or issue a new link.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
