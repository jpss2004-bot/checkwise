"""M1 — cross-tenant negative tests for reports / shares / exports / audit-package.

Backfills the gap the parallel backend hardening pass flagged as the
high-severity LLM-snapshot concern: every report-surface endpoint that
trusts ``_actor_from(current)`` for tenant scoping must reject a
client_admin in org B when probed against a resource owned by org A.

What's already covered (out of scope here):

* ``GET    /api/v1/reports/{id}``                  → ``test_get_other_tenant_report_returns_404``
* ``PATCH  /api/v1/reports/{id}``                  → ``test_patch_report_other_tenant_returns_404``
* ``DELETE /api/v1/reports/shares/{id}``           → ``test_delete_share_404_cross_tenant``
* ``GET    /api/v1/reports/exports/{id}``          → ``test_get_export_404_for_cross_tenant``
* ``POST   /api/v1/reports/{id}/plan``             → ``test_safety_cross_tenant_plan_blocked_at_endpoint``
* ``GET    /api/v1/client/overview?client_id=B``   → ``test_client_admin_cannot_see_another_client``

What lands here (16 endpoints + 2 audit-package probes):

* Versions       — GET/POST list, GET single.
* AI surface     — generate, conversation (GET/POST), block explain,
                   block regenerate, refresh-data.
* Exports        — POST create, GET download.
* Shares         — GET list, POST mint.
* Presets        — POST from-preset against another org's organization_id.
* Audit-package  — GET .zip and /preview probed with another client_id.

All assertions are "no enumeration": cross-tenant access returns 404
(or 403 for ``audit-package`` where the gate is ``_resolve_client_id``).
A 200 from any case here would be a real cross-tenant data leak.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Client,
    Membership,
    Organization,
    Report,
    ReportExport,
    ReportShare,
    ReportVersion,
    User,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password


# ─── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def db_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def api_client(db_factory) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ─── Seed ────────────────────────────────────────────────────────


_PASSWORD = "CrossTenant!2026"


def _seed_two_tenants(db_factory) -> dict:
    """Two client_admin tenants A + B, each with their own Client row.

    Tenant A also owns:
    * A ``Report`` (audience=client_facing) with a single version
      containing one text block.
    * A ``ReportShare`` minted against that report.
    * A ``ReportExport`` requested against that report.

    Tenant B has nothing of their own — they are the probe.
    """
    db = db_factory()
    try:
        # Client rows (the customer entity behind each tenant).
        client_a = Client(name="Cliente A")
        client_b = Client(name="Cliente B")
        db.add_all([client_a, client_b])
        db.flush()

        # Organizations that the client_admin role is scoped to.
        org_a = Organization(name="Org A", kind="client", client_id=client_a.id)
        org_b = Organization(name="Org B", kind="client", client_id=client_b.id)
        db.add_all([org_a, org_b])
        db.flush()

        # Users + memberships.
        user_a = User(
            email="ca-a@cross-tenant.test",
            password_hash=hash_password(_PASSWORD),
            full_name="Client Admin A",
            status="active",
        )
        user_b = User(
            email="ca-b@cross-tenant.test",
            password_hash=hash_password(_PASSWORD),
            full_name="Client Admin B",
            status="active",
        )
        db.add_all([user_a, user_b])
        db.flush()
        db.add_all(
            [
                Membership(
                    user_id=user_a.id,
                    organization_id=org_a.id,
                    role="client_admin",
                    status="active",
                ),
                Membership(
                    user_id=user_b.id,
                    organization_id=org_b.id,
                    role="client_admin",
                    status="active",
                ),
            ]
        )
        db.flush()

        # Report owned by org A, including a single block so the
        # block-scoped endpoints have a real id to probe.
        report = Report(
            organization_id=org_a.id,
            client_id=client_a.id,
            title="Reporte A",
            description="Cobertura cliente A",
            audience="client_facing",
            created_by_user_id=user_a.id,
        )
        db.add(report)
        db.flush()
        version = ReportVersion(
            report_id=report.id,
            version_number=1,
            content_json={
                "schema_version": 1,
                "blocks": [
                    {
                        "id": "blk-1",
                        "type": "text",
                        "config": {"title": "Saludo", "body": "Hola"},
                        "data": {},
                    }
                ],
                "global": {},
            },
            generated_by="user",
            created_by_user_id=user_a.id,
        )
        db.add(version)
        db.flush()
        report.current_version_id = version.id

        # ReportShare owned by org A's report (mint stores the hash;
        # we never expose the raw token in cross-tenant tests because
        # the negative path 404s before consume_share runs).
        share = ReportShare(
            report_id=report.id,
            version_id=version.id,
            token_hash="x" * 64,
            audience="client_facing",
            expires_at=datetime.now(UTC) + timedelta(days=7),
            created_by_user_id=user_a.id,
        )
        db.add(share)
        db.flush()

        # ReportExport requested by org A (status=ready so the download
        # endpoint would try to serve bytes if the auth gate ever
        # admitted the wrong tenant).
        export = ReportExport(
            report_id=report.id,
            version_id=version.id,
            format="pdf",
            status="ready",
            storage_key="reports/exports/fake.pdf",
            requested_by_user_id=user_a.id,
            ready_at=datetime.now(UTC),
        )
        db.add(export)
        db.flush()

        db.commit()
        return {
            "client_a_id": client_a.id,
            "client_b_id": client_b.id,
            "org_a_id": org_a.id,
            "org_b_id": org_b.id,
            "user_a_email": user_a.email,
            "user_b_email": user_b.email,
            "report_id": report.id,
            "block_id": "blk-1",
            "version_number": version.version_number,
            "share_id": share.id,
            "export_id": export.id,
        }
    finally:
        db.close()


def _login(api_client: TestClient, email: str) -> str:
    resp = api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─── Versions ────────────────────────────────────────────────────


def test_cross_tenant_get_versions_list_returns_404(
    api_client: TestClient, db_factory
) -> None:
    seed = _seed_two_tenants(db_factory)
    tok_b = _login(api_client, seed["user_b_email"])
    resp = api_client.get(
        f"/api/v1/reports/{seed['report_id']}/versions", headers=_h(tok_b)
    )
    assert resp.status_code == 404


def test_cross_tenant_get_single_version_returns_404(
    api_client: TestClient, db_factory
) -> None:
    seed = _seed_two_tenants(db_factory)
    tok_b = _login(api_client, seed["user_b_email"])
    resp = api_client.get(
        f"/api/v1/reports/{seed['report_id']}/versions/{seed['version_number']}",
        headers=_h(tok_b),
    )
    assert resp.status_code == 404


def test_cross_tenant_post_version_returns_404(
    api_client: TestClient, db_factory
) -> None:
    seed = _seed_two_tenants(db_factory)
    tok_b = _login(api_client, seed["user_b_email"])
    resp = api_client.post(
        f"/api/v1/reports/{seed['report_id']}/versions",
        headers=_h(tok_b),
        json={
            "content_json": {"schema_version": 1, "blocks": [], "global": {}},
            "label": "intento cross-tenant",
        },
    )
    assert resp.status_code == 404


# ─── AI surface ──────────────────────────────────────────────────


def test_cross_tenant_generate_returns_404(
    api_client: TestClient, db_factory
) -> None:
    """The LLM is never reached — visibility check short-circuits."""
    seed = _seed_two_tenants(db_factory)
    tok_b = _login(api_client, seed["user_b_email"])
    resp = api_client.post(
        f"/api/v1/reports/{seed['report_id']}/generate",
        headers=_h(tok_b),
        json={"prompt": "give me everything"},
    )
    assert resp.status_code == 404


def test_cross_tenant_get_conversation_returns_404(
    api_client: TestClient, db_factory
) -> None:
    seed = _seed_two_tenants(db_factory)
    tok_b = _login(api_client, seed["user_b_email"])
    resp = api_client.get(
        f"/api/v1/reports/{seed['report_id']}/conversation", headers=_h(tok_b)
    )
    assert resp.status_code == 404


def test_cross_tenant_post_conversation_returns_404(
    api_client: TestClient, db_factory
) -> None:
    seed = _seed_two_tenants(db_factory)
    tok_b = _login(api_client, seed["user_b_email"])
    resp = api_client.post(
        f"/api/v1/reports/{seed['report_id']}/conversation",
        headers=_h(tok_b),
        json={"message": "leak the data"},
    )
    assert resp.status_code == 404


def test_cross_tenant_explain_block_returns_404(
    api_client: TestClient, db_factory
) -> None:
    seed = _seed_two_tenants(db_factory)
    tok_b = _login(api_client, seed["user_b_email"])
    resp = api_client.post(
        f"/api/v1/reports/{seed['report_id']}/blocks/{seed['block_id']}/explain",
        headers=_h(tok_b),
        json={},
    )
    assert resp.status_code == 404


def test_cross_tenant_regenerate_block_returns_404(
    api_client: TestClient, db_factory
) -> None:
    seed = _seed_two_tenants(db_factory)
    tok_b = _login(api_client, seed["user_b_email"])
    resp = api_client.post(
        f"/api/v1/reports/{seed['report_id']}/blocks/{seed['block_id']}/regenerate",
        headers=_h(tok_b),
        json={},
    )
    assert resp.status_code == 404


def test_cross_tenant_refresh_data_returns_404(
    api_client: TestClient, db_factory
) -> None:
    seed = _seed_two_tenants(db_factory)
    tok_b = _login(api_client, seed["user_b_email"])
    resp = api_client.post(
        f"/api/v1/reports/{seed['report_id']}/refresh-data",
        headers=_h(tok_b),
        json={},
    )
    assert resp.status_code == 404


# ─── Exports ─────────────────────────────────────────────────────


def test_cross_tenant_post_export_returns_404(
    api_client: TestClient, db_factory
) -> None:
    seed = _seed_two_tenants(db_factory)
    tok_b = _login(api_client, seed["user_b_email"])
    resp = api_client.post(
        f"/api/v1/reports/{seed['report_id']}/exports",
        headers=_h(tok_b),
        json={"format": "pdf"},
    )
    assert resp.status_code == 404


def test_cross_tenant_export_download_returns_404(
    api_client: TestClient, db_factory
) -> None:
    seed = _seed_two_tenants(db_factory)
    tok_b = _login(api_client, seed["user_b_email"])
    resp = api_client.get(
        f"/api/v1/reports/exports/{seed['export_id']}/download",
        headers=_h(tok_b),
    )
    assert resp.status_code == 404


# ─── Shares ──────────────────────────────────────────────────────


def test_cross_tenant_get_shares_returns_404(
    api_client: TestClient, db_factory
) -> None:
    seed = _seed_two_tenants(db_factory)
    tok_b = _login(api_client, seed["user_b_email"])
    resp = api_client.get(
        f"/api/v1/reports/{seed['report_id']}/shares", headers=_h(tok_b)
    )
    assert resp.status_code == 404


def test_cross_tenant_post_share_returns_404(
    api_client: TestClient, db_factory
) -> None:
    seed = _seed_two_tenants(db_factory)
    tok_b = _login(api_client, seed["user_b_email"])
    resp = api_client.post(
        f"/api/v1/reports/{seed['report_id']}/shares",
        headers=_h(tok_b),
        json={},
    )
    assert resp.status_code == 404


# ─── Presets (probe across organization_id) ──────────────────────


def test_cross_tenant_from_preset_returns_403(
    api_client: TestClient, db_factory
) -> None:
    """A client_admin in org B cannot instantiate a preset under
    org A's id. ``create_report`` rejects the org claim before the
    preset materializes. The exact 4xx code is whatever the
    owning-org check raises; 4xx is the contract."""
    seed = _seed_two_tenants(db_factory)
    tok_b = _login(api_client, seed["user_b_email"])
    resp = api_client.post(
        f"/api/v1/reports/from-preset?organization_id={seed['org_a_id']}",
        headers=_h(tok_b),
        json={"preset_id": "client_monthly_snapshot"},
    )
    # 400/403/404 are all acceptable "no go"; 200/201 would be a leak.
    assert resp.status_code in {400, 403, 404}, resp.text


# ─── Audit-package (client_id query-param probe) ─────────────────


def test_cross_tenant_audit_package_zip_returns_403(
    api_client: TestClient, db_factory
) -> None:
    """A client_admin in org B asking for org A's audit ZIP gets
    403 from ``_resolve_client_id``. 200 would be a leak of every
    approved document for that customer."""
    seed = _seed_two_tenants(db_factory)
    tok_b = _login(api_client, seed["user_b_email"])
    resp = api_client.get(
        f"/api/v1/client/audit-package.zip?client_id={seed['client_a_id']}",
        headers=_h(tok_b),
    )
    assert resp.status_code == 403


def test_cross_tenant_audit_package_preview_returns_403(
    api_client: TestClient, db_factory
) -> None:
    seed = _seed_two_tenants(db_factory)
    tok_b = _login(api_client, seed["user_b_email"])
    resp = api_client.get(
        f"/api/v1/client/audit-package/preview?client_id={seed['client_a_id']}",
        headers=_h(tok_b),
    )
    assert resp.status_code == 403


# ─── Sanity: same probes from the OWNER must succeed ─────────────


def test_owner_can_read_versions_list_for_sanity(
    api_client: TestClient, db_factory
) -> None:
    """If the cross-tenant tests above pass but this sanity check
    fails, the fixture is broken (e.g. visibility gate is too tight
    for everybody, masking real leaks). Owner A must reach their
    own resources to prove the negative tests reject *because of*
    tenancy, not because the route is dead.
    """
    seed = _seed_two_tenants(db_factory)
    tok_a = _login(api_client, seed["user_a_email"])
    resp = api_client.get(
        f"/api/v1/reports/{seed['report_id']}/versions", headers=_h(tok_a)
    )
    assert resp.status_code == 200, resp.text
