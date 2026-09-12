---
id: account-merge-accounts-web
title: Merge two accounts (the web app)
category: account
tags: [account, duplicate, merge, web]
audience: customer
severity: normal
---

# Merge two accounts (the web app)

## Symptom

Someone signed up twice, often once with SSO and once with a password.

## Cause

Accounts are keyed by email address, so two addresses mean two accounts even for the same person.

## Resolution

These steps are written for **the web app**. Clear the site data for app.acme.example under your browser's privacy settings.

1. Decide which account to keep - normally the one with the workspace membership you care about.
2. Move any projects solely owned by the other account by transferring ownership.
3. Remove the redundant account from the workspace, then delete it from its own Settings > Profile.
4. If both addresses must remain usable, add the second as an alias under Settings > Profile > Email aliases instead.

## Verify

One account remains, holding every project, and signs in with the expected address.

## When to escalate

Escalate when the redundant account cannot be signed into to delete it.
