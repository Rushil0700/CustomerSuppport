---
id: account-change-email-web
title: Change the email address on an account (the web app)
category: account
tags: [account, email, profile, web]
audience: customer
severity: normal
---

# Change the email address on an account (the web app)

## Symptom

A member wants their sign-in address updated after a name change or a move between companies.

## Cause

The email address is the login identity, so changing it requires confirming the new address.

## Resolution

These steps are written for **the web app**. Clear the site data for app.acme.example under your browser's privacy settings.

1. Open Settings > Profile and choose **Change email**.
2. Enter the new address and your current password.
3. Open the confirmation link sent to the *new* address; it expires in 24 hours.
4. A notice is sent to the old address for 30 days so a hijack is noticed.

## Verify

The new address appears under Settings > Profile and can sign in.

## When to escalate

Escalate when the customer no longer controls either address, or when SSO is enforced - the address then comes from the identity provider and must be changed there.
