#!/usr/bin/env python
"""Generate the support knowledge base under ``support-kb/``.

The corpus describes a fictional SaaS ("Acme Cloud") so the retrieval quality of
the RAG engine can be measured against realistic support content. Documents are
composed from a curated catalogue of genuine support scenarios - symptom, cause,
numbered resolution steps, escalation criteria - expanded across the product
surfaces each scenario applies to.

The output is deterministic: running this twice produces byte-identical files,
so re-running it never creates spurious diffs or duplicate vectors.

Usage::

    python scripts/generate_kb.py            # write support-kb/
    python scripts/generate_kb.py --count    # report how many docs would be written
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
KB_DIR = REPO_ROOT / "support-kb"

PRODUCT = "Acme Cloud"
SUPPORT_EMAIL = "support@acme.example"
STATUS_PAGE = "https://status.acme.example"


@dataclass
class Doc:
    """One knowledge base article to be written to disk."""

    doc_id: str
    title: str
    category: str
    tags: list[str]
    body: str
    audience: str = "customer"
    severity: str = "normal"

    def render(self) -> str:
        """Serialise to Markdown with YAML front matter."""
        tags = ", ".join(sorted(set(self.tags)))
        return (
            "---\n"
            f"id: {self.doc_id}\n"
            f"title: {self.title}\n"
            f"category: {self.category}\n"
            f"tags: [{tags}]\n"
            f"audience: {self.audience}\n"
            f"severity: {self.severity}\n"
            "---\n\n"
            f"{self.body.strip()}\n"
        )


@dataclass
class Scenario:
    """A support scenario expanded into one document per surface."""

    slug: str
    title: str
    symptom: str
    cause: str
    steps: list[str]
    verify: str
    escalate: str
    tags: list[str]
    surfaces: list[str] = field(default_factory=lambda: [""])
    severity: str = "normal"


# --- Surfaces ----------------------------------------------------------------

PLATFORMS = ["web", "windows", "macos", "ios", "android"]
PLATFORM_LABEL = {
    "web": "the web app",
    "windows": "the Windows desktop app",
    "macos": "the macOS desktop app",
    "ios": "the iOS app",
    "android": "the Android app",
}
PLATFORM_HINT = {
    "web": "Clear the site data for app.acme.example under your browser's privacy settings.",
    "windows": "Settings are stored in `%APPDATA%\\AcmeCloud\\config.json`.",
    "macos": "Settings are stored in `~/Library/Application Support/AcmeCloud/config.json`.",
    "ios": "Force-quit by swiping up from the app switcher before retrying.",
    "android": "Use Settings > Apps > Acme Cloud > Storage > Clear cache (not Clear data).",
}

PLANS = ["free", "starter", "team", "business", "enterprise"]
PLAN_LABEL = {
    "free": "Free",
    "starter": "Starter",
    "team": "Team",
    "business": "Business",
    "enterprise": "Enterprise",
}
PLAN_SEATS = {"free": 1, "starter": 3, "team": 25, "business": 200, "enterprise": "unlimited"}
PLAN_PRICE = {"free": "$0", "starter": "$12", "team": "$29", "business": "$59", "enterprise": "custom"}

INTEGRATIONS = [
    ("slack", "Slack"),
    ("microsoft-teams", "Microsoft Teams"),
    ("google-drive", "Google Drive"),
    ("dropbox", "Dropbox"),
    ("github", "GitHub"),
    ("gitlab", "GitLab"),
    ("jira", "Jira"),
    ("linear", "Linear"),
    ("asana", "Asana"),
    ("trello", "Trello"),
    ("notion", "Notion"),
    ("salesforce", "Salesforce"),
    ("hubspot", "HubSpot"),
    ("zendesk", "Zendesk"),
    ("intercom", "Intercom"),
    ("stripe", "Stripe"),
    ("quickbooks", "QuickBooks"),
    ("okta", "Okta"),
    ("azure-ad", "Microsoft Entra ID"),
    ("google-workspace", "Google Workspace"),
    ("zoom", "Zoom"),
    ("figma", "Figma"),
    ("zapier", "Zapier"),
    ("webhooks", "Outgoing Webhooks"),
    ("s3", "Amazon S3"),
]

API_ERRORS = [
    ("400", "invalid_request", "A required field was missing or malformed.",
     "Compare your payload against the schema at /docs/api#schemas. The `detail` array names the offending field."),
    ("401", "missing_credentials", "No API key was supplied.",
     "Send the key in the `Authorization: Bearer sk_live_...` header, not as a query parameter."),
    ("401", "invalid_api_key", "The key was revoked, rotated, or mistyped.",
     "Generate a fresh key under Settings > Developers > API keys and update your secret store."),
    ("403", "insufficient_scope", "The key lacks the scope the endpoint requires.",
     "Edit the key and grant the scope named in the error, then retry. Scopes take effect immediately."),
    ("403", "plan_restricted", "The endpoint is not available on your plan.",
     "The API is available from the Team plan upward. Upgrade under Settings > Billing."),
    ("404", "resource_not_found", "The id does not exist, or belongs to another workspace.",
     "Confirm the id and that your key belongs to the same workspace as the resource."),
    ("409", "idempotency_conflict", "The same Idempotency-Key was reused with a different body.",
     "Generate a new UUID per logical operation; reuse a key only when retrying that exact request."),
    ("409", "version_conflict", "The record changed between your read and your write.",
     "Re-read the record, reapply your change to the new `version`, and retry."),
    ("413", "payload_too_large", "The request body exceeded 10 MB.",
     "Use the multipart upload endpoint for files above 10 MB."),
    ("422", "validation_failed", "The payload parsed but failed business validation.",
     "Read the `errors[].field` and `errors[].reason` pairs; each maps to one input."),
    ("429", "rate_limited", "You exceeded the requests-per-minute budget for your plan.",
     "Honour the `Retry-After` header and back off exponentially. Burst capacity refills over 60 seconds."),
    ("429", "concurrency_limited", "Too many simultaneous long-running jobs.",
     "Queue jobs client-side and keep in-flight jobs under the limit shown in the error `detail`."),
    ("500", "internal_error", "An unexpected failure on our side.",
     f"Retry with backoff. If it persists, send us the `request_id` from the response and check {STATUS_PAGE}."),
    ("502", "upstream_error", "A downstream provider failed.",
     "Safe to retry; these are almost always transient."),
    ("503", "maintenance", "The endpoint is briefly unavailable during a deploy.",
     f"Retry after the interval in `Retry-After`. Watch {STATUS_PAGE} for scheduled windows."),
    ("504", "timeout", "The request exceeded the 30 second gateway budget.",
     "Narrow the query with filters or pagination; export endpoints should be used for bulk reads."),
]

APP_ERRORS = [
    ("ERR_SYNC_QUOTA", "Sync paused: storage limit reached",
     "The workspace used every byte of its plan allowance, including trash and version history.",
     "Empty trash, reduce version retention, archive finished projects, or upgrade. Sync resumes on its own within minutes of dropping below the limit."),
    ("ERR_SYNC_LOCKED", "Sync paused: file locked by another application",
     "Another program holds an exclusive lock on the file - Office and Adobe applications do this while a document is open.",
     "Close the application holding the file. The transfer resumes within a minute without any further action."),
    ("ERR_PATH_TOO_LONG", "Path exceeds the operating system limit",
     "The full path is longer than 260 characters, which Windows rejects.",
     "Shorten a parent folder name, or move the folder closer to the drive root. Enabling long path support in Windows also works but needs a policy change."),
    ("ERR_INVALID_CHARS", "File name contains unsupported characters",
     "The name contains one of \\\\ / : * ? \" < > |, which at least one supported platform refuses.",
     "Rename the file. Until you do, the rest of that folder's queue stays blocked behind it."),
    ("ERR_WORKSPACE_READONLY", "Workspace is read-only",
     "Billing lapsed past the 14 day grace period, or an admin suspended writes deliberately.",
     "Settle the outstanding invoice under Settings > Billing. Write access returns within a minute of a successful charge."),
    ("ERR_SEAT_LIMIT", "No seats available",
     "Every seat on the plan is taken by an active member or a pending invitation.",
     "Remove a member, revoke an unaccepted invitation, or add seats under Settings > Billing."),
    ("ERR_FILE_TOO_LARGE", "File exceeds the maximum size for this plan",
     "The single-file limit is a hard per-plan ceiling checked before the upload starts.",
     "Split the file, compress it, or upgrade. Nothing is uploaded partially - the file is refused outright."),
    ("ERR_VIRUS_DETECTED", "Upload blocked by malware scanning",
     "Our scanner matched a known malware signature in the file.",
     "The upload is refused and the file quarantined. If you believe it is a false positive, contact support with the file name and the time - do not retry, the result will be identical."),
    ("ERR_SSO_REQUIRED", "Password sign-in disabled for this domain",
     "An admin enforced SAML SSO, which disables password login for the whole email domain.",
     "Use **Continue with SSO**, or reach the workspace through your identity provider's app tile."),
    ("ERR_DEVICE_PENDING", "Device awaiting approval",
     "Device approval is enabled and an admin has not yet approved this device.",
     "Ask a workspace admin to approve it under Settings > Security > Devices. You receive an email when it is approved."),
    ("ERR_IP_BLOCKED", "Access denied from this network",
     "The workspace has an IP allowlist and your current address is not on it.",
     "Connect through the corporate VPN, or ask an admin to add your CIDR range. API keys are subject to the same list."),
    ("ERR_LINK_EXPIRED", "This share link has expired",
     "The link reached its expiry date, or the file moved workspace, which invalidates links.",
     "Ask the sender to generate a fresh link. Expiry cannot be extended on an existing link."),
    ("ERR_LINK_PASSWORD", "Incorrect share link password",
     "The password on the share link does not match.",
     "Passwords are case-sensitive and are not recoverable - the sender must reset it or issue a new link."),
    ("ERR_DOMAIN_RESTRICTED", "Share link restricted to approved domains",
     "An admin limited share links to specific email domains and the recipient's address is outside them.",
     "Share with the person by email instead, or ask an admin to add the recipient's domain under Settings > Security."),
    ("ERR_PROJECT_ARCHIVED", "Project is archived and read-only",
     "Archived projects are deliberately frozen to halve their storage cost.",
     "Unarchive it from the project menu. Unarchiving is instant and restores full write access."),
    ("ERR_VERSION_CONFLICT", "This file changed since you opened it",
     "Someone else saved the file while you had it open.",
     "Reload and reapply your change, or save yours as a copy. Both versions are always preserved - nothing is silently overwritten."),
    ("ERR_TRASH_EXPIRED", "Item is no longer recoverable",
     "The file has been in trash for more than 30 days and has been purged.",
     "Check whether an earlier version survives elsewhere, or whether the file exists on a device that was offline. Beyond 35 days it is gone from backups too."),
    ("ERR_EXPORT_IN_PROGRESS", "An export is already running",
     "Only one export job runs per workspace at a time.",
     "Wait for the running export to finish; you receive an email with the download link. Large workspaces take several hours."),
    ("ERR_INTEGRATION_TOKEN", "Integration credentials expired",
     "The OAuth grant was revoked, or the authorising user lost access in the third-party tool.",
     "Reconnect the integration under Settings > Integrations. Use a service account so staff turnover does not break it again."),
    ("ERR_INDEX_PENDING", "File not yet searchable",
     "Indexing runs a few minutes behind upload, and longer for very large files.",
     "Wait five minutes and search again. Search by filename works immediately."),
    ("ERR_MFA_REQUIRED", "Multi-factor authentication required",
     "An admin requires MFA for all members and yours is not enrolled.",
     "Enrol under Settings > Security > Two-factor authentication. New members get a seven day grace period."),
    ("ERR_RATE_LIMITED_UI", "Too many requests - slow down",
     "An unusual burst of actions from one session tripped the abuse protection.",
     "Wait 60 seconds. If a script is driving the web app, move it to the API, which has documented, higher limits."),
    ("ERR_UNSUPPORTED_BROWSER", "This browser is not supported",
     "The web app needs a browser released within roughly the last two years.",
     "Update to a current Chrome, Edge, Firefox or Safari. Internet Explorer is not supported at all."),
    ("ERR_CLOCK_SKEW", "Device clock is out of sync",
     "The device clock differs from real time by more than 30 seconds, which breaks TOTP codes and request signing.",
     "Enable automatic time synchronisation in the operating system's date and time settings, then retry."),
    ("ERR_DISK_FULL", "Not enough local disk space",
     "The sync folder's drive has less free space than the pending download needs.",
     "Free space, move the sync folder to a larger drive, or use selective sync to exclude folders you do not need locally."),
]

API_ENDPOINTS = [
    ("list-workspaces", "List workspaces", "GET", "/v1/workspaces", "workspaces:read",
     "Returns every workspace the key can access, newest first."),
    ("create-workspace", "Create a workspace", "POST", "/v1/workspaces", "workspaces:write",
     "Creates a workspace and makes the calling user its owner."),
    ("list-projects", "List projects", "GET", "/v1/projects", "projects:read",
     "Supports `workspace_id`, `status` and `updated_since` filters."),
    ("create-project", "Create a project", "POST", "/v1/projects", "projects:write",
     "Requires `name` and `workspace_id`."),
    ("update-project", "Update a project", "PATCH", "/v1/projects/{id}", "projects:write",
     "Partial update; send only the fields you are changing plus `version`."),
    ("delete-project", "Delete a project", "DELETE", "/v1/projects/{id}", "projects:write",
     "Soft-deletes for 30 days, after which the data is unrecoverable."),
    ("list-files", "List files", "GET", "/v1/files", "files:read",
     "Cursor-paginated; follow `next_cursor` until it is null."),
    ("upload-file", "Upload a file", "POST", "/v1/files", "files:write",
     "Multipart upload. Files above 10 MB must use the resumable session endpoint."),
    ("download-file", "Download a file", "GET", "/v1/files/{id}/content", "files:read",
     "Returns a 302 to a signed URL valid for 15 minutes."),
    ("create-share-link", "Create a share link", "POST", "/v1/files/{id}/links", "files:share",
     "Optional `expires_at` and `password` fields."),
    ("list-members", "List workspace members", "GET", "/v1/members", "members:read",
     "Includes seat status, role and last-active timestamp."),
    ("invite-member", "Invite a member", "POST", "/v1/members", "members:write",
     "Consumes a seat immediately on Team and Business plans."),
    ("remove-member", "Remove a member", "DELETE", "/v1/members/{id}", "members:write",
     "Frees the seat at the end of the current billing period."),
    ("list-webhooks", "List webhook endpoints", "GET", "/v1/webhooks", "webhooks:read",
     "Shows the last delivery status for each endpoint."),
    ("create-webhook", "Register a webhook", "POST", "/v1/webhooks", "webhooks:write",
     "Returns a signing secret shown exactly once."),
    ("replay-webhook", "Replay a webhook delivery", "POST", "/v1/webhooks/{id}/replay", "webhooks:write",
     "Re-sends the stored payload; useful after fixing a receiver bug."),
    ("list-events", "List audit events", "GET", "/v1/events", "audit:read",
     "Business and Enterprise plans retain 12 months of events."),
    ("export-data", "Start a data export", "POST", "/v1/exports", "workspace:export",
     "Asynchronous; poll the returned job id or wait for the `export.completed` webhook."),
    ("usage-summary", "Fetch usage", "GET", "/v1/usage", "billing:read",
     "Daily granularity for the current billing period."),
    ("rotate-key", "Rotate an API key", "POST", "/v1/keys/{id}/rotate", "keys:write",
     "Issues a new secret and keeps the old one valid for a 24 hour overlap."),
    ("search", "Search content", "GET", "/v1/search", "files:read",
     "Full-text and filename search. Supports `q`, `project_id`, `type` and `updated_since`."),
    ("get-file", "Fetch file metadata", "GET", "/v1/files/{id}", "files:read",
     "Metadata only; use the content endpoint for bytes."),
    ("move-file", "Move or rename a file", "PATCH", "/v1/files/{id}", "files:write",
     "Changing `parent_id` moves it; changing `name` renames it. Share links survive both."),
    ("copy-file", "Copy a file", "POST", "/v1/files/{id}/copy", "files:write",
     "Copies within or across projects in the same workspace."),
    ("list-versions", "List file versions", "GET", "/v1/files/{id}/versions", "files:read",
     "Newest first; retention depends on the plan."),
    ("restore-version", "Restore a file version", "POST", "/v1/files/{id}/versions/{version}/restore", "files:write",
     "Creates a new version from the old content rather than rewriting history."),
    ("list-comments", "List comments", "GET", "/v1/files/{id}/comments", "comments:read",
     "Threaded; each comment carries `parent_id` where it is a reply."),
    ("create-comment", "Post a comment", "POST", "/v1/files/{id}/comments", "comments:write",
     "Mentions use `@[user_id]` and trigger a notification."),
    ("list-trash", "List trashed items", "GET", "/v1/trash", "files:read",
     "Items older than 30 days are absent - they have been purged."),
    ("restore-trash", "Restore from trash", "POST", "/v1/trash/{id}/restore", "files:write",
     "Restores to the original location, recreating parent folders if needed."),
    ("empty-trash", "Empty trash", "DELETE", "/v1/trash", "files:write",
     "Irreversible. Frees quota immediately."),
    ("archive-project", "Archive a project", "POST", "/v1/projects/{id}/archive", "projects:write",
     "Makes the project read-only and roughly halves its storage footprint."),
    ("list-invites", "List pending invitations", "GET", "/v1/invites", "members:read",
     "Pending invitations consume seats, so reconcile this against your seat count."),
    ("revoke-invite", "Revoke an invitation", "DELETE", "/v1/invites/{id}", "members:write",
     "Frees the seat immediately, unlike removing an active member."),
    ("list-keys", "List API keys", "GET", "/v1/keys", "keys:read",
     "Shows scopes, creation date and last use. Secrets are never returned."),
    ("create-key", "Create an API key", "POST", "/v1/keys", "keys:write",
     "The secret is returned exactly once - store it immediately."),
    ("revoke-key", "Revoke an API key", "DELETE", "/v1/keys/{id}", "keys:write",
     "Takes effect within seconds across every region."),
    ("list-integrations", "List integrations", "GET", "/v1/integrations", "integrations:read",
     "Includes connection status and last sync time for each."),
    ("verify-webhook", "Verify a webhook signature", "POST", "/v1/webhooks/{id}/test", "webhooks:read",
     "Sends a signed test payload so you can validate your verification code."),
    ("whoami", "Identify the calling key", "GET", "/v1/whoami", "",
     "Returns the workspace, scopes and rate limit for the key. Needs no scope - useful as a first call when debugging auth."),
]

WORKFLOWS = [
    ("onboard-new-hire", "Onboard a new team member",
     ["Invite them at Settings > Members with the **member** role; use **guest** for contractors.",
      "Add them to the projects they need. Members see all projects, so guests are the right choice for narrow access.",
      "Ask them to enrol in MFA on day one - workspace-wide enforcement gives new members only seven days.",
      "Point them at the getting-started articles: install, invite, organise, share."],
     "They can sign in, see the expected projects, and appear as Active in Settings > Members."),
    ("offboard-departing-member", "Offboard someone who is leaving",
     ["Transfer ownership of anything they solely own - projects and, critically, the workspace itself.",
      "Reassign their integrations; personal OAuth grants break the moment their account goes.",
      "Remove them from Settings > Members. Their files stay; only access is removed.",
      "Revoke API keys they created under Settings > Developers.",
      "Check Settings > Security > Active sessions to confirm nothing remains signed in."],
     "The audit log records the removal and no sessions or keys remain for that account."),
    ("quarterly-access-review", "Run a quarterly access review",
     ["Export the member list and roles from Settings > Members.",
      "Question every admin - admin is the role that accumulates without anyone noticing.",
      "Review guests: contractors whose engagement ended should be removed, not downgraded.",
      "Review API keys by last-used date and revoke anything idle for 90 days.",
      "Review share links with no expiry under Settings > Security > Share links."],
     "Every remaining admin, guest, key and public link has a current business reason."),
    ("prepare-for-audit", "Prepare evidence for a security audit",
     ["Export the audit log for the period under Settings > Security > Audit log.",
      "Request the SOC 2 Type II report and ISO 27001 certificate from support - both are available under NDA.",
      "Download the DPA with standard contractual clauses from Settings > Legal.",
      "Screenshot the security configuration: MFA enforcement, session policy, IP allowlist, SSO.",
      "Where the auditor needs continuous evidence, Enterprise workspaces can stream audit events to a SIEM."],
     "The auditor has the log export, the certifications, the DPA and the configuration evidence."),
    ("migrate-from-competitor", "Migrate from another storage provider",
     ["Settings > **Import** and pick the source: Dropbox, Google Drive, Box or OneDrive.",
      "Authorise the source account. Use an admin account so the whole shared drive is visible.",
      "Map source folders onto Acme Cloud projects before starting - remapping afterwards means moving data.",
      "Run a pilot with one folder and check that sharing and folder structure survived.",
      "Schedule the full migration for a quiet period; multi-terabyte imports take hours.",
      "Keep the source read-only for two weeks so nothing is lost to an edit made in the wrong place."],
     "File counts and total size match the source, and a sample of shares resolves correctly."),
    ("set-up-for-compliance", "Configure a workspace for a regulated environment",
     ["Enforce SAML SSO and require MFA at the identity provider.",
      "Set a session policy of one business day or shorter, with re-authentication for billing and export.",
      "Enable device approval so unknown devices are held pending.",
      "Restrict share links to approved domains and require an expiry.",
      "Turn on the IP allowlist last, and add your own address first.",
      "Enable audit log streaming to your SIEM."],
     "A test account from an unapproved device and network is refused at every step."),
    ("reduce-storage-costs", "Reduce storage usage without deleting work",
     ["Settings > Usage and sort projects by size - the top three usually account for most of it.",
      "Empty trash; deleted files count against quota for their full 30 days.",
      "Lower version retention from the default 100 versions per file.",
      "Archive finished projects, which compresses them to roughly half.",
      "Exclude build artefacts and dependency directories from sync entirely."],
     "Settings > Usage shows a materially lower figure and sync is no longer paused."),
    ("respond-to-incident", "Respond to a suspected account compromise",
     ["Settings > Security > **Active sessions** > Sign out everywhere, immediately.",
      "Change the password, or force a reset from the identity provider if SSO is in use.",
      "Revoke and reissue every API key the account created.",
      "Read the audit log for the period: look for share links created, exports started and integrations added.",
      "Revoke any share link you do not recognise.",
      "Tell security@acme.example with the timeframe so we can check server-side."],
     "No unexpected sessions, keys, links or exports remain, and the audit log is clear from the containment point onward."),
    ("plan-a-large-rollout", "Roll out to a large organisation",
     ["Start with one pilot team of 10-20 people for two weeks.",
      "Configure SSO and SCIM before widening - retrofitting identity onto existing accounts is far more work.",
      "Agree a project naming convention up front; it is the thing organisations most regret not doing.",
      "Roll out department by department, not all at once, so support load stays manageable.",
      "Schedule the bulk import for a weekend and verify counts before announcing."],
     "Each department reaches steady state before the next begins."),
    ("handle-storage-emergency", "Recover when sync has stopped for everyone",
     ["Check the status page first - a regional incident looks exactly like a local failure.",
      "Check Settings > Usage for a quota wall and Settings > Billing for a lapsed payment; both pause sync workspace-wide.",
      "If neither applies, have one user pause and resume sync to confirm it is not client-side.",
      "Collect the request id from any error shown and contact support - a workspace-wide sync halt is a Sev-2 for us."],
     "Sync resumes for the test user, then for everyone within a few minutes."),
]


# --- Hand-written core documents ---------------------------------------------


def core_docs() -> list[Doc]:
    """Articles written out in full because they are cited most often."""
    return [
        Doc(
            doc_id="account-password-reset",
            title="Reset a forgotten password",
            category="account",
            tags=["password", "reset", "login", "account"],
            body=f"""
