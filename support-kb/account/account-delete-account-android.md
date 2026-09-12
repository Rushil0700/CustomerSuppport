---
id: account-delete-account-android
title: Delete a personal account (the Android app)
category: account
tags: [account, android, deletion, privacy]
audience: customer
severity: normal
---

# Delete a personal account (the Android app)

## Symptom

A user wants their individual account removed, separately from the workspace.

## Cause

Accounts and workspaces are distinct: leaving every workspace does not delete the account.

## Resolution

These steps are written for **the Android app**. Use Settings > Apps > Acme Cloud > Storage > Clear cache (not Clear data).

1. Leave or transfer ownership of every workspace you own.
2. Settings > Profile > **Delete account**.
3. Confirm with your password; SSO accounts confirm through the identity provider.
4. The account is disabled immediately and purged after 30 days.

## Verify

Sign-in reports that the account does not exist.

## When to escalate

Escalate if the user is the sole owner of a workspace that other people still use - ownership must be transferred first.
