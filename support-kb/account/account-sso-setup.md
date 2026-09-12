---
id: account-sso-setup
title: Set up SAML single sign-on
category: account
tags: [admin, saml, security, sso]
audience: customer
severity: normal
---

# Set up SAML single sign-on

## Symptom

An admin wants staff to sign in through the company identity provider.

## Cause

SSO must be configured on both sides and the domain proven before it can be enforced.

## Resolution

1. Settings > Security > **SAML SSO** (Business and Enterprise plans).
2. Copy the ACS URL and Entity ID into your identity provider.
3. Paste the provider's metadata URL or XML back into Acme Cloud.
4. Verify your domain with the supplied DNS TXT record.
5. Test with one account before choosing **Enforce SSO**; enforcement immediately disables password login for the whole domain.

## Verify

A test user reaches the workspace through the identity provider's app tile.

## When to escalate

Escalate any enforcement that locks out every admin - recovery requires staff to disable enforcement server-side.
