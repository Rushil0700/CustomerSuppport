---
id: security-encryption
title: How data is encrypted
category: security
tags: [compliance, encryption, security]
audience: customer
severity: normal
---

# How data is encrypted

Data is encrypted in transit with TLS 1.3 (TLS 1.2 accepted for legacy clients;
SSL and TLS 1.0/1.1 are refused). At rest, content is encrypted with AES-256
using keys held in a managed KMS and rotated annually.

Enterprise workspaces may supply their own key (BYOK) through AWS KMS or Google
Cloud KMS. Revoking that key renders the workspace unreadable within minutes -
which is the point, but it is not reversible, so treat revocation as a break-glass
action.
