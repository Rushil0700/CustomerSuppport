---
id: troubleshooting-proxy-blocking-web
title: The app cannot reach the service on a corporate network (the web app)
category: troubleshooting
tags: [enterprise, firewall, network, proxy, web]
audience: customer
severity: normal
---

# The app cannot reach the service on a corporate network (the web app)

## Symptom

Connection errors at the office but not at home.

## Cause

A proxy, TLS inspection, or a firewall rule.

## Resolution

These steps are written for **the web app**. Clear the site data for app.acme.example under your browser's privacy settings.

1. Ask IT to allow `*.acme.example` on TCP 443.
2. Exempt our domains from TLS interception - we pin certificates, so an inspecting proxy breaks the connection by design.
3. Configure the proxy explicitly under Settings > Network if the system proxy is not detected.
4. For a proxy requiring authentication, use the credentials field rather than expecting single sign-on to flow through.

## Verify

The connection indicator turns green on the corporate network.

## When to escalate

Escalate with the exact error and a traceroute when IT confirms the allowlist is in place.
