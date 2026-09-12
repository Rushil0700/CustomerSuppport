---
id: account-invite-not-received-android
title: An invitation email never arrived (the Android app)
category: account
tags: [android, email, invite, members]
audience: customer
severity: normal
---

# An invitation email never arrived (the Android app)

## Symptom

A new teammate says they were never invited, although the admin sees the invite as pending.

## Cause

Invitations are sent once and can be filtered, quarantined, or sent to a typo'd address.

## Resolution

These steps are written for **the Android app**. Use Settings > Apps > Acme Cloud > Storage > Clear cache (not Clear data).

1. Settings > Members and confirm the address is spelled correctly; if not, revoke and re-invite.
2. Ask the recipient to search all mail folders for 'acme.example'.
3. Choose **Resend invite**; this issues a fresh 7 day link.
4. As a fallback, use **Copy invite link** and send it over your own channel.

## Verify

The member row changes from Pending to Active once they accept.

## When to escalate

Escalate if three resends to a verified-correct address all fail, which suggests the address is on a bounce suppression list.
