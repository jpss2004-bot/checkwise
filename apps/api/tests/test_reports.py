"""Phase 3.1 — Reports backend tests.

Covers the entity-level CRUD endpoints:
    POST /api/v1/reports
    GET  /api/v1/reports
    GET  /api/v1/reports/{id}
    PATCH /api/v1/reports/{id}
    POST /api/v1/reports/{id}/versions
    GET  /api/v1/reports/{id}/versions
    GET  /api/v1/reports/{id}/versions/{n}

Test discipline:
- Happy path per endpoint.
- Tenant isolation per endpoint: a user in org A cannot see / mutate a
  report owned by org B. Internal admins can.
- Scope rule: non-internal_only audience requires client_id or
  vendor_id.

AI / streaming / conversation / share / export endpoints are not in
3.1; they get their own tests in later sub-phases.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Client,
    Membership,
    Organization,
    Report,
    ReportVersion,
    User,
    Vendor,
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


# ─── Test helpers ────────────────────────────────────────────────


def _seed_user(
    db_factory,
    *,
    email: str,
    role: str | None,
    org_kind: str = "internal",
    org_name: str = "Test Org",
) -> tuple[str, str, str | None]:
    """Returns (password, email, organization_id).

    ``role=None`` produces a user with no memberships.
    """
    db = db_factory()
    try:
        password = "ReportsTest!2026"
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name="Reports Test",
            status="active",
        )
        db.add(user)
        db.flush()
        org_id: str | None = None
        if role is not None:
            org = Organization(name=org_name, kind=org_kind)
            db.add(org)
            db.flush()
            db.add(
                Membership(
                    user_id=user.id,
                    organization_id=org.id,
                    role=role,
                    status="active",
                )
            )
            org_id = org.id
        db.commit()
        return password, user.email, org_id
    finally:
        db.close()


def _login(api_client: TestClient, email: str, password: str) -> str:
    resp = api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _admin_token(api_client, db_factory) -> str:
    pw, email, _ = _seed_user(
        db_factory, email="adm@reports.test", role="operations_admin"
    )
    return _login(api_client, email, pw)


def _client_admin(api_client, db_factory, org_name: str) -> tuple[str, str]:
    """Returns (token, organization_id) for a client_admin in a new org."""
    pw, email, org_id = _seed_user(
        db_factory,
        email=f"{org_name.lower().replace(' ', '_')}@reports.test",
        role="client_admin",
        org_kind="client",
        org_name=org_name,
    )
    assert org_id is not None
    return _login(api_client, email, pw), org_id


def _seed_client_row(db_factory, name: str) -> str:
    db = db_factory()
    try:
        c = Client(name=name)
        db.add(c)
        db.commit()
        return c.id
    finally:
        db.close()


def _seed_vendor_row(
    db_factory, *, client_id: str, name: str, rfc: str = "VDR000101AA0"
) -> str:
    db = db_factory()
    try:
        v = Vendor(client_id=client_id, name=name, rfc=rfc)
        db.add(v)
        db.commit()
        return v.id
    finally:
        db.close()


# ─── Auth / permissions ──────────────────────────────────────────


def test_post_report_rejects_unauthenticated(api_client: TestClient) -> None:
    resp = api_client.post(
        "/api/v1/reports",
        json={"title": "x", "audience": "internal_only"},
    )
    assert resp.status_code == 401


def test_list_reports_rejects_unauthenticated(api_client: TestClient) -> None:
    resp = api_client.get("/api/v1/reports")
    assert resp.status_code == 401


# ─── Happy paths ────────────────────────────────────────────────


def test_create_internal_report_returns_v1(api_client: TestClient, db_factory) -> None:
    token = _admin_token(api_client, db_factory)
    resp = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={
            "title": "Resumen REPSE mayo 2026",
            "description": "Cobertura mensual",
            "audience": "internal_only",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "Resumen REPSE mayo 2026"
    assert body["audience"] == "internal_only"
    assert body["status"] == "draft"
    assert body["current_version_id"] is not None
    assert body["current_version"]["version_number"] == 1
    assert body["current_version"]["generated_by"] == "user"
    assert body["current_version"]["content_json"] == {
        "schema_version": 1,
        "blocks": [],
        "global": {},
    }


def test_create_with_initial_content_seeds_v1(api_client: TestClient, db_factory) -> None:
    token = _admin_token(api_client, db_factory)
    canvas = {
        "schema_version": 1,
        "blocks": [{"id": "b1", "type": "text", "config": {"heading": "hi"}}],
        "global": {"period": "2026-M05"},
    }
    resp = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={
            "title": "Custom",
            "audience": "internal_only",
            "initial_content_json": canvas,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["current_version"]["content_json"] == canvas


def test_get_report_returns_latest_version(api_client: TestClient, db_factory) -> None:
    token = _admin_token(api_client, db_factory)
    created = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={"title": "T", "audience": "internal_only"},
    ).json()
    report_id = created["id"]
    resp = api_client.get(f"/api/v1/reports/{report_id}", headers=_h(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == report_id
    assert body["current_version"]["version_number"] == 1


def test_list_reports_returns_visible_only(api_client: TestClient, db_factory) -> None:
    admin = _admin_token(api_client, db_factory)
    client_a_tok, client_a_org = _client_admin(api_client, db_factory, "Cliente A")
    client_b_tok, client_b_org = _client_admin(api_client, db_factory, "Cliente B")
    client_a_row = _seed_client_row(db_factory, "Cliente A SA")
    client_b_row = _seed_client_row(db_factory, "Cliente B SA")

    # Admin creates one report per client org (specifying organization_id
    # since admin has multiple orgs available).
    r_a = api_client.post(
        f"/api/v1/reports?organization_id={client_a_org}",
        headers=_h(admin),
        json={
            "title": "A report",
            "audience": "client_facing",
            "client_id": client_a_row,
        },
    )
    assert r_a.status_code == 201, r_a.text
    r_b = api_client.post(
        f"/api/v1/reports?organization_id={client_b_org}",
        headers=_h(admin),
        json={
            "title": "B report",
            "audience": "client_facing",
            "client_id": client_b_row,
        },
    )
    assert r_b.status_code == 201, r_b.text

    # client_a sees only their own.
    list_a = api_client.get("/api/v1/reports", headers=_h(client_a_tok)).json()
    titles_a = {item["title"] for item in list_a["items"]}
    assert titles_a == {"A report"}

    # client_b sees only theirs.
    list_b = api_client.get("/api/v1/reports", headers=_h(client_b_tok)).json()
    titles_b = {item["title"] for item in list_b["items"]}
    assert titles_b == {"B report"}

    # admin sees both.
    list_admin = api_client.get("/api/v1/reports", headers=_h(admin)).json()
    titles_admin = {item["title"] for item in list_admin["items"]}
    assert titles_admin == {"A report", "B report"}


def test_get_other_tenant_report_returns_404(
    api_client: TestClient, db_factory
) -> None:
    admin = _admin_token(api_client, db_factory)
    other_tok, other_org = _client_admin(api_client, db_factory, "Otro")
    client_row = _seed_client_row(db_factory, "Cliente Otro")

    created = api_client.post(
        f"/api/v1/reports?organization_id={other_org}",
        headers=_h(admin),
        json={"title": "Owned by Other", "audience": "client_facing", "client_id": client_row},
    ).json()
    report_id = created["id"]

    # First-party (other org) can read.
    own = api_client.get(f"/api/v1/reports/{report_id}", headers=_h(other_tok))
    assert own.status_code == 200

    # Third-party (a different client_admin) gets 404 (indistinguishable
    # from not-found by design — no enumeration).
    third_tok, _ = _client_admin(api_client, db_factory, "Tercero")
    third = api_client.get(f"/api/v1/reports/{report_id}", headers=_h(third_tok))
    assert third.status_code == 404


def test_patch_report_updates_metadata(api_client: TestClient, db_factory) -> None:
    token = _admin_token(api_client, db_factory)
    created = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={"title": "Old", "audience": "internal_only"},
    ).json()
    report_id = created["id"]
    resp = api_client.patch(
        f"/api/v1/reports/{report_id}",
        headers=_h(token),
        json={"title": "New title", "status": "active"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "New title"
    assert body["status"] == "active"


def test_patch_report_other_tenant_returns_404(
    api_client: TestClient, db_factory
) -> None:
    admin = _admin_token(api_client, db_factory)
    target_tok, target_org = _client_admin(api_client, db_factory, "Target")
    client_row = _seed_client_row(db_factory, "T")
    created = api_client.post(
        f"/api/v1/reports?organization_id={target_org}",
        headers=_h(admin),
        json={"title": "Owned by Target", "audience": "client_facing", "client_id": client_row},
    ).json()
    report_id = created["id"]

    # Different tenant cannot patch.
    other_tok, _ = _client_admin(api_client, db_factory, "Outsider")
    resp = api_client.patch(
        f"/api/v1/reports/{report_id}",
        headers=_h(other_tok),
        json={"title": "Hijack"},
    )
    assert resp.status_code == 404


def test_create_version_appends_with_incremented_number(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    created = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={"title": "T", "audience": "internal_only"},
    ).json()
    report_id = created["id"]

    resp = api_client.post(
        f"/api/v1/reports/{report_id}/versions",
        headers=_h(token),
        json={
            "content_json": {"schema_version": 1, "blocks": [], "global": {}},
            "label": "manual save",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["version_number"] == 2

    listing = api_client.get(
        f"/api/v1/reports/{report_id}/versions", headers=_h(token)
    ).json()
    assert listing["total"] == 2
    # Descending order.
    assert listing["items"][0]["version_number"] == 2
    assert listing["items"][1]["version_number"] == 1


def test_get_specific_version(api_client: TestClient, db_factory) -> None:
    token = _admin_token(api_client, db_factory)
    created = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={"title": "T", "audience": "internal_only"},
    ).json()
    report_id = created["id"]
    resp = api_client.get(
        f"/api/v1/reports/{report_id}/versions/1", headers=_h(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["version_number"] == 1
    assert body["content_json"]["schema_version"] == 1


def test_get_missing_version_returns_404(api_client: TestClient, db_factory) -> None:
    token = _admin_token(api_client, db_factory)
    created = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={"title": "T", "audience": "internal_only"},
    ).json()
    report_id = created["id"]
    resp = api_client.get(
        f"/api/v1/reports/{report_id}/versions/99", headers=_h(token)
    )
    assert resp.status_code == 404


# ─── Validation rules ───────────────────────────────────────────


def test_client_facing_without_scope_rejected(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    resp = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={"title": "T", "audience": "client_facing"},
    )
    assert resp.status_code == 422
    assert "client_id" in resp.json()["detail"]


def test_vendor_facing_with_vendor_scope_ok(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    client_row = _seed_client_row(db_factory, "ClientForVendor")
    vendor_row = _seed_vendor_row(
        db_factory, client_id=client_row, name="Distribuidora Demo"
    )
    resp = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={
            "title": "Per-vendor",
            "audience": "vendor_facing",
            "vendor_id": vendor_row,
        },
    )
    assert resp.status_code == 201


def test_user_with_no_membership_cannot_create(
    api_client: TestClient, db_factory
) -> None:
    pw, email, _ = _seed_user(db_factory, email="orphan@reports.test", role=None)
    token = _login(api_client, email, pw)
    resp = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={"title": "x", "audience": "internal_only"},
    )
    assert resp.status_code == 403


def test_db_state_after_create(api_client: TestClient, db_factory) -> None:
    """Sanity: created report + version persisted with the right shape."""
    token = _admin_token(api_client, db_factory)
    created = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={"title": "T", "audience": "internal_only"},
    ).json()

    db = db_factory()
    try:
        report = db.scalar(select(Report).where(Report.id == created["id"]))
        assert report is not None
        assert report.title == "T"
        assert report.current_version_id is not None

        versions = list(
            db.scalars(select(ReportVersion).where(ReportVersion.report_id == report.id))
        )
        assert len(versions) == 1
        assert versions[0].version_number == 1
        assert versions[0].generated_by == "user"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# CW-DOS-001 — report content size caps (write-time)
# ---------------------------------------------------------------------------


def _new_report(api_client: TestClient, token: str) -> str:
    return api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={"title": "T", "audience": "internal_only"},
    ).json()["id"]


def test_create_version_rejects_oversized_content_json(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    report_id = _new_report(api_client, token)
    huge = "A" * (settings.REPORT_CONTENT_MAX_BYTES + 1000)
    resp = api_client.post(
        f"/api/v1/reports/{report_id}/versions",
        headers=_h(token),
        json={"content_json": {"blocks": [{"type": "text", "data": {"text": huge}}]}},
    )
    assert resp.status_code == 413, resp.text
    # Not persisted — only the seed v1 exists.
    listing = api_client.get(
        f"/api/v1/reports/{report_id}/versions", headers=_h(token)
    ).json()
    assert listing["total"] == 1


def test_create_version_rejects_too_many_blocks(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    report_id = _new_report(api_client, token)
    blocks = [{"type": "divider"} for _ in range(settings.REPORT_CONTENT_MAX_BLOCKS + 1)]
    resp = api_client.post(
        f"/api/v1/reports/{report_id}/versions",
        headers=_h(token),
        json={"content_json": {"blocks": blocks}},
    )
    assert resp.status_code == 413, resp.text


def test_create_version_rejects_deep_nesting(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    report_id = _new_report(api_client, token)
    nested: dict = {"x": 1}
    for _ in range(settings.REPORT_CONTENT_MAX_DEPTH + 5):
        nested = {"x": nested}
    resp = api_client.post(
        f"/api/v1/reports/{report_id}/versions",
        headers=_h(token),
        json={"content_json": nested},
    )
    assert resp.status_code == 413, resp.text


def test_create_version_rejects_oversized_block_text(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    report_id = _new_report(api_client, token)
    # Per-block text over the cap, but total bytes under the byte cap.
    text = "A" * (settings.REPORT_CONTENT_MAX_TEXT_PER_BLOCK + 100)
    resp = api_client.post(
        f"/api/v1/reports/{report_id}/versions",
        headers=_h(token),
        json={"content_json": {"blocks": [{"type": "text", "data": {"text": text}}]}},
    )
    assert resp.status_code == 413, resp.text


def test_create_version_accepts_normal_content(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    report_id = _new_report(api_client, token)
    resp = api_client.post(
        f"/api/v1/reports/{report_id}/versions",
        headers=_h(token),
        json={
            "content_json": {
                "schema_version": 1,
                "blocks": [{"type": "text", "data": {"text": "ok"}}],
                "global": {},
            }
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["version_number"] == 2


def test_post_report_rejects_oversized_initial_content(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    huge = "A" * (settings.REPORT_CONTENT_MAX_BYTES + 1000)
    resp = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={
            "title": "T",
            "audience": "internal_only",
            "initial_content_json": {
                "blocks": [{"type": "text", "data": {"text": huge}}]
            },
        },
    )
    assert resp.status_code == 413, resp.text
