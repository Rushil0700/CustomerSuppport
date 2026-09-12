---
id: api-error-403-plan_restricted
title: API error 403 plan_restricted
category: api
tags: [403, api, error, plan_restricted]
audience: customer
severity: normal
---

# API error 403 `plan_restricted`

## What it means

The endpoint is not available on your plan.

## Example response

```json
{
  "error": "plan_restricted",
  "status": 403,
  "detail": "See the message field for the specific field or limit involved.",
  "request_id": "req_01HZX9Q2N4"
}
```

## How to fix it

The API is available from the Team plan upward. Upgrade under Settings > Billing.

## Is it safe to retry?

No. Retrying an identical request produces the same error; change the request first.

## Still stuck?

Quote the `request_id` from the response when contacting support. It lets us
find the exact call in our logs, which is far faster than a description.
