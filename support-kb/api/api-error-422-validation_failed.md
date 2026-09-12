---
id: api-error-422-validation_failed
title: API error 422 validation_failed
category: api
tags: [422, api, error, validation_failed]
audience: customer
severity: normal
---

# API error 422 `validation_failed`

## What it means

The payload parsed but failed business validation.

## Example response

```json
{
  "error": "validation_failed",
  "status": 422,
  "detail": "See the message field for the specific field or limit involved.",
  "request_id": "req_01HZX9Q2N4"
}
```

## How to fix it

Read the `errors[].field` and `errors[].reason` pairs; each maps to one input.

## Is it safe to retry?

No. Retrying an identical request produces the same error; change the request first.

## Still stuck?

Quote the `request_id` from the response when contacting support. It lets us
find the exact call in our logs, which is far faster than a description.
