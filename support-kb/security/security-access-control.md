---
id: security-access-control
title: Who inside Acme can see customer data
category: security
tags: [access-control, compliance, security]
audience: customer
severity: normal
---

# Who inside Acme can see customer data

Access to production data requires a named, time-boxed approval and is logged
to an append-only audit trail reviewed monthly. Support staff can see workspace
and billing metadata by default; reading file *content* requires explicit,
per-incident customer consent recorded in the ticket.

Engineers have no standing production access. Break-glass access pages the
security team and expires after four hours.
