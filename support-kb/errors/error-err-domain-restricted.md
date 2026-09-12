---
id: error-err-domain-restricted
title: ERR_DOMAIN_RESTRICTED: Share link restricted to approved domains
category: errors
tags: [err_domain_restricted, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_DOMAIN_RESTRICTED: Share link restricted to approved domains

## What it means

An admin limited share links to specific email domains and the recipient's address is outside them.

## How to fix it

Share with the person by email instead, or ask an admin to add the recipient's domain under Settings > Security.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
