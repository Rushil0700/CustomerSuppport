---
id: workflow-migrate-from-competitor
title: Migrate from another storage provider
category: workflows
tags: [admin, migrate-from-competitor, workflow]
audience: admin
severity: normal
---

# Migrate from another storage provider

## Who this is for

Workspace owners and admins. Some steps need the owner role, which is noted
where it applies.

## Steps

1. Settings > **Import** and pick the source: Dropbox, Google Drive, Box or OneDrive.
2. Authorise the source account. Use an admin account so the whole shared drive is visible.
3. Map source folders onto Acme Cloud projects before starting - remapping afterwards means moving data.
4. Run a pilot with one folder and check that sharing and folder structure survived.
5. Schedule the full migration for a quiet period; multi-terabyte imports take hours.
6. Keep the source read-only for two weeks so nothing is lost to an edit made in the wrong place.

## Verify

File counts and total size match the source, and a sample of shares resolves correctly.

## When to escalate

Escalate when a step cannot be completed because the required control is absent
from your plan, or when the verification above does not hold after completing
every step.
