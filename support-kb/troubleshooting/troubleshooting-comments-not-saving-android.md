---
id: troubleshooting-comments-not-saving-android
title: Comments disappear after posting (the Android app)
category: troubleshooting
tags: [android, collaboration, comments, troubleshooting]
audience: customer
severity: normal
---

# Comments disappear after posting (the Android app)

## Symptom

A comment appears briefly and then vanishes on refresh.

## Cause

The comment failed server-side validation, the session expired mid-post, or the user lost access to the project between opening it and commenting.

## Resolution

These steps are written for **the Android app**. Use Settings > Apps > Acme Cloud > Storage > Clear cache (not Clear data).

1. Refresh and confirm you still have edit access to the project.
2. Re-post a short comment without mentions or attachments to isolate the cause.
3. Mentions of users who have left the workspace cause the whole comment to be rejected - remove them.
4. If the session expired, sign in again; drafts are kept locally for an hour.

## Verify

A plain comment persists across a refresh.

## When to escalate

Escalate when a plain comment on a project you demonstrably can edit still fails.
