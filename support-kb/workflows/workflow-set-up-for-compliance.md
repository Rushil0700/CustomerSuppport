---
id: workflow-set-up-for-compliance
title: Configure a workspace for a regulated environment
category: workflows
tags: [admin, set-up-for-compliance, workflow]
audience: admin
severity: normal
---

# Configure a workspace for a regulated environment

## Who this is for

Workspace owners and admins. Some steps need the owner role, which is noted
where it applies.

## Steps

1. Enforce SAML SSO and require MFA at the identity provider.
2. Set a session policy of one business day or shorter, with re-authentication for billing and export.
3. Enable device approval so unknown devices are held pending.
4. Restrict share links to approved domains and require an expiry.
5. Turn on the IP allowlist last, and add your own address first.
6. Enable audit log streaming to your SIEM.

## Verify

A test account from an unapproved device and network is refused at every step.

## When to escalate

Escalate when a step cannot be completed because the required control is absent
from your plan, or when the verification above does not hold after completing
every step.
