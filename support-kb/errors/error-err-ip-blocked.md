---
id: error-err-ip-blocked
title: ERR_IP_BLOCKED: Access denied from this network
category: errors
tags: [err_ip_blocked, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_IP_BLOCKED: Access denied from this network

## What it means

The workspace has an IP allowlist and your current address is not on it.

## How to fix it

Connect through the corporate VPN, or ask an admin to add your CIDR range. API keys are subject to the same list.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
