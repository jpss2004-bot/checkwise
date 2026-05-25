"""One-shot fill of ``route_policy_manifest.json`` policy fields.

After running ``seed_route_policy_manifest.py`` the manifest carries
122 entries with ``TBD —`` placeholders. This script applies the
per-gate defaults agreed in the 2026-05-25 sale-readiness audit so
the test ``tests/test_route_policy_manifest.py`` becomes green.

After this script lands, any further refinements (route-level
nuances, audit_rule downgrades, new tenant edges) are HAND edits to
the JSON file. Do not re-run this script — it will overwrite manual
changes.

Usage from ``apps/api``::

    python -m scripts.fill_route_policy_defaults

It edits ``app/security/route_policy_manifest.json`` in place.
"""

from __future__ import annotations

import json
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[1]
_MANIFEST_PATH = _API_ROOT / "app" / "security" / "route_policy_manifest.json"


# Per-gate defaults. The cell key is (gate, method-class) where
# method-class is "READ" for GET and "MUTATE" for POST/PATCH/PUT/DELETE.
_DEFAULTS: dict[tuple[str, str], dict[str, str]] = {
    ("internal_admin", "READ"): {
        "tenant_rule": "cross-tenant (internal_admin is global)",
        "audit_rule": "not_logged (read-only)",
        "rate_limit_rule": "none (auth-gated)",
        "error_lang": "es",
    },
    ("internal_admin", "MUTATE"): {
        "tenant_rule": "cross-tenant (internal_admin is global)",
        "audit_rule": "logged via _audit_admin",
        "rate_limit_rule": "none (auth-gated)",
        "error_lang": "es",
    },
    ("client_admin_or_admin", "READ"): {
        "tenant_rule": "scoped via _resolve_client_id() membership check",
        "audit_rule": "not_logged (read-only)",
        "rate_limit_rule": "none (auth-gated)",
        "error_lang": "es",
    },
    ("client_admin_or_admin", "MUTATE"): {
        "tenant_rule": "scoped via _resolve_client_id() membership check",
        "audit_rule": "logged",
        "rate_limit_rule": "none (auth-gated)",
        "error_lang": "es",
    },
    ("reviewer_or_admin", "READ"): {
        "tenant_rule": "cross-tenant (reviewer/admin is global)",
        "audit_rule": "not_logged (read-only)",
        "rate_limit_rule": "none (auth-gated)",
        "error_lang": "es",
    },
    ("reviewer_or_admin", "MUTATE"): {
        "tenant_rule": "cross-tenant (reviewer/admin is global)",
        "audit_rule": "logged via submission_workflow.apply_reviewer_decision",
        "rate_limit_rule": "none (auth-gated)",
        "error_lang": "es",
    },
    ("provider_workspace", "READ"): {
        "tenant_rule": "current_portal_workspace dependency validates session-vs-path workspace_id",
        "audit_rule": "not_logged (read-only)",
        "rate_limit_rule": "none (auth-gated)",
        "error_lang": "es",
    },
    ("provider_workspace", "MUTATE"): {
        "tenant_rule": "current_portal_workspace dependency validates session-vs-path workspace_id",
        "audit_rule": "logged",
        "rate_limit_rule": "none (auth-gated)",
        "error_lang": "es",
    },
    ("authenticated_jwt", "READ"): {
        "tenant_rule": "scoped by report service via _actor_from(current)",
        "audit_rule": "not_logged (read-only)",
        "rate_limit_rule": "none (auth-gated)",
        "error_lang": "es_partial (raw service exceptions can leak; M2 will normalize)",
    },
    ("authenticated_jwt", "MUTATE"): {
        "tenant_rule": "scoped by report service via _actor_from(current)",
        "audit_rule": "logged for create/patch/version/generate/export/share; AI conversation turns sampled",
        "rate_limit_rule": "none (auth-gated; M3 adds AI-heavy + export limits)",
        "error_lang": "es_partial (raw service exceptions can leak; M2 will normalize)",
    },
    ("local_or_internal_admin", "READ"): {
        "tenant_rule": "cross-tenant (internal_admin is global)",
        "audit_rule": "not_logged (read-only)",
        "rate_limit_rule": "none (gate-restricted)",
        "error_lang": "es",
    },
    ("local_or_internal_admin", "MUTATE"): {
        "tenant_rule": "cross-tenant (internal_admin is global)",
        "audit_rule": "logged",
        "rate_limit_rule": "none (gate-restricted)",
        "error_lang": "es_partial (metadata-dry-run technical messages are dev-facing)",
    },
    ("public_health", "READ"): {
        "tenant_rule": "n/a (public health probe)",
        "audit_rule": "not_logged (no mutation)",
        "rate_limit_rule": "none (read-only public)",
        "error_lang": "es",
    },
    ("public_catalog", "READ"): {
        "tenant_rule": "n/a (public reference catalog)",
        "audit_rule": "not_logged (read-only)",
        "rate_limit_rule": "none (read-only public)",
        "error_lang": "es",
    },
    ("public_with_rate_limit", "MUTATE"): {
        "tenant_rule": "n/a (public submission endpoint)",
        "audit_rule": "logged (contact/feedback persistence + auth event)",
        "rate_limit_rule": "per-endpoint limiter (login / forgot-password / contact / feedback)",
        "error_lang": "es_partial (feedback router has English messages; M2 will normalize)",
    },
    ("signed_token", "READ"): {
        "tenant_rule": "report scoped via signed-token lookup",
        "audit_rule": "sampled (token resolution audited on POST /unlock only)",
        "rate_limit_rule": "TODO (M3 adds share-unlock brute-force limiter)",
        "error_lang": "es",
    },
    ("signed_token", "MUTATE"): {
        "tenant_rule": "report scoped via signed-token lookup with password unlock check",
        "audit_rule": "logged on unlock success and failure",
        "rate_limit_rule": "TODO (M3 adds share-unlock brute-force limiter)",
        "error_lang": "es",
    },
    ("session_helper", "MUTATE"): {
        "tenant_rule": "n/a (session establishment / teardown)",
        "audit_rule": "logged for POST /enter; not_logged for POST /logout (no state change)",
        "rate_limit_rule": "none (uses parent auth)",
        "error_lang": "es",
    },
    ("session_helper", "READ"): {
        "tenant_rule": "scoped to the caller's own portal session",
        "audit_rule": "not_logged (read-only)",
        "rate_limit_rule": "none (uses parent auth)",
        "error_lang": "es",
    },
}


