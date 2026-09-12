---
id: security-password-requirements
title: Password requirements
category: security
tags: [compliance, password-requirements, security]
audience: customer
severity: normal
---

# Password requirements

Passwords must be at least 12 characters. We impose no composition rules -
forced symbols and digits demonstrably produce weaker, more predictable
passwords - but we do check every new password against a corpus of known-breached
credentials and refuse matches.

Admins on Business and Enterprise can require a minimum length up to 64 and set a
rotation period. We advise against rotation: NIST withdrew that recommendation
because scheduled rotation drives people toward predictable variations.
