---
id: api-error-401-invalid_api_key
title: API error 401 invalid_api_key
category: api
tags: [401, api, error, invalid_api_key]
audience: customer
severity: normal
---

# API error 401 `invalid_api_key`

## What it means

The key was revoked, rotated, or mistyped.

## Example response

```json
{
  "error": "invalid_api_key",
  "status": 401,
  "detail": "See the message field for the specific field or limit involved.",
  "request_id": "req_01HZX9Q2N4"
}
```

## How to fix it

Generate a fresh key under Settings > Developers > API keys and update your secret store.

## Is it safe to retry?

No. Retrying an identical request produces the same error; change the request first.

## Still stuck?

Quote the `request_id` from the response when contacting support. It lets us
find the exact call in our logs, which is far faster than a description.