# Per-route overrides for the small number of edges the gate-level
# defaults can't express cleanly. Add to this dict; do NOT widen the
# defaults table.
_OVERRIDES: dict[tuple[str, str], dict[str, str]] = {
    # GET /admin/audit-log is read-only against an immutable table.
    ("GET", "/api/v1/admin/audit-log"): {
        "notes": "Reads the immutable audit_log itself; never mutates.",
    },
    # The two notification mark-read endpoints are the known P1 gap
    # from both audits (Pass 3 + the PDF) — flag explicitly so the
    # next maintainer knows this is the route to fix first.
    ("POST", "/api/v1/client/notifications/{notification_id}/read"): {
        "audit_rule": "not_logged (P1 GAP — Pass 3 finding P3-01; add add_audit_event)",
        "notes": "P1 fix scheduled: write client.notification_read audit row.",
    },
    ("POST", "/api/v1/client/notifications/read-all"): {
        "audit_rule": "not_logged (P1 GAP — Pass 3 finding P3-01; add add_audit_event)",
        "notes": "P1 fix scheduled: write client.notifications_all_read audit row.",
    },
    # Provider mark-read mirrors the client gap.
    ("POST", "/api/v1/portal/workspaces/{workspace_id}/notifications/{notification_id}/read"): {
        "audit_rule": "not_logged (P1 GAP — same shape as P3-01 on the provider side)",
        "notes": "P1 fix scheduled: write provider.notification_read audit row.",
    },
    ("POST", "/api/v1/portal/workspaces/{workspace_id}/notifications/read-all"): {
        "audit_rule": "not_logged (P1 GAP — same shape as P3-01 on the provider side)",
        "notes": "P1 fix scheduled: write provider.notifications_all_read audit row.",
    },
    # Public landing contact form — rate limit + persistence + Slack.
    ("POST", "/api/v1/contact"): {
        "rate_limit_rule": "contact_limiter (per-IP sliding window)",
    },
    ("POST", "/api/v1/feedback/public"): {
        "rate_limit_rule": "feedback_limiter (per-IP-hash sliding window)",
    },
    ("POST", "/api/v1/feedback"): {
        "rate_limit_rule": "per-user 10/min sliding window",
        "audit_rule": "logged (feedback_reports row + Slack delivery audit)",
    },
    ("POST", "/api/v1/auth/login"): {
        "rate_limit_rule": "login_limiter (per-(IP,email) sliding window)",
        "audit_rule": "sampled (login failures audited at a lower rate; success not audited in the auth_log table directly)",
    },
    ("POST", "/api/v1/auth/forgot-password"): {
        "rate_limit_rule": "forgot_password_limiter (per-email + per-IP)",
        "audit_rule": "logged (password_reset_token row)",
    },
    ("POST", "/api/v1/auth/reset-password"): {
        "rate_limit_rule": "consume-side limiter inherited from token issuance",
        "audit_rule": "logged (password_reset_token.used_at + auth event)",
    },
    # /auth/me is a read; /auth/set-password is a mutation.
    ("GET", "/api/v1/auth/me"): {
        "tenant_rule": "n/a (returns the caller's own identity)",
    },
    ("POST", "/api/v1/auth/set-password"): {
        "tenant_rule": "n/a (mutates the caller's own credentials)",
        "audit_rule": "logged (auth.password_changed)",
    },
    # /portal/me returns the caller's own portal session.
    ("GET", "/api/v1/portal/me"): {
        "tenant_rule": "scoped via current_portal_workspace session lookup",
    },
    # /portal/legal-consent mutates the workspace's consent state.
    ("POST", "/api/v1/portal/workspaces/{workspace_id}/legal-consent"): {
        "audit_rule": "logged via provider.legal_consent_accepted with version + IP + UA metadata",
    },
    # Audit-package download writes its own audit row before streaming.
    ("GET", "/api/v1/client/audit-package.zip"): {
        "audit_rule": "logged via client.audit_package_downloaded",
    },
    ("GET", "/api/v1/client/audit-package/preview"): {
        "audit_rule": "not_logged (preview is a hot read; full download writes the audit row)",
    },
    # Reviewer document download distinguishes inline vs ?download=1.
    ("GET", "/api/v1/reviewer/submissions/{submission_id}/document"): {
        "audit_rule": "logged on ?download=1 (reviewer.document_downloaded); inline preview not logged",
    },
    # Provider document download mirrors the reviewer split.
    ("GET", "/api/v1/portal/workspaces/{workspace_id}/submissions/{submission_id}/document"): {
        "audit_rule": "logged on ?download=1 (provider.document_downloaded); inline preview not logged",
    },
    # Admin and client vendor expediente ZIPs both audit.
    ("GET", "/api/v1/admin/vendors/{vendor_id}/expediente.zip"): {
        "audit_rule": "logged via admin.vendor_expediente_downloaded",
    },
    ("GET", "/api/v1/client/vendors/{vendor_id}/expediente.zip"): {
        "audit_rule": "logged via client.vendor_expediente_downloaded",
    },
    ("GET", "/api/v1/portal/workspaces/{workspace_id}/expediente.zip"): {
        "audit_rule": "logged via provider.expediente_downloaded",
    },
    # WISE event POST is bulk analytics — sampled.
    ("POST", "/api/v1/portal/workspaces/{workspace_id}/wise/events"): {
        "audit_rule": "sampled (WiseEvent table is the canonical store)",
    },
    ("POST", "/api/v1/portal/workspaces/{workspace_id}/wise/ask"): {
        "audit_rule": "sampled (WiseEvent on ask)",
        "rate_limit_rule": "TODO (M3 adds AI-heavy rate limiter)",
    },
    # Reports AI generate / blocks/explain / blocks/regenerate /
    # conversation are AI-heavy; flag for the M3 rate-limit work.
    ("POST", "/api/v1/reports/{report_id}/generate"): {
        "rate_limit_rule": "TODO (M3 adds AI-heavy rate limiter)",
    },
    ("POST", "/api/v1/reports/{report_id}/blocks/{block_id}/explain"): {
        "rate_limit_rule": "TODO (M3 adds AI-heavy rate limiter)",
    },
    ("POST", "/api/v1/reports/{report_id}/blocks/{block_id}/regenerate"): {
        "rate_limit_rule": "TODO (M3 adds AI-heavy rate limiter)",
    },
    ("POST", "/api/v1/reports/{report_id}/conversation"): {
        "rate_limit_rule": "TODO (M3 adds AI-heavy rate limiter)",
    },
    # /reports/_engine and /reports/_presets are read-only metadata.
    ("GET", "/api/v1/reports/_engine"): {
        "tenant_rule": "n/a (returns the report engine catalog)",
    },
    ("GET", "/api/v1/reports/_presets"): {
        "tenant_rule": "scoped by audience the caller can instantiate",
    },
    # Report exports + shares — see PDF audit notes.
    ("GET", "/api/v1/reports/exports/{export_id}"): {
        "tenant_rule": "scoped via parent report's audience and creator",
    },
    ("GET", "/api/v1/reports/exports/{export_id}/download"): {
        "audit_rule": "logged on successful redirect to presigned URL",
        "tenant_rule": "scoped via parent report's audience; presigned URL has 15 min TTL",
    },
    ("DELETE", "/api/v1/reports/shares/{share_id}"): {
        "audit_rule": "logged via reports.share_revoked",
    },
    # /submissions (legacy public-shaped intake) is local-or-internal.
    ("POST", "/api/v1/submissions"): {
        "audit_rule": "logged via submission lifecycle",
    },
    # /metadata-dry-run is gated to local-or-internal-admin per the
    # config kill switches.
    ("POST", "/api/v1/metadata-dry-run/pdf"): {
        "audit_rule": "not_logged (dry-run never persists)",
    },
}


def _method_class(method: str) -> str:
    return "READ" if method == "GET" else "MUTATE"


def main() -> None:
    manifest = json.loads(_MANIFEST_PATH.read_text())

    for row in manifest["routes"]:
        gate = row["gate"]
        cls = _method_class(row["method"])
        defaults = _DEFAULTS.get((gate, cls))
        if defaults is None:
            # Public_health / public_catalog only have READs; if a
            # MUTATE landed under one of those gates, fail loudly.
            raise SystemExit(
                f"No default policy block for gate={gate} method-class={cls}; "
                f"add it to _DEFAULTS or fix the route classification.\n"
                f"  Route: {row['method']} {row['path']}"
            )
        for field, value in defaults.items():
            row[field] = value
        overrides = _OVERRIDES.get((row["method"], row["path"]))
        if overrides:
            for field, value in overrides.items():
                row[field] = value
        # Keep notes field present even when empty.
        row.setdefault("notes", "")

    _MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    print(f"Filled policy fields for {len(manifest['routes'])} routes.")


if __name__ == "__main__":
    main()
