"""Tests for the provider legal-consent gate.

Phase 1 / Slice 1A — exercises ``POST /portal/workspaces/{id}/legal-consent``
end-to-end against the same in-memory SQLite engine ``test_portal`` uses.
The helpers from ``test_portal`` are re-imported so a single workspace
seed setup stays canonical.
"""

# ruff: noqa: F811 — ``api_client`` is a pytest fixture imported from
# ``tests.test_portal``; pytest discovers it by parameter name, which
# ruff interprets as a redefinition of the imported symbol. The pattern
# is the documented pytest workaround.

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.v1.portal import CURRENT_LEGAL_CONSENT_VERSION
from app.models import AuditLog, ProviderWorkspace
from tests.test_portal import (  # noqa: F401 — api_client is a fixture
    _setup_workspace_session,
    api_client,
)


def _testing_session_factory(api_client: TestClient):
    return api_client.app.state.testing_session  # type: ignore[attr-defined]


def test_consent_accept_persists_timestamp_and_version(
    api_client: TestClient,
) -> None:
    access = _setup_workspace_session(api_client)
    workspace_id = access["workspace_id"]

    response = api_client.post(
        f"/api/v1/portal/workspaces/{workspace_id}/legal-consent",
        headers={"user-agent": "checkwise-tests/legal-consent/1.0"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["workspace_id"] == workspace_id
    assert body["legal_consent_version"] == CURRENT_LEGAL_CONSENT_VERSION
    assert body["legal_consent_accepted_at"]

    # Workspace row reflects acceptance.
    factory = _testing_session_factory(api_client)
    db = factory()
    try:
        workspace = db.get(ProviderWorkspace, workspace_id)
        assert workspace is not None
        assert workspace.legal_consent_accepted_at is not None
        assert workspace.legal_consent_version == CURRENT_LEGAL_CONSENT_VERSION
    finally:
        db.close()


def test_consent_accept_writes_audit_log_with_metadata(
    api_client: TestClient,
) -> None:
    access = _setup_workspace_session(api_client)
    workspace_id = access["workspace_id"]

    response = api_client.post(
        f"/api/v1/portal/workspaces/{workspace_id}/legal-consent",
        headers={
            "user-agent": "checkwise-tests/legal-consent/1.0",
            "x-forwarded-for": "203.0.113.42, 10.0.0.1",
        },
    )
    assert response.status_code == 200, response.text

    factory = _testing_session_factory(api_client)
    db = factory()
    try:
        events = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "provider.legal_consent_accepted",
                AuditLog.entity_id == workspace_id,
            )
            .all()
        )
        assert len(events) == 1
        event = events[0]
        assert event.entity_type == "provider_workspace"
        assert event.actor_type == "provider"
        # Audit metadata captures the version + raw IP + user-agent for
        # forensic linkage. The first hop in X-Forwarded-For wins so a
        # proxy address doesn't mask the real client.
        assert event.event_metadata is not None
        assert event.event_metadata["version"] == CURRENT_LEGAL_CONSENT_VERSION
        assert event.event_metadata["ip"] == "203.0.113.42"
        assert (
            event.event_metadata["user_agent"]
            == "checkwise-tests/legal-consent/1.0"
        )
        assert event.after is not None
        assert (
            event.after["legal_consent_version"]
            == CURRENT_LEGAL_CONSENT_VERSION
        )
    finally:
        db.close()


def test_consent_accept_is_idempotent(api_client: TestClient) -> None:
    access = _setup_workspace_session(api_client)
    workspace_id = access["workspace_id"]

    first = api_client.post(
        f"/api/v1/portal/workspaces/{workspace_id}/legal-consent"
    )
    assert first.status_code == 200
    first_at = first.json()["legal_consent_accepted_at"]

    second = api_client.post(
        f"/api/v1/portal/workspaces/{workspace_id}/legal-consent"
    )
    assert second.status_code == 200
    # Timestamp must not move on idempotent re-accept.
    assert second.json()["legal_consent_accepted_at"] == first_at

    # And only ONE audit row exists.
    factory = _testing_session_factory(api_client)
    db = factory()
    try:
        count = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "provider.legal_consent_accepted",
                AuditLog.entity_id == workspace_id,
            )
            .count()
        )
        assert count == 1
    finally:
        db.close()


