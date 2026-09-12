---
id: security-data-residency
title: Where your data is stored
category: security
tags: [compliance, data-residency, security]
audience: customer
severity: normal
---

# Where your data is stored

Workspace content is stored in the region chosen at creation: us-east, eu-west or
ap-southeast. It stays there, including backups.

Metadata needed to route requests - workspace ids, and the region mapping itself -
is global by necessity. Support tooling and billing records are held in us-east
regardless of workspace region.

The region cannot be changed after creation; moving means exporting and importing
into a new workspace.
