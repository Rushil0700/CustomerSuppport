---
id: api-error-400-invalid_request
title: API error 400 invalid_request
category: api
tags: [400, api, error, invalid_request]
audience: customer
severity: normal
---

# API error 400 `invalid_request`

## What it means

A required field was missing or malformed.

## Example response

```json
{
  "error": "invalid_request",
  "status": 400,
  "detail": "See the message field for the specific field or limit involved.",
  "request_id": "req_01HZX9Q2N4"
}
```

## How to fix it

Compare your payload against the schema at /docs/api#schemas. The `detail` array names the offending field.

## Is it safe to retry?

No. Retrying an identical request produces the same error; change the request first.

## Still stuck?

Quote the `request_id` from the response when contacting support. It lets us
find the exact call in our logs, which is far faster than a description.
