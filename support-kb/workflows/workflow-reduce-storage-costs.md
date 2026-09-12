---
id: workflow-reduce-storage-costs
title: Reduce storage usage without deleting work
category: workflows
tags: [admin, reduce-storage-costs, workflow]
audience: admin
severity: normal
---

# Reduce storage usage without deleting work

## Who this is for

Workspace owners and admins. Some steps need the owner role, which is noted
where it applies.

## Steps

1. Settings > Usage and sort projects by size - the top three usually account for most of it.
2. Empty trash; deleted files count against quota for their full 30 days.
3. Lower version retention from the default 100 versions per file.
4. Archive finished projects, which compresses them to roughly half.
5. Exclude build artefacts and dependency directories from sync entirely.

## Verify

Settings > Usage shows a materially lower figure and sync is no longer paused.

## When to escalate

Escalate when a step cannot be completed because the required control is absent
from your plan, or when the verification above does not hold after completing
every step.
