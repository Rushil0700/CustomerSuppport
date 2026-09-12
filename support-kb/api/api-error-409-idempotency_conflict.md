---
id: api-error-409-idempotency_conflict
title: API error 409 idempotency_conflict
category: api
tags: [409, api, error, idempotency_conflict]
audience: customer
severity: normal
---

# API error 409 `idempotency_conflict`

## What it means

The same Idempotency-Key was reused with a different body.

## Example response

```json
{
  "error": "idempotency_conflict",
  "status": 409,
  "detail": "See the message field for the specific field or limit involved.",
  "request_id": "req_01HZX9Q2N4"
}
```

## How to fix it

Generate a new UUID per logical operation; reuse a key only when retrying that exact request.

## Is it safe to retry?

No. Retrying an identical request produces the same error; change the request first.

## Still stuck?

Quote the `request_id` from the response when contacting support. It lets us
find the exact call in our logs, which is far faster than a description.
