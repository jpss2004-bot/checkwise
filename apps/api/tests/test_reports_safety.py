"""Unit tests for the vendor-scope safety helper used by provider blocks.

Covers ``app.services.reports.blocks._safety.assert_workspace_scope`` —
the redundant defence-in-depth check every vendor-only block fetcher
must call before issuing DB queries (see P1.1 in
docs/PROVIDER_REPORTS_REDESIGN_PLAN.md).

These tests run without a DB or HTTP fixture; the helper only
reasons over the ``ReportActor`` + ``ReportScope`` value objects.
"""

from __future__ import annotations

import pytest

from app.constants.reports import ReportAudience
from app.services.report_service import ReportActor, ReportPermissionError
from app.services.reports.blocks._safety import assert_workspace_scope
from app.services.reports.context import ReportScope


def _scope(
    audience: ReportAudience,
    *,
    vendor_id: str | None = "vend-a",
    client_id: str | None = "client-a",
) -> ReportScope:
    return ReportScope(
        organization_id="org-a",
        audience=audience,
        client_id=client_id,
        vendor_id=vendor_id,
        period="2026-M05",
    )


def _provider_actor(vendor_id: str = "vend-a") -> ReportActor:
    return ReportActor(
        user_id="user-1",
        organization_ids=("org-a",),
        roles=(),
        workspace_vendor_id=vendor_id,
        workspace_client_id="client-a",
    )


def _internal_actor() -> ReportActor:
    return ReportActor(
        user_id="user-2",
        organization_ids=("internal-org",),
        roles=("operations_admin",),
    )


def _client_admin_actor() -> ReportActor:
    return ReportActor(
        user_id="user-3",
        organization_ids=("client-org",),
        roles=("client_admin",),
    )


def test_helper_is_noop_for_non_vendor_facing_audience() -> None:
    """The helper only enforces vendor scope. Other audiences fall
    through to the standard RBAC; this helper must not raise on them.
    """
    actor = _provider_actor()
    for aud in (
        ReportAudience.INTERNAL_ONLY,
        ReportAudience.CLIENT_FACING,
        ReportAudience.EXTERNAL_SIGNED,
    ):
        assert_workspace_scope(actor=actor, scope=_scope(aud))


def test_helper_passes_when_provider_scope_matches_workspace() -> None:
    """Workspace owner reading vendor_facing data scoped to their
    own vendor — the happy path."""
    actor = _provider_actor(vendor_id="vend-a")
    scope = _scope(ReportAudience.VENDOR_FACING, vendor_id="vend-a")
    # No exception = pass.
    assert_workspace_scope(actor=actor, scope=scope)


def test_helper_raises_on_cross_vendor_mismatch() -> None:
    """Workspace owner attempting to read another vendor's data —
    the case the helper exists to catch when a block fetcher is asked
    to run against an attacker-supplied vendor_id."""
    actor = _provider_actor(vendor_id="vend-a")
    scope = _scope(ReportAudience.VENDOR_FACING, vendor_id="vend-b")
    with pytest.raises(ReportPermissionError):
        assert_workspace_scope(actor=actor, scope=scope)


def test_helper_raises_on_missing_vendor_id() -> None:
    """A vendor_facing scope without a vendor_id is structurally
    invalid — refuse early instead of letting the fetcher try to query
    on None."""
    actor = _provider_actor()
    scope = _scope(ReportAudience.VENDOR_FACING, vendor_id=None)
    with pytest.raises(ReportPermissionError):
        assert_workspace_scope(actor=actor, scope=scope)


def test_helper_bypasses_for_internal_staff() -> None:
    """Internal staff may author reports for any vendor. The helper
    must not block them even when the scope's vendor differs from
    their own (they have none)."""
    actor = _internal_actor()
    scope = _scope(ReportAudience.VENDOR_FACING, vendor_id="vend-any")
    assert_workspace_scope(actor=actor, scope=scope)


def test_helper_raises_for_client_admin_on_vendor_scope() -> None:
    """A client_admin is not a workspace owner and is not internal —
    they have no business reading vendor-facing block data, even within
    their own client. (Their normal RBAC already restricts them to
    client_facing audiences; this is the defence-in-depth layer.)"""
    actor = _client_admin_actor()
    scope = _scope(ReportAudience.VENDOR_FACING, vendor_id="vend-a")
    with pytest.raises(ReportPermissionError):
        assert_workspace_scope(actor=actor, scope=scope)
