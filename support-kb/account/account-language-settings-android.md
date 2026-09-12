---
id: account-language-settings-android
title: Change the interface language (the Android app)
category: account
tags: [android, language, localisation, profile]
audience: customer
severity: normal
---

# Change the interface language (the Android app)

## Symptom

The app is not in the user's preferred language.

## Cause

Language follows the profile setting, falling back to the browser or OS locale.

## Resolution

These steps are written for **the Android app**. Use Settings > Apps > Acme Cloud > Storage > Clear cache (not Clear data).

1. Settings > Profile > **Language**.
2. Choose from the supported languages; the change applies immediately without a reload.
3. Email notifications follow the same setting.
4. File content is never translated - only the interface.

## Verify

Menus appear in the chosen language.

## When to escalate

Report untranslated strings to support rather than escalating as a fault.
