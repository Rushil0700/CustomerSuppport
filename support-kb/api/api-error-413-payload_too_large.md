---
id: api-error-413-payload_too_large
title: API error 413 payload_too_large
category: api
tags: [413, api, error, payload_too_large]
audience: customer
severity: normal
---

# API error 413 `payload_too_large`

## What it means

The request body exceeded 10 MB.

## Example response

```json
{
  "error": "payload_too_large",
  "status": 413,
  "detail": "See the message field for the specific field or limit involved.",
  "request_id": "req_01HZX9Q2N4"
}
```

## How to fix it

Use the multipart upload endpoint for files above 10 MB.

## Is it safe to retry?

No. Retrying an identical request produces the same error; change the request first.

## Still stuck?

Quote the `request_id` from the response when contacting support. It lets us
find the exact call in our logs, which is far faster than a description.
