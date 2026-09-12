---
id: api-list-workspaces
title: API: List workspaces
category: api
tags: [api, list, reference]
audience: customer
severity: normal
---

# API: List workspaces

```
GET https://api.acme.example/v1/workspaces
```

**Required scope:** `workspaces:read`

Returns every workspace the key can access, newest first.

## Request

```bash
curl -X GET "https://api.acme.example/v1/workspaces" \
  -H "Authorization: Bearer $ACME_API_KEY" \
  -H "Content-Type: application/json"
```

## Notes

- All endpoints are versioned; `/v1` is stable and will not break.
- Rate limits are per API key: 60 requests/minute on Team, 600 on Business,
  negotiated on Enterprise. The `X-RateLimit-Remaining` header tracks your budget.
- Every response carries a `request_id`. Log it - support asks for it first.
- Write endpoints accept an `Idempotency-Key` header; reuse it only when
  retrying the identical request.

## Errors

See the API error articles for `401`, `403`, `404`, `409` and `429`, which are
the codes this endpoint returns most often.
