---
id: api-error-429-concurrency_limited
title: API error 429 concurrency_limited
category: api
tags: [429, api, concurrency_limited, error]
audience: customer
severity: normal
---

# API error 429 `concurrency_limited`

## What it means

Too many simultaneous long-running jobs.

## Example response

```json
{
  "error": "concurrency_limited",
  "status": 429,
  "detail": "See the message field for the specific field or limit involved.",
  "request_id": "req_01HZX9Q2N4"
}
```

## How to fix it

Queue jobs client-side and keep in-flight jobs under the limit shown in the error `detail`.

## Is it safe to retry?

Yes - retry with exponential backoff.

## Still stuck?

Quote the `request_id` from the response when contacting support. It lets us
find the exact call in our logs, which is far faster than a description.
