---
id: api-error-403-insufficient_scope
title: API error 403 insufficient_scope
category: api
tags: [403, api, error, insufficient_scope]
audience: customer
severity: normal
---

# API error 403 `insufficient_scope`

## What it means

The key lacks the scope the endpoint requires.

## Example response

```json
{
  "error": "insufficient_scope",
  "status": 403,
  "detail": "See the message field for the specific field or limit involved.",
  "request_id": "req_01HZX9Q2N4"
}
```

## How to fix it

Edit the key and grant the scope named in the error, then retry. Scopes take effect immediately.

## Is it safe to retry?

No. Retrying an identical request produces the same error; change the request first.

## Still stuck?

Quote the `request_id` from the response when contacting support. It lets us
find the exact call in our logs, which is far faster than a description.