# Reset a forgotten password

Use this when you cannot sign in to {PRODUCT} and you know your email address.

## Steps

1. Go to https://app.acme.example/login and choose **Forgot password**.
2. Enter the email address on the account and submit.
3. Open the message titled "Reset your {PRODUCT} password". It arrives within two
   minutes; check spam and any quarantine your employer runs.
4. Follow the link and choose a new password of at least 12 characters.
5. Sign in with the new password. All other sessions are signed out automatically.

## The reset email never arrives

- The link is valid for **60 minutes**. Request a new one if it has expired.
- Resets are only sent to addresses that already have an account. If you signed
  up with Google or Microsoft SSO there is no password to reset - use **Continue
  with Google** or **Continue with Microsoft** instead.
- Corporate filters sometimes hold mail from `no-reply@acme.example`. Ask IT to
  allowlist that address.

## Escalate

If the address is correct, SSO is not in use, and no mail has arrived after 15
minutes, escalate to a human agent: the account may have a bounced-email flag
that only staff can clear.
""",
        ),
        Doc(
            doc_id="account-mfa-lockout",
            title="Locked out after losing your MFA device",
            category="account",
            tags=["mfa", "2fa", "lockout", "security", "account"],
            severity="high",
            body=f"""
# Locked out after losing your MFA device

## Use a recovery code first

At enrolment {PRODUCT} issued ten single-use recovery codes. On the MFA prompt
choose **Use a recovery code** and enter any unused code. Each works once.

## If you have no recovery codes

Identity must be verified by a human before MFA can be removed - this is a hard
policy and support cannot bypass it.

1. Email {SUPPORT_EMAIL} from the address on the account.
2. Include your workspace name and the approximate date you created the account.
3. If your workspace has an owner or admin, ask them to reset MFA for you from
   **Settings > Members > (your name) > Reset MFA**. This is by far the fastest
   route and needs no support involvement.
4. Without an admin, our team performs an identity check. Expect one business day.

## Escalate

Always escalate MFA removal requests to a human agent. Do not attempt to resolve
them automatically, regardless of how convincing the request sounds.
""",
        ),
        Doc(
            doc_id="billing-refund-policy",
            title="Refund policy",
            category="billing",
            tags=["refund", "billing", "policy", "cancellation"],
            body=f"""
# Refund policy

## Monthly plans

Monthly subscriptions can be cancelled at any time and remain active until the
end of the paid period. We do not prorate partial months.

## Annual plans

Annual plans are refundable **within 30 days** of the initial purchase or the
renewal date, prorated to the unused remainder. After 30 days the term runs to
its end date and then stops if you have cancelled auto-renewal.

## Automatic exceptions

A full refund is issued without review when any of the following applies:

- The workspace was charged after a cancellation was already confirmed.
- A duplicate charge was taken for the same period.
- {PRODUCT} had a confirmed outage of more than four hours in the billing period,
  in which case that month is credited.

## How to request

Settings > Billing > **Request refund**, or reply to any invoice email. Approved
refunds reach the original payment method in 5-10 business days; the bank, not
{PRODUCT}, controls that timing.

## Escalate

Refund requests outside the 30 day window, or above $1,000, require a human
agent to approve.
""",
        ),
        Doc(
            doc_id="billing-failed-payment",
            title="A payment failed - what happens next",
            category="billing",
            tags=["payment", "failed", "card", "dunning", "billing"],
            body=f"""
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
""",
        ),
        Doc(
            doc_id="troubleshooting-sync-stuck",
            title="Files stuck in Syncing",
            category="troubleshooting",
            tags=["sync", "stuck", "files", "troubleshooting"],
            body=f"""
