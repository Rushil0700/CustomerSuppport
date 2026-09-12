---
id: api-move-file
title: API: Move or rename a file
category: api
tags: [api, move, reference]
audience: customer
severity: normal
---

# API: Move or rename a file

```
PATCH https://api.acme.example/v1/files/{id}
```

**Required scope:** `files:write`

Changing `parent_id` moves it; changing `name` renames it. Share links survive both.

## Request

```bash
curl -X PATCH "https://api.acme.example/v1/files/{id}" \
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
