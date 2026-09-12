---
id: api-error-504-timeout
title: API error 504 timeout
category: api
tags: [504, api, error, timeout]
audience: customer
severity: normal
---

# API error 504 `timeout`

## What it means

The request exceeded the 30 second gateway budget.

## Example response

```json
{
  "error": "timeout",
  "status": 504,
  "detail": "See the message field for the specific field or limit involved.",
  "request_id": "req_01HZX9Q2N4"
}
```

## How to fix it

Narrow the query with filters or pagination; export endpoints should be used for bulk reads.

## Is it safe to retry?

Yes - retry with exponential backoff.

## Still stuck?

Quote the `request_id` from the response when contacting support. It lets us
find the exact call in our logs, which is far faster than a description.
