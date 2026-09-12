---
id: mobile-mobile-push-ios
title: Push notifications do not arrive on mobile (the iOS app)
category: mobile
tags: [ios, mobile, notifications, push]
audience: customer
severity: normal
---

# Push notifications do not arrive on mobile (the iOS app)

## Symptom

No banners or badges on the phone.

## Cause

OS notification permission, battery optimisation, or the account signed in on a different device.

## Resolution

These steps are written for **the iOS app**. Force-quit by swiping up from the app switcher before retrying.

1. Grant notification permission in the OS settings for Acme Cloud.
2. Exempt the app from battery optimisation or Low Power Mode restrictions.
3. Confirm you are signed into the workspace that generates the events.
4. Sign out and back in to re-register the push token - a token goes stale after a restore from backup.

## Verify

A test comment produces a banner within a minute.

## When to escalate

Escalate after a sign-out and sign-in with permissions confirmed.
