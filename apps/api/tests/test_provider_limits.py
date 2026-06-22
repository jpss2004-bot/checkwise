"""Phase A — provider-limit enforcement + the /client/plan meter.

End to end over the real FastAPI app: the hard cap on client self-service
add, the "restore instead" affordance for an archived-RFC re-add, archiving
frees a slot, reactivate re-checks the cap, internal_admin override (on both
the client and admin doors, audited), and the GET /client/plan snapshot.
"""

from __future__ import annotations

import itertools
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
    AuditLog,
    Client,
    Membership,
    Organization,
    User,
    Vendor,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password

_PASSWORD = "ProviderLimits!2026"
_seq = itertools.count(1)


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


def _seed_client(db_factory, *, plan=None, provider_limit=None) -> dict:
    seq = next(_seq)
    email = f"owner-{seq}@checkwise.example"
    db = db_factory()
    try:
        client = Client(name=f"Cliente {seq}")
        db.add(client)
        db.flush()
        org = Organization(
            name=f"Cliente {seq}",
            kind="client",
            client_id=client.id,
            seat_limit=3,
            plan=plan,
            provider_limit=provider_limit,
        )
        db.add(org)
        db.flush()
        owner = User(
            email=email,
            password_hash=hash_password(_PASSWORD),
            full_name=f"Owner {seq}",
            status="active",
        )
        db.add(owner)
        db.flush()
        db.add(
            Membership(
                user_id=owner.id,
                organization_id=org.id,
                role="client_admin",
                is_primary=True,
                status="active",
            )
        )
        db.commit()
        return {"client_id": client.id, "org_id": org.id, "owner_email": email}
    finally:
        db.close()


def _seed_vendor(db_factory, client_id: str, *, status="active", rfc=None) -> str:
    seq = next(_seq)
    db = db_factory()
    try:
        vendor = Vendor(
            client_id=client_id,
            name=f"Proveedor {seq}",
            rfc=rfc or f"SEED{seq:08d}",
            persona_type="moral",
            status=status,
        )
        db.add(vendor)
        db.commit()
        return vendor.id
    finally:
        db.close()


def _seed_internal_admin(db_factory) -> dict:
    seq = next(_seq)
    email = f"staff-{seq}@checkwise.example"
    db = db_factory()
    try:
        user = User(
            email=email,
            password_hash=hash_password(_PASSWORD),
            full_name=f"Staff {seq}",
            status="active",
        )
        db.add(user)
        db.flush()
        org = Organization(name=f"Internal {seq}", kind="internal")
        db.add(org)
        db.flush()
        db.add(
            Membership(
                user_id=user.id,
                organization_id=org.id,
                role="internal_admin",
                status="active",
            )
        )
        db.commit()
        return {"email": email}
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


def _add_provider(api_client, token, *, rfc=None, client_id=None):
    n = next(_seq)
    body = {
        "vendor_name": f"Nuevo Proveedor {n}",
        "vendor_rfc": rfc or f"ADD{n:09d}",
        "persona_type": "moral",
        "contact_name": f"Contacto {n}",
        "contact_email": f"prov-{n}@checkwise.example",
    }
    params = {"client_id": client_id} if client_id else {}
    return api_client.post(
        "/api/v1/client/providers", json=body, params=params, headers=_h(token)
    )


# ---------------------------------------------------------------------------
# Client self-service add — the hard cap
# ---------------------------------------------------------------------------


def test_add_blocked_at_cap(db_factory, api_client):
    ctx = _seed_client(db_factory, plan="demo", provider_limit=1)
    _seed_vendor(db_factory, ctx["client_id"])  # fills the single slot
    token = _login(api_client, ctx["owner_email"])
    resp = _add_provider(api_client, token)
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "provider_limit_reached"
    assert detail["limit"] == 1
    assert "máximo" in detail["message"]


