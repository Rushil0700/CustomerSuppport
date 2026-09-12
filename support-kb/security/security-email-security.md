---
id: security-email-security
title: Email authentication for notifications
category: security
tags: [compliance, email-security, security]
audience: customer
severity: normal
---

# Email authentication for notifications

Our notification mail is signed with DKIM, authorised by SPF, and covered by a
DMARC policy of `reject` on acme.example. If a message claiming to be from us
fails these checks, your mail server should already have rejected it.

If your organisation rewrites or relays our mail in a way that breaks DKIM, ask
IT to allowlist `no-reply@acme.example` rather than disabling DMARC checks.
