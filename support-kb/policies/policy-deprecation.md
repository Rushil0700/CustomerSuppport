---
id: policy-deprecation
title: How APIs and features are deprecated
category: policies
tags: [deprecation, policy]
audience: customer
severity: normal
---

# How APIs and features are deprecated

Stable APIs are supported for at least 12 months after a deprecation notice.
Notices are published in the changelog, sent to workspace owners by email, and
returned in a `Sunset` header on affected endpoints.

Beta APIs may change with 30 days' notice. We do not remove a stable endpoint
without a documented migration path.
