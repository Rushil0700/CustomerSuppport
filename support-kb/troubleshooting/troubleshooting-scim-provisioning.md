---
id: troubleshooting-scim-provisioning
title: SCIM provisioning is not creating users
category: troubleshooting
tags: [enterprise, provisioning, scim, sso]
audience: customer
severity: normal
---

# SCIM provisioning is not creating users

## Symptom

Users added in the identity provider do not appear in Acme Cloud.

## Cause

A mis-scoped SCIM token, unmapped attributes, or users not assigned to the application.

## Resolution

1. Confirm the user is assigned to the Acme Cloud application in the identity provider - unassigned users are never sent.
2. Check the SCIM token has not expired under Settings > Security > SCIM.
3. Map `userName` to the email address; this is the mismatch that causes most silent failures.
4. Read the provisioning log in your identity provider - it names the failing attribute.

## Verify

A newly assigned test user appears in Settings > Members within a minute.

## When to escalate

Escalate with the identity provider's provisioning log when the mapping is correct.
