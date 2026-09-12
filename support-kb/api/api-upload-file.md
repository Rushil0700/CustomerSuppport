---
id: api-upload-file
title: API: Upload a file
category: api
tags: [api, reference, upload]
audience: customer
severity: normal
---

# API: Upload a file

```
POST https://api.acme.example/v1/files
```

**Required scope:** `files:write`

Multipart upload. Files above 10 MB must use the resumable session endpoint.

## Request

```bash
curl -X POST "https://api.acme.example/v1/files" \
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
