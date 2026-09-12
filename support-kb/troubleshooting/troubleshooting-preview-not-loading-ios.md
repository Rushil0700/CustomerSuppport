---
id: troubleshooting-preview-not-loading-ios
title: A file preview will not load (the iOS app)
category: troubleshooting
tags: [files, ios, preview, troubleshooting]
audience: customer
severity: normal
---

# A file preview will not load (the iOS app)

## Symptom

The preview pane spins or shows 'Preview unavailable'.

## Cause

An unsupported format, a file still being processed, or a content blocker intercepting the preview frame.

## Resolution

These steps are written for **the iOS app**. Force-quit by swiping up from the app switcher before retrying.

1. Check the supported formats article - archives, executables and files over 2 GB never preview.
2. Newly uploaded files take a minute or two to render a preview; large PDFs take longer.
3. Disable content blockers for app.acme.example; several block our preview iframe.
4. Download the file to confirm the content itself is intact.

## Verify

The preview renders, or the download opens correctly and the format is simply unsupported.

## When to escalate

Escalate when a supported format under the size limit still fails to preview an hour after upload.
