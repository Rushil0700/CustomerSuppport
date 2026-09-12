---
id: troubleshooting-storage-full
title: The workspace is out of storage
category: troubleshooting
tags: [quota, storage, usage]
audience: customer
severity: normal
---

# The workspace is out of storage

## Symptom

Uploads are rejected with 'storage limit reached' and sync pauses.

## Cause

Total stored bytes, including trash and version history, reached the plan limit.

## Resolution

1. Settings > Usage shows the breakdown by project, including trash and versions.
2. Empty Trash - deleted files count against the quota for their full 30 days.
3. Reduce version history retention under Settings > Storage; the default keeps 100 versions per file.
4. Archive finished projects: archived projects are compressed and count at roughly half their size.
5. Otherwise upgrade the plan.

## Verify

Usage drops below the limit and sync resumes automatically within minutes.

## When to escalate

Escalate when usage does not drop after emptying trash, which can indicate an orphaned upload session.
