---
id: troubleshooting-cannot-login
title: Cannot sign in although the password is correct
category: troubleshooting
tags: [account, login, signin, troubleshooting]
audience: customer
severity: normal
---

# Cannot sign in although the password is correct

Work through these in order; each is a genuinely different cause.

1. **Wrong workspace.** Email plus password authenticates you, but you may have
   been invited to a different workspace than the one you are opening. Use the
   workspace switcher on the login screen.
2. **The account is suspended for non-payment.** The error reads "This workspace
   is read-only". See the failed payment article.
3. **SSO is now enforced.** Once an admin enables SAML, password login stops
   working for everyone in the domain. Use **Continue with SSO**.
4. **Too many attempts.** Ten failures locks sign-in for 15 minutes. Wait it out;
   the counter resets automatically and no support action is needed.
5. **The invitation was never accepted.** Pending invites cannot sign in. Ask the
   admin to resend it from Settings > Members.

## Escalate

Escalate if none of the five apply, or if the customer reports the account exists
but the login page reports "account not found" - that mismatch needs staff tools.
