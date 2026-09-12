---
id: api-error-401-missing_credentials
title: API error 401 missing_credentials
category: api
tags: [401, api, error, missing_credentials]
audience: customer
severity: normal
---

# API error 401 `missing_credentials`

## What it means

No API key was supplied.

## Example response

```json
{
  "error": "missing_credentials",
  "status": 401,
  "detail": "See the message field for the specific field or limit involved.",
  "request_id": "req_01HZX9Q2N4"
}
```

## How to fix it

Send the key in the `Authorization: Bearer sk_live_...` header, not as a query parameter.

## Is it safe to retry?

No. Retrying an identical request produces the same error; change the request first.

## Still stuck?

Quote the `request_id` from the response when contacting support. It lets us
find the exact call in our logs, which is far faster than a description.
