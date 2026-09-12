---
id: workflow-offboard-departing-member
title: Offboard someone who is leaving
category: workflows
tags: [admin, offboard-departing-member, workflow]
audience: admin
severity: normal
---

# Offboard someone who is leaving

## Who this is for

Workspace owners and admins. Some steps need the owner role, which is noted
where it applies.

## Steps

1. Transfer ownership of anything they solely own - projects and, critically, the workspace itself.
2. Reassign their integrations; personal OAuth grants break the moment their account goes.
3. Remove them from Settings > Members. Their files stay; only access is removed.
4. Revoke API keys they created under Settings > Developers.
5. Check Settings > Security > Active sessions to confirm nothing remains signed in.

## Verify

The audit log records the removal and no sessions or keys remain for that account.

## When to escalate

Escalate when a step cannot be completed because the required control is absent
from your plan, or when the verification above does not hold after completing
every step.
