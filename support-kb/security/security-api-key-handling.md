---
id: security-api-key-handling
title: Handling API keys safely
category: security
tags: [api-key-handling, compliance, security]
audience: customer
severity: normal
---

# Handling API keys safely

A key's secret is shown exactly once, at creation. Store it in a secret manager,
never in source control or a CI configuration file.

Scope each key to the narrowest set of permissions the job needs, and create one
key per system rather than sharing one everywhere - a shared key cannot be
revoked without breaking everything at once.

Rotate with the rotate endpoint, which keeps the old secret valid for 24 hours so
you can deploy the new one without downtime. Keys unused for 90 days are flagged
in the developer settings; revoke them.
