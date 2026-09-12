---
id: error-err-link-expired
title: ERR_LINK_EXPIRED: This share link has expired
category: errors
tags: [err_link_expired, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_LINK_EXPIRED: This share link has expired

## What it means

The link reached its expiry date, or the file moved workspace, which invalidates links.

## How to fix it

Ask the sender to generate a fresh link. Expiry cannot be extended on an existing link.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
