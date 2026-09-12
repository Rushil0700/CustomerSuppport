---
id: api-error-500-internal_error
title: API error 500 internal_error
category: api
tags: [500, api, error, internal_error]
audience: customer
severity: normal
---

# API error 500 `internal_error`

## What it means

An unexpected failure on our side.

## Example response

```json
{
  "error": "internal_error",
  "status": 500,
  "detail": "See the message field for the specific field or limit involved.",
  "request_id": "req_01HZX9Q2N4"
}
```

## How to fix it

Retry with backoff. If it persists, send us the `request_id` from the response and check https://status.acme.example.

## Is it safe to retry?

Yes - retry with exponential backoff.

## Still stuck?

Quote the `request_id` from the response when contacting support. It lets us
find the exact call in our logs, which is far faster than a description.
