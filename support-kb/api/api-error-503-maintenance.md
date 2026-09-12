---
id: api-error-503-maintenance
title: API error 503 maintenance
category: api
tags: [503, api, error, maintenance]
audience: customer
severity: normal
---

# API error 503 `maintenance`

## What it means

The endpoint is briefly unavailable during a deploy.

## Example response

```json
{
  "error": "maintenance",
  "status": 503,
  "detail": "See the message field for the specific field or limit involved.",
  "request_id": "req_01HZX9Q2N4"
}
```

## How to fix it

Retry after the interval in `Retry-After`. Watch https://status.acme.example for scheduled windows.

## Is it safe to retry?

Yes - retry with exponential backoff.

## Still stuck?

Quote the `request_id` from the response when contacting support. It lets us
find the exact call in our logs, which is far faster than a description.
