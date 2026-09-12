---
id: billing-update-vat
title: Add or correct a VAT / GST number
category: billing
tags: [billing, invoice, tax, vat]
audience: customer
severity: normal
---

# Add or correct a VAT / GST number

## Symptom

An invoice shows tax that should have been reverse-charged, or the tax id is missing.

## Cause

Tax treatment is derived from the billing country and the tax id on file at the moment of invoicing.

## Resolution

1. Settings > Billing > **Billing details**.
2. Enter the VAT/GST/ABN number and the registered address.
3. Save. Validation against the tax authority takes up to a minute.
4. Future invoices apply the reverse charge where the rules allow.

## Verify

The next invoice shows the tax id and a zero-rated line where applicable.

## When to escalate

Escalate to request a reissued invoice for a period already billed - only finance can reissue.
