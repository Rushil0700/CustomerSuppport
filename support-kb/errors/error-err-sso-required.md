---
id: error-err-sso-required
title: ERR_SSO_REQUIRED: Password sign-in disabled for this domain
category: errors
tags: [err_sso_required, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_SSO_REQUIRED: Password sign-in disabled for this domain

## What it means

An admin enforced SAML SSO, which disables password login for the whole email domain.

## How to fix it

Use **Continue with SSO**, or reach the workspace through your identity provider's app tile.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
