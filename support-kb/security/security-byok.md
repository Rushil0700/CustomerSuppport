---
id: security-byok
title: Bringing your own encryption key
category: security
tags: [byok, compliance, security]
audience: customer
severity: normal
---

# Bringing your own encryption key

Enterprise workspaces can supply a customer-managed key through AWS KMS or Google
Cloud KMS. We use it to wrap the data encryption keys, so revoking it makes the
workspace unreadable within minutes.

That is the point of the feature, and it is not reversible: if the key is
destroyed rather than merely disabled, the data is unrecoverable. Treat
revocation as a break-glass action and test the process in a non-production
workspace first.
