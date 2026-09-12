---
id: billing-failed-payment
title: A payment failed - what happens next
category: billing
tags: [billing, card, dunning, failed, payment]
audience: customer
severity: normal
---

# A payment failed - what happens next

## The retry schedule

When a charge is declined we retry on **day 1, day 3 and day 7**. The workspace
stays fully active for all 14 days of the grace period. On day 15 the workspace
moves to read-only: existing data stays safe and downloadable, but new writes
are blocked until payment succeeds.

## Fix it yourself

1. Settings > Billing > **Payment method**.
2. Add a working card or switch to invoice billing (Business and Enterprise).
3. Choose **Retry now**. The charge is attempted immediately.

## Common decline reasons

- *insufficient_funds* - the bank declined; another card usually works.
- *card_expired* - update the expiry date.
- *do_not_honor* - a generic bank refusal. The customer must call their bank; we
  receive no further detail and cannot override it.
- *3d_secure_required* - the cardholder must complete the bank's confirmation
  prompt. Choose **Retry now** while the cardholder is at their device.

## Escalate

Escalate if a workspace has already moved to read-only and the customer disputes
the charge, or if the same card fails after three different fixes.
