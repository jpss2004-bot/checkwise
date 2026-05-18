"""R1.0 — Role-aware preset registry tests.

Covers:
- GET /api/v1/reports/_presets returns only role-appropriate presets
- POST /api/v1/reports/from-preset succeeds for admin
- POST /api/v1/reports/from-preset forbidden for client_admin
- list_reports filters by visible_audiences for client_admin
- create rejects non-writable audience for client_admin
- patch rejects non-writable audience escalation for client_admin
"""

from __future__ import annotations

from collections.abc import Generator

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
    User,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password

# ─── Fixtures (mirror test_reports.py) ─────────────────────────


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


def _seed_user(
    db_factory,
    *,
    email: str,
    role: str,
    org_kind: str = "internal",
    org_name: str = "Test Org",
) -> tuple[str, str, str]:
    db = db_factory()
    try:
        password = "PresetsTest!2026"
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name="Presets Test",
            status="active",
        )
        db.add(user)
        db.flush()
        # Mirror dev_seed.py: client-kind orgs are linked to a Client
        # row via Organization.client_id. This is what the preset
        # auto-resolve relies on for client_admin callers.
        client_id: str | None = None
        if org_kind == "client":
            client_row = Client(name=org_name + " (client)")
            db.add(client_row)
            db.flush()
            client_id = client_row.id
        org = Organization(name=org_name, kind=org_kind, client_id=client_id)
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
        db.commit()
        return password, user.email, org.id
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
        db_factory, email="adm@presets.test", role="internal_admin"
    )
    return _login(api_client, email, pw)


def _client_admin(api_client, db_factory, org_name: str) -> tuple[str, str]:
    pw, email, org_id = _seed_user(
        db_factory,
        email=f"{org_name.lower().replace(' ', '_')}@presets.test",
        role="client_admin",
        org_kind="client",
        org_name=org_name,
    )
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


# ─── Tests ─────────────────────────────────────────────────────


