---
id: api-error-502-upstream_error
title: API error 502 upstream_error
category: api
tags: [502, api, error, upstream_error]
audience: customer
severity: normal
---

# API error 502 `upstream_error`

## What it means

A downstream provider failed.

## Example response

```json
{
  "error": "upstream_error",
  "status": 502,
  "detail": "See the message field for the specific field or limit involved.",
  "request_id": "req_01HZX9Q2N4"
}
```

## How to fix it

Safe to retry; these are almost always transient.

## Is it safe to retry?

Yes - retry with exponential backoff.

## Still stuck?

Quote the `request_id` from the response when contacting support. It lets us
find the exact call in our logs, which is far faster than a description.
