---
id: policy-api-terms
title: API terms of use
category: policies
tags: [api-terms, policy]
audience: customer
severity: normal
---

# API terms of use

The API is for building integrations with your own workspace data. You may not
use it to mirror the service, to resell storage, or to circumvent plan limits.

Respect the rate limits and the `Retry-After` header. Persistent disregard for
backoff is treated as abuse and can result in key revocation.

Cache responses where you sensibly can; polling an unchanged resource every
second helps nobody.