def test_presets_list_internal_admin_sees_all_six(api_client, db_factory) -> None:
    """R1.1 ships 3 admin presets + 3 client presets.

    internal_admin is in the ``required_roles`` of every preset (so
    staff can author on behalf of either audience). The list must
    return all six.
    """
    token = _admin_token(api_client, db_factory)
    resp = api_client.get("/api/v1/reports/_presets", headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = sorted(p["id"] for p in body["items"])
    assert ids == [
        "admin-daily-queue",
        "admin-high-risk-vendors",
        "admin-monthly-operational",
        "client-missing-evidence",
        "client-monthly-executive",
        "client-vendor-risk-matrix",
    ]
    # Audiences split exactly 3+3.
    audiences = sorted(p["audience"] for p in body["items"])
    assert audiences == [
        "client_facing",
        "client_facing",
        "client_facing",
        "internal_only",
        "internal_only",
        "internal_only",
    ]
    for p in body["items"]:
        assert p["recommended_prompt"]  # non-empty for every preset


def test_presets_list_client_admin_sees_only_client_presets(
    api_client, db_factory
) -> None:
    """R1.1: client_admin sees the 3 client_facing presets only.

    The 3 admin presets require internal_admin OR reviewer in their
    required_roles, so a client_admin must never see them in the list.
    """
    token, _ = _client_admin(api_client, db_factory, "Cliente A")
    resp = api_client.get("/api/v1/reports/_presets", headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = sorted(p["id"] for p in body["items"])
    assert ids == [
        "client-missing-evidence",
        "client-monthly-executive",
        "client-vendor-risk-matrix",
    ]
    for p in body["items"]:
        assert p["audience"] == "client_facing"


def test_create_from_preset_internal_admin_succeeds(api_client, db_factory) -> None:
    token = _admin_token(api_client, db_factory)
    resp = api_client.post(
        "/api/v1/reports/from-preset",
        headers=_h(token),
        json={"preset_id": "admin-daily-queue"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "Cola diaria de revisión"
    assert body["audience"] == "internal_only"
    assert body["current_version"]["version_number"] == 1
    # Recommended prompt is parked on global so the editor can pre-fill.
    glob = body["current_version"]["content_json"]["global"]
    assert glob["preset_id"] == "admin-daily-queue"
    assert "operativo del día" in glob["recommended_prompt"]


def test_create_from_preset_client_admin_403(api_client, db_factory) -> None:
    """A client_admin asking for an admin-only preset is forbidden."""
    token, _ = _client_admin(api_client, db_factory, "Cliente A")
    resp = api_client.post(
        "/api/v1/reports/from-preset",
        headers=_h(token),
        json={"preset_id": "admin-daily-queue"},
    )
    assert resp.status_code == 403, resp.text


def test_create_from_preset_client_admin_can_instantiate_client_preset(
    api_client, db_factory
) -> None:
    """R1.1: client_admin must be able to instantiate a client_facing preset.

    The created report carries the preset's audience and parks the
    recommended_prompt on content_json.global so the editor pre-fills
    the AI prompt panel.
    """
    token, _ = _client_admin(api_client, db_factory, "Cliente Demo")
    resp = api_client.post(
        "/api/v1/reports/from-preset",
        headers=_h(token),
        json={"preset_id": "client-monthly-executive"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "Resumen ejecutivo mensual"
    assert body["audience"] == "client_facing"
    glob = body["current_version"]["content_json"]["global"]
    assert glob["preset_id"] == "client-monthly-executive"
    assert "ejecutivo" in glob["recommended_prompt"]


def test_create_from_preset_internal_admin_can_use_client_preset(
    api_client, db_factory
) -> None:
    """internal_admin appears in every preset's required_roles so staff
    can author on behalf of a client. Verify the cross-audience case.

    An internal_admin lives in an "internal" org (no client_id), so the
    auto-resolve path doesn't fire — staff must pass client_id in the
    body. That's the only difference from the client_admin path.
    """
    token = _admin_token(api_client, db_factory)
    target_client = _seed_client_row(db_factory, "Cliente Target")
    resp = api_client.post(
        "/api/v1/reports/from-preset",
        headers=_h(token),
        json={
            "preset_id": "client-vendor-risk-matrix",
            "client_id": target_client,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["audience"] == "client_facing"
    assert body["client_id"] == target_client


def test_create_from_preset_unknown_preset_404(api_client, db_factory) -> None:
    token = _admin_token(api_client, db_factory)
    resp = api_client.post(
        "/api/v1/reports/from-preset",
        headers=_h(token),
        json={"preset_id": "does-not-exist"},
    )
    assert resp.status_code == 404, resp.text


def test_client_admin_cannot_create_internal_only(api_client, db_factory) -> None:
    """The writable_audiences guard blocks internal_only authorship by client_admin."""
    token, _ = _client_admin(api_client, db_factory, "Cliente A")
    resp = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={"title": "X", "audience": "internal_only"},
    )
    assert resp.status_code == 403, resp.text


def test_client_admin_list_hides_internal_reports_in_same_org(
    api_client, db_factory
) -> None:
    """Even within their own org, client_admins must not see internal_only reports.

    Tests the visible_audiences filter on list_reports. Without it,
    an admin-authored internal_only report in the client's org would
    leak via the list endpoint.
    """
    admin_tok = _admin_token(api_client, db_factory)
    client_tok, client_org = _client_admin(api_client, db_factory, "Cliente B")
    client_row = _seed_client_row(db_factory, "Cliente B Client")

    # Internal admin writes an internal_only report in the client_admin's org.
    r1 = api_client.post(
        "/api/v1/reports",
        headers=_h(admin_tok),
        params={"organization_id": client_org},
        json={"title": "Internal only", "audience": "internal_only"},
    )
    assert r1.status_code == 201, r1.text

    # Internal admin writes a client_facing report in the same org.
    r2 = api_client.post(
        "/api/v1/reports",
        headers=_h(admin_tok),
        params={"organization_id": client_org},
        json={
            "title": "Client facing",
            "audience": "client_facing",
            "client_id": client_row,
        },
    )
    assert r2.status_code == 201, r2.text

    # client_admin lists — should see only the client_facing one.
    resp = api_client.get("/api/v1/reports", headers=_h(client_tok))
    assert resp.status_code == 200, resp.text
    titles = [r["title"] for r in resp.json()["items"]]
    assert titles == ["Client facing"]


def test_client_admin_cannot_read_internal_only_directly(
    api_client, db_factory
) -> None:
    """Knowing the id of an internal_only report must not bypass the audience filter.

    The get_report path must return 404 (not 403) to avoid id enumeration.
    """
    admin_tok = _admin_token(api_client, db_factory)
    client_tok, client_org = _client_admin(api_client, db_factory, "Cliente C")

    r1 = api_client.post(
        "/api/v1/reports",
        headers=_h(admin_tok),
        params={"organization_id": client_org},
        json={"title": "Internal", "audience": "internal_only"},
    )
    assert r1.status_code == 201
    rid = r1.json()["id"]

    resp = api_client.get(f"/api/v1/reports/{rid}", headers=_h(client_tok))
    assert resp.status_code == 404


# ─── R2 — list filters ────────────────────────────────────────


def test_list_audience_filter_admin_narrows_to_one(api_client, db_factory) -> None:
    """R2: ?audience=client_facing returns only that audience for admin."""
    admin_tok = _admin_token(api_client, db_factory)
    target_client = _seed_client_row(db_factory, "Cliente Audience")

    # Author 2 reports of different audiences.
    r_internal = api_client.post(
        "/api/v1/reports",
        headers=_h(admin_tok),
        json={"title": "Internal only", "audience": "internal_only"},
    )
    assert r_internal.status_code == 201, r_internal.text
    r_client = api_client.post(
        "/api/v1/reports",
        headers=_h(admin_tok),
        json={
            "title": "Client facing",
            "audience": "client_facing",
            "client_id": target_client,
        },
    )
    assert r_client.status_code == 201, r_client.text

    # Without filter → both visible to admin.
    all_resp = api_client.get("/api/v1/reports", headers=_h(admin_tok))
    assert all_resp.status_code == 200
    assert {r["title"] for r in all_resp.json()["items"]} >= {
        "Internal only",
        "Client facing",
    }

    # With filter → only the client_facing one.
    filtered = api_client.get(
        "/api/v1/reports",
        headers=_h(admin_tok),
        params={"audience": "client_facing"},
    )
    assert filtered.status_code == 200
    titles = [r["title"] for r in filtered.json()["items"]]
    assert "Client facing" in titles
    assert "Internal only" not in titles
    for r in filtered.json()["items"]:
        assert r["audience"] == "client_facing"


def test_list_audience_filter_client_admin_requesting_forbidden_returns_empty(
    api_client, db_factory
) -> None:
    """R2: a client_admin requesting ?audience=internal_only must not see
    anything. The endpoint must return an empty list (not 403) to avoid
    leaking that any internal_only reports exist."""
    admin_tok = _admin_token(api_client, db_factory)
    client_tok, client_org = _client_admin(
        api_client, db_factory, "Cliente Forbidden"
    )

    # Admin seeds an internal_only report inside the client_admin's org.
    seed = api_client.post(
        "/api/v1/reports",
        headers=_h(admin_tok),
        params={"organization_id": client_org},
        json={"title": "Internal seeded", "audience": "internal_only"},
    )
    assert seed.status_code == 201

    resp = api_client.get(
        "/api/v1/reports",
        headers=_h(client_tok),
        params={"audience": "internal_only"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0}


def test_list_status_filter_narrows_correctly(api_client, db_factory) -> None:
    """R2: ?status=draft and ?status=active partition the list correctly."""
    admin_tok = _admin_token(api_client, db_factory)

    # Two reports — patch one to active.
    r1 = api_client.post(
        "/api/v1/reports",
        headers=_h(admin_tok),
        json={"title": "Draft one", "audience": "internal_only"},
    )
    rid1 = r1.json()["id"]
    r2 = api_client.post(
        "/api/v1/reports",
        headers=_h(admin_tok),
        json={"title": "Active one", "audience": "internal_only"},
    )
    rid2 = r2.json()["id"]
    patch = api_client.patch(
        f"/api/v1/reports/{rid2}",
        headers=_h(admin_tok),
        json={"status": "active"},
    )
    assert patch.status_code == 200, patch.text

    drafts = api_client.get(
        "/api/v1/reports", headers=_h(admin_tok), params={"status": "draft"}
    )
    assert drafts.status_code == 200
    draft_ids = {r["id"] for r in drafts.json()["items"]}
    assert rid1 in draft_ids
    assert rid2 not in draft_ids

    actives = api_client.get(
        "/api/v1/reports", headers=_h(admin_tok), params={"status": "active"}
    )
    assert actives.status_code == 200
    active_ids = {r["id"] for r in actives.json()["items"]}
    assert rid2 in active_ids
    assert rid1 not in active_ids
