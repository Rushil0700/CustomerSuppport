---
id: api-error-429-rate_limited
title: API error 429 rate_limited
category: api
tags: [429, api, error, rate_limited]
audience: customer
severity: normal
---

# API error 429 `rate_limited`

## What it means

You exceeded the requests-per-minute budget for your plan.

## Example response

```json
{
  "error": "rate_limited",
  "status": 429,
  "detail": "See the message field for the specific field or limit involved.",
  "request_id": "req_01HZX9Q2N4"
}
```

## How to fix it

Honour the `Retry-After` header and back off exponentially. Burst capacity refills over 60 seconds.

## Is it safe to retry?

Yes - retry with exponential backoff.

## Still stuck?

Quote the `request_id` from the response when contacting support. It lets us
find the exact call in our logs, which is far faster than a description.
