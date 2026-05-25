"""M0 — Route policy manifest CI gate.

Per the 2026-05-25 sale-readiness audit and the parallel backend
hardening pass, every FastAPI route under ``/api/v1/*`` must carry
an explicit policy entry in
``app/security/route_policy_manifest.json``. The entry declares:

- ``gate`` — which auth/role/tenant dependency protects the route.
- ``tenant_rule`` — how tenant boundaries are enforced (or why
  none is needed).
- ``audit_rule`` — whether mutations write an ``audit_log`` row.
- ``rate_limit_rule`` — which limiter applies (or "none").
- ``error_lang`` — Spanish coverage of user-facing errors.

This test fails when:

1. A new route ships without an entry in the manifest (so any PR
   that introduces an endpoint must consciously declare its policy).
2. The manifest carries an entry whose route has been deleted (so
   stale policy doesn't drift after a refactor).
3. Any entry still carries a ``TBD —`` placeholder in a required
   field (so the manifest cannot be merged half-filled).
4. Any entry's classified ``gate`` no longer matches the live
   route's introspected dependencies (so a refactor that downgrades
   a route's gate is caught at CI).

Run ``python -m scripts.seed_route_policy_manifest`` to regenerate
the manifest with the latest route list, then re-fill any policy
fields a new entry requires.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.introspect_routes import introspect

_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "security"
    / "route_policy_manifest.json"
)

_REQUIRED_POLICY_FIELDS = (
    "gate",
    "tenant_rule",
    "audit_rule",
    "rate_limit_rule",
    "error_lang",
)

_TBD_PREFIX = "TBD —"

# Canonical set of permitted ``gate`` values. Reject typos.
_ALLOWED_GATES = frozenset(
    {
        "internal_admin",
        "client_admin_or_admin",
        "reviewer_or_admin",
        "provider_workspace",
        "authenticated_jwt",
        "local_or_internal_admin",
        "public_health",
        "public_catalog",
        "public_with_rate_limit",
        "signed_token",
        "session_helper",
    }
)


def _load_manifest() -> dict:
    assert _MANIFEST_PATH.exists(), (
        f"Route policy manifest not found at {_MANIFEST_PATH}. "
        "Run `python -m scripts.seed_route_policy_manifest` from "
        "apps/api to seed it."
    )
    return json.loads(_MANIFEST_PATH.read_text())


def _manifest_index(manifest: dict) -> dict[tuple[str, str], dict]:
    return {(row["method"], row["path"]): row for row in manifest["routes"]}


def _live_route_index() -> dict[tuple[str, str], dict]:
    return {(row["method"], row["path"]): row for row in introspect()}


def test_every_live_route_has_a_manifest_entry() -> None:
    """Catches: someone added a new endpoint without classifying it."""
    manifest = _manifest_index(_load_manifest())
    live = _live_route_index()
    missing = sorted(set(live) - set(manifest))
    assert not missing, (
        "These live routes have NO entry in "
        "app/security/route_policy_manifest.json. Add them with the "
        "right gate / tenant_rule / audit_rule / rate_limit_rule / "
        "error_lang. Run `python -m scripts.seed_route_policy_manifest` "
        "to regenerate the boilerplate, then fill the TBD fields.\n"
        + "\n".join(f"  {m:6} {p}" for m, p in missing)
    )


def test_no_stale_manifest_entries() -> None:
    """Catches: a route was removed but the manifest entry remained."""
    manifest = _manifest_index(_load_manifest())
    live = _live_route_index()
    stale = sorted(set(manifest) - set(live))
    assert not stale, (
        "These manifest entries point at routes that no longer exist "
        "in the FastAPI app. Remove them from "
        "app/security/route_policy_manifest.json or restore the route.\n"
        + "\n".join(f"  {m:6} {p}" for m, p in stale)
    )


def test_no_tbd_policy_fields() -> None:
    """Catches: a manifest row was added without filling the policy."""
    manifest = _load_manifest()
    incomplete: list[str] = []
    for row in manifest["routes"]:
        key = f"{row['method']:6} {row['path']}"
        for field in _REQUIRED_POLICY_FIELDS:
            value = (row.get(field) or "").strip()
            if not value:
                incomplete.append(f"{key} | field='{field}' is empty")
            elif value.startswith(_TBD_PREFIX):
                incomplete.append(f"{key} | field='{field}' still starts with 'TBD —'")
    assert not incomplete, (
        "These manifest entries have unfilled policy fields. Edit "
        "app/security/route_policy_manifest.json and replace every "
        "TBD value with the real policy.\n" + "\n".join(f"  {x}" for x in incomplete)
    )


def test_every_gate_value_is_recognised() -> None:
    """Catches: typos like 'internal-admin' or 'admin' in the gate field."""
    manifest = _load_manifest()
    unknown_gates: list[tuple[str, str, str]] = []
    for row in manifest["routes"]:
        gate = (row.get("gate") or "").strip()
        if gate not in _ALLOWED_GATES:
            unknown_gates.append((row["method"], row["path"], gate))
    assert not unknown_gates, (
        "These manifest entries declare a gate value that isn't in "
        "the canonical set. Fix the typo or add the new gate label "
        "to _ALLOWED_GATES in this test (then update the docs).\n"
        + "\n".join(f"  {m:6} {p} | gate={g!r}" for m, p, g in unknown_gates)
    )


def test_classified_gate_matches_function_dependencies() -> None:
    """Catches: a refactor downgrades a route's gate without updating
    the manifest.

    Compares the manifest's ``gate`` field against the dependency set
    introspected from the live FastAPI app. The check is one-way: if
    the function uses ``AdminUser``, the manifest MUST say
    ``internal_admin``. The manifest may LEGITIMATELY tighten or
    annotate the live signature with additional context (e.g.
    `signed_token` for a public-shaped route gated only by a token in
    the path).
    """
    manifest = _manifest_index(_load_manifest())
    mismatches: list[str] = []
    for (method, path), live_row in _live_route_index().items():
        manifest_row = manifest.get((method, path))
        if manifest_row is None:
            continue  # caught by test_every_live_route_has_a_manifest_entry
        declared = manifest_row.get("gate", "")
        deps = set(live_row["depends_on"])
        expected = _expected_gate_from_deps(deps, path)
        if expected is None:
            continue  # detector wasn't confident; trust manifest
        if expected != declared:
            mismatches.append(
                f"{method:6} {path} | manifest gate={declared!r}, "
                f"introspected deps suggest {expected!r} (deps={sorted(deps)})"
            )
    assert not mismatches, (
        "Manifest gate values diverge from introspected function deps. "
        "Either update the manifest to match the new dependency, or "
        "intentionally annotate the row with an explanatory ``notes`` "
        "field and add the path to the EXCEPT list in this test.\n"
        + "\n".join(f"  {m}" for m in mismatches)
    )


def _expected_gate_from_deps(deps: set[str], path: str) -> str | None:
    """Best-effort inverse of the seed script's classifier.

    Returns ``None`` when the detector cannot be confident — for
    example, paths that match no rule (in which case the test trusts
    the manifest).
    """
    if "AdminUser" in deps:
        return "internal_admin"
    if "ReviewerDep" in deps:
        return "reviewer_or_admin"
    if "ClientUser" in deps:
        return "client_admin_or_admin"
    if "current_portal_workspace" in deps:
        return "provider_workspace"
    if "require_local_or_internal_admin" in deps:
        return "local_or_internal_admin"
    if {"get_current_user", "CurrentUser"} & deps:
        return "authenticated_jwt"
    if path.startswith("/api/v1/health"):
        return "public_health"
    return None
