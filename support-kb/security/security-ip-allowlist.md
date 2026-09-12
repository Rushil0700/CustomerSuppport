---
id: security-ip-allowlist
title: Restricting access by IP address
category: security
tags: [compliance, ip-allowlist, security]
audience: customer
severity: normal
---

# Restricting access by IP address

Enterprise workspaces can allow only named CIDR ranges. Add them under
Settings > Security > **IP allowlist**.

Add your own current address before saving - the rule applies immediately and it
is entirely possible to lock yourself out. API keys are subject to the same list,
so remember CI runners and servers, whose egress addresses are easy to forget.
