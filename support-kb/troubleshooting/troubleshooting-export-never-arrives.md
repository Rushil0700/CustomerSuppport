---
id: troubleshooting-export-never-arrives
title: A data export never arrives
category: troubleshooting
tags: [backup, data, export]
audience: customer
severity: normal
---

# A data export never arrives

## Symptom

An export was started but no email came.

## Cause

Large exports take hours, the email was filtered, or the job failed on an unreadable file.

## Resolution

1. Settings > Workspace > Export shows the job status and progress.
2. Multi-terabyte exports genuinely take several hours - check the progress before assuming failure.
3. Search mail for 'acme.example'; the link mail is easily filtered.
4. Download links expire after 7 days; if yours has, start the export again.

## Verify

The job shows Completed and the signed link downloads.

## When to escalate

Escalate when the job shows Failed, or has been running for more than 12 hours.
