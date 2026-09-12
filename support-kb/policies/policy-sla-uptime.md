---
id: policy-sla-uptime
title: Uptime commitment and service credits
category: policies
tags: [credits, policy, sla, uptime]
audience: customer
severity: normal
---

# Uptime commitment and service credits

## Targets

| Plan | Monthly uptime | Support response |
| --- | --- | --- |
| Free | none | community only |
| Starter | 99.5% | 2 business days |
| Team | 99.9% | 1 business day |
| Business | 99.9% | 4 business hours |
| Enterprise | 99.95% | 1 hour, 24x7 for Sev-1 |

Uptime excludes scheduled maintenance, announced at least 72 hours ahead on
https://status.acme.example, capped at four hours per month.

## Service credits

| Monthly uptime | Credit |
| --- | --- |
| Below target but at or above 99.0% | 10% of the monthly fee |
| 95.0% to 98.99% | 25% |
| Below 95.0% | 50% |

Credits are requested within 30 days of the incident and applied to the next
invoice. They are the sole remedy for missed uptime.

## Escalate

Credit requests are approved by a human agent; the automated agent should
explain the policy and hand the request over.