def test_consent_surfaced_on_workspace_summary(api_client: TestClient) -> None:
    access = _setup_workspace_session(api_client)
    workspace_id = access["workspace_id"]

    # Before consent: /me reflects un-accepted state.
    me_before = api_client.get("/api/v1/portal/me").json()
    assert me_before["legal_consent_accepted_at"] is None
    assert me_before["legal_consent_version"] is None

    api_client.post(
        f"/api/v1/portal/workspaces/{workspace_id}/legal-consent"
    )

    # After consent: /me reflects accepted state with version.
    me_after = api_client.get("/api/v1/portal/me").json()
    assert me_after["legal_consent_accepted_at"]
    assert me_after["legal_consent_version"] == CURRENT_LEGAL_CONSENT_VERSION


def test_consent_rejects_cross_tenant(api_client: TestClient) -> None:
    """A workspace owner cannot accept consent on someone else's workspace.

    Tenant guard is enforced by ``current_portal_workspace`` — the path
    workspace_id is matched against the resolved workspace, so a
    mismatched id returns 404 (never 200 from the wrong row).
    """
    access = _setup_workspace_session(api_client)

    # Mint a second user owning a different workspace, but keep the
    # first user's cookie set on api_client. The second workspace's id
    # must not be acceptable from the first user's session.
    second_access = _setup_workspace_session(
        api_client,
        payload={
            "client_name": "Cliente Piloto CheckWise",
            "filial_name": "Filial Sur",
            "vendor_name": "Otro Proveedor SA",
            "vendor_rfc": "OTR250101AB1",
            "persona_type": "moral",
            "contract_reference": "CTR-002",
        },
    )
    # The second _setup_workspace_session call left ``api_client`` logged
    # in as the second user. Re-login as the first user by replaying
    # /portal/enter with their token? Simpler: use the second user's
    # session to try to accept consent on the FIRST workspace id.
    cross_response = api_client.post(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/legal-consent",
    )
    # ``current_portal_workspace`` rejects a path id that doesn't match
    # the resolved session workspace.
    assert cross_response.status_code in (403, 404), cross_response.text
    # Sanity: the second user's OWN workspace consent still works.
    own_response = api_client.post(
        f"/api/v1/portal/workspaces/{second_access['workspace_id']}/legal-consent",
    )
    assert own_response.status_code == 200, own_response.text


def test_consent_version_bump_writes_new_audit_row(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slice 1B — a document version bump invalidates the prior accept.

    When ``CURRENT_LEGAL_CONSENT_VERSION`` advances from ``v0-draft`` to
    a new value, a returning provider's next POST must NOT be treated
    as idempotent. The workspace row + a fresh audit event must record
    the re-acceptance at the new version, with ``before`` carrying the
    prior state so the audit trail tells the full story.
    """
    import app.api.v1.portal as portal_module

    access = _setup_workspace_session(api_client)
    workspace_id = access["workspace_id"]

    first = api_client.post(
        f"/api/v1/portal/workspaces/{workspace_id}/legal-consent"
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["legal_consent_version"] == "v0-draft"
    first_at = first_body["legal_consent_accepted_at"]

    # Simulate the legal team republishing the document set.
    monkeypatch.setattr(portal_module, "CURRENT_LEGAL_CONSENT_VERSION", "v1-test")

    second = api_client.post(
        f"/api/v1/portal/workspaces/{workspace_id}/legal-consent"
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["legal_consent_version"] == "v1-test"
    # Timestamp MUST advance — this is a fresh acceptance, not idempotent.
    assert second_body["legal_consent_accepted_at"] != first_at

    # Two audit rows total: v0-draft accept + v1-test re-accept. The
    # second carries ``before.legal_consent_version="v0-draft"`` so a
    # forensic reader can replay the sequence.
    factory = _testing_session_factory(api_client)
    db = factory()
    try:
        events = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "provider.legal_consent_accepted",
                AuditLog.entity_id == workspace_id,
            )
            .order_by(AuditLog.created_at.asc())
            .all()
        )
        assert len(events) == 2
        first_event, second_event = events
        assert first_event.before is None
        assert (
            first_event.event_metadata["version"] == "v0-draft"
        )
        assert second_event.before == {
            "legal_consent_accepted_at": first_at,
            "legal_consent_version": "v0-draft",
        }
        assert second_event.event_metadata["version"] == "v1-test"
        assert second_event.event_metadata["previous_version"] == "v0-draft"
    finally:
        db.close()


def test_consent_surfaces_current_version_on_summary(
    api_client: TestClient,
) -> None:
    """Slice 1B — ``/me`` carries the canonical current version so the
    frontend can compute the version-mismatch arm of the gate without
    hardcoding the version client-side."""
    _setup_workspace_session(api_client)
    body = api_client.get("/api/v1/portal/me").json()
    assert body["current_legal_consent_version"] == "v0-draft"