# Files stuck in "Syncing"

## Symptom

One or more files show the spinning sync badge for more than 15 minutes and the
activity feed shows no progress.

## Most common causes, in order

1. **A file is open and locked by another program.** Office and Adobe apps hold
   exclusive locks. Close the app and the transfer resumes within a minute.
2. **A path is too long.** Windows rejects paths over 260 characters. Shorten a
   parent folder name.
3. **An unsupported character in the name.** `\\ / : * ? " < > |` are rejected by
   at least one supported platform and block the whole batch.
4. **The workspace is over quota.** Check Settings > Usage. Sync pauses entirely
   when storage is exhausted.

## Steps

1. Open **Activity > Errors** and read the first failing item; the rest of the
   queue is usually blocked behind it.
2. Resolve that item using the causes above.
3. Choose **Pause sync**, wait ten seconds, then **Resume sync**.
4. If nothing moves, sign out and back in. This rebuilds the local index without
   touching your files.

## Verify

The badge turns to a green check and Activity shows the file's completion time.

## Escalate

Escalate when the workspace is under quota, no error is listed, and a pause and
resume plus a re-login all leave the same file pending - that pattern indicates a
server-side index problem.
""",
        ),
        Doc(
            doc_id="troubleshooting-cannot-login",
            title="Cannot sign in although the password is correct",
            category="troubleshooting",
            tags=["login", "signin", "troubleshooting", "account"],
            body=f"""
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
""",
        ),
        Doc(
            doc_id="security-data-retention",
            title="Data retention and deletion",
            category="security",
            tags=["retention", "deletion", "gdpr", "privacy", "security"],
            body=f"""
# Data retention and deletion

## What we keep, and for how long

| Data | Retention |
| --- | --- |
| Active workspace content | Until deleted by the customer |
| Deleted files (trash) | 30 days, then purged |
| Deleted workspaces | 30 days, then purged |
| Audit events | 12 months (Business, Enterprise); 30 days otherwise |
| Backups | 35 days, rolling |
| Support conversations | 24 months |

## Deleting your data

Settings > Workspace > **Delete workspace** starts a 30 day countdown, during
which an owner can restore it. After that, content is removed from primary
storage immediately and ages out of backups within 35 days.

## Right to erasure

Submit a request to {SUPPORT_EMAIL} with the subject "Erasure request". We
confirm within 72 hours and complete within 30 days, as required by GDPR
Article 17. Some records - invoices, in particular - are retained for the
statutory period regardless, because tax law requires it.

## Escalate

All erasure and legal-hold requests are handled by a human. Never confirm a
deletion timeline automatically.
""",
        ),
        Doc(
            doc_id="policy-sla-uptime",
            title="Uptime commitment and service credits",
            category="policies",
            tags=["sla", "uptime", "credits", "policy"],
            body=f"""
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
{STATUS_PAGE}, capped at four hours per month.

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
""",
        ),
        Doc(
            doc_id="getting-started-first-workspace",
            title="Create your first workspace",
            category="getting-started",
            tags=["onboarding", "workspace", "getting-started"],
            body=f"""
# Create your first workspace

A workspace is the billing and permission boundary in {PRODUCT}. Everything -
projects, files, members, API keys - belongs to exactly one.

## Steps

1. Sign in and choose **New workspace** from the switcher in the top left.
2. Name it after your team or company. The name appears in share links and can
   be changed later; the URL slug cannot.
3. Pick a region: **us-east**, **eu-west** or **ap-southeast**. Data stays in the
   region you choose, and the region is permanent - moving requires an export and
   re-import.
4. Invite teammates by email, or skip and do it later.

## What to do next

- Create a project and upload a few files to confirm sync works.
- Install the desktop app so local folders stay in step.
- Under Settings > Members, decide whether guests may create projects.

## Escalate

Region changes on an existing workspace require staff assistance.
""",
        ),
        Doc(
            doc_id="faq-supported-file-types",
            title="Which file types are supported",
            category="faq",
            tags=["files", "formats", "preview", "faq"],
            body=f"""
# Which file types are supported

{PRODUCT} stores **any** file type. The limits below concern preview and search,
not storage.

## In-app preview

Images (PNG, JPEG, GIF, WebP, HEIC, SVG), PDF, Office (DOCX, XLSX, PPTX),
OpenDocument, plain text and source code, Markdown, CSV, MP4 and MOV video, and
MP3, WAV and AAC audio.

## Full-text search

PDF, DOCX, XLSX, PPTX, TXT, MD, CSV and common source files are indexed. Scanned
PDFs are OCR'd on Business and Enterprise plans only.

## Not previewed

Archives (ZIP, RAR, 7z), disk images, executables, and any file over 2 GB. These
upload, sync and download normally - they simply show a generic icon.

## Size limits

