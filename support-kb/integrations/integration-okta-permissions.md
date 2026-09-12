---
id: integration-okta-permissions
title: What the Okta integration can access
category: integrations
tags: [integration, okta, permissions, security]
audience: customer
severity: normal
---

# What the Okta integration can access

Security teams ask this before approving an integration, so here it is plainly.

## Granted to Acme Cloud

The integration receives an OAuth token scoped to the permissions you approve at
connection time. We request the narrowest scopes that make the features work:
read access to the resources you select, and write access only where the
integration creates something on your behalf.

## Granted to Okta

Okta receives access only to the Acme Cloud projects you select during setup.
Selecting no projects leaves the integration connected but inert, which is a
reasonable way to stage a rollout.

## What we store

The OAuth token (encrypted at rest), the resource mapping, and a sync cursor. We
do not copy Okta content into Acme Cloud beyond what the integration's features
explicitly require, and what is copied is listed on the integration's card.

## Reviewing and revoking

- Settings > Integrations > Okta shows the scopes in force and who authorised them.
- The audit log records the grant, every scope change, and the revocation.
- Revoking is immediate on our side; also remove the app inside Okta, since a
  one-sided revocation leaves a stale grant listed on the other.

## When to escalate

Escalate when a security review needs scope detail beyond this article, or a
written confirmation of data flows for an audit.
