---
id: account-password-reset
title: Reset a forgotten password
category: account
tags: [account, login, password, reset]
audience: customer
severity: normal
---

# Reset a forgotten password

Use this when you cannot sign in to Acme Cloud and you know your email address.

## Steps

1. Go to https://app.acme.example/login and choose **Forgot password**.
2. Enter the email address on the account and submit.
3. Open the message titled "Reset your Acme Cloud password". It arrives within two
   minutes; check spam and any quarantine your employer runs.
4. Follow the link and choose a new password of at least 12 characters.
5. Sign in with the new password. All other sessions are signed out automatically.

## The reset email never arrives

- The link is valid for **60 minutes**. Request a new one if it has expired.
- Resets are only sent to addresses that already have an account. If you signed
  up with Google or Microsoft SSO there is no password to reset - use **Continue
  with Google** or **Continue with Microsoft** instead.
- Corporate filters sometimes hold mail from `no-reply@acme.example`. Ask IT to
  allowlist that address.

## Escalate

If the address is correct, SSO is not in use, and no mail has arrived after 15
minutes, escalate to a human agent: the account may have a bounced-email flag
that only staff can clear.