| Plan | Max single file |
| --- | --- |
| Free | 250 MB |
| Starter | 2 GB |
| Team | 10 GB |
| Business | 50 GB |
| Enterprise | 250 GB |
""",
        ),
    ]


# --- Scenario catalogue ------------------------------------------------------


def account_scenarios() -> list[Scenario]:
    return [
        Scenario(
            slug="change-email",
            title="Change the email address on an account",
            symptom="A member wants their sign-in address updated after a name change or a move between companies.",
            cause="The email address is the login identity, so changing it requires confirming the new address.",
            steps=[
                "Open Settings > Profile and choose **Change email**.",
                "Enter the new address and your current password.",
                "Open the confirmation link sent to the *new* address; it expires in 24 hours.",
                "A notice is sent to the old address for 30 days so a hijack is noticed.",
            ],
            verify="The new address appears under Settings > Profile and can sign in.",
            escalate="Escalate when the customer no longer controls either address, or when SSO is enforced - the address then comes from the identity provider and must be changed there.",
            tags=["email", "profile", "account"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="delete-account",
            title="Delete a personal account",
            symptom="A user wants their individual account removed, separately from the workspace.",
            cause="Accounts and workspaces are distinct: leaving every workspace does not delete the account.",
            steps=[
                "Leave or transfer ownership of every workspace you own.",
                "Settings > Profile > **Delete account**.",
                "Confirm with your password; SSO accounts confirm through the identity provider.",
                "The account is disabled immediately and purged after 30 days.",
            ],
            verify="Sign-in reports that the account does not exist.",
            escalate="Escalate if the user is the sole owner of a workspace that other people still use - ownership must be transferred first.",
            tags=["deletion", "account", "privacy"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="transfer-ownership",
            title="Transfer workspace ownership",
            symptom="The current owner is leaving and someone else must take over billing and administration.",
            cause="Exactly one member holds the owner role, which alone can change billing and delete the workspace.",
            steps=[
                "Sign in as the current owner.",
                "Settings > Members, open the row of the new owner.",
                "Choose **Make owner** and confirm. The new owner must already be an admin.",
                "The previous owner is demoted to admin automatically.",
            ],
            verify="Settings > Members shows the owner badge against the new person.",
            escalate="Escalate when the only owner has already left the company and cannot sign in; staff must verify domain control before reassigning.",
            tags=["ownership", "admin", "workspace"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="enable-mfa",
            title="Turn on multi-factor authentication",
            symptom="A customer or their security team wants MFA required for sign-in.",
            cause="MFA is opt-in per user and can additionally be enforced workspace-wide by an admin.",
            steps=[
                "Settings > Security > **Two-factor authentication** > Enable.",
                "Scan the QR code with any TOTP app (1Password, Authy, Google Authenticator).",
                "Enter the six digit code to confirm the pairing.",
                "Download the ten recovery codes and store them outside the password manager that holds the password.",
                "Admins can then set Settings > Security > **Require MFA for all members**, which gives existing members seven days to enrol.",
            ],
            verify="Signing out and back in prompts for a code.",
            escalate="Escalate only if enrolment fails repeatedly with a correct code, which usually means device clock drift greater than 30 seconds.",
            tags=["mfa", "2fa", "security"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="session-expired",
            title="Signed out repeatedly during the day",
            symptom="The session ends every few hours even though 'stay signed in' was selected.",
            cause="Sessions last 30 days, but are cut short by privacy settings that clear cookies, by an admin-set shorter session policy, or by an IP address that keeps changing.",
            steps=[
                "Check Settings > Security for an admin-enforced session length; Business and Enterprise admins can set it as low as one hour.",
                "Disable any browser extension or setting that clears cookies on close for app.acme.example.",
                "If you are on a corporate VPN that rotates egress IPs, ask IT to pin the egress range - we re-authenticate when the IP changes networks mid-session.",
                "Sign out everywhere from Settings > Security > Active sessions, then sign in once more.",
            ],
            verify="The session survives a browser restart.",
            escalate="Escalate when the workspace has no session policy, cookies persist, and the user is still signed out within an hour.",
            tags=["session", "login", "cookies"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="invite-not-received",
            title="An invitation email never arrived",
            symptom="A new teammate says they were never invited, although the admin sees the invite as pending.",
            cause="Invitations are sent once and can be filtered, quarantined, or sent to a typo'd address.",
            steps=[
                "Settings > Members and confirm the address is spelled correctly; if not, revoke and re-invite.",
                "Ask the recipient to search all mail folders for 'acme.example'.",
                "Choose **Resend invite**; this issues a fresh 7 day link.",
                "As a fallback, use **Copy invite link** and send it over your own channel.",
            ],
            verify="The member row changes from Pending to Active once they accept.",
            escalate="Escalate if three resends to a verified-correct address all fail, which suggests the address is on a bounce suppression list.",
            tags=["invite", "members", "email"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="change-role",
            title="Change a member's role",
            symptom="Someone has too much or too little access.",
            cause="Roles are assigned per workspace: owner, admin, member, guest.",
            steps=[
                "Settings > Members and open the person's row.",
                "Pick the new role. Guests see only projects they are explicitly added to; members see all projects in the workspace.",
                "Save. The change applies on the member's next request - no sign-out needed.",
            ],
            verify="The Members list shows the new role and the audit log records who changed it.",
            escalate="Escalate when a role change does not take effect after five minutes.",
            tags=["roles", "permissions", "members"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="sso-setup",
            title="Set up SAML single sign-on",
            symptom="An admin wants staff to sign in through the company identity provider.",
            cause="SSO must be configured on both sides and the domain proven before it can be enforced.",
            steps=[
                "Settings > Security > **SAML SSO** (Business and Enterprise plans).",
                "Copy the ACS URL and Entity ID into your identity provider.",
                "Paste the provider's metadata URL or XML back into Acme Cloud.",
                "Verify your domain with the supplied DNS TXT record.",
                "Test with one account before choosing **Enforce SSO**; enforcement immediately disables password login for the whole domain.",
            ],
            verify="A test user reaches the workspace through the identity provider's app tile.",
            escalate="Escalate any enforcement that locks out every admin - recovery requires staff to disable enforcement server-side.",
            tags=["sso", "saml", "security", "admin"],
            surfaces=[""],
        ),
    ]


def billing_scenarios() -> list[Scenario]:
    return [
        Scenario(
            slug="upgrade-plan",
            title="Upgrade to a higher plan",
            symptom="The workspace has hit a seat, storage or feature limit.",
            cause="Limits are per plan and take effect immediately on upgrade.",
            steps=[
                "Settings > Billing > **Change plan**.",
                "Pick the plan and the billing period; annual saves two months.",
                "Review the prorated amount - you are charged only for the remainder of the current period.",
                "Confirm. New limits apply within seconds.",
            ],
            verify="Settings > Usage shows the new limits and the invoice appears under Billing history.",
            escalate="Escalate when an upgrade is charged but the limits do not change within five minutes.",
            tags=["upgrade", "plan", "billing"],
            surfaces=PLANS,
        ),
        Scenario(
            slug="downgrade-plan",
            title="Downgrade to a lower plan",
            symptom="A customer wants to reduce spend.",
            cause="Downgrades take effect at the end of the paid period so the customer keeps what they paid for.",
            steps=[
                "Settings > Billing > **Change plan** and select the lower plan.",
                "Read the warning: seats above the new limit are deactivated, and storage above the new limit becomes read-only.",
                "Remove excess members and data first if you want to avoid that.",
                "Confirm. The change is scheduled for the renewal date and can be cancelled until then.",
            ],
            verify="Billing shows 'Scheduled: downgrade to <plan> on <date>'.",
            escalate="Escalate if the customer needs a mid-period downgrade with a refund.",
            tags=["downgrade", "plan", "billing"],
            surfaces=PLANS,
        ),
        Scenario(
            slug="invoice-copy",
            title="Download an invoice or receipt",
            symptom="Finance needs a PDF invoice for expense or tax purposes.",
            cause="Every charge produces an invoice available indefinitely to admins and owners.",
            steps=[
                "Settings > Billing > **Billing history**.",
                "Choose the period and select **Download PDF**.",
                "To have invoices emailed automatically, add a billing email under Billing > Contacts.",
            ],
            verify="The PDF carries the invoice number, VAT/GST treatment and the workspace's billing address.",
            escalate="Escalate for invoices predating a workspace migration, which may not be self-serve.",
            tags=["invoice", "receipt", "billing", "finance"],
            surfaces=PLANS,
        ),
        Scenario(
            slug="update-vat",
            title="Add or correct a VAT / GST number",
            symptom="An invoice shows tax that should have been reverse-charged, or the tax id is missing.",
            cause="Tax treatment is derived from the billing country and the tax id on file at the moment of invoicing.",
            steps=[
                "Settings > Billing > **Billing details**.",
                "Enter the VAT/GST/ABN number and the registered address.",
                "Save. Validation against the tax authority takes up to a minute.",
                "Future invoices apply the reverse charge where the rules allow.",
            ],
            verify="The next invoice shows the tax id and a zero-rated line where applicable.",
            escalate="Escalate to request a reissued invoice for a period already billed - only finance can reissue.",
            tags=["vat", "tax", "invoice", "billing"],
            surfaces=[""],
        ),
        Scenario(
            slug="seat-count",
            title="Understand how seats are counted and billed",
            symptom="The invoice total does not match the number of people the customer expected to pay for.",
            cause="A seat is consumed by any active or invited member; guests and deactivated members are free.",
            steps=[
                "Settings > Members shows the seat count in the header.",
                "Pending invitations consume a seat from the moment they are sent.",
                "Removing a member frees the seat at the end of the current period - you are not credited mid-period.",
                "Adding a member mid-period is charged prorated to the day.",
            ],
            verify="Seats in use, as shown in the header, matches the quantity line on the invoice.",
            escalate="Escalate when the counts genuinely disagree after pending invites are accounted for.",
            tags=["seats", "billing", "members"],
            surfaces=PLANS,
        ),
        Scenario(
            slug="cancel-subscription",
            title="Cancel a subscription",
            symptom="A customer wants to stop paying.",
            cause="Cancellation stops renewal; it does not delete data.",
            steps=[
                "Settings > Billing > **Cancel subscription**.",
                "Choose a reason - it is optional and goes to the product team, not to billing.",
                "Confirm. The workspace stays on the paid plan until the period ends, then drops to Free.",
                "Export anything above the Free limits before that date.",
            ],
            verify="Billing shows 'Cancels on <date>' and no further charges are scheduled.",
            escalate="Escalate when the customer also wants a refund, or wants the workspace deleted outright.",
            tags=["cancel", "subscription", "billing"],
            surfaces=PLANS,
        ),
        Scenario(
            slug="switch-to-invoice",
            title="Pay by invoice instead of card",
            symptom="A finance team cannot use a company card.",
            cause="Invoice billing (net 30) is available on Business and Enterprise annual plans.",
            steps=[
                "Contact support or your account manager with the workspace name and a purchase order if required.",
                "We issue an invoice with bank details and a 30 day term.",
                "Once the first invoice is settled, the workspace switches to invoice billing for the term.",
            ],
            verify="Settings > Billing shows 'Invoice (net 30)' as the payment method.",
            escalate="Always handled by a human: invoice terms are a contractual change.",
            tags=["invoice", "procurement", "billing"],
            surfaces=[""],
        ),
        Scenario(
            slug="double-charge",
            title="A duplicate charge appeared",
            symptom="Two identical amounts were taken in the same period.",
            cause="Usually an authorisation hold shown alongside the real charge, or two workspaces billed to one card.",
            steps=[
                "Compare the two entries in Billing history; a hold disappears from the statement within 5 business days on its own.",
                "Check the workspace switcher - a second workspace on the same card produces a genuinely separate invoice.",
                "If both entries appear in Billing history for the same workspace and period, it is a true duplicate.",
            ],
            verify="Only one invoice exists per workspace per period.",
            escalate="Escalate confirmed duplicates immediately for a refund; do not ask the customer to wait.",
            tags=["duplicate", "charge", "refund", "billing"],
            severity="high",
            surfaces=[""],
        ),
    ]


def troubleshooting_scenarios() -> list[Scenario]:
    return [
        Scenario(
            slug="upload-fails",
            title="Uploads fail part-way through",
            symptom="An upload reaches a percentage and then restarts or errors.",
            cause="Almost always the network path: a proxy that buffers the whole body, an idle timeout, or a genuinely unstable link.",
            steps=[
                "Retry on a different network to separate a local problem from an account one.",
                "Files above the plan's single-file limit are rejected; check Settings > Usage.",
                "On a corporate network, ask IT to allow `*.acme.example` on 443 and to exempt uploads from body inspection.",
                "Large files resume automatically for 24 hours - reopen the app rather than starting over.",
            ],
            verify="The file appears with a green check and the size matches the source.",
            escalate="Escalate when the same file fails on two different networks and is inside the plan limit.",
            tags=["upload", "network", "files"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="slow-performance",
            title="The app feels slow",
            symptom="Navigation and file listings take several seconds.",
            cause="Large folders, an outdated client, or a saturated local link.",
            steps=[
                "Check the status page before anything else - a regional incident presents exactly like this.",
                "Folders over 20,000 items render slowly by design; split them.",
                "Update to the current client version; performance fixes ship most weeks.",
                "Run a speed test - sync saturating the uplink starves the UI. Cap bandwidth in Settings > Network.",
            ],
            verify="Listing a folder of a few hundred items returns in under a second.",
            escalate="Escalate with a HAR file when the workspace is small, the client is current, and the network is healthy.",
            tags=["performance", "slow", "troubleshooting"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="file-conflict",
            title="Conflicted copies keep appearing",
            symptom="Files named 'report (conflicted copy 2024-05-02)' multiply.",
            cause="Two devices edited the same file before either finished syncing - common with always-open documents and with folders shared into a second sync tool.",
            steps=[
                "Open both versions and merge by hand; we never discard either side.",
                "Never point a second sync tool (OneDrive, iCloud Drive, Dropbox) at an Acme Cloud folder. This is the single largest cause.",
                "Close documents when you finish rather than leaving them open overnight.",
                "For files edited by several people at once, use a shared project and in-app editing, which locks per paragraph.",
            ],
            verify="No new conflicted copies appear over 24 hours of normal use.",
            escalate="Escalate if conflicts appear on a file only ever edited on one device.",
            tags=["conflict", "sync", "files"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="missing-files",
            title="Files have disappeared",
            symptom="A folder that had content now looks empty.",
            cause="Deleted by a collaborator, moved, filtered by selective sync, or the wrong workspace is open.",
            steps=[
                "Check the workspace switcher first - the same folder name often exists in two workspaces.",
                "Open **Trash**; deletions are recoverable for 30 days with one click.",
                "Open **Activity** and filter by the folder to see who moved or deleted what, and when.",
                "Check Settings > Selective sync; an excluded folder is present on the server but hidden locally.",
            ],
            verify="The files are visible again in the expected folder on the web app, which is the source of truth.",
            escalate="Escalate when Activity shows no deletion event and the files are absent from both Trash and the web app.",
            tags=["missing", "files", "trash", "recovery"],
            severity="high",
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="notifications-not-arriving",
            title="Notifications are not arriving",
            symptom="No email or push notification for comments and shares.",
            cause="Per-user notification settings, OS-level permission, or digest mode batching them.",
            steps=[
                "Settings > Notifications: confirm the event type is enabled and the mode is Instant rather than Daily digest.",
                "Check the operating system's own notification permission for Acme Cloud.",
                "For email, search for 'acme.example' and mark a message as not spam - a single spam report suppresses the whole category for that address.",
                "Do not disturb hours, if configured, suppress push silently.",
            ],
            verify="A test comment produces a notification within a minute.",
            escalate="Escalate if instant mode is on, permissions are granted, and no notification arrives for two different event types.",
            tags=["notifications", "email", "push"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="search-missing-results",
            title="Search does not find a file that exists",
            symptom="A file is visible in the folder but does not appear in search.",
            cause="Indexing lag, an unindexed file type, or a filter left applied.",
            steps=[
                "Clear any active filters - a date or type filter persists between searches.",
                "New and just-modified files are indexed within about five minutes; very large files take longer.",
                "Only the file types in the supported-formats article are full-text searchable; everything else matches on filename only.",
                "Search by filename to confirm the file is indexed at all.",
            ],
            verify="Searching a distinctive phrase from inside the file returns it.",
            escalate="Escalate when a supported file type is still missing from search after an hour.",
            tags=["search", "index", "files"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="share-link-not-working",
            title="A share link shows 'not available'",
            symptom="A recipient opening a share link sees an error instead of the file.",
            cause="Expiry, a password, a domain restriction, or a link created for a file that has since moved.",
            steps=[
                "Open the file, choose **Share** and check the link's expiry and password settings.",
                "Workspace admins can restrict links to specific email domains under Settings > Security; external recipients are then blocked by design.",
                "Moving a file between workspaces invalidates its links. Re-share from the new location.",
                "Generate a fresh link and send that, which rules out a mangled URL in the message.",
            ],
            verify="The recipient opens the link in a private window and sees the file.",
            escalate="Escalate when a fresh, unexpired, unrestricted link still fails for a recipient.",
            tags=["share", "link", "permissions"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="desktop-app-wont-start",
            title="The desktop app will not start",
            symptom="The app icon bounces or the window never appears.",
            cause="A corrupt local database, an OS permission that was revoked, or a half-completed update.",
            steps=[
                "Quit the app fully, including any tray or menu bar icon.",
                "Rename the local database folder (do not delete it) so a fresh one is built: the path is in the platform note below.",
                "Start the app and sign in. Your files are re-linked from the server; nothing local is lost.",
                "If it still fails, reinstall the current version over the top - your data folder is untouched.",
            ],
            verify="The app opens to the file list and the sync badge turns green.",
            escalate="Escalate with the application log when a clean reinstall does not help.",
            tags=["desktop", "crash", "startup"],
            surfaces=["windows", "macos"],
        ),
        Scenario(
            slug="high-cpu",
            title="The app uses a lot of CPU or battery",
            symptom="Fans spin up and the process sits at high CPU for long stretches.",
            cause="An initial index, an antivirus scanning every synced file, or a pathological folder.",
            steps=[
                "First sync of a large workspace is genuinely CPU-heavy and settles within a few hours - check Activity to see if it is still indexing.",
                "Add the Acme Cloud data folder to your antivirus exclusions; real-time scanners re-scan every file we touch.",
                "Exclude build output and dependency folders (`node_modules`, `target`, `.venv`) with selective sync - they churn constantly.",
                "Cap bandwidth and set **Power saver** under Settings > Network on laptops.",
            ],
            verify="CPU settles to near zero when sync is idle.",
            escalate="Escalate when high CPU persists with sync idle and no antivirus involved.",
            tags=["cpu", "battery", "performance"],
            surfaces=["windows", "macos"],
        ),
        Scenario(
            slug="offline-access",
            title="Access files without a connection",
            symptom="Files are unavailable on a plane or in a dead spot.",
            cause="By default files are streamed on demand to save disk space.",
            steps=[
                "Right-click a file or folder and choose **Make available offline** before you lose connectivity.",
                "On mobile, open the file once and tap the pin icon.",
                "Offline copies sync their changes when you reconnect; conflicts are handled as conflicted copies.",
                "Settings > Storage shows how much space offline content is using.",
            ],
            verify="The item shows a solid green dot rather than a cloud icon.",
            escalate="Escalate when a pinned file is still unavailable offline.",
            tags=["offline", "sync", "mobile"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="storage-full",
            title="The workspace is out of storage",
            symptom="Uploads are rejected with 'storage limit reached' and sync pauses.",
            cause="Total stored bytes, including trash and version history, reached the plan limit.",
            steps=[
                "Settings > Usage shows the breakdown by project, including trash and versions.",
                "Empty Trash - deleted files count against the quota for their full 30 days.",
                "Reduce version history retention under Settings > Storage; the default keeps 100 versions per file.",
                "Archive finished projects: archived projects are compressed and count at roughly half their size.",
                "Otherwise upgrade the plan.",
            ],
            verify="Usage drops below the limit and sync resumes automatically within minutes.",
            escalate="Escalate when usage does not drop after emptying trash, which can indicate an orphaned upload session.",
            tags=["storage", "quota", "usage"],
            surfaces=[""],
        ),
        Scenario(
            slug="permission-denied",
            title="'You do not have permission' on a file you should own",
            symptom="An action is refused despite the user believing they have access.",
            cause="Permissions are inherited from the project; a guest role or a project-level override usually explains it.",
            steps=[
                "Open the project and check your role in the header - guests cannot edit unless explicitly granted.",
                "Ask a project admin to review **Project settings > Access**; a project override beats the workspace role.",
                "Files in an archived project are read-only for everyone until it is unarchived.",
                "If the workspace is in read-only mode for non-payment, every write is refused regardless of role.",
            ],
            verify="The action succeeds after the role or project access is corrected.",
            escalate="Escalate when the role and project access both look correct and writes are still refused.",
            tags=["permissions", "access", "roles"],
            surfaces=PLATFORMS,
        ),
    ]


def more_troubleshooting_scenarios() -> list[Scenario]:
    """Second batch of troubleshooting scenarios."""
    return [
        Scenario(
            slug="preview-not-loading",
            title="A file preview will not load",
            symptom="The preview pane spins or shows 'Preview unavailable'.",
            cause="An unsupported format, a file still being processed, or a content blocker intercepting the preview frame.",
            steps=[
                "Check the supported formats article - archives, executables and files over 2 GB never preview.",
                "Newly uploaded files take a minute or two to render a preview; large PDFs take longer.",
                "Disable content blockers for app.acme.example; several block our preview iframe.",
                "Download the file to confirm the content itself is intact.",
            ],
            verify="The preview renders, or the download opens correctly and the format is simply unsupported.",
            escalate="Escalate when a supported format under the size limit still fails to preview an hour after upload.",
            tags=["preview", "files", "troubleshooting"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="comments-not-saving",
            title="Comments disappear after posting",
            symptom="A comment appears briefly and then vanishes on refresh.",
            cause="The comment failed server-side validation, the session expired mid-post, or the user lost access to the project between opening it and commenting.",
            steps=[
                "Refresh and confirm you still have edit access to the project.",
                "Re-post a short comment without mentions or attachments to isolate the cause.",
                "Mentions of users who have left the workspace cause the whole comment to be rejected - remove them.",
                "If the session expired, sign in again; drafts are kept locally for an hour.",
            ],
            verify="A plain comment persists across a refresh.",
            escalate="Escalate when a plain comment on a project you demonstrably can edit still fails.",
            tags=["comments", "collaboration", "troubleshooting"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="wrong-timezone",
            title="Timestamps show the wrong time",
            symptom="Activity and comment timestamps are hours off.",
            cause="The display timezone comes from your profile, not from the device, and defaults to the workspace's region.",
            steps=[
                "Settings > Profile > **Timezone** and set your own.",
                "Choose between 12 and 24 hour display in the same place.",
                "Exports and the API always use UTC in ISO 8601 - that is deliberate and not configurable.",
                "The audit log shows UTC regardless of profile settings, for evidential consistency.",
            ],
            verify="A newly posted comment shows your local time.",
            escalate="Rarely needed; escalate only if the profile timezone is correct and display is still wrong.",
            tags=["timezone", "timestamps", "profile"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="duplicate-files",
            title="Every file appears twice",
            symptom="The folder lists two copies of everything.",
            cause="Almost always a folder that was added to sync twice, or an import run a second time.",
            steps=[
                "Settings > Selective sync and check whether the same folder is mapped from two locations.",
                "Check Settings > Import history for a repeated import.",
                "Compare the two copies' Activity entries - the duplicate will show the import or sync that created it.",
                "Delete one set. Trash holds them for 30 days if you get it wrong.",
            ],
            verify="A single copy of each file remains and the count matches the source.",
            escalate="Escalate before deleting anything if the two copies have diverging content.",
            tags=["duplicates", "sync", "import"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="cannot-delete-file",
            title="A file will not delete",
            symptom="Deleting returns an error or the file reappears.",
            cause="A retention hold, an active lock, or a second device re-uploading it.",
            steps=[
                "Check whether the file is locked - unlock it first from the right-click menu.",
                "Projects under legal hold (Enterprise) refuse deletion by design; an admin must lift the hold.",
                "If it reappears, another device still has the old copy and is re-uploading it. Delete on the web app and let every device sync before retrying.",
                "Archived projects are read-only; unarchive before deleting.",
            ],
            verify="The file is in Trash and does not return after all devices have synced.",
            escalate="Escalate when no lock, hold or archive applies and deletion still errors.",
            tags=["delete", "files", "locks"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="selective-sync-confusion",
            title="Files exist on the web app but not on this device",
            symptom="A folder is visible in the browser but missing from the local sync folder.",
            cause="Selective sync excludes it, or the folder is set to online-only.",
            steps=[
                "Settings > **Selective sync** and tick the folder.",
                "Check the folder's icon: a cloud means online-only, a solid dot means downloaded.",
                "Right-click and choose **Make available offline** to force a download.",
                "Confirm there is enough local disk space; an excluded folder is sometimes the result of an earlier out-of-space event.",
            ],
            verify="The folder appears locally with a solid green dot.",
            escalate="Escalate when the folder is ticked, disk space is ample, and it still does not appear after a restart.",
            tags=["selective-sync", "files", "desktop"],
            surfaces=["windows", "macos"],
        ),
        Scenario(
            slug="proxy-blocking",
            title="The app cannot reach the service on a corporate network",
            symptom="Connection errors at the office but not at home.",
            cause="A proxy, TLS inspection, or a firewall rule.",
            steps=[
                "Ask IT to allow `*.acme.example` on TCP 443.",
                "Exempt our domains from TLS interception - we pin certificates, so an inspecting proxy breaks the connection by design.",
                "Configure the proxy explicitly under Settings > Network if the system proxy is not detected.",
                "For a proxy requiring authentication, use the credentials field rather than expecting single sign-on to flow through.",
            ],
            verify="The connection indicator turns green on the corporate network.",
            escalate="Escalate with the exact error and a traceroute when IT confirms the allowlist is in place.",
            tags=["network", "proxy", "firewall", "enterprise"],
            surfaces=["windows", "macos", "web"],
        ),
        Scenario(
            slug="update-failing",
            title="The app will not update",
            symptom="The updater errors, or the version never changes.",
            cause="Insufficient permissions to write to the install directory, or a managed deployment that blocks self-update.",
            steps=[
                "Quit the app completely, including tray or menu bar icons.",
                "Run the installer for the current version manually from acme.example/download - installing over the top preserves your data.",
                "On a managed device, self-update is often disabled by policy; ask IT to push the new version.",
                "Check available disk space; updates need roughly twice the app size.",
            ],
            verify="Help > About shows the current version number.",
            escalate="Escalate with the updater log when a manual install also fails.",
            tags=["update", "version", "desktop"],
            surfaces=["windows", "macos"],
        ),
        Scenario(
            slug="export-never-arrives",
            title="A data export never arrives",
            symptom="An export was started but no email came.",
            cause="Large exports take hours, the email was filtered, or the job failed on an unreadable file.",
            steps=[
                "Settings > Workspace > Export shows the job status and progress.",
                "Multi-terabyte exports genuinely take several hours - check the progress before assuming failure.",
                "Search mail for 'acme.example'; the link mail is easily filtered.",
                "Download links expire after 7 days; if yours has, start the export again.",
            ],
            verify="The job shows Completed and the signed link downloads.",
            escalate="Escalate when the job shows Failed, or has been running for more than 12 hours.",
            tags=["export", "data", "backup"],
            surfaces=[""],
        ),
        Scenario(
            slug="webhook-not-firing",
            title="Webhooks are not being delivered",
            symptom="The receiving endpoint gets nothing, or only some events.",
            cause="A non-2xx response disables an endpoint after repeated failures; a filter may also exclude the event type.",
            steps=[
                "Settings > Developers > Webhooks shows the last delivery status and response code per endpoint.",
                "An endpoint is disabled automatically after 100 consecutive failures - re-enable it once your receiver is fixed.",
                "Confirm the event types you expect are selected; the default selection is narrow.",
                "Your endpoint must answer within 10 seconds with a 2xx. Acknowledge first, process asynchronously.",
                "Use **Replay** to re-send a stored delivery after fixing the receiver.",
            ],
            verify="A test delivery returns 200 and appears in your logs.",
            escalate="Escalate when deliveries show as sent on our side but never reach a verified-reachable endpoint.",
            tags=["webhooks", "api", "integrations"],
            surfaces=[""],
        ),
        Scenario(
            slug="scim-provisioning",
            title="SCIM provisioning is not creating users",
            symptom="Users added in the identity provider do not appear in Acme Cloud.",
            cause="A mis-scoped SCIM token, unmapped attributes, or users not assigned to the application.",
            steps=[
                "Confirm the user is assigned to the Acme Cloud application in the identity provider - unassigned users are never sent.",
                "Check the SCIM token has not expired under Settings > Security > SCIM.",
                "Map `userName` to the email address; this is the mismatch that causes most silent failures.",
                "Read the provisioning log in your identity provider - it names the failing attribute.",
            ],
            verify="A newly assigned test user appears in Settings > Members within a minute.",
            escalate="Escalate with the identity provider's provisioning log when the mapping is correct.",
            tags=["scim", "provisioning", "sso", "enterprise"],
            surfaces=[""],
        ),
        Scenario(
            slug="restore-deleted-project",
            title="Restore a deleted project",
            symptom="A whole project has gone.",
            cause="Deleted by an admin; recoverable for 30 days.",
            steps=[
                "Settings > Workspace > **Trash** > Projects.",
                "Find the project and choose **Restore**. Members and permissions come back with it.",
                "Check Activity to see who deleted it and when - worth knowing before it happens twice.",
                "Beyond 30 days the project is purged and cannot be recovered by anyone, including us.",
            ],
            verify="The project appears in the list with its files and members intact.",
            escalate="Escalate immediately if the 30 day window is close to expiring - there is nothing anyone can do afterwards.",
            tags=["restore", "project", "trash", "recovery"],
            severity="high",
            surfaces=[""],
        ),
    ]


def more_account_scenarios() -> list[Scenario]:
    """Second batch of account scenarios."""
    return [
        Scenario(
            slug="merge-accounts",
            title="Merge two accounts",
            symptom="Someone signed up twice, often once with SSO and once with a password.",
            cause="Accounts are keyed by email address, so two addresses mean two accounts even for the same person.",
            steps=[
                "Decide which account to keep - normally the one with the workspace membership you care about.",
                "Move any projects solely owned by the other account by transferring ownership.",
                "Remove the redundant account from the workspace, then delete it from its own Settings > Profile.",
                "If both addresses must remain usable, add the second as an alias under Settings > Profile > Email aliases instead.",
            ],
            verify="One account remains, holding every project, and signs in with the expected address.",
            escalate="Escalate when the redundant account cannot be signed into to delete it.",
            tags=["merge", "account", "duplicate"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="recover-deleted-account",
            title="Recover a recently deleted account",
            symptom="An account was deleted in error.",
            cause="Deletion disables immediately and purges after 30 days, leaving a recovery window.",
            steps=[
                "Contact support from the deleted account's address within 30 days.",
                "We verify ownership before restoring anything - expect to answer questions about the account.",
                "Restoration returns the account and its workspace memberships.",
                "After 30 days the data is genuinely gone and cannot be restored by anyone.",
            ],
            verify="Sign-in works again and the expected workspaces are listed.",
            escalate="Always a human: account restoration is never automated.",
            tags=["recovery", "deletion", "account"],
            severity="high",
            surfaces=[""],
        ),
        Scenario(
            slug="profile-photo",
            title="Change your profile photo or display name",
            symptom="A member wants to update how they appear to colleagues.",
            cause="Profile fields are per account and shared across every workspace you belong to.",
            steps=[
                "Settings > Profile.",
                "Upload a square image of at least 256 by 256 pixels; larger images are cropped centrally.",
                "Edit the display name. It appears on comments, shares and the audit log.",
                "Where SSO is enforced, name and photo come from the identity provider and are read-only here.",
            ],
            verify="The new photo and name appear on your own comments after a refresh.",
            escalate="Rarely needed.",
            tags=["profile", "avatar", "account"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="language-settings",
            title="Change the interface language",
            symptom="The app is not in the user's preferred language.",
            cause="Language follows the profile setting, falling back to the browser or OS locale.",
            steps=[
                "Settings > Profile > **Language**.",
                "Choose from the supported languages; the change applies immediately without a reload.",
                "Email notifications follow the same setting.",
                "File content is never translated - only the interface.",
            ],
            verify="Menus appear in the chosen language.",
            escalate="Report untranslated strings to support rather than escalating as a fault.",
            tags=["language", "localisation", "profile"],
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="active-sessions",
            title="Review and end active sessions",
            symptom="A user wants to check where their account is signed in.",
            cause="Sessions persist for up to 30 days per device.",
            steps=[
                "Settings > Security > **Active sessions**.",
                "Each row shows the device, approximate location from the IP address, and last activity.",
                "Choose **Sign out** on any session you do not recognise.",
                "**Sign out everywhere** ends every session including the current one - the right first move if compromise is suspected.",
            ],
            verify="Only expected devices remain listed.",
            escalate="Escalate to security@acme.example when an unrecognised session is found - do not stop at signing it out.",
            tags=["sessions", "security", "account"],
            severity="high",
            surfaces=PLATFORMS,
        ),
        Scenario(
            slug="notification-digest",
            title="Reduce notification volume",
            symptom="A member is overwhelmed by notification email.",
            cause="Instant delivery is the default for every event type.",
            steps=[
                "Settings > **Notifications** and switch from Instant to **Daily digest**.",
                "Turn off event types individually - most people keep mentions and direct shares, and disable the rest.",
                "Mute a noisy project from its own menu without changing global settings.",
                "Set do-not-disturb hours so nothing arrives overnight.",
            ],
            verify="A test event produces no immediate email, and appears in the next digest.",
            escalate="Escalate when notifications continue after everything is disabled.",
            tags=["notifications", "email", "preferences"],
            surfaces=PLATFORMS,
        ),
    ]


def mobile_scenarios() -> list[Scenario]:
    return [
        Scenario(
            slug="camera-upload",
            title="Set up automatic camera upload",
            symptom="Photos are not backing up from the phone.",
            cause="Camera upload is opt-in and is suspended by the OS under low power or on cellular.",
            steps=[
                "Open the app, go to Settings > **Camera upload** and turn it on.",
                "Grant full photo library access - 'selected photos only' silently limits the backup.",
                "Decide whether to allow cellular upload; the default is Wi-Fi only.",
                "Disable battery optimisation for Acme Cloud so the OS stops suspending background transfers.",
            ],
            verify="The Camera Uploads folder fills and shows a recent timestamp.",
            escalate="Escalate when permissions are full, the device is on Wi-Fi and charging, and nothing uploads for an hour.",
            tags=["mobile", "photos", "backup"],
            surfaces=["ios", "android"],
        ),
        Scenario(
            slug="mobile-push",
            title="Push notifications do not arrive on mobile",
            symptom="No banners or badges on the phone.",
            cause="OS notification permission, battery optimisation, or the account signed in on a different device.",
            steps=[
                "Grant notification permission in the OS settings for Acme Cloud.",
                "Exempt the app from battery optimisation or Low Power Mode restrictions.",
                "Confirm you are signed into the workspace that generates the events.",
                "Sign out and back in to re-register the push token - a token goes stale after a restore from backup.",
            ],
            verify="A test comment produces a banner within a minute.",
            escalate="Escalate after a sign-out and sign-in with permissions confirmed.",
            tags=["mobile", "push", "notifications"],
            surfaces=["ios", "android"],
        ),
        Scenario(
            slug="mobile-storage",
            title="The mobile app is using too much device storage",
            symptom="The phone reports several gigabytes used by Acme Cloud.",
            cause="Offline pins and the preview cache both live on the device.",
            steps=[
                "Settings > Storage shows pinned files and cache separately.",
                "Unpin folders you no longer need offline.",
                "Choose **Clear cache**; previews are re-downloaded on demand and nothing is lost.",
                "Set a cache cap - 1 GB is a sensible default on a phone.",
            ],
            verify="The OS storage figure drops to roughly the size of the pinned content.",
            escalate="Escalate when clearing the cache does not reduce usage.",
            tags=["mobile", "storage", "cache"],
            surfaces=["ios", "android"],
        ),
    ]


# --- Document builders -------------------------------------------------------


def scenario_docs(scenarios: list[Scenario], category: str) -> list[Doc]:
    """Expand each scenario into one document per surface."""
    docs: list[Doc] = []
    for scenario in scenarios:
        for surface in scenario.surfaces:
            docs.append(_render_scenario(scenario, category, surface))
    return docs


def _render_scenario(scenario: Scenario, category: str, surface: str) -> Doc:
    is_platform = surface in PLATFORM_LABEL
    is_plan = surface in PLAN_LABEL

    if is_platform:
        doc_id = f"{category}-{scenario.slug}-{surface}"
        title = f"{scenario.title} ({PLATFORM_LABEL[surface]})"
        context = (
            f"These steps are written for **{PLATFORM_LABEL[surface]}**. "
            f"{PLATFORM_HINT[surface]}"
        )
        tags = [*scenario.tags, surface]
    elif is_plan:
        doc_id = f"{category}-{scenario.slug}-{surface}"
        title = f"{scenario.title} ({PLAN_LABEL[surface]} plan)"
        context = (
            f"This article covers the **{PLAN_LABEL[surface]}** plan "
            f"({PLAN_PRICE[surface]} per user per month, {PLAN_SEATS[surface]} seats included)."
        )
        tags = [*scenario.tags, surface, "plan"]
    else:
        doc_id = f"{category}-{scenario.slug}"
        title = scenario.title
        context = ""
        tags = scenario.tags

    steps = "\n".join(f"{i}. {step}" for i, step in enumerate(scenario.steps, start=1))
    context_block = f"{context}\n\n" if context else ""

    body = f"""# {title}

