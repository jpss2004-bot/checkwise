"""Seed ``app/security/route_policy_manifest.json`` from the live app.

Run ONCE to bootstrap the manifest, then HAND-EDIT the JSON to refine
individual policy entries. The pytest at
``tests/test_route_policy_manifest.py`` is the source of truth for
what counts as a passing policy entry; this script just prepopulates
the boilerplate so the M0 milestone doesn't require typing 122
entries by hand.

Pattern detection rules (best-effort):

- ``AdminUser`` in deps → gate="internal_admin"
- ``ReviewerDep`` → gate="reviewer_or_admin"
- ``ClientUser`` → gate="client_admin_or_admin"
- ``current_portal_workspace`` → gate="provider_workspace"
- ``CurrentUser`` / ``get_current_user`` → gate="authenticated_jwt"
- ``require_local_or_internal_admin`` → gate="local_or_internal_admin"
- Path-based fallbacks for the routers that don't use a named alias:
  * ``/api/v1/health*`` → "public_health"
  * ``/api/v1/catalogs``, ``/api/v1/compliance/*`` → "public_catalog"
  * ``/api/v1/contact`` → "public_with_rate_limit"
  * ``/api/v1/feedback/public`` → "public_with_rate_limit"
  * ``/api/v1/r/*`` → "signed_token"
  * ``/api/v1/portal/enter``, ``/api/v1/portal/logout`` → "session_helper"

Each row also gets default placeholder values for the policy fields
(``tenant_rule``, ``audit_rule``, ``rate_limit_rule``,
``error_lang``, ``notes``). Maintainers fill these in via PR review
on the JSON file.

Usage from ``apps/api`` directory::

    python -m scripts.seed_route_policy_manifest

The script ALWAYS overwrites the manifest. Do not run it after
manual edits have been applied without merging the diff yourself.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.introspect_routes import introspect

# Script lives at ``apps/api/scripts/seed_route_policy_manifest.py``;
# the manifest lives at ``apps/api/app/security/route_policy_manifest.json``.
_API_ROOT = Path(__file__).resolve().parents[1]  # apps/api
_MANIFEST_PATH = _API_ROOT / "app" / "security" / "route_policy_manifest.json"
_PROJECT_ROOT = _API_ROOT.parents[1]  # repo root, used only for nice display paths

# Default policy template fields. Operators fill these per route.
_DEFAULT_POLICY_FIELDS: dict[str, str] = {
    "tenant_rule": "TBD — describe how tenant is resolved or 'cross-tenant (admin-global)' if intentional",
    "audit_rule": "TBD — one of: 'logged', 'sampled', 'not_logged (read-only)', 'not_logged (no mutation)'",
    "rate_limit_rule": "TBD — one of: 'auth_login_limiter', 'forgot_password_limiter', 'contact_limiter', 'feedback_limiter', 'none (auth-gated)'",
    "error_lang": "TBD — 'es', 'es_partial', 'en_partial'",
    "notes": "",
}


def _gate_for(method: str, path: str, deps: list[str]) -> str:
    dep_set = set(deps)
    if "AdminUser" in dep_set:
        return "internal_admin"
    if "ReviewerDep" in dep_set:
        return "reviewer_or_admin"
    if "ClientUser" in dep_set:
        return "client_admin_or_admin"
    if "current_portal_workspace" in dep_set:
        return "provider_workspace"
    if "require_local_or_internal_admin" in dep_set:
        return "local_or_internal_admin"
    if {"CurrentUser", "get_current_user"} & dep_set:
        return "authenticated_jwt"
    if path.startswith("/api/v1/health"):
        return "public_health"
    if path == "/api/v1/catalogs" or path.startswith("/api/v1/compliance/"):
        return "public_catalog"
    if path == "/api/v1/contact":
        return "public_with_rate_limit"
    if path == "/api/v1/feedback/public":
        return "public_with_rate_limit"
    if path.startswith("/api/v1/r/"):
        return "signed_token"
    if path in {"/api/v1/portal/enter", "/api/v1/portal/logout", "/api/v1/portal/me"}:
        return "session_helper"
    if path.startswith("/api/v1/portal/workspaces/"):
        return "provider_workspace"
    if path.startswith("/api/v1/auth/"):
        # /auth/login, /auth/forgot-password, /auth/reset-password are
        # public-with-rate-limit; /auth/me and /auth/set-password are
        # authenticated_jwt. Disambiguate by path.
        if path in {"/api/v1/auth/login", "/api/v1/auth/forgot-password", "/api/v1/auth/reset-password"}:
            return "public_with_rate_limit"
        return "authenticated_jwt"
    if path == "/api/v1/submissions":
        return "local_or_internal_admin"
    if path == "/api/v1/metadata-dry-run/pdf":
        return "local_or_internal_admin"
    if path == "/api/v1/feedback":
        return "authenticated_jwt"
    return "UNKNOWN"


def main() -> None:
    rows = introspect()
    manifest: list[dict] = []
    for row in rows:
        gate = _gate_for(row["method"], row["path"], row["depends_on"])
        manifest.append(
            {
                "method": row["method"],
                "path": row["path"],
                "function": row["endpoint_qualname"],
                "router": row["router_module"],
                "file": row["endpoint_file"],
                "lineno": row["endpoint_lineno"],
                "gate": gate,
                **_DEFAULT_POLICY_FIELDS,
            }
        )

    _MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _MANIFEST_PATH.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "description": (
                    "Route policy manifest for the FastAPI backend. Every "
                    "route in app.api.v1 MUST have an entry here. The pytest "
                    "at tests/test_route_policy_manifest.py fails on (a) any "
                    "new route lacking a manifest entry, (b) any manifest "
                    "entry whose route no longer exists, and (c) any entry "
                    "with a TBD policy field. Edit by hand; do not "
                    "auto-regenerate after the M0 seed."
                ),
                "routes": manifest,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    sys.stdout.write(
        f"Wrote {len(manifest)} routes to {_MANIFEST_PATH.relative_to(_PROJECT_ROOT)}\n"
    )


if __name__ == "__main__":
    main()