def test_add_succeeds_under_cap(db_factory, api_client):
    ctx = _seed_client(db_factory, plan="standard")  # default 30
    token = _login(api_client, ctx["owner_email"])
    assert _add_provider(api_client, token).status_code == 201


def test_archived_provider_frees_a_slot(db_factory, api_client):
    ctx = _seed_client(db_factory, plan="demo", provider_limit=1)
    vid = _seed_vendor(db_factory, ctx["client_id"])
    token = _login(api_client, ctx["owner_email"])
    assert _add_provider(api_client, token).status_code == 409
    deact = api_client.post(
        f"/api/v1/client/vendors/{vid}/deactivate", headers=_h(token)
    )
    assert deact.status_code == 200, deact.text
    assert _add_provider(api_client, token).status_code == 201


def test_readd_archived_rfc_returns_restore_hint(db_factory, api_client):
    ctx = _seed_client(db_factory, plan="standard")
    rfc = "ARCHIVED00001"  # 13 chars
    vid = _seed_vendor(db_factory, ctx["client_id"], status="inactive", rfc=rfc)
    token = _login(api_client, ctx["owner_email"])
    resp = _add_provider(api_client, token, rfc=rfc)
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "provider_archived"
    assert detail["vendor_id"] == vid


# ---------------------------------------------------------------------------
# Reactivate re-checks the cap
# ---------------------------------------------------------------------------


def test_reactivate_blocked_at_cap(db_factory, api_client):
    ctx = _seed_client(db_factory, plan="demo", provider_limit=1)
    _seed_vendor(db_factory, ctx["client_id"])  # 1 active = at cap
    archived = _seed_vendor(db_factory, ctx["client_id"], status="inactive")
    token = _login(api_client, ctx["owner_email"])
    resp = api_client.post(
        f"/api/v1/client/vendors/{archived}/reactivate", headers=_h(token)
    )
    assert resp.status_code == 409, resp.text