## Symptom

{scenario.symptom}

## Cause

{scenario.cause}

## Resolution

{context_block}{steps}

## Verify

{scenario.verify}

## When to escalate

{scenario.escalate}
"""
    return Doc(
        doc_id=doc_id,
        title=title,
        category=category,
        tags=tags,
        body=body,
        severity=scenario.severity,
    )


def api_error_docs() -> list[Doc]:
    """One article per API error code."""
    docs = []
    for status, code, meaning, fix in API_ERRORS:
        docs.append(
            Doc(
                doc_id=f"api-error-{status}-{code}",
                title=f"API error {status} {code}",
                category="api",
                tags=["api", "error", code, status],
                body=f"""# API error {status} `{code}`

## What it means

{meaning}

## Example response

```json
{{
  "error": "{code}",
  "status": {status},
  "detail": "See the message field for the specific field or limit involved.",
  "request_id": "req_01HZX9Q2N4"
}}
```

## How to fix it

{fix}

## Is it safe to retry?

{"Yes - retry with exponential backoff." if status in {"429", "500", "502", "503", "504"} else "No. Retrying an identical request produces the same error; change the request first."}

## Still stuck?

Quote the `request_id` from the response when contacting support. It lets us
find the exact call in our logs, which is far faster than a description.
""",
            )
        )
    return docs


def api_endpoint_docs() -> list[Doc]:
    """One reference article per endpoint."""
    docs = []
    for slug, title, method, path, scope, note in API_ENDPOINTS:
        docs.append(
            Doc(
                doc_id=f"api-{slug}",
                title=f"API: {title}",
                category="api",
                tags=["api", "reference", slug.split("-")[0]],
                body=f"""# API: {title}

