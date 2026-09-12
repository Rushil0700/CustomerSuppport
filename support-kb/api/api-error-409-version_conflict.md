---
id: api-error-409-version_conflict
title: API error 409 version_conflict
category: api
tags: [409, api, error, version_conflict]
audience: customer
severity: normal
---

# API error 409 `version_conflict`

## What it means

The record changed between your read and your write.

## Example response

```json
{
  "error": "version_conflict",
  "status": 409,
  "detail": "See the message field for the specific field or limit involved.",
  "request_id": "req_01HZX9Q2N4"
}
```

## How to fix it

Re-read the record, reapply your change to the new `version`, and retry.

## Is it safe to retry?

No. Retrying an identical request produces the same error; change the request first.

## Still stuck?

Quote the `request_id` from the response when contacting support. It lets us
find the exact call in our logs, which is far faster than a description.
