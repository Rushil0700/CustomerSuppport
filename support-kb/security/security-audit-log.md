---
id: security-audit-log
title: Reading the audit log
category: security
tags: [audit-log, compliance, security]
audience: customer
severity: normal
---

# Reading the audit log

Settings > Security > **Audit log** records sign-ins, permission changes,
share link creation, integration grants and data exports. Each entry has an
actor, an IP address, a user agent and a timestamp in UTC.

Retention is 12 months on Business and Enterprise, 30 days elsewhere. Enterprise
workspaces can stream events continuously to an S3 bucket or a SIEM.
