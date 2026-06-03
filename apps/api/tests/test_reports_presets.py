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
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Client,
    Membership,
    Organization,
    ProviderWorkspace,
    User,
    Vendor,
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


def _provider_workspace_user(
    api_client: TestClient,
    db_factory,
    *,
    email: str,
    client_name: str,
    vendor_name: str,
    create_org_for_client: bool = True,
) -> tuple[str, str, str]:
    """Seed a role-less provider user owning a ``ProviderWorkspace``.

    Mirrors the boss.demo shape in dev_seed.py — a User with no
    Membership rows but with a workspace tying them to a Vendor +
    Client. Optionally creates the matching client Organization so
    ``_actor_from`` can resolve the owning-org for writes.

    Returns ``(token, vendor_id, client_id)``.
    """
    db = db_factory()
    try:
        password = "PresetsTest!2026"
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name="Provider Test",
            status="active",
            must_change_password=False,
        )
        db.add(user)
        db.flush()

        client = Client(name=client_name)
        db.add(client)
        db.flush()

        if create_org_for_client:
            org = Organization(
                name=f"{client_name} — Cliente",
                kind="client",
                client_id=client.id,
            )
            db.add(org)
            db.flush()

        vendor = Vendor(
            client_id=client.id,
            name=vendor_name,
            rfc=f"V{abs(hash(vendor_name)) % 10**11:011d}A",
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()

        workspace = ProviderWorkspace(
            client_id=client.id,
            vendor_id=vendor.id,
            contract_id=None,
            owner_user_id=user.id,
            filial_name="Filial test",
            persona_type="moral",
            display_name=vendor_name,
            access_token=f"tok-{vendor.id}",
            onboarding_completed_at=None,
            status="active",
        )
        db.add(workspace)
        db.commit()
        return _login(api_client, user.email, password), vendor.id, client.id
    finally:
        db.close()


# ─── Tests ─────────────────────────────────────────────────────


def test_presets_list_internal_admin_sees_all_seven(api_client, db_factory) -> None:
    """3 admin presets + 4 client presets (added client-vendor-detail).

    internal_admin is in the ``required_roles`` of every preset (so
    staff can author on behalf of either audience). The list must
    return all seven.
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
        "client-vendor-detail",
        "client-vendor-risk-matrix",
    ]
    # Audiences split 4 client + 3 admin.
    audiences = sorted(p["audience"] for p in body["items"])
    assert audiences == [
        "client_facing",
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
    """client_admin sees the 4 client_facing presets only.

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
        "client-vendor-detail",
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


# ─── P1 — workspace-owner / provider visibility ────────────────


def test_workspace_actor_sees_three_provider_presets_only(
    api_client, db_factory
) -> None:
    """P1: a role-less workspace owner sees the 3 vendor_facing presets,
    and none of the admin (3) or client (3) presets."""
    tok, _, _ = _provider_workspace_user(
        api_client,
        db_factory,
        email="provider@presets.test",
        client_name="Cliente Provider",
        vendor_name="Vendor Provider",
    )
    resp = api_client.get("/api/v1/reports/_presets", headers=_h(tok))
    assert resp.status_code == 200, resp.text
    ids = sorted(p["id"] for p in resp.json()["items"])
    assert ids == [
        "provider-current-state",
        "provider-missing-documents",
        "provider-recent-rejections",
    ]
    for p in resp.json()["items"]:
        assert p["audience"] == "vendor_facing"


def test_workspace_actor_from_preset_auto_resolves_vendor_and_client(
    api_client, db_factory
) -> None:
    """P1: ``POST /from-preset`` auto-fills vendor_id + client_id from
    the caller's ProviderWorkspace when the preset is vendor_facing.
    The created Report carries both fields verbatim."""
    tok, vendor_id, client_id = _provider_workspace_user(
        api_client,
        db_factory,
        email="provider2@presets.test",
        client_name="Cliente Auto",
        vendor_name="Vendor Auto",
    )
    resp = api_client.post(
        "/api/v1/reports/from-preset",
        headers=_h(tok),
        json={"preset_id": "provider-current-state"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # P1.8 (2026-05-20): workspace-owner from-preset titles are
    # qualified with the workspace display name (or vendor name as
    # fallback) so providers don't end up with multiple reports
    # called "Mi estado de cumplimiento". Internal staff still get
    # the bare preset title.
    assert body["title"] == "Mi estado de cumplimiento · Vendor Auto"
    assert body["audience"] == "vendor_facing"
    assert body["vendor_id"] == vendor_id
    assert body["client_id"] == client_id


def test_workspace_actor_list_only_returns_own_vendor(
    api_client, db_factory
) -> None:
    """P1: cross-vendor isolation. Provider A cannot see a vendor_facing
    report scoped to vendor B, even when they share a client."""
    admin_tok = _admin_token(api_client, db_factory)

    # Provider A creates a vendor_facing report about themselves.
    tok_a, vendor_a, client_a = _provider_workspace_user(
        api_client,
        db_factory,
        email="prov_a@presets.test",
        client_name="Cliente Shared",
        vendor_name="Vendor A",
    )
    create = api_client.post(
        "/api/v1/reports/from-preset",
        headers=_h(tok_a),
        json={"preset_id": "provider-current-state"},
    )
    assert create.status_code == 201

    # Admin seeds another vendor_facing report — same client, different vendor.
    other_vendor_db = db_factory()
    try:
        other_v = Vendor(
            client_id=client_a,
            name="Vendor B",
            rfc="VBO99988877X",
            persona_type="moral",
        )
        other_vendor_db.add(other_v)
        other_vendor_db.commit()
        other_vendor_id = other_v.id
    finally:
        other_vendor_db.close()
    other = api_client.post(
        "/api/v1/reports",
        headers=_h(admin_tok),
        json={
            "title": "About vendor B",
            "audience": "vendor_facing",
            "vendor_id": other_vendor_id,
        },
    )
    assert other.status_code == 201
    other_rid = other.json()["id"]

    # Provider A lists — sees only their own report.
    resp = api_client.get("/api/v1/reports", headers=_h(tok_a))
    assert resp.status_code == 200
    visible = [r["vendor_id"] for r in resp.json()["items"]]
    assert vendor_a in visible
    assert other_vendor_id not in visible

    # Provider A asking for the other report by id → 404, not 403.
    direct = api_client.get(f"/api/v1/reports/{other_rid}", headers=_h(tok_a))
    assert direct.status_code == 404


def test_workspace_actor_cannot_read_client_facing(api_client, db_factory) -> None:
    """P1: the vendor_facing branch does NOT grant access to
    client_facing reports, even when the report's vendor_id matches
    the provider's. The audience boundary holds."""
    admin_tok = _admin_token(api_client, db_factory)
    tok_p, vendor_id, client_id = _provider_workspace_user(
        api_client,
        db_factory,
        email="prov_aud@presets.test",
        client_name="Cliente Aud",
        vendor_name="Vendor Aud",
    )

    # Admin authors a client_facing report scoped to the provider's vendor.
    created = api_client.post(
        "/api/v1/reports",
        headers=_h(admin_tok),
        json={
            "title": "Client view of vendor",
            "audience": "client_facing",
            "client_id": client_id,
            "vendor_id": vendor_id,
        },
    )
    assert created.status_code == 201
    rid = created.json()["id"]

    # Provider sees no rows on the list (audience not in visible set).
    resp = api_client.get("/api/v1/reports", headers=_h(tok_p))
    assert resp.status_code == 200
    titles = [r["title"] for r in resp.json()["items"]]
    assert "Client view of vendor" not in titles

    # Direct read → 404.
    direct = api_client.get(f"/api/v1/reports/{rid}", headers=_h(tok_p))
    assert direct.status_code == 404


def test_workspace_actor_admin_preset_forbidden(api_client, db_factory) -> None:
    """P1: a provider asking for an admin-only preset is forbidden — the
    workspace-owner branch must not leak admin or client templates."""
    tok, _, _ = _provider_workspace_user(
        api_client,
        db_factory,
        email="prov_fb@presets.test",
        client_name="Cliente Fb",
        vendor_name="Vendor Fb",
    )
    for preset_id in (
        "admin-daily-queue",
        "client-monthly-executive",
    ):
        resp = api_client.post(
            "/api/v1/reports/from-preset",
            headers=_h(tok),
            json={"preset_id": preset_id},
        )
        assert resp.status_code == 403, (preset_id, resp.text)


def test_client_admin_still_sees_only_client_presets_after_p1(
    api_client, db_factory
) -> None:
    """Regression guard: provider presets must not change what
    client_admin sees. They get exactly the 4 client_facing presets."""
    tok, _ = _client_admin(api_client, db_factory, "Cliente Regression")
    resp = api_client.get("/api/v1/reports/_presets", headers=_h(tok))
    assert resp.status_code == 200
    ids = sorted(p["id"] for p in resp.json()["items"])
    assert ids == [
        "client-missing-evidence",
        "client-monthly-executive",
        "client-vendor-detail",
        "client-vendor-risk-matrix",
    ]


def test_admin_sees_all_seven_role_presets(api_client, db_factory) -> None:
    """Admin sees 3 admin + 4 client = 7. The 3 provider presets have
    empty required_roles, so they appear ONLY for workspace owners —
    never for staff who aren't workspace owners.
    """
    tok = _admin_token(api_client, db_factory)
    resp = api_client.get("/api/v1/reports/_presets", headers=_h(tok))
    assert resp.status_code == 200
    ids = sorted(p["id"] for p in resp.json()["items"])
    # Seven — admin is NOT a workspace owner, so the empty-required_roles
    # provider presets stay invisible to staff.
    assert ids == [
        "admin-daily-queue",
        "admin-high-risk-vendors",
        "admin-monthly-operational",
        "client-missing-evidence",
        "client-monthly-executive",
        "client-vendor-detail",
        "client-vendor-risk-matrix",
    ]


# ─── P1.1 — Safety scaffolding for provider blocks ─────────────


def _seed_second_workspace_for(
    db_factory,
    *,
    user_email: str,
    client_name: str,
    vendor_name: str,
) -> tuple[str, str]:
    """Attach a SECOND active ProviderWorkspace to an existing user.

    Used to reproduce the dual-workspace ambiguity: one User row
    owning more than one ProviderWorkspace. Returns
    ``(vendor_id, client_id)`` for the new workspace.
    """
    db = db_factory()
    try:
        user = db.scalar(select(User).where(User.email == user_email))
        assert user is not None, f"seed user {user_email} not found"

        client = Client(name=client_name)
        db.add(client)
        db.flush()

        org = Organization(
            name=f"{client_name} — Cliente",
            kind="client",
            client_id=client.id,
        )
        db.add(org)
        db.flush()

        vendor = Vendor(
            client_id=client.id,
            name=vendor_name,
            rfc=f"V{abs(hash(vendor_name)) % 10**11:011d}A",
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()

        workspace = ProviderWorkspace(
            client_id=client.id,
            vendor_id=vendor.id,
            contract_id=None,
            owner_user_id=user.id,
            filial_name="Filial test",
            persona_type="moral",
            display_name=vendor_name,
            access_token=f"tok-{vendor.id}",
            onboarding_completed_at=None,
            status="active",
        )
        db.add(workspace)
        db.commit()
        return vendor.id, client.id
    finally:
        db.close()


def test_dual_workspace_owner_resolution_is_deterministic_and_isolated(
    api_client, db_factory
) -> None:
    """P1.1: when one user owns two active ProviderWorkspaces, the API
    must (a) deterministically pick the same workspace on every
    request and (b) never leak the *other* workspace's reports.

    Multi-workspace visibility (seeing reports from both vendors at
    once) is a deferred follow-up. Until then the contract is: the
    lowest-id workspace wins and the other vendor's reports stay
    invisible — exactly as if the second workspace did not exist.
    """
    # Provider with workspace A.
    tok, vendor_a, _client_a = _provider_workspace_user(
        api_client,
        db_factory,
        email="dual_ws@presets.test",
        client_name="Cliente DualA",
        vendor_name="Vendor DualA",
    )

    # Same user gains a second active workspace pointing at vendor B.
    vendor_b, _client_b = _seed_second_workspace_for(
        db_factory,
        user_email="dual_ws@presets.test",
        client_name="Cliente DualB",
        vendor_name="Vendor DualB",
    )
    assert vendor_a != vendor_b

    # Admin seeds a vendor_facing report against each vendor so we can
    # see which side the actor resolution lands on.
    admin_tok = _admin_token(api_client, db_factory)
    r_a = api_client.post(
        "/api/v1/reports",
        headers=_h(admin_tok),
        json={"title": "About vendor A", "audience": "vendor_facing", "vendor_id": vendor_a},
    )
    r_b = api_client.post(
        "/api/v1/reports",
        headers=_h(admin_tok),
        json={"title": "About vendor B", "audience": "vendor_facing", "vendor_id": vendor_b},
    )
    assert r_a.status_code == 201 and r_b.status_code == 201, (r_a.text, r_b.text)

    # Determinism: the same user, repeated calls, same resolved
    # workspace. We don't pin which workspace wins (UUID id ordering is
    # implementation-defined) — only that it is consistent and that
    # the *other* workspace's report is hidden either way.
    first = api_client.get("/api/v1/reports", headers=_h(tok))
    second = api_client.get("/api/v1/reports", headers=_h(tok))
    assert first.status_code == 200 and second.status_code == 200

    titles_first = sorted(r["title"] for r in first.json()["items"])
    titles_second = sorted(r["title"] for r in second.json()["items"])
    assert titles_first == titles_second, (
        "Workspace pick must be deterministic across requests"
    )

    # Isolation: the user sees exactly ONE of the two seeded reports,
    # and direct-by-id reads on the other return 404.
    visible_titles = set(titles_first)
    assert visible_titles in (
        {"About vendor A"},
        {"About vendor B"},
    ), visible_titles

    hidden_id = (
        r_b.json()["id"]
        if "About vendor A" in visible_titles
        else r_a.json()["id"]
    )
    direct = api_client.get(f"/api/v1/reports/{hidden_id}", headers=_h(tok))
    assert direct.status_code == 404, direct.text

    # Belt-and-braces: confirm the API actually picked the
    # lowest-ordered workspace by id (matches the ORDER BY clause in
    # _actor_from). Reads the DB directly so a future refactor that
    # changes the ordering also has to update this assertion.
    db = db_factory()
    try:
        ws_ids = list(
            db.scalars(
                select(ProviderWorkspace.id)
                .where(ProviderWorkspace.owner_user_id == (
                    db.scalar(select(User.id).where(User.email == "dual_ws@presets.test"))
                ))
                .order_by(ProviderWorkspace.id)
            )
        )
        expected_vendor = db.scalar(
            select(ProviderWorkspace.vendor_id).where(
                ProviderWorkspace.id == ws_ids[0]
            )
        )
    finally:
        db.close()

    expected_title = (
        "About vendor A" if expected_vendor == vendor_a else "About vendor B"
    )
    assert visible_titles == {expected_title}, (
        "API resolution must agree with ORDER BY ProviderWorkspace.id"
    )


def test_workspace_actor_from_preset_rejects_foreign_vendor_id(
    api_client, db_factory
) -> None:
    """P1.1 safety fix: a workspace-owning provider must not be able
    to author a vendor_facing report against a *different* vendor by
    passing its id in the from-preset body.

    Before this guard, the auto-resolve only fired when ``vendor_id``
    was ``None`` — so a provider passing an explicit foreign id sailed
    through and created an orphan report tagged with the other
    vendor's id. The provider could never read it back (the list /
    get filters scope to their own workspace_vendor_id), but the row
    polluted the other vendor's surface.
    """
    # Provider A, with their own workspace.
    tok_a, _vendor_a, _client_a = _provider_workspace_user(
        api_client,
        db_factory,
        email="foreign_vid@presets.test",
        client_name="Cliente Foreign",
        vendor_name="Vendor Foreign A",
    )

    # Admin seeds an unrelated vendor B that provider A has no claim to.
    db = db_factory()
    try:
        other_client = Client(name="Cliente Otro")
        db.add(other_client)
        db.flush()
        other_vendor = Vendor(
            client_id=other_client.id,
            name="Vendor Otro",
            rfc="VOTRO99988877X",
            persona_type="moral",
        )
        db.add(other_vendor)
        db.commit()
        other_vendor_id = other_vendor.id
    finally:
        db.close()

    # Provider A attempts to instantiate a provider preset against
    # vendor B's id. Must be rejected, not silently accepted.
    resp = api_client.post(
        "/api/v1/reports/from-preset",
        headers=_h(tok_a),
        json={
            "preset_id": "provider-current-state",
            "vendor_id": other_vendor_id,
        },
    )
    assert resp.status_code == 403, resp.text

    # And the report list still shows nothing scoped to vendor B —
    # there must be no row created under the rejected request.
    listed = api_client.get("/api/v1/reports", headers=_h(tok_a))
    assert listed.status_code == 200
    vendor_ids_visible = {r.get("vendor_id") for r in listed.json()["items"]}
    assert other_vendor_id not in vendor_ids_visible


# ─── L1: patch_report tenant-lock for workspace owners ──────────
#
# can_write_report grants providers write access to any report whose
# vendor_id matches their workspace. That's correct for refresh /
# version / regenerate. patch_report previously left vendor_id /
# client_id / audience unguarded, so a workspace owner could PATCH
# their own report's tenancy metadata to point at another vendor.
# The UI never exposes this, but the API used to accept it. These
# tests pin the L1 (2026-05-20) tightening: each of the three
# mutation paths now returns 403, internal staff still bypass.


def test_workspace_owner_cannot_patch_vendor_id_to_foreign_vendor(
    api_client, db_factory
) -> None:
    """L1: provider PATCHing vendor_id away from their workspace's
    vendor is rejected, even though can_write_report grants the
    initial write on their own report."""
    tok, vendor_id, _client_id = _provider_workspace_user(
        api_client,
        db_factory,
        email="patch_l1_v@presets.test",
        client_name="Cliente L1 V",
        vendor_name="Vendor L1 V",
    )
    # Create a vendor_facing report owned by this provider.
    created = api_client.post(
        "/api/v1/reports/from-preset",
        headers=_h(tok),
        json={"preset_id": "provider-current-state"},
    )
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]

    # Seed a different vendor the provider has no claim to.
    db = db_factory()
    try:
        foreign_client = Client(name="Cliente Foreign Vendor Patch")
        db.add(foreign_client)
        db.flush()
        foreign_vendor = Vendor(
            client_id=foreign_client.id,
            name="Vendor Foreign Patch",
            rfc="VFGPATCH1234X",
            persona_type="moral",
        )
        db.add(foreign_vendor)
        db.commit()
        foreign_vendor_id = foreign_vendor.id
    finally:
        db.close()

    # Provider attempts to reassign the report to the foreign vendor.
    resp = api_client.patch(
        f"/api/v1/reports/{report_id}",
        headers=_h(tok),
        json={"vendor_id": foreign_vendor_id},
    )
    assert resp.status_code == 403, resp.text
    assert "vendor" in resp.text.lower()

    # State unchanged: read it back and confirm vendor_id still matches
    # the provider's own workspace vendor.
    after = api_client.get(f"/api/v1/reports/{report_id}", headers=_h(tok))
    assert after.status_code == 200
    assert after.json()["vendor_id"] == vendor_id


def test_workspace_owner_cannot_patch_client_id_to_foreign_client(
    api_client, db_factory
) -> None:
    """L1: same shape as vendor_id but for client_id. Even if the
    workspace owner could write the report, they cannot move it to a
    different client's scope."""
    tok, _vendor_id, client_id = _provider_workspace_user(
        api_client,
        db_factory,
        email="patch_l1_c@presets.test",
        client_name="Cliente L1 C",
        vendor_name="Vendor L1 C",
    )
    created = api_client.post(
        "/api/v1/reports/from-preset",
        headers=_h(tok),
        json={"preset_id": "provider-current-state"},
    )
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]

    db = db_factory()
    try:
        foreign_client = Client(name="Cliente Foreign Client Patch")
        db.add(foreign_client)
        db.commit()
        foreign_client_id = foreign_client.id
    finally:
        db.close()

    resp = api_client.patch(
        f"/api/v1/reports/{report_id}",
        headers=_h(tok),
        json={"client_id": foreign_client_id},
    )
    assert resp.status_code == 403, resp.text
    assert "client" in resp.text.lower()

    after = api_client.get(f"/api/v1/reports/{report_id}", headers=_h(tok))
    assert after.status_code == 200
    assert after.json()["client_id"] == client_id


def test_workspace_owner_cannot_patch_audience_away_from_vendor_facing(
    api_client, db_factory
) -> None:
    """L1: audience is part of the tenant lock. Workspace owners
    cannot promote a vendor_facing report into client_facing or
    internal_only, even if writable_audiences() would otherwise
    permit it."""
    tok, _vendor_id, _client_id = _provider_workspace_user(
        api_client,
        db_factory,
        email="patch_l1_a@presets.test",
        client_name="Cliente L1 A",
        vendor_name="Vendor L1 A",
    )
    created = api_client.post(
        "/api/v1/reports/from-preset",
        headers=_h(tok),
        json={"preset_id": "provider-current-state"},
    )
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]

    # Try every non-vendor_facing audience.
    for audience in ("internal_only", "client_facing", "external_signed"):
        resp = api_client.patch(
            f"/api/v1/reports/{report_id}",
            headers=_h(tok),
            json={"audience": audience},
        )
        assert resp.status_code == 403, f"{audience}: {resp.text}"

    after = api_client.get(f"/api/v1/reports/{report_id}", headers=_h(tok))
    assert after.status_code == 200
    assert after.json()["audience"] == "vendor_facing"


def test_internal_admin_can_still_reassign_report_vendor(
    api_client, db_factory
) -> None:
    """L1 negative case: the tenant lock is workspace-owner only.
    Internal staff retain cross-tenant mutation rights — they
    operate across the platform and need to be able to correct a
    misattributed vendor_id during reviewer workflows."""
    admin_tok = _admin_token(api_client, db_factory)
    # Seed two vendors.
    db = db_factory()
    try:
        client_a = Client(name="Cliente Internal A")
        db.add(client_a)
        db.flush()
        vendor_a = Vendor(
            client_id=client_a.id,
            name="Vendor Internal A",
            rfc="VINT0001111A",
            persona_type="moral",
        )
        db.add(vendor_a)
        vendor_b = Vendor(
            client_id=client_a.id,
            name="Vendor Internal B",
            rfc="VINT0002222B",
            persona_type="moral",
        )
        db.add(vendor_b)
        db.commit()
        vendor_a_id, vendor_b_id, client_a_id = vendor_a.id, vendor_b.id, client_a.id
    finally:
        db.close()

    created = api_client.post(
        "/api/v1/reports",
        headers=_h(admin_tok),
        json={
            "title": "Internal admin vendor swap",
            "audience": "vendor_facing",
            "client_id": client_a_id,
            "vendor_id": vendor_a_id,
        },
    )
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]

    # Internal admin reassigns to vendor B — must succeed.
    resp = api_client.patch(
        f"/api/v1/reports/{report_id}",
        headers=_h(admin_tok),
        json={"vendor_id": vendor_b_id},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["vendor_id"] == vendor_b_id