def test_reactivate_succeeds_when_slot_free(db_factory, api_client):
    ctx = _seed_client(db_factory, plan="demo", provider_limit=2)
    _seed_vendor(db_factory, ctx["client_id"])  # 1 active, 1 slot free
    archived = _seed_vendor(db_factory, ctx["client_id"], status="inactive")
    token = _login(api_client, ctx["owner_email"])
    resp = api_client.post(
        f"/api/v1/client/vendors/{archived}/reactivate", headers=_h(token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "active"


# ---------------------------------------------------------------------------
# internal_admin override (audited) on both doors
# ---------------------------------------------------------------------------


def test_internal_admin_override_adds_over_cap(db_factory, api_client):
    ctx = _seed_client(db_factory, plan="demo", provider_limit=1)
    _seed_vendor(db_factory, ctx["client_id"])  # at cap
    staff = _seed_internal_admin(db_factory)
    token = _login(api_client, staff["email"])
    resp = _add_provider(api_client, token, client_id=ctx["client_id"])
    assert resp.status_code == 201, resp.text


def test_internal_admin_override_reactivates_over_cap(db_factory, api_client):
    ctx = _seed_client(db_factory, plan="demo", provider_limit=1)
    _seed_vendor(db_factory, ctx["client_id"])  # 1 active = at cap
    archived = _seed_vendor(db_factory, ctx["client_id"], status="inactive")
    staff = _seed_internal_admin(db_factory)
    token = _login(api_client, staff["email"])
    resp = api_client.post(
        f"/api/v1/client/vendors/{archived}/reactivate",
        params={"client_id": ctx["client_id"]},
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text  # internal_admin exceeds the cap
    # ...and the over-cap restore is audited so a billing bypass is detectable.
    db = db_factory()
    try:
        row = db.scalars(
            select(AuditLog).where(
                AuditLog.action == "client.provider_reactivated"
            )
        ).first()
        assert row is not None
        assert row.event_metadata.get("over_limit_override") is True
    finally:
        db.close()


def test_admin_create_vendor_over_cap_allowed_and_audited(db_factory, api_client):
    ctx = _seed_client(db_factory, plan="demo", provider_limit=1)
    _seed_vendor(db_factory, ctx["client_id"])  # at cap
    staff = _seed_internal_admin(db_factory)
    token = _login(api_client, staff["email"])
    body = {
        "client_id": ctx["client_id"],
        "name": "Proveedor Admin",
        "rfc": "ADMINV000001",
        "persona_type": "moral",
    }
    resp = api_client.post("/api/v1/admin/vendors", json=body, headers=_h(token))
    assert resp.status_code == 201, resp.text

    db = db_factory()
    try:
        row = db.scalars(
            select(AuditLog).where(AuditLog.action == "admin.vendor.created")
        ).first()
        assert row is not None
        assert row.event_metadata.get("over_limit_override") is True
    finally:
        db.close()


def test_admin_create_vendor_orphan_legacy_client(db_factory, api_client):
    """A legacy Client with no Organization carries no plan — the admin door
    creates the vendor uncapped, with no over-limit audit metadata."""
    db = db_factory()
    try:
        client = Client(name="Orphan Legacy")
        db.add(client)
        db.commit()
        client_id = client.id
    finally:
        db.close()
    staff = _seed_internal_admin(db_factory)
    token = _login(api_client, staff["email"])
    body = {
        "client_id": client_id,
        "name": "Proveedor Huérfano",
        "rfc": "ORPHAN000001",
        "persona_type": "moral",
    }
    resp = api_client.post("/api/v1/admin/vendors", json=body, headers=_h(token))
    assert resp.status_code == 201, resp.text
    db = db_factory()
    try:
        row = db.scalars(
            select(AuditLog).where(AuditLog.action == "admin.vendor.created")
        ).first()
        assert row is not None
        # No Organization → no plan to enforce → no over-limit metadata.
        assert (row.event_metadata or {}).get("over_limit_override") is None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /client/plan
# ---------------------------------------------------------------------------


def test_get_client_plan_reports_usage(db_factory, api_client):
    ctx = _seed_client(db_factory, plan="standard")
    _seed_vendor(db_factory, ctx["client_id"])
    _seed_vendor(db_factory, ctx["client_id"])
    _seed_vendor(db_factory, ctx["client_id"], status="inactive")
    token = _login(api_client, ctx["owner_email"])
    body = api_client.get("/api/v1/client/plan", headers=_h(token)).json()
    assert body["plan"] == "standard"
    assert body["plan_label"] == "Estándar"
    assert body["provider_limit"] == 30
    assert body["providers_used"] == 2  # archived excluded
    assert body["providers_available"] == 28
    assert body["capabilities"]["export_audit_package"] is True
    assert body["can_manage"] is True


def test_get_client_plan_demo_gates_exports(db_factory, api_client):
    ctx = _seed_client(db_factory, plan="demo")
    token = _login(api_client, ctx["owner_email"])
    body = api_client.get("/api/v1/client/plan", headers=_h(token)).json()
    assert body["plan"] == "demo"
    assert body["provider_limit"] == 5
    assert body["capabilities"]["export_audit_package"] is False


def test_get_client_plan_legacy_is_uncapped(db_factory, api_client):
    ctx = _seed_client(db_factory, plan="legacy")
    token = _login(api_client, ctx["owner_email"])
    body = api_client.get("/api/v1/client/plan", headers=_h(token)).json()
    assert body["provider_limit"] is None
    assert body["providers_available"] is None


def test_get_client_plan_honours_per_tenant_override(db_factory, api_client):
    """An explicit provider_limit overrides the tier default end to end."""
    ctx = _seed_client(db_factory, plan="standard", provider_limit=15)
    _seed_vendor(db_factory, ctx["client_id"])
    token = _login(api_client, ctx["owner_email"])
    body = api_client.get("/api/v1/client/plan", headers=_h(token)).json()
    assert body["plan"] == "standard"
    assert body["provider_limit"] == 15  # override, not the tier default 30
    assert body["providers_available"] == 14