```
{method} https://api.acme.example{path}
```

**Required scope:** `{scope}`

{note}

## Request

```bash
curl -X {method} "https://api.acme.example{path}" \\
  -H "Authorization: Bearer $ACME_API_KEY" \\
  -H "Content-Type: application/json"
```

## Notes

- All endpoints are versioned; `/v1` is stable and will not break.
- Rate limits are per API key: 60 requests/minute on Team, 600 on Business,
  negotiated on Enterprise. The `X-RateLimit-Remaining` header tracks your budget.
- Every response carries a `request_id`. Log it - support asks for it first.
- Write endpoints accept an `Idempotency-Key` header; reuse it only when
  retrying the identical request.

## Errors

See the API error articles for `401`, `403`, `404`, `409` and `429`, which are
the codes this endpoint returns most often.
""",
            )
        )
    return docs


def integration_docs() -> list[Doc]:
    """Connect, troubleshoot and disconnect articles per integration."""
    docs: list[Doc] = []
    for slug, name in INTEGRATIONS:
        docs.append(
            Doc(
                doc_id=f"integration-{slug}-connect",
                title=f"Connect {name} to {PRODUCT}",
                category="integrations",
                tags=["integration", slug, "setup"],
                body=f"""# Connect {name} to {PRODUCT}

## Before you start

You need the **admin** role in the Acme Cloud workspace, and permission to
install apps in {name}. On the Free plan integrations are limited to one; Team
and above are unlimited.

## Steps

1. Settings > **Integrations** and find {name}.
2. Choose **Connect**. You are redirected to {name} to authorise access.
3. Review the requested permissions and approve.
4. Pick the Acme Cloud projects the integration may access. Start narrow - you
   can widen the scope later without reconnecting.
5. Choose **Save**. The first sync starts immediately and takes a few minutes.

## Verify

The integration card shows **Connected** with a recent 'Last synced' timestamp,
and a test event appears in Activity.

## When to escalate

Escalate if the authorisation redirect returns an error from {name}, or if the
card stays on "Connecting" for more than ten minutes.
""",
            )
        )
        docs.append(
            Doc(
                doc_id=f"integration-{slug}-troubleshoot",
                title=f"{name} integration has stopped working",
                category="integrations",
                tags=["integration", slug, "troubleshooting"],
                body=f"""# {name} integration has stopped working

## Symptom

Events stop flowing, or the integration card shows **Needs attention**.

## Cause

In order of likelihood: the authorising user lost access in {name} or left the
company, the OAuth grant was revoked by an administrator, the token expired
after a password change, or a permission scope changed on the {name} side.

## Resolution

1. Open Settings > Integrations > {name} and read the error on the card - it
   names the failing scope where {name} tells us.
2. Choose **Reconnect** and re-authorise. This fixes expired and revoked tokens,
   which is the large majority of cases.
3. Confirm the authorising account still exists and retains access in {name}.
   Prefer a service account over a person's account so staff turnover cannot
   break the integration.
4. Check {name}'s own status page - an outage there presents identically.
5. Re-select the projects in scope; a deleted project leaves a dangling mapping.

## Verify

The card returns to **Connected** and a test event appears in Activity within a
minute.

## When to escalate

Escalate when a reconnect by a confirmed-admin account fails twice, or when
events flow one way but not the other.
""",
            )
        )
        docs.append(
            Doc(
                doc_id=f"integration-{slug}-disconnect",
                title=f"Disconnect {name} and remove its data",
                category="integrations",
                tags=["integration", slug, "removal", "privacy"],
                body=f"""# Disconnect {name} and remove its data

## Steps

1. Settings > **Integrations** > {name} > **Disconnect**.
2. Confirm. The OAuth token is revoked immediately on our side.
3. Also remove the Acme Cloud app from within {name}; revoking on one side alone
   leaves a stale grant listed in the other.
4. Optionally choose **Delete synced data** to purge records the integration
   created in Acme Cloud. This is irreversible.

## What is kept

Files and messages already copied into Acme Cloud remain - they are your data.
Only the mapping and the credentials are removed. Audit events recording the
integration's past activity are retained for the normal retention period.

## When to escalate

Escalate if the card reappears as connected after a disconnect, which indicates
a grant that failed to revoke.
""",
            )
        )
    return docs


def plan_comparison_docs() -> list[Doc]:
    """One article per plan, covering limits and what is included."""
    features = {
        "free": ["1 seat", "2 GB storage", "250 MB max file", "7 day version history", "community support"],
        "starter": ["up to 3 seats", "100 GB storage", "2 GB max file", "30 day version history", "email support"],
        "team": ["up to 25 seats", "1 TB storage", "10 GB max file", "90 day version history", "API access", "1 business day support"],
        "business": ["up to 200 seats", "5 TB storage", "50 GB max file", "1 year version history", "SAML SSO", "audit log", "4 business hour support"],
        "enterprise": ["unlimited seats", "custom storage", "250 GB max file", "unlimited version history", "SAML SSO + SCIM", "audit log export", "24x7 Sev-1 support", "custom DPA"],
    }
    docs = []
    for plan in PLANS:
        items = "\n".join(f"- {f}" for f in features[plan])
        docs.append(
            Doc(
                doc_id=f"plan-{plan}",
                title=f"What is included in the {PLAN_LABEL[plan]} plan",
                category="billing",
                tags=["plan", plan, "pricing", "limits"],
                body=f"""# What is included in the {PLAN_LABEL[plan]} plan

**{PLAN_PRICE[plan]} per user per month** (annual billing saves two months).

## Included

{items}

## Limits that trip people up

- Seats are counted including pending invitations.
- Storage is workspace-wide, not per user, and includes trash and version history.
- The maximum single-file size is a hard limit; larger files are rejected at
  upload rather than truncated.

## Changing plan

Upgrades apply immediately and are prorated. Downgrades apply at the end of the
current period. See the upgrade and downgrade articles for the exact steps.
""",
            )
        )
    return docs


def security_docs() -> list[Doc]:
    """Security and compliance articles."""
    topics = [
        ("encryption", "How data is encrypted",
         """Data is encrypted in transit with TLS 1.3 (TLS 1.2 accepted for legacy clients;
SSL and TLS 1.0/1.1 are refused). At rest, content is encrypted with AES-256
using keys held in a managed KMS and rotated annually.

Enterprise workspaces may supply their own key (BYOK) through AWS KMS or Google
Cloud KMS. Revoking that key renders the workspace unreadable within minutes -
which is the point, but it is not reversible, so treat revocation as a break-glass
action."""),
        ("access-control", "Who inside Acme can see customer data",
         """Access to production data requires a named, time-boxed approval and is logged
to an append-only audit trail reviewed monthly. Support staff can see workspace
and billing metadata by default; reading file *content* requires explicit,
per-incident customer consent recorded in the ticket.

Engineers have no standing production access. Break-glass access pages the
security team and expires after four hours."""),
        ("compliance", "Compliance certifications",
         """We hold SOC 2 Type II (audited annually, report available under NDA) and
ISO 27001. We act as a processor under GDPR and offer a DPA with the standard
contractual clauses to all paid plans. HIPAA BAAs are available on Enterprise.

PCI scope is limited: card details go directly to our payment processor and never
touch our servers."""),
        ("incident-response", "How security incidents are handled",
         """Suspected incidents are triaged within one hour, 24x7. Confirmed incidents
affecting customer data are notified to affected workspaces within 72 hours, with
a factual description of what happened, what data was involved, and what we are
doing about it.

Report a suspected issue to security@acme.example. We do not take legal action
against good-faith security research that follows our disclosure policy."""),
        ("audit-log", "Reading the audit log",
         """Settings > Security > **Audit log** records sign-ins, permission changes,
share link creation, integration grants and data exports. Each entry has an
actor, an IP address, a user agent and a timestamp in UTC.

Retention is 12 months on Business and Enterprise, 30 days elsewhere. Enterprise
workspaces can stream events continuously to an S3 bucket or a SIEM."""),
        ("ip-allowlist", "Restricting access by IP address",
         """Enterprise workspaces can allow only named CIDR ranges. Add them under
Settings > Security > **IP allowlist**.

Add your own current address before saving - the rule applies immediately and it
is entirely possible to lock yourself out. API keys are subject to the same list,
so remember CI runners and servers, whose egress addresses are easy to forget."""),
        ("session-policy", "Setting a session timeout",
         """Business and Enterprise admins can shorten the default 30 day session under
Settings > Security > **Session policy**, to as little as one hour, and can
require re-authentication for sensitive actions such as changing billing details
or exporting data.

Shorter sessions trade convenience for containment; one business day is a common
compromise."""),
        ("device-approval", "Approving new devices",
         """With device approval enabled, a sign-in from an unrecognised device is held
pending until an admin approves it under Settings > Security > **Devices**.

The user sees a waiting screen and receives an email when approved. Approvals
last until the device is explicitly revoked."""),
        ("phishing", "Recognising phishing that imitates Acme Cloud",
         f"""We never ask for your password, a recovery code or an MFA code - not by email,
not by phone, not in chat. Any message that does is fraudulent.

Genuine mail comes from `@acme.example` and links only to `acme.example`
domains. Hover a link before clicking and check the domain character by
character; lookalike domains are the standard technique.

Forward suspicious messages to security@acme.example and then delete them. If
you entered credentials somewhere suspicious, change your password immediately
and sign out all sessions from Settings > Security, then tell {SUPPORT_EMAIL}."""),
        ("pentest", "Penetration testing your own workspace",
         """Customers may test their own workspace without prior approval, subject to the
rules of engagement at acme.example/security/testing: no denial of service, no
testing against other tenants, and no social engineering of our staff.

Share findings with security@acme.example. Include the request id where you have
one - it makes reproduction far quicker."""),
    ]
    return [
        Doc(
            doc_id=f"security-{slug}",
            title=title,
            category="security",
            tags=["security", slug, "compliance"],
            body=f"# {title}\n\n{content.strip()}\n",
        )
        for slug, title, content in topics
    ]


def policy_docs() -> list[Doc]:
    """Customer-facing policies the agent must quote rather than improvise."""
    topics = [
        ("acceptable-use", "Acceptable use policy",
         """Acme Cloud may not be used to store or distribute malware, child sexual abuse
