---
id: account-enable-mfa-ios
title: Turn on multi-factor authentication (the iOS app)
category: account
tags: [2fa, ios, mfa, security]
audience: customer
severity: normal
---

# Turn on multi-factor authentication (the iOS app)

## Symptom

A customer or their security team wants MFA required for sign-in.

## Cause

MFA is opt-in per user and can additionally be enforced workspace-wide by an admin.

## Resolution

These steps are written for **the iOS app**. Force-quit by swiping up from the app switcher before retrying.

1. Settings > Security > **Two-factor authentication** > Enable.
2. Scan the QR code with any TOTP app (1Password, Authy, Google Authenticator).
3. Enter the six digit code to confirm the pairing.
4. Download the ten recovery codes and store them outside the password manager that holds the password.
5. Admins can then set Settings > Security > **Require MFA for all members**, which gives existing members seven days to enrol.

## Verify

Signing out and back in prompts for a code.

## When to escalate

Escalate only if enrolment fails repeatedly with a correct code, which usually means device clock drift greater than 30 seconds.
