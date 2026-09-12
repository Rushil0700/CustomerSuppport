---
id: faq-api-pagination
title: How does pagination work in the API?
category: faq
tags: [api-pagination, faq]
audience: customer
severity: normal
---

# How does pagination work in the API?

Cursor-based. Follow `next_cursor` from each response until it is null. Do not construct cursors yourself - they are opaque and their format may change.
