---
id: troubleshooting-share-link-not-working-web
title: A share link shows 'not available' (the web app)
category: troubleshooting
tags: [link, permissions, share, web]
audience: customer
severity: normal
---

# A share link shows 'not available' (the web app)

## Symptom

A recipient opening a share link sees an error instead of the file.

## Cause

Expiry, a password, a domain restriction, or a link created for a file that has since moved.

## Resolution

These steps are written for **the web app**. Clear the site data for app.acme.example under your browser's privacy settings.

1. Open the file, choose **Share** and check the link's expiry and password settings.
2. Workspace admins can restrict links to specific email domains under Settings > Security; external recipients are then blocked by design.
3. Moving a file between workspaces invalidates its links. Re-share from the new location.
4. Generate a fresh link and send that, which rules out a mangled URL in the message.

## Verify

The recipient opens the link in a private window and sees the file.

## When to escalate

Escalate when a fresh, unexpired, unrestricted link still fails for a recipient.
