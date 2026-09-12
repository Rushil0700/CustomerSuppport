---
id: error-err-project-archived
title: ERR_PROJECT_ARCHIVED: Project is archived and read-only
category: errors
tags: [err_project_archived, error, troubleshooting]
audience: customer
severity: normal
---

# ERR_PROJECT_ARCHIVED: Project is archived and read-only

## What it means

Archived projects are deliberately frozen to halve their storage cost.

## How to fix it

Unarchive it from the project menu. Unarchiving is instant and restores full write access.

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
