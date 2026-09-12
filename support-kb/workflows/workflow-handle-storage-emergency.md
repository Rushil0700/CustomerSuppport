---
id: workflow-handle-storage-emergency
title: Recover when sync has stopped for everyone
category: workflows
tags: [admin, handle-storage-emergency, workflow]
audience: admin
severity: normal
---

# Recover when sync has stopped for everyone

## Who this is for

Workspace owners and admins. Some steps need the owner role, which is noted
where it applies.

## Steps

1. Check the status page first - a regional incident looks exactly like a local failure.
2. Check Settings > Usage for a quota wall and Settings > Billing for a lapsed payment; both pause sync workspace-wide.
3. If neither applies, have one user pause and resume sync to confirm it is not client-side.
4. Collect the request id from any error shown and contact support - a workspace-wide sync halt is a Sev-2 for us.

## Verify

Sync resumes for the test user, then for everyone within a few minutes.

## When to escalate

Escalate when a step cannot be completed because the required control is absent
from your plan, or when the verification above does not hold after completing
every step.
