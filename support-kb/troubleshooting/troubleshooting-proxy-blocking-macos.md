---
id: troubleshooting-proxy-blocking-macos
title: The app cannot reach the service on a corporate network (the macOS desktop app)
category: troubleshooting
tags: [enterprise, firewall, macos, network, proxy]
audience: customer
severity: normal
---

# The app cannot reach the service on a corporate network (the macOS desktop app)

## Symptom

Connection errors at the office but not at home.

## Cause

A proxy, TLS inspection, or a firewall rule.

## Resolution

These steps are written for **the macOS desktop app**. Settings are stored in `~/Library/Application Support/AcmeCloud/config.json`.

1. Ask IT to allow `*.acme.example` on TCP 443.
2. Exempt our domains from TLS interception - we pin certificates, so an inspecting proxy breaks the connection by design.
3. Configure the proxy explicitly under Settings > Network if the system proxy is not detected.
4. For a proxy requiring authentication, use the credentials field rather than expecting single sign-on to flow through.

## Verify

The connection indicator turns green on the corporate network.

## When to escalate

Escalate with the exact error and a traceroute when IT confirms the allowlist is in place.