material, content that infringes copyright, or material that violates applicable
law. We act on reports at abuse@acme.example.

Automated bulk access outside the documented API, attempts to circumvent rate
limits, and reselling storage capacity are all prohibited and are grounds for
suspension.

Enforcement is graduated: notice, then restriction, then suspension. Content that
is illegal on its face is removed immediately and without notice."""),
        ("fair-use-bandwidth", "Fair use limits on bandwidth",
         """Unlimited plans carry a fair use ceiling of 2 TB of egress per seat per month.
Crossing it triggers a notice, not a cut-off; sustained overage is discussed with
the account owner and may require a plan change.

Share link traffic counts toward the workspace that owns the file, which matters
for public links that get picked up by an aggregator."""),
        ("beta-features", "Using beta features",
         """Features marked Beta are functional but unfinished. They are excluded from the
SLA, may change or be withdrawn with a week's notice, and should not be relied on
for production work.

Opt in per workspace under Settings > Labs. Feedback goes to beta@acme.example."""),
        ("deprecation", "How APIs and features are deprecated",
         """Stable APIs are supported for at least 12 months after a deprecation notice.
Notices are published in the changelog, sent to workspace owners by email, and
returned in a `Sunset` header on affected endpoints.

Beta APIs may change with 30 days' notice. We do not remove a stable endpoint
without a documented migration path."""),
        ("support-scope", "What support covers",
         f"""Support covers the use, configuration and behaviour of {PRODUCT}: setup,
troubleshooting, billing and account questions, and bug reports.

Support does not cover writing your integration code, debugging your own
application, general network administration on your side, or recovering data
deleted beyond the retention window. We will always point you to the right
documentation, and for integration work our solutions engineers are available on
Enterprise plans."""),
        ("account-suspension", "Why an account can be suspended",
         """A workspace can be suspended for non-payment after the 14 day grace period, for
a confirmed acceptable use violation, or at the request of the workspace owner.

Suspension makes the workspace read-only rather than deleting it. Data is
retained for 30 days after suspension and can be restored by settling the balance
or resolving the violation.

Reinstatement after an abuse suspension requires a human review."""),
        ("data-portability", "Exporting all of your data",
         """Owners and admins can export everything under Settings > Workspace > **Export**.
The export includes files in their original formats, a JSON manifest of metadata,
comments, and the audit log where retained.

Exports are prepared asynchronously; you get an email with a signed download link
valid for 7 days. A multi-terabyte workspace takes several hours. There is no
charge and no limit on how often you export - portability is not gated."""),
        ("price-changes", "How price changes are handled",
         """Existing subscriptions keep their price for the remainder of the current term.
Price changes are announced at least 60 days before they take effect and apply at
the next renewal.

Annual customers are notified before their renewal date with enough time to
cancel if they choose."""),
    ]
    return [
        Doc(
            doc_id=f"policy-{slug}",
            title=title,
            category="policies",
            tags=["policy", slug],
            body=f"# {title}\n\n{content.strip()}\n",
        )
        for slug, title, content in topics
    ]


def faq_docs() -> list[Doc]:
    """Short answers to the highest-volume questions."""
    faqs = [
        ("trial-length", "How long is the free trial?",
         "Every paid plan comes with a 14 day trial. No card is required to start it. At the end you are moved to Free unless you subscribe; nothing is deleted."),
        ("change-region", "Can I move my workspace to another region?",
         "Not in place. The region is fixed when the workspace is created. Moving means exporting and importing into a new workspace, which support can help plan for large datasets."),
        ("multiple-workspaces", "Can one account belong to several workspaces?",
         "Yes, with no limit. Switch between them from the top-left switcher. Each workspace bills separately."),
        ("version-history", "How far back does version history go?",
         "7 days on Free, 30 on Starter, 90 on Team, one year on Business, unlimited on Enterprise. Every save creates a version; restore from the file's History tab."),
        ("file-locking", "Can I lock a file so nobody else edits it?",
         "Yes - right-click and choose **Lock**. Locks are advisory in the desktop app and enforced in the web app, and expire automatically after 24 hours."),
        ("guest-access", "Do guests count toward my seat limit?",
         "No. Guests see only the projects they are added to and are free on every plan. Converting a guest to a member consumes a seat."),
        ("api-availability", "Which plans include API access?",
         "Team and above. Rate limits scale with the plan: 60 requests/minute on Team, 600 on Business, negotiated on Enterprise."),
        ("mobile-offline", "Does the mobile app work offline?",
         "Yes for files you have pinned. Tap the pin icon on a file or folder before you lose connectivity; changes sync when you reconnect."),
        ("bulk-invite", "Can I invite many people at once?",
         "Paste a comma-separated list into the invite box, or upload a CSV of email and role pairs. Business and Enterprise can provision automatically with SCIM instead."),
        ("delete-vs-archive", "What is the difference between deleting and archiving a project?",
         "Archiving makes a project read-only and halves its storage footprint, and is reversible at any time. Deleting moves it to trash for 30 days and then purges it permanently."),
        ("shared-drive-migration", "Can I migrate from another provider?",
         "Yes. Settings > Import supports Dropbox, Google Drive, Box and OneDrive, preserving folder structure and, where the source exposes it, sharing. Large migrations are best scheduled with support."),
        ("custom-domain", "Can share links use my own domain?",
         "On Enterprise, yes. Add a CNAME for the subdomain you want and we issue the certificate. Existing links keep working."),
        ("service-account", "Should integrations use a personal account?",
         "No. Use a service account so the integration survives staff turnover. Service accounts do not consume a seat when used only for integrations."),
        ("email-in", "Can I email files into a project?",
         "Each project has an address under Project settings > Email-in. Attachments land in an Inbox folder. The address accepts mail only from workspace members by default."),
        ("two-accounts-same-email", "Can I have two accounts with the same email?",
         "No. The email address is the identity. Use workspaces to separate contexts, or a plus-address for a genuinely separate account."),
    ]
    return [
        Doc(
            doc_id=f"faq-{slug}",
            title=question,
            category="faq",
            tags=["faq", slug],
            body=f"# {question}\n\n{answer}\n",
        )
        for slug, question, answer in faqs
    ]


def getting_started_docs() -> list[Doc]:
    """Onboarding walkthroughs, one per platform where it matters."""
    guides = [
        ("install", "Install {PRODUCT}",
         ["Download the current build from acme.example/download.",
          "Run the installer and sign in with your workspace address.",
          "Choose a local folder; the default is fine unless you keep data on a second drive.",
          "Pick which projects sync to this device - start with one to confirm it works."],
         "The tray or menu bar icon shows a green check and files appear in the chosen folder."),
        ("invite-team", "Invite your team",
         ["Settings > Members > **Invite**.",
          "Paste addresses separated by commas and pick a role for each.",
          "Members see every project; guests see only what you add them to.",
          "Invitations expire after 7 days and can be resent."],
         "Each invitee appears as Pending and flips to Active on acceptance."),
        ("organise-projects", "Organise work into projects",
         ["Create one project per team, client or initiative rather than per file type.",
          "Set access at the project level; files inherit it.",
          "Archive projects when they finish - archived projects stay searchable and cost half the storage.",
          "Use a shallow folder structure inside projects; search is faster than nesting."],
         "The project list reflects how your team actually talks about its work."),
        ("first-share", "Share your first file",
         ["Select a file and choose **Share**.",
          "Share with a person by email, or create a link.",
          "Set an expiry and, for anything sensitive, a password.",
          "Choose view or edit access - view is the safe default."],
         "The recipient opens the file and the share appears in Activity."),
    ]
    docs = []
    for slug, title, steps, verify in guides:
        for platform in PLATFORMS:
            body_steps = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, start=1))
            docs.append(
                Doc(
                    doc_id=f"getting-started-{slug}-{platform}",
                    title=f"{title.format(PRODUCT=PRODUCT)} on {PLATFORM_LABEL[platform]}",
                    category="getting-started",
                    tags=["getting-started", "onboarding", slug, platform],
                    body=f"""# {title.format(PRODUCT=PRODUCT)} on {PLATFORM_LABEL[platform]}

## Steps

{body_steps}

## Platform note

{PLATFORM_HINT[platform]}

## Verify

{verify}

## Next

Work through the other getting-started articles in order: install, invite your
team, organise projects, then share your first file.
""",
                )
            )
    return docs


def app_error_docs() -> list[Doc]:
    """One article per in-app error code."""
    return [
        Doc(
            doc_id=f"error-{code.lower().replace('_', '-')}",
            title=f"{code}: {title}",
            category="errors",
            tags=["error", code.lower(), "troubleshooting"],
            body=f"""# {code}: {title}

## What it means

{meaning}

## How to fix it

{fix}

## Where you see it

This code appears in the app's error banner, in the desktop client's Activity
panel, and in the `code` field of any related API response.

## When to escalate

Escalate if the fix above has been applied in full and the same code returns
within an hour. Quote the code and the time it occurred - both appear in the
audit log and let us find the exact event.
""",
        )
        for code, title, meaning, fix in APP_ERRORS
    ]


def workflow_docs() -> list[Doc]:
    """Admin-facing runbooks that combine several features."""
    docs = []
    for slug, title, steps, verify in WORKFLOWS:
        body_steps = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, start=1))
        docs.append(
            Doc(
                doc_id=f"workflow-{slug}",
                title=title,
                category="workflows",
                tags=["workflow", "admin", slug],
                audience="admin",
                body=f"""# {title}

## Who this is for

Workspace owners and admins. Some steps need the owner role, which is noted
where it applies.

## Steps

{body_steps}

## Verify

{verify}

## When to escalate

Escalate when a step cannot be completed because the required control is absent
from your plan, or when the verification above does not hold after completing
every step.
""",
            )
        )
    return docs


def integration_permission_docs() -> list[Doc]:
    """What each integration can see, for security reviews."""
    return [
        Doc(
            doc_id=f"integration-{slug}-permissions",
            title=f"What the {name} integration can access",
            category="integrations",
            tags=["integration", slug, "permissions", "security"],
            body=f"""# What the {name} integration can access

Security teams ask this before approving an integration, so here it is plainly.

## Granted to Acme Cloud

The integration receives an OAuth token scoped to the permissions you approve at
connection time. We request the narrowest scopes that make the features work:
read access to the resources you select, and write access only where the
integration creates something on your behalf.

## Granted to {name}

{name} receives access only to the Acme Cloud projects you select during setup.
Selecting no projects leaves the integration connected but inert, which is a
reasonable way to stage a rollout.

## What we store

The OAuth token (encrypted at rest), the resource mapping, and a sync cursor. We
do not copy {name} content into Acme Cloud beyond what the integration's features
explicitly require, and what is copied is listed on the integration's card.

## Reviewing and revoking

- Settings > Integrations > {name} shows the scopes in force and who authorised them.
- The audit log records the grant, every scope change, and the revocation.
- Revoking is immediate on our side; also remove the app inside {name}, since a
  one-sided revocation leaves a stale grant listed on the other.

## When to escalate

Escalate when a security review needs scope detail beyond this article, or a
written confirmation of data flows for an audit.
""",
        )
        for slug, name in INTEGRATIONS
    ]


def integration_limit_docs() -> list[Doc]:
    """Sync behaviour and limits per integration."""
    return [
        Doc(
            doc_id=f"integration-{slug}-limits",
            title=f"{name} integration: sync behaviour and limits",
            category="integrations",
            tags=["integration", slug, "limits", "sync"],
            body=f"""# {name} integration: sync behaviour and limits

## How often it syncs

Events flow within a minute in normal operation. After a reconnect or an outage
at either end, the integration replays from its last cursor, so nothing is lost -
but a large backlog can take an hour to drain.

## Rate limits

{name} enforces its own API limits. When we are throttled the integration backs
off exponentially and retries; the card shows **Catching up** rather than an
error. This is expected and needs no action unless it persists for hours.

## What is not synced

- Items in the trash on either side.
- Content the authorising account cannot itself see - the integration never has
  more access than the person who connected it.
- Files above your plan's single-file size limit.
- Revisions older than the current one, unless the integration's card says otherwise.

## Deletions

Deletions propagate as deletions, not as permanent removals: the item lands in
trash on the receiving side and stays recoverable for 30 days. This is deliberate -
a misconfigured integration should not be able to destroy data irreversibly.

## Conflicts

When the same item changes on both sides between syncs, we keep both and mark
one as a conflicted copy. We never silently discard an edit.

## When to escalate

Escalate when the card has shown **Catching up** for more than four hours, or
when items that satisfy all the conditions above are still not syncing.
""",
        )
        for slug, name in INTEGRATIONS
    ]


def extra_security_docs() -> list[Doc]:
    """Second batch of security articles."""
    topics = [
        ("password-requirements", "Password requirements",
         """Passwords must be at least 12 characters. We impose no composition rules -
forced symbols and digits demonstrably produce weaker, more predictable
passwords - but we do check every new password against a corpus of known-breached
credentials and refuse matches.

Admins on Business and Enterprise can require a minimum length up to 64 and set a
rotation period. We advise against rotation: NIST withdrew that recommendation
because scheduled rotation drives people toward predictable variations."""),
        ("api-key-handling", "Handling API keys safely",
         """A key's secret is shown exactly once, at creation. Store it in a secret manager,
never in source control or a CI configuration file.

Scope each key to the narrowest set of permissions the job needs, and create one
key per system rather than sharing one everywhere - a shared key cannot be
revoked without breaking everything at once.

