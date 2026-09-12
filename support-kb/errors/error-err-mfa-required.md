---
id: error-err-mfa-required
title: ERR_MFA_REQUIRED: Multi-factor authentication required
category: errors
tags: [err_mfa_required, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_MFA_REQUIRED: Multi-factor authentication required

## What it means

An admin requires MFA for all members and yours is not enrolled.

## How to fix it

Enrol under Settings > Security > Two-factor authentication. New members get a seven day grace period.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
