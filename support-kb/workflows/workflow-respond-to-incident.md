---
id: workflow-respond-to-incident
title: Respond to a suspected account compromise
category: workflows
tags: [admin, respond-to-incident, workflow]
audience: admin
severity: normal
---

# Respond to a suspected account compromise

## Who this is for

Workspace owners and admins. Some steps need the owner role, which is noted
where it applies.

## Steps

1. Settings > Security > **Active sessions** > Sign out everywhere, immediately.
2. Change the password, or force a reset from the identity provider if SSO is in use.
3. Revoke and reissue every API key the account created.
4. Read the audit log for the period: look for share links created, exports started and integrations added.
5. Revoke any share link you do not recognise.
6. Tell security@acme.example with the timeframe so we can check server-side.

## Verify

No unexpected sessions, keys, links or exports remain, and the audit log is clear from the containment point onward.

## When to escalate

Escalate when a step cannot be completed because the required control is absent
from your plan, or when the verification above does not hold after completing
every step.
