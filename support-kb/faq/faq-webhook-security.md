---
id: faq-webhook-security
title: How do I verify a webhook came from you?
category: faq
tags: [faq, webhook-security]
audience: customer
severity: normal
---

# How do I verify a webhook came from you?

Each delivery carries an `X-Acme-Signature` header: an HMAC-SHA256 of the raw body using your endpoint's signing secret. Compare it in constant time, against the raw bytes, before parsing.
