---
id: api-error-404-resource_not_found
title: API error 404 resource_not_found
category: api
tags: [404, api, error, resource_not_found]
audience: customer
severity: normal
---

# API error 404 `resource_not_found`

## What it means

The id does not exist, or belongs to another workspace.

## Example response

```json
{
  "error": "resource_not_found",
  "status": 404,
  "detail": "See the message field for the specific field or limit involved.",
  "request_id": "req_01HZX9Q2N4"
}
```

## How to fix it

Confirm the id and that your key belongs to the same workspace as the resource.

## Is it safe to retry?

No. Retrying an identical request produces the same error; change the request first.

## Still stuck?

Quote the `request_id` from the response when contacting support. It lets us
find the exact call in our logs, which is far faster than a description.
