---
id: error-err-seat-limit
title: ERR_SEAT_LIMIT: No seats available
category: errors
tags: [err_seat_limit, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_SEAT_LIMIT: No seats available

## What it means

Every seat on the plan is taken by an active member or a pending invitation.

## How to fix it

Remove a member, revoke an unaccepted invitation, or add seats under Settings > Billing.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
