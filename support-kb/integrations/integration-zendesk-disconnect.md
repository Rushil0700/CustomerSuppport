---
id: integration-zendesk-disconnect
title: Disconnect Zendesk and remove its data
category: integrations
tags: [integration, privacy, removal, zendesk]
audience: customer
severity: normal
---

# Disconnect Zendesk and remove its data

## Steps

1. Settings > **Integrations** > Zendesk > **Disconnect**.
2. Confirm. The OAuth token is revoked immediately on our side.
3. Also remove the Acme Cloud app from within Zendesk; revoking on one side alone
   leaves a stale grant listed in the other.
4. Optionally choose **Delete synced data** to purge records the integration
   created in Acme Cloud. This is irreversible.

## What is kept

Files and messages already copied into Acme Cloud remain - they are your data.
Only the mapping and the credentials are removed. Audit events recording the
integration's past activity are retained for the normal retention period.

## When to escalate

Escalate if the card reappears as connected after a disconnect, which indicates
a grant that failed to revoke.