Rotate with the rotate endpoint, which keeps the old secret valid for 24 hours so
you can deploy the new one without downtime. Keys unused for 90 days are flagged
in the developer settings; revoke them."""),
        ("sub-processors", "Sub-processors",
         """Our current sub-processors are listed at acme.example/legal/subprocessors, with
the region and purpose of each: cloud hosting, email delivery, payment processing,
error monitoring and support tooling.

Subscribe on that page to be notified 30 days before a new sub-processor is
added, which is the window in which Enterprise customers may object under the
DPA."""),
        ("bug-bounty", "Reporting a vulnerability",
         """Report to security@acme.example, encrypted with the PGP key published at
acme.example/.well-known/security.txt. We acknowledge within one business day and
aim to triage within three.

Rewards range from $100 to $15,000 by severity. In scope: the web app, API,
desktop and mobile clients. Out of scope: denial of service, social engineering,
issues requiring a rooted or jailbroken device, and reports generated by a
scanner without a working proof of concept.

We will not pursue legal action against research that follows this policy."""),
        ("shared-responsibility", "Shared responsibility model",
         """We are responsible for the security *of* the platform: infrastructure, encryption,
availability, patching, and the integrity of the service.

You are responsible for security *in* your workspace: who you invite and with
what role, which share links you create and whether they expire, which
integrations you authorise, whether MFA is enforced, and the security of your own
devices and identity provider.

Most incidents we see originate on the customer side of that line - usually an
over-broad share link or an account without MFA."""),
        ("data-residency", "Where your data is stored",
         """Workspace content is stored in the region chosen at creation: us-east, eu-west or
ap-southeast. It stays there, including backups.

Metadata needed to route requests - workspace ids, and the region mapping itself -
is global by necessity. Support tooling and billing records are held in us-east
regardless of workspace region.

The region cannot be changed after creation; moving means exporting and importing
into a new workspace."""),
        ("legal-hold", "Placing content under legal hold",
         """Enterprise workspaces can place a project or an individual's content under legal
hold from Settings > Compliance. Held content cannot be deleted by anyone,
including workspace owners, and is exempt from the 30 day trash purge.

Holds are recorded in the audit log with the actor and the reason. Only a
compliance admin can release one. Held content still counts toward storage
quota."""),
        ("email-security", "Email authentication for notifications",
         """Our notification mail is signed with DKIM, authorised by SPF, and covered by a
DMARC policy of `reject` on acme.example. If a message claiming to be from us
fails these checks, your mail server should already have rejected it.

If your organisation rewrites or relays our mail in a way that breaks DKIM, ask
IT to allowlist `no-reply@acme.example` rather than disabling DMARC checks."""),
        ("byok", "Bringing your own encryption key",
         """Enterprise workspaces can supply a customer-managed key through AWS KMS or Google
Cloud KMS. We use it to wrap the data encryption keys, so revoking it makes the
workspace unreadable within minutes.

That is the point of the feature, and it is not reversible: if the key is
destroyed rather than merely disabled, the data is unrecoverable. Treat
revocation as a break-glass action and test the process in a non-production
workspace first."""),
        ("logging-privacy", "What we log about your activity",
         """We log request metadata - timestamps, workspace and user ids, IP addresses, user
agents, endpoints, response codes and request ids. We do not log request bodies
or file content.

Operational logs are retained for 30 days. The customer-visible audit log is
separate and retained per the retention article. Support staff querying logs for
a ticket see only metadata unless you explicitly consent to content access."""),
    ]
    return [
        Doc(
            doc_id=f"security-{slug}",
            title=title,
            category="security",
            tags=["security", slug, "compliance"],
            body=f"# {title}\n\n{content.strip()}\n",
        )
        for slug, title, content in topics
    ]


def extra_policy_docs() -> list[Doc]:
    """Second batch of policies."""
    topics = [
        ("trial-terms", "Free trial terms",
         """Every paid plan offers a 14 day trial, once per workspace, with no card required.
Trials carry the full feature set of the plan, including the API and SSO.

At the end the workspace moves to Free. Nothing is deleted, but content above the
Free limits becomes read-only until you subscribe or reduce usage. We email a
reminder three days before the trial ends."""),
        ("nonprofit-discount", "Discounts for nonprofits and education",
         """Registered nonprofits and accredited educational institutions receive 50% off
Team and Business plans. Apply with proof of status at acme.example/nonprofit;
verification takes about three business days.

The discount applies at the next renewal and does not stack with annual billing
promotions - you get whichever is larger."""),
        ("reseller-policy", "Buying through a reseller",
         """Enterprise plans may be purchased through an authorised reseller. Billing and
invoicing then run through them, while support and the technical relationship
stay with us.

Plan changes go through the reseller. Support requests come directly to us - you
do not need to route a technical question through a procurement channel."""),
        ("api-terms", "API terms of use",
         """The API is for building integrations with your own workspace data. You may not
use it to mirror the service, to resell storage, or to circumvent plan limits.

Respect the rate limits and the `Retry-After` header. Persistent disregard for
backoff is treated as abuse and can result in key revocation.

Cache responses where you sensibly can; polling an unchanged resource every
second helps nobody."""),
        ("content-ownership", "Who owns the content you upload",
         """You do. We claim no ownership of customer content and acquire only the licence
necessary to store, transmit, back up and display it to the people you share it
with.

That licence ends when you delete the content or close the account, subject to
the backup ageing window described in the retention article."""),
        ("third-party-apps", "Using third-party apps with Acme Cloud",
         """Apps in our directory are reviewed for scope hygiene and basic security, but
they are operated by their publishers, not by us. Your data flowing into a
third-party app is governed by that publisher's terms.

Admins can restrict which apps members may authorise under Settings > Security >
App governance, which is worth doing before a rollout rather than after."""),
        ("service-changes", "Changes to the service",
         """We add and improve features continuously. Material changes that reduce
functionality are announced at least 30 days ahead in the changelog and by email
to workspace owners.

Stable API deprecations follow the longer 12 month schedule in the deprecation
policy. We do not remove a documented capability without a migration path."""),
        ("dispute-resolution", "Resolving a billing dispute",
         f"""Raise a dispute with {SUPPORT_EMAIL} before contacting your bank. A chargeback
automatically suspends the workspace while the bank investigates, which is
usually worse for you than a conversation with us.

We respond to disputes within two business days. Where we are wrong we refund
without argument; where we are not, you get the invoice detail and the usage
records behind the charge."""),
    ]
    return [
        Doc(
            doc_id=f"policy-{slug}",
            title=title,
            category="policies",
            tags=["policy", slug],
            body=f"# {title}\n\n{content.strip()}\n",
        )
        for slug, title, content in topics
    ]


def extra_faq_docs() -> list[Doc]:
    """Second batch of short answers."""
    faqs = [
        ("keyboard-shortcuts", "Are there keyboard shortcuts?",
         "Yes. Press `?` anywhere in the web app for the full list. The ones worth learning are `/` to search, `u` to upload, and `g` then `p` to jump to projects."),
        ("dark-mode", "Is there a dark mode?",
         "Yes - Settings > Appearance, with Light, Dark and System options. The desktop and mobile apps follow the OS setting by default."),
        ("file-requests", "Can someone send me files without an account?",
         "Yes. Create a file request from a folder's menu and share the link. Uploads land in that folder and the sender never signs in or sees your other files."),
        ("watermarks", "Can I watermark shared files?",
         "On Business and Enterprise, yes. Enable it per share link; the viewer's email and the time are overlaid on previews and downloads of PDFs and images."),
        ("download-limits", "Can I limit how many times a link is downloaded?",
         "Yes on Business and above. Set a download cap alongside the expiry when creating the link; the link stops working once the cap is reached."),
        ("api-sandbox", "Is there a sandbox for API testing?",
         "Create a separate free workspace and use a key scoped to it. There is no separate sandbox host - the same `/v1` API serves it."),
        ("sdk-languages", "Which SDKs do you publish?",
         "Official clients for Python, TypeScript, Go and Java, all on the public package registries. The REST API is stable and documented for anything else."),
        ("bulk-download", "How do I download an entire project?",
         "Select the project and choose Download as ZIP for anything under 20 GB. Above that, use the export endpoint, which produces a signed multi-part download."),
        ("restore-old-version", "How do I go back to an earlier version of a file?",
         "Open the file's History tab, preview the version you want and choose Restore. Restoring creates a new version rather than erasing the ones in between."),
        ("who-viewed", "Can I see who viewed a shared file?",
         "Yes for links created on Team and above. The file's Activity tab lists viewers by email where they were signed in, and by IP where they were not."),
        ("trash-retention", "How long do deleted files stay recoverable?",
         "30 days on every plan, after which they are purged from primary storage and age out of backups within a further 35 days. There is no way to recover them afterwards."),
        ("storage-shared", "Is storage per user or per workspace?",
         "Per workspace. One member uploading a large dataset consumes the shared allowance, which is why Settings > Usage breaks it down by project."),
        ("edit-in-office", "Can I edit Office documents in place?",
         "Yes. Opening a DOCX, XLSX or PPTX offers editing in the browser or in the desktop Office app, saving back to Acme Cloud as a new version."),
        ("two-factor-sms", "Do you support SMS as a second factor?",
         "No, deliberately. SMS is vulnerable to SIM-swap attacks. We support TOTP apps and hardware security keys (WebAuthn), which are both stronger."),
        ("security-keys", "Can I use a hardware security key?",
         "Yes. Settings > Security > Security keys supports WebAuthn keys such as YubiKey. Register at least two so losing one is not a lockout."),
        ("api-pagination", "How does pagination work in the API?",
         "Cursor-based. Follow `next_cursor` from each response until it is null. Do not construct cursors yourself - they are opaque and their format may change."),
        ("webhook-security", "How do I verify a webhook came from you?",
         "Each delivery carries an `X-Acme-Signature` header: an HMAC-SHA256 of the raw body using your endpoint's signing secret. Compare it in constant time, against the raw bytes, before parsing."),
        ("status-updates", "How do I find out about outages?",
         f"Subscribe at {STATUS_PAGE} for email, RSS or webhook updates. Sev-1 incidents are also emailed to workspace owners automatically."),
        ("account-manager", "Do I get a dedicated contact?",
         "Enterprise customers get a named customer success manager and a shared Slack channel. Business customers get priority routing but not a named contact."),
        ("training", "Do you offer training for my team?",
         "Live onboarding sessions are included on Business and Enterprise. Self-serve video walkthroughs covering the same material are free for everyone at acme.example/learn."),
    ]
    return [
        Doc(
            doc_id=f"faq-{slug}",
            title=question,
            category="faq",
            tags=["faq", slug],
            body=f"# {question}\n\n{answer}\n",
        )
        for slug, question, answer in faqs
    ]


def build_corpus() -> list[Doc]:
    """Assemble the full knowledge base."""
    docs: list[Doc] = []
    docs += core_docs()
    docs += scenario_docs(account_scenarios() + more_account_scenarios(), "account")
    docs += scenario_docs(billing_scenarios(), "billing")
    docs += scenario_docs(
        troubleshooting_scenarios() + more_troubleshooting_scenarios(), "troubleshooting"
    )
    docs += scenario_docs(mobile_scenarios(), "mobile")
    docs += api_error_docs()
    docs += api_endpoint_docs()
    docs += app_error_docs()
    docs += integration_docs()
    docs += integration_permission_docs()
    docs += integration_limit_docs()
    docs += plan_comparison_docs()
    docs += security_docs()
    docs += extra_security_docs()
    docs += policy_docs()
    docs += extra_policy_docs()
    docs += workflow_docs()
    docs += faq_docs()
    docs += extra_faq_docs()
    docs += getting_started_docs()

    seen: dict[str, Doc] = {}
    for doc in docs:
        if doc.doc_id in seen:
            raise ValueError(f"duplicate document id: {doc.doc_id}")
        seen[doc.doc_id] = doc
    return docs


def write_corpus(kb_dir: Path, *, clean: bool = True) -> int:
    """Write every document to ``kb_dir/<category>/<doc_id>.md``."""
    docs = build_corpus()
    if clean and kb_dir.exists():
        for child in kb_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)

    for doc in docs:
        target = kb_dir / doc.category
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{doc.doc_id}.md").write_text(doc.render(), encoding="utf-8")

    _write_index(kb_dir, docs)
    return len(docs)


def _write_index(kb_dir: Path, docs: list[Doc]) -> None:
    """Write a README listing the corpus; excluded from indexing by the loader."""
    by_category: dict[str, int] = {}
    for doc in docs:
        by_category[doc.category] = by_category.get(doc.category, 0) + 1

    rows = "\n".join(
        f"| {category} | {count} |" for category, count in sorted(by_category.items())
    )
    kb_dir.mkdir(parents=True, exist_ok=True)
    (kb_dir / "README.md").write_text(
        f"""# Support knowledge base

{len(docs)} articles describing {PRODUCT}, a fictional SaaS used to exercise the
RAG engine with realistic support content.

| Category | Articles |
| --- | --- |
{rows}
| **Total** | **{len(docs)}** |

Every article is Markdown with YAML front matter (`id`, `title`, `category`,
`tags`, `audience`, `severity`). Articles are generated by
`scripts/generate_kb.py`, which is deterministic - regenerate rather than
editing files here, or your changes will be overwritten.

Index them into the vector store with `make kb` (`python scripts/seed_kb.py`).
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=KB_DIR, help="output directory")
    parser.add_argument("--count", action="store_true", help="only report the document count")
    parser.add_argument("--no-clean", action="store_true", help="keep existing category folders")
    args = parser.parse_args()

    if args.count:
        print(f"{len(build_corpus())} documents")
        return 0

    written = write_corpus(args.out, clean=not args.no_clean)
    print(f"Wrote {written} knowledge base documents to {args.out}")
    if written < 500:
        print(f"WARNING: corpus is below the 500 document target ({written})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
