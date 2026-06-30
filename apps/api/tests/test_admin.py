"""Phase 7 — Admin Operations Core tests.

Covers the new ``/admin`` router: overview, clients, vendors,
workspaces, requirements, calendar, audit-log. Each mutation is
expected to write an ``AuditLog`` row with
``actor_type='internal_admin'`` and
``metadata.source='admin_operations'``.
"""

from __future__ import annotations

import zipfile
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
    AuditLog,
    Client,
    Document,
    Institution,
    Membership,
    Organization,
    Period,
    ProviderWorkspace,
    Requirement,
    Submission,
    User,
    ValidationEvent,
    Vendor,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password


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


def _seed_user(db_factory, *, email: str, role: str | None) -> str:
    """Returns the access_token for an internal user with the given role.

    ``role=None`` produces a user with no memberships (so admin endpoints
    should reject as 403).
    """
    db = db_factory()
    try:
        password = "AdminTest!2026"
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name="Admin Test",
            status="active",
        )
        db.add(user)
        db.flush()
        if role is not None:
            org = Organization(name="LegalShelf", kind="internal")
            db.add(org)
            db.flush()
            db.add(
                Membership(
                    user_id=user.id, organization_id=org.id, role=role, status="active"
                )
            )
        db.commit()
        user_email = user.email
    finally:
        db.close()
    return password, user_email


def _login(api_client: TestClient, email: str, password: str) -> str:
    resp = api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _admin_token(api_client: TestClient, db_factory) -> str:
    pw, email = _seed_user(db_factory, email="adm@checkwise.test", role="operations_admin")
    return _login(api_client, email, pw)


def _reviewer_token(api_client: TestClient, db_factory) -> str:
    pw, email = _seed_user(db_factory, email="rev@checkwise.test", role="platform_admin")
    return _login(api_client, email, pw)


def _platform_admin_token(api_client: TestClient, db_factory) -> str:
    """A pure platform_admin — IT/control-plane role WITHOUT internal_admin.

    Migration 0044 backfilled platform_admin onto every internal_admin, so
    in production every operator holds both and the IT-vs-Ops split is
    latent. This fixture mints the role in isolation so the boundary can be
    exercised for real.
    """
    pw, email = _seed_user(
        db_factory, email="plat@checkwise.test", role="platform_admin"
    )
    return _login(api_client, email, pw)


def _seed_institution(db_factory, *, code: str = "sat") -> str:
    db = db_factory()
    try:
        existing = db.scalar(select(Institution).where(Institution.code == code))
        if existing:
            return existing.id
        inst = Institution(code=code, name=code.upper())
        db.add(inst)
        db.commit()
        return inst.id
    finally:
        db.close()


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Permission gates
# ---------------------------------------------------------------------------


def test_overview_rejects_unauthenticated(api_client: TestClient) -> None:
    resp = api_client.get("/api/v1/admin/overview")
    assert resp.status_code == 401


def test_overview_accepts_review_team(
    api_client: TestClient, db_factory
) -> None:
    """Role-model redesign: the CheckWise review team (platform_admin) now
    owns the compliance surface, so /admin/overview is allowed."""
    token = _reviewer_token(api_client, db_factory)
    resp = api_client.get("/api/v1/admin/overview", headers=_h(token))
    assert resp.status_code == 200, resp.text


def test_user_directory_rejects_review_team(
    api_client: TestClient, db_factory
) -> None:
    """The load-bearing new boundary: the review team (platform_admin)
    runs compliance but must NOT reach user/role management, which is
    superadmin-only (operations_admin).

    /admin/users is PlatformUser-gated, now require_role(operations_admin).
    """
    token = _platform_admin_token(api_client, db_factory)
    resp = api_client.get("/api/v1/admin/users", headers=_h(token))
    assert resp.status_code == 403, resp.text


def test_user_directory_accepts_operations_admin(
    api_client: TestClient, db_factory
) -> None:
    """The superadmin (operations_admin) owns user/role management."""
    token = _admin_token(api_client, db_factory)
    resp = api_client.get("/api/v1/admin/users", headers=_h(token))
    assert resp.status_code == 200, resp.text


def test_audit_log_accepts_platform_admin_only(
    api_client: TestClient, db_factory
) -> None:
    token = _platform_admin_token(api_client, db_factory)
    resp = api_client.get("/api/v1/admin/audit-log", headers=_h(token))
    assert resp.status_code == 200, resp.text


def test_overview_accepts_internal_admin(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    resp = api_client.get("/api/v1/admin/overview", headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in (
        "clients_total",
        "vendors_total",
        "active_workspaces_total",
        "pending_reviews_total",
        "rejected_or_correction_total",
        "recent_submissions_total",
        "recent_audit_events_total",
    ):
        assert key in body


def test_overview_recent_counts_use_seven_day_window(
    api_client: TestClient, db_factory
) -> None:
    """``recent_*`` counters are real 7-day windows on ``created_at``:
    a 30-day-old submission/audit row must NOT be counted, a fresh one
    must be."""
    from datetime import timedelta

    from app.models.entities import utc_now

    db = db_factory()
    try:
        institution = Institution(code="sat_overview", name="SAT Overview")
        db.add(institution)
        db.flush()
        client = Client(name="Cliente Overview", rfc="OVW260101AB1")
        db.add(client)
        db.flush()
        vendor = Vendor(
            client_id=client.id, name="Vendor Overview", rfc="VOV260101AB1"
        )
        db.add(vendor)
        db.flush()
        period = Period(
            code="2026-M05",
            period_key="2026-M05",
            year=2026,
            month=5,
            period_type="mensual",
        )
        db.add(period)
        db.flush()
        requirement = Requirement(
            code="overview_req",
            name="Overview Req",
            institution_id=institution.id,
            load_type="pdf",
            frequency="mensual",
            risk_level="medium",
            is_active=True,
            current_version=1,
        )
        db.add(requirement)
        db.flush()

        now = utc_now()
        stale = now - timedelta(days=30)
        for idx, ts in enumerate((now, stale)):
            db.add(
                Submission(
                    client_id=client.id,
                    vendor_id=vendor.id,
                    institution_id=institution.id,
                    requirement_id=requirement.id,
                    period_id=period.id,
                    status="pendiente_revision",
                    load_type="pdf",
                    requirement_code=f"overview_req_{idx}",
                    period_key="2026-M05",
                    created_at=ts,
                    updated_at=ts,
                )
            )
        # One stale + one fresh audit row.
        for ts, suffix in ((stale, "stale"), (now, "fresh")):
            db.add(
                AuditLog(
                    action=f"admin.test.{suffix}",
                    entity_type="client",
                    entity_id=client.id,
                    created_at=ts,
                )
            )
        db.commit()
    finally:
        db.close()

    token = _admin_token(api_client, db_factory)
    resp = api_client.get("/api/v1/admin/overview", headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Only the fresh submission falls inside the window.
    assert body["recent_submissions_total"] == 1

    # The stale audit row is excluded; the count matches exactly the
    # rows inside the window (the fresh seed + anything the login flow
    # itself logged), which is strictly fewer than the table total.
    from datetime import UTC, datetime

    db = db_factory()
    try:
        cutoff = datetime.now(UTC) - timedelta(days=7)
        all_rows = list(db.scalars(select(AuditLog)))
        fresh_audit = len(
            [r for r in all_rows if r.created_at.replace(tzinfo=UTC) >= cutoff]
        )
    finally:
        db.close()
    assert fresh_audit >= 1
    assert body["recent_audit_events_total"] == fresh_audit
    assert body["recent_audit_events_total"] < len(all_rows)


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------


def _assert_audit_admin(
    db_factory, *, action: str, entity_id: str, before_must_be_none: bool = False
) -> AuditLog:
    db = db_factory()
    try:
        row = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == action, AuditLog.entity_id == entity_id)
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        assert row is not None, f"expected audit_log row for {action} / {entity_id}"
        assert row.actor_type == "operations_admin"
        assert row.actor_id is not None
        meta = row.event_metadata or {}
        assert meta.get("source") == "admin_operations"
        if before_must_be_none:
            assert row.before is None
        return row
    finally:
        db.close()


def _seed_client_via_db(db_factory, *, name: str, rfc: str | None = None) -> str:
    """Insert a Client row directly. Replaces the old
    ``POST /api/v1/admin/clients`` silent-create that the unified
    user-provisioning flow removed."""
    db = db_factory()
    try:
        from app.models import Client as _C

        client = _C(
            name=name,
            rfc=rfc,
            email=f"{name.lower().replace(' ', '-')}@test.example",
            status="active",
        )
        db.add(client)
        db.commit()
        return client.id
    finally:
        db.close()


def test_admin_can_update_client_and_write_audit(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    created_id = _seed_client_via_db(db_factory, name="Cliente A")
    resp = api_client.patch(
        f"/api/v1/admin/clients/{created_id}",
        json={"name": "Cliente A Renombrado", "status": "inactive"},
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Cliente A Renombrado"
    assert resp.json()["status"] == "inactive"
    row = _assert_audit_admin(
        db_factory, action="admin.client.updated", entity_id=created_id
    )
    assert (row.before or {}).get("name") == "Cliente A"
    assert (row.after or {}).get("name") == "Cliente A Renombrado"


def test_list_clients_paginates_and_searches(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    _seed_client_via_db(db_factory, name="Alfa Corp", rfc="ALF260101AAA")
    _seed_client_via_db(db_factory, name="Beta Industries", rfc="BET260101BBB")
    _seed_client_via_db(db_factory, name="Gamma Servicios", rfc="GAM260101CCC")

    # Server-side search narrows (case-insensitive) and sets a truthful total.
    body = api_client.get(
        "/api/v1/admin/clients", params={"search": "beta"}, headers=_h(token)
    ).json()
    assert body["total"] == 1
    assert [c["name"] for c in body["items"]] == ["Beta Industries"]

    # Pagination: limit/offset walk the set with a page-capped item count and
    # no overlap between pages.
    page1 = api_client.get(
        "/api/v1/admin/clients", params={"limit": 2, "offset": 0}, headers=_h(token)
    ).json()
    page2 = api_client.get(
        "/api/v1/admin/clients", params={"limit": 2, "offset": 2}, headers=_h(token)
    ).json()
    assert page1["total"] >= 3
    assert len(page1["items"]) == 2
    ids = {c["id"] for c in page1["items"]} | {c["id"] for c in page2["items"]}
    assert len(ids) == len(page1["items"]) + len(page2["items"])


# ---------------------------------------------------------------------------
# Vendors
# ---------------------------------------------------------------------------


def test_admin_can_create_vendor_for_existing_client(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    client_id = _seed_client_via_db(db_factory, name="Cli")
    resp = api_client.post(
        "/api/v1/admin/vendors",
        json={
            "client_id": client_id,
            "name": "Proveedor X",
            "rfc": "PVX260512AB1",
            "contact_email": "ops@x.test",
            "persona_type": "moral",
        },
        headers=_h(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["client_id"] == client_id
    _assert_audit_admin(
        db_factory, action="admin.vendor.created", entity_id=body["id"], before_must_be_none=True
    )


def test_admin_create_vendor_for_missing_client_fails(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    resp = api_client.post(
        "/api/v1/admin/vendors",
        json={
            "client_id": "does-not-exist",
            "name": "Proveedor Huérfano",
            "rfc": "PVH260512AB1",
        },
        headers=_h(token),
    )
    assert resp.status_code == 404


def test_list_vendors_paginates_searches_and_labels_client(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    client_id = _seed_client_via_db(db_factory, name="Tenant Uno")
    for name, rfc in (
        ("Proveedor Uno", "PUN260101AB1"),
        ("Proveedor Dos", "PDO260101AB2"),
    ):
        created = api_client.post(
            "/api/v1/admin/vendors",
            json={
                "client_id": client_id,
                "name": name,
                "rfc": rfc,
                "persona_type": "moral",
            },
            headers=_h(token),
        )
        assert created.status_code == 201, created.text

    # Each row carries the denormalised client name (so the roster never has to
    # load the whole clients catalog to label rows).
    listed = api_client.get("/api/v1/admin/vendors", headers=_h(token)).json()
    assert listed["total"] >= 2
    assert all(v["client_name"] == "Tenant Uno" for v in listed["items"])

    # Server-side search narrows by vendor name (not the client name).
    one = api_client.get(
        "/api/v1/admin/vendors", params={"search": "Uno"}, headers=_h(token)
    ).json()
    assert {v["name"] for v in one["items"]} == {"Proveedor Uno"}
    assert one["total"] == 1

    # Pagination caps the page count.
    capped = api_client.get(
        "/api/v1/admin/vendors", params={"limit": 1, "offset": 0}, headers=_h(token)
    ).json()
    assert len(capped["items"]) == 1
    assert capped["total"] >= 2


def test_admin_can_update_vendor_and_write_audit(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    client_id = _seed_client_via_db(db_factory, name="Cli2")
    vendor = api_client.post(
        "/api/v1/admin/vendors",
        json={"client_id": client_id, "name": "Proveedor Antes", "rfc": "PVA260512AB1"},
        headers=_h(token),
    ).json()
    resp = api_client.patch(
        f"/api/v1/admin/vendors/{vendor['id']}",
        json={"contact_email": "ops@new.test", "status": "inactive"},
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["contact_email"] == "ops@new.test"
    assert body["status"] == "inactive"
    _assert_audit_admin(db_factory, action="admin.vendor.updated", entity_id=vendor["id"])


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------


def _seed_workspace(db_factory) -> tuple[str, str]:
    """Insert a ProviderWorkspace + parent client/vendor; return ids."""
    db = db_factory()
    try:
        client = Client(name="Cli ws")
        db.add(client)
        db.flush()
        vendor = Vendor(
            client_id=client.id,
            name="Vendor ws",
            rfc="WSV260512AB1",
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()
        ws = ProviderWorkspace(
            client_id=client.id,
            vendor_id=vendor.id,
            persona_type="moral",
            display_name="Vendor ws",
            access_token="SECRET-TOKEN-DO-NOT-LEAK",
        )
        db.add(ws)
        db.commit()
        return ws.id, ws.access_token
    finally:
        db.close()


def _write_metadata_preview_xlsx(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="00 Guia" sheetId="1" r:id="rId1"/>
    <sheet name="01 Revision" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>"""
    sheet1 = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="inlineStr"><is><t>CheckWise Metadata Review</t></is></c></row>
    <row r="2"><c r="A2" t="inlineStr"><is><t>Documento esperado</t></is></c><c r="B2" t="inlineStr"><is><t>Acuse SISUB</t></is></c></row>
  </sheetData>
</worksheet>"""
    sheet2 = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="inlineStr"><is><t>Campo</t></is></c><c r="B1" t="inlineStr"><is><t>Accion sugerida</t></is></c></row>
  </sheetData>
</worksheet>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/worksheets/sheet1.xml", sheet1)
        archive.writestr("xl/worksheets/sheet2.xml", sheet2)


def _write_client_master_xlsx(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="00 Guia" sheetId="1" r:id="rId1"/>
    <sheet name="01 Metadata" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>"""
    sheet1 = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="inlineStr"><is><t>Metadata documental del cliente</t></is></c></row>
  </sheetData>
</worksheet>"""
    sheet2 = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="inlineStr"><is><t>Cliente</t></is></c><c r="B1" t="inlineStr"><is><t>Proveedor</t></is></c><c r="C1" t="inlineStr"><is><t>Periodo</t></is></c><c r="D1" t="inlineStr"><is><t>Nombre del documento</t></is></c><c r="E1" t="inlineStr"><is><t>Tipo de documento</t></is></c><c r="F1" t="inlineStr"><is><t>Subtipo</t></is></c><c r="G1" t="inlineStr"><is><t>Institucion</t></is></c><c r="H1" t="inlineStr"><is><t>Fecha principal</t></is></c><c r="I1" t="inlineStr"><is><t>Participantes</t></is></c><c r="J1" t="inlineStr"><is><t>Descripcion</t></is></c><c r="K1" t="inlineStr"><is><t>Anexos</t></is></c><c r="L1" t="inlineStr"><is><t>Etiquetas</t></is></c><c r="M1" t="inlineStr"><is><t>Archivo PDF</t></is></c></row>
    <row r="2"><c r="A2" t="inlineStr"><is><t>Cliente Metadata</t></is></c><c r="B2" t="inlineStr"><is><t>Proveedor Metadata</t></is></c><c r="C2" t="inlineStr"><is><t>2026-M05</t></is></c><c r="D2" t="inlineStr"><is><t>Proveedor Metadata Acuse SISUB Mayo</t></is></c><c r="E2" t="inlineStr"><is><t>Formatos</t></is></c><c r="F2" t="inlineStr"><is><t>Acuse SISUB</t></is></c><c r="G2" t="inlineStr"><is><t>stps_repse</t></is></c><c r="M2" t="inlineStr"><is><t>acuse_sisub.pdf</t></is></c></row>
  </sheetData>
</worksheet>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/worksheets/sheet1.xml", sheet1)
        archive.writestr("xl/worksheets/sheet2.xml", sheet2)


def _seed_metadata_export(db_factory, export_root) -> str:
    db = db_factory()
    try:
        client = Client(name="Cliente Metadata")
        db.add(client)
        db.flush()
        vendor = Vendor(
            client_id=client.id,
            name="Proveedor Metadata",
            rfc="PMD260512AB1",
            persona_type="moral",
        )
        db.add(vendor)
        institution = Institution(code="repse", name="REPSE")
        db.add(institution)
        db.flush()
        period = Period(
            code="2026-M05",
            period_key="2026-M05",
            year=2026,
            month=5,
            period_type="mensual",
        )
        db.add(period)
        requirement = Requirement(
            code="acuse_sisub",
            name="Acuse SISUB",
            institution_id=institution.id,
            load_type="pdf",
            frequency="cuatrimestral",
            risk_level="medium",
            is_active=True,
            current_version=1,
        )
        db.add(requirement)
        db.flush()
        submission = Submission(
            client_id=client.id,
            vendor_id=vendor.id,
            period_id=period.id,
            institution_id=institution.id,
            requirement_id=requirement.id,
            load_type="pdf",
            status="pendiente_revision",
            requirement_code="acuse_sisub",
            period_key="2026-M05",
        )
        db.add(submission)
        db.flush()
        document = Document(
            submission_id=submission.id,
            storage_key="documents/demo.pdf",
            original_filename="acuse_sisub.pdf",
            mime_type="application/pdf",
            size_bytes=128,
            sha256="a" * 64,
        )
        db.add(document)
        db.flush()
        output_path = export_root / "cliente-metadata" / "proveedor-metadata" / "2026-m05" / "acuse_sisub" / "latest_metadata.xlsx"
        master_path = export_root / "cliente-metadata" / "client_master_metadata.xlsx"
        _write_metadata_preview_xlsx(output_path)
        _write_client_master_xlsx(master_path)
        event = ValidationEvent(
            submission_id=submission.id,
            document_id=document.id,
            event_type="metadata_table_exported",
            rule_code="metadata_table_export",
            result="completed",
            severity="info",
            payload={
                "document_type_code": "acuse_sisub",
                "output_path": str(output_path),
                "latest_path": str(output_path),
                "master_path": str(master_path),
            },
        )
        db.add(event)
        db.commit()
        return event.id
    finally:
        db.close()


def test_admin_workspaces_response_redacts_access_token(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    ws_id, secret = _seed_workspace(db_factory)

    listing = api_client.get("/api/v1/admin/workspaces", headers=_h(token)).json()
    assert "access_token" not in listing["items"][0]
    assert secret not in str(listing)

    detail = api_client.get(
        f"/api/v1/admin/workspaces/{ws_id}", headers=_h(token)
    ).json()
    assert "access_token" not in detail
    assert secret not in str(detail)


def test_admin_can_patch_workspace_and_write_audit(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    ws_id, _ = _seed_workspace(db_factory)
    resp = api_client.patch(
        f"/api/v1/admin/workspaces/{ws_id}",
        json={"status": "inactive", "display_name": "Vendor ws renamed"},
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "inactive"
    assert body["display_name"] == "Vendor ws renamed"
    _assert_audit_admin(
        db_factory, action="admin.workspace.updated", entity_id=ws_id
    )


def test_admin_can_list_preview_and_download_metadata_exports(
    api_client: TestClient, db_factory, tmp_path
) -> None:
    old_export_path = settings.METADATA_EXPORT_PATH
    export_root = tmp_path / "metadata_exports"
    settings.METADATA_EXPORT_PATH = str(export_root)
    try:
        token = _admin_token(api_client, db_factory)
        event_id = _seed_metadata_export(db_factory, export_root)

        listing = api_client.get("/api/v1/admin/metadata-exports", headers=_h(token))
        assert listing.status_code == 200, listing.text
        item = listing.json()["items"][0]
        assert item["id"] == event_id
        assert item["client_name"] == "Cliente Metadata"
        assert item["client_id"]
        assert item["vendor_name"] == "Proveedor Metadata"
        assert item["document_type_code"] == "acuse_sisub"
        assert item["file_exists"] is True
        assert item["preview_available"] is True
        assert item["master_available"] is True
        assert item["latest_path"].endswith("latest_metadata.xlsx")
        assert item["master_path"].endswith("client_master_metadata.xlsx")

        preview = api_client.get(
            f"/api/v1/admin/metadata-exports/{event_id}", headers=_h(token)
        )
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["export"]["id"] == event_id
        assert body["sheets"][0]["name"] == "00 Guia"
        assert body["sheets"][0]["rows"][0][0] == "CheckWise Metadata Review"
        assert body["sheets"][1]["rows"][0][1] == "Accion sugerida"

        master = api_client.get(
            f"/api/v1/admin/metadata-exports/clients/{item['client_id']}/master",
            headers=_h(token),
        )
        assert master.status_code == 200, master.text
        assert master.json()["master_path"].endswith("client_master_metadata.xlsx")
        assert master.json()["sheets"][1]["name"] == "01 Metadata"

        client_metadata = api_client.get(
            f"/api/v1/admin/clients/{item['client_id']}/metadata",
            headers=_h(token),
        )
        assert client_metadata.status_code == 200, client_metadata.text
        client_body = client_metadata.json()
        assert client_body["client"]["name"] == "Cliente Metadata"
        assert client_body["master_available"] is True
        assert client_body["documents"][0]["proveedor"] == "Proveedor Metadata"
        assert client_body["documents"][0]["nombre_documento"] == "Proveedor Metadata Acuse SISUB Mayo"

        download = api_client.get(
            f"/api/v1/admin/metadata-exports/{event_id}/download",
            headers=_h(token),
        )
        assert download.status_code == 200, download.text
        assert (
            download.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        master_download = api_client.get(
            f"/api/v1/admin/metadata-exports/clients/{item['client_id']}/master/download",
            headers=_h(token),
        )
        assert master_download.status_code == 200, master_download.text
    finally:
        settings.METADATA_EXPORT_PATH = old_export_path


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------


def test_admin_can_list_institutions_sorted_by_name(
    api_client: TestClient, db_factory
) -> None:
    """``GET /admin/institutions`` returns the seeded catalog as
    ``{id, code, name}`` items ordered by name ascending."""
    db = db_factory()
    try:
        db.add(Institution(code="stps", name="STPS"))
        db.add(Institution(code="imss_cat", name="IMSS"))
        db.add(Institution(code="infonavit", name="Infonavit"))
        db.commit()
    finally:
        db.close()

    token = _admin_token(api_client, db_factory)
    resp = api_client.get("/api/v1/admin/institutions", headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) == {"items"}
    names = [item["name"] for item in body["items"]]
    assert names == ["IMSS", "Infonavit", "STPS"]
    for item in body["items"]:
        assert set(item.keys()) == {"id", "code", "name"}
        assert item["id"]
    codes = {item["code"] for item in body["items"]}
    assert codes == {"stps", "imss_cat", "infonavit"}


def test_institutions_rejects_unauthenticated(api_client: TestClient) -> None:
    resp = api_client.get("/api/v1/admin/institutions")
    assert resp.status_code == 401


def test_institutions_accepts_review_team(
    api_client: TestClient, db_factory
) -> None:
    """Review team (platform_admin) has the compliance surface."""
    token = _reviewer_token(api_client, db_factory)
    resp = api_client.get("/api/v1/admin/institutions", headers=_h(token))
    assert resp.status_code == 200, resp.text


def test_admin_can_list_requirements(api_client: TestClient, db_factory) -> None:
    token = _admin_token(api_client, db_factory)
    inst_id = _seed_institution(db_factory)
    # Seed one requirement directly so the list isn't empty.
    db = db_factory()
    try:
        db.add(
            Requirement(
                code="ADM-REQ-001",
                name="Requisito de prueba",
                institution_id=inst_id,
                load_type="mensual",
                frequency="mensual",
                risk_level="medium",
                current_version=1,
            )
        )
        db.commit()
    finally:
        db.close()
    resp = api_client.get("/api/v1/admin/requirements", headers=_h(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    codes = [item["code"] for item in body["items"]]
    assert "ADM-REQ-001" in codes


def test_admin_can_create_requirement_and_write_audit(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    inst_id = _seed_institution(db_factory)
    resp = api_client.post(
        "/api/v1/admin/requirements",
        json={
            "code": "ADM-NEW-001",
            "name": "Requisito creado vía admin",
            "institution_id": inst_id,
            "load_type": "mensual",
            "frequency": "mensual",
            "risk_level": "alto",
            "legal_basis": "Artículo 15-A",
            "human_review_required": True,
            "required": True,
        },
        headers=_h(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == "ADM-NEW-001"
    assert body["version"] is not None
    assert body["version"]["legal_basis"] == "Artículo 15-A"
    _assert_audit_admin(
        db_factory, action="admin.requirement.created", entity_id=body["id"]
    )


def test_admin_can_update_requirement_and_write_audit(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    inst_id = _seed_institution(db_factory)
    created = api_client.post(
        "/api/v1/admin/requirements",
        json={
            "code": "ADM-UPD-001",
            "name": "Por renombrar",
            "institution_id": inst_id,
            "load_type": "mensual",
            "frequency": "mensual",
        },
        headers=_h(token),
    ).json()
    resp = api_client.patch(
        f"/api/v1/admin/requirements/{created['id']}",
        json={"name": "Renombrado", "is_active": False},
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Renombrado"
    assert body["is_active"] is False
    _assert_audit_admin(
        db_factory, action="admin.requirement.updated", entity_id=created["id"]
    )


# ---------------------------------------------------------------------------
# Periods + calendar
# ---------------------------------------------------------------------------


def test_admin_can_list_periods_and_calendar(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    db = db_factory()
    try:
        db.add(
            Period(
                code="2026-M05",
                period_key="2026-M05",
                year=2026,
                month=5,
                period_type="mensual",
            )
        )
        db.commit()
    finally:
        db.close()

    periods = api_client.get(
        "/api/v1/admin/periods?year=2026", headers=_h(token)
    ).json()
    assert any(p["period_key"] == "2026-M05" for p in periods["items"])

    calendar = api_client.get(
        "/api/v1/admin/calendar?year=2026", headers=_h(token)
    ).json()
    assert calendar["year"] == 2026
    assert len(calendar["months"]) == 12
    # Every month carries an institutions array (possibly empty).
    for month in calendar["months"]:
        assert "expected_total" in month
        assert isinstance(month["institutions"], list)


# ---------------------------------------------------------------------------
# Audit log explorer
# ---------------------------------------------------------------------------


def test_audit_log_filters_and_respects_limit(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    # Seed 3 clients via DB + 3 PATCHes so the audit log gets 3
    # ``admin.client.updated`` rows. The old test used the deleted
    # ``POST /admin/clients`` endpoint that emitted
    # ``admin.client.created`` rows; the unified provisioning flow
    # emits ``admin.user.provisioned`` rows instead, on entity_type=user.
    ids: list[str] = []
    for i in range(3):
        client_id = _seed_client_via_db(db_factory, name=f"AuditCli{i}")
        api_client.patch(
            f"/api/v1/admin/clients/{client_id}",
            json={"name": f"AuditCli{i} Renombrado"},
            headers=_h(token),
        )
        ids.append(client_id)

    resp = api_client.get(
        "/api/v1/admin/audit-log?action=admin.client.updated",
        headers=_h(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    actions = {item["action"] for item in body["items"]}
    assert actions == {"admin.client.updated"}
    assert len(body["items"]) >= 3

    by_entity = api_client.get(
        f"/api/v1/admin/audit-log?entity_id={ids[0]}", headers=_h(token)
    ).json()
    assert len(by_entity["items"]) == 1
    assert by_entity["items"][0]["entity_id"] == ids[0]

    limited = api_client.get(
        "/api/v1/admin/audit-log?limit=2", headers=_h(token)
    ).json()
    assert len(limited["items"]) <= 2
    assert limited["limit"] == 2

    by_type = api_client.get(
        "/api/v1/admin/audit-log?entity_type=client", headers=_h(token)
    ).json()
    assert all(item["entity_type"] == "client" for item in by_type["items"])


# ---------------------------------------------------------------------------
# Phase 9 / Slice 9A — reviewer queue counters
# ---------------------------------------------------------------------------


def test_reviewer_queue_returns_approved_rejected_counts(
    api_client: TestClient, db_factory
) -> None:
    """The queue response carries a rolling 7-day count of approved
    and rejected submissions so the queue page can render a stat
    strip above the actionable list. Counts both ``aprobado`` AND
    ``excepcion_legal`` toward the approved bucket — both resolve
    the slot positively.
    """
    from datetime import timedelta

    from app.models import Submission
    from app.models.entities import utc_now

    db = db_factory()
    try:
        # Seed the minimum scaffold (client, vendor, institution,
        # period, requirement) for terminal submissions.
        existing_inst = db.scalar(
            select(Institution).where(Institution.code == "imss")
        )
        institution = existing_inst or Institution(code="imss", name="IMSS")
        if not existing_inst:
            db.add(institution)
            db.flush()
        client = Client(name="Cliente Counters", rfc="COU260101AB1")
        db.add(client)
        db.flush()
        vendor = Vendor(
            client_id=client.id,
            name="Vendor Counters",
            rfc="VEN260101AB1",
        )
        db.add(vendor)
        db.flush()
        period = Period(
            code="2026-M05",
            period_key="2026-M05",
            year=2026,
            month=5,
            period_type="mensual",
        )
        db.add(period)
        db.flush()
        requirement = Requirement(
            code="counters_req",
            name="Counters Req",
            institution_id=institution.id,
            load_type="pdf",
            frequency="mensual",
            risk_level="medium",
            is_active=True,
            current_version=1,
        )
        db.add(requirement)
        db.flush()

        # Inside the window: 2 approved + 1 excepcion_legal + 3 rejected.
        # Outside the window: 1 approved + 1 rejected (8 days ago).
        now = utc_now()
        recent = now
        stale = now - timedelta(days=8)
        seed_specs = [
            ("aprobado", recent),
            ("aprobado", recent),
            ("excepcion_legal", recent),
            ("rechazado", recent),
            ("rechazado", recent),
            ("rechazado", recent),
            ("aprobado", stale),
            ("rechazado", stale),
        ]
        for idx, (status_value, ts) in enumerate(seed_specs):
            db.add(
                Submission(
                    client_id=client.id,
                    vendor_id=vendor.id,
                    institution_id=institution.id,
                    requirement_id=requirement.id,
                    period_id=period.id,
                    status=status_value,
                    load_type="pdf",
                    requirement_code=f"counters_req_{idx}",
                    period_key="2026-M05",
                    created_at=ts,
                    updated_at=ts,
                )
            )
        db.commit()
    finally:
        db.close()

    token = _reviewer_token(api_client, db_factory)
    resp = api_client.get("/api/v1/reviewer/queue", headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Inside the 7-day window: 2 aprobado + 1 excepcion_legal = 3
    # approved, 3 rejected. The stale rows are excluded.
    assert body["approved_last_7d_count"] == 3
    assert body["rejected_last_7d_count"] == 3


# ---------------------------------------------------------------------------
# P2 (2026-06-10 audit) — ops-console rollup + per-client compliance
# ---------------------------------------------------------------------------


def _seed_rollup_world(db_factory) -> dict:
    """One client with two vendors:

    * ``Vendor Rojo`` — workspace with zero submissions → semáforo red
      ("sin avance": 0 required slots on track).
    * ``Vendor Amarillo`` — one *approved* onboarding submission
      (``ONB-CONT-001``, a required expediente slot) → some progress,
      rest pending, nothing actionable → semáforo yellow.

    Plus two queue-pending submissions (``pendiente_revision``) on the
    red vendor — one fresh, one 30h old — whose requirement codes are
    NOT in the compliance catalog so they don't perturb the slot math.
    """
    from datetime import timedelta

    from app.models.entities import utc_now

    db = db_factory()
    try:
        institution = Institution(code="sat_rollup", name="SAT Rollup")
        db.add(institution)
        db.flush()
        client = Client(name="Cliente Rollup", rfc="ROL260101AB1")
        db.add(client)
        db.flush()
        period = Period(
            code="2026-M05",
            period_key="2026-M05",
            year=2026,
            month=5,
            period_type="mensual",
        )
        db.add(period)
        db.flush()
        requirement = Requirement(
            code="rollup_req",
            name="Rollup Req",
            institution_id=institution.id,
            load_type="pdf",
            frequency="mensual",
            risk_level="medium",
            is_active=True,
            current_version=1,
        )
        db.add(requirement)
        db.flush()

        red_vendor = Vendor(
            client_id=client.id,
            name="Vendor Rojo",
            rfc="ROJ260101AB1",
            persona_type="moral",
        )
        yellow_vendor = Vendor(
            client_id=client.id,
            name="Vendor Amarillo",
            rfc="AMA260101AB1",
            persona_type="moral",
        )
        db.add_all([red_vendor, yellow_vendor])
        db.flush()
        db.add_all(
            [
                ProviderWorkspace(
                    client_id=client.id,
                    vendor_id=red_vendor.id,
                    persona_type="moral",
                    display_name="Vendor Rojo",
                    access_token="tok-rollup-red",
                ),
                ProviderWorkspace(
                    client_id=client.id,
                    vendor_id=yellow_vendor.id,
                    persona_type="moral",
                    display_name="Vendor Amarillo",
                    access_token="tok-rollup-yellow",
                ),
            ]
        )
        db.flush()

        now = utc_now()
        # Yellow vendor: one approved required onboarding slot.
        db.add(
            Submission(
                client_id=client.id,
                vendor_id=yellow_vendor.id,
                institution_id=institution.id,
                requirement_id=requirement.id,
                period_id=period.id,
                status="aprobado",
                load_type="pdf",
                requirement_code="ONB-CONT-001",
                created_at=now,
                updated_at=now,
            )
        )
        # Queue-pending submissions: one fresh, one 30h old.
        for idx, ts in enumerate((now, now - timedelta(hours=30))):
            db.add(
                Submission(
                    client_id=client.id,
                    vendor_id=red_vendor.id,
                    institution_id=institution.id,
                    requirement_id=requirement.id,
                    period_id=period.id,
                    status="pendiente_revision",
                    load_type="pdf",
                    requirement_code=f"rollup_queue_{idx}",
                    period_key="2026-M05",
                    created_at=ts,
                    updated_at=ts,
                )
            )
        db.commit()
        return {
            "client_id": client.id,
            "red_vendor_id": red_vendor.id,
            "yellow_vendor_id": yellow_vendor.id,
        }
    finally:
        db.close()


def test_rollup_returns_client_semaphore_and_queue_blocks(
    api_client: TestClient, db_factory
) -> None:
    seeded = _seed_rollup_world(db_factory)
    token = _admin_token(api_client, db_factory)
    resp = api_client.get("/api/v1/admin/rollup", headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # --- clients block ---
    row = next(c for c in body["clients"] if c["client_id"] == seeded["client_id"])
    assert row["client_name"] == "Cliente Rollup"
    assert row["vendors_total"] == 2
    assert row["red_count"] == 1
    assert row["yellow_count"] == 1
    assert row["green_count"] == 0
    # Both vendors are far from compliant — the averaged pct must sit
    # at the bottom of the scale (the yellow vendor's single approved
    # slot rounds the client average to ~0-2%).
    assert 0 <= row["compliance_pct"] < 100
    assert row["missing_required_total"] > 0
    for key in ("pending_reviews_total", "due_soon_total"):
        assert key in row

    # --- queue block ---
    queue = body["queue"]
    assert queue["pending_total"] == 2
    assert queue["oldest_age_hours"] is not None
    assert queue["oldest_age_hours"] >= 30
    buckets = queue["age_buckets"]
    assert buckets["under_24h"] == 1
    assert buckets["h24_to_72h"] == 1
    assert buckets["over_72h"] == 0
    assert buckets["over_7d"] == 0

    # --- throughput block (the approved ONB doc is inside the window) ---
    assert body["throughput"]["approved_last_7d"] >= 1
    assert body["throughput"]["rejected_last_7d"] == 0

    # --- inbox block ---
    inbox = body["inbox"]
    for key in (
        "contact_requests_pending",
        "correction_requests_pending",
        "feedback_reports_new",
    ):
        assert inbox[key] == 0


def test_rollup_queue_is_empty_safe(api_client: TestClient, db_factory) -> None:
    """With nothing seeded the queue block is all zeros and
    ``oldest_age_hours`` is null, not 0."""
    token = _admin_token(api_client, db_factory)
    resp = api_client.get("/api/v1/admin/rollup", headers=_h(token))
    assert resp.status_code == 200, resp.text
    queue = resp.json()["queue"]
    assert queue["pending_total"] == 0
    assert queue["oldest_age_hours"] is None


def test_rollup_snapshot_roundtrip_matches_live_and_staleness(db_factory) -> None:
    """The cached snapshot payload reconstructs to exactly the live per-client
    scan (no serialization drift), and the staleness window behaves."""
    from datetime import UTC, datetime, timedelta

    from app.api.v1.admin import (
        _compute_rollup_clients,
        _load_rollup_snapshot,
        _refresh_rollup_snapshot,
        _rollup_snapshot_is_stale,
    )
    from app.core.time import today_mx

    _seed_rollup_world(db_factory)
    today = today_mx()
    year = today.year
    db = db_factory()
    try:
        live_clients, live_risk = _compute_rollup_clients(db, today=today, year=year)
        _refresh_rollup_snapshot(db, year=year, today=today)
        snap = _load_rollup_snapshot(db, year)
        assert snap is not None
        # Snapshot is byte-equal to the live compute round-tripped through JSON.
        assert snap.payload["clients"] == [c.model_dump() for c in live_clients]
        assert snap.payload["vendors_at_risk"] == [v.model_dump() for v in live_risk]
        # A second refresh replaces (still one row per year), never duplicates.
        _refresh_rollup_snapshot(db, year=year, today=today)
        assert _load_rollup_snapshot(db, year) is not None
    finally:
        db.close()

    now = datetime.now(UTC)
    assert _rollup_snapshot_is_stale(now, now) is False
    assert _rollup_snapshot_is_stale(now - timedelta(hours=1), now) is True


def test_rollup_serves_from_snapshot_when_present(
    api_client: TestClient, db_factory
) -> None:
    """When a fresh snapshot exists the endpoint serves it (snapshot_at set) and
    the cached client rows match the seeded world; ?refresh forces a recompute."""
    from app.api.v1.admin import _refresh_rollup_snapshot
    from app.core.time import today_mx

    seeded = _seed_rollup_world(db_factory)
    token = _admin_token(api_client, db_factory)

    today = today_mx()
    db = db_factory()
    try:
        _refresh_rollup_snapshot(db, year=today.year, today=today)
    finally:
        db.close()

    body = api_client.get("/api/v1/admin/rollup", headers=_h(token)).json()
    assert body["snapshot_at"] is not None  # served from the cache, not live
    row = next(c for c in body["clients"] if c["client_id"] == seeded["client_id"])
    assert row["vendors_total"] == 2
    assert row["red_count"] == 1
    # Live counters ride alongside the cached scan.
    assert body["queue"]["pending_total"] == 2

    # ?refresh=true recomputes inline and still serves a snapshot timestamp.
    forced = api_client.get(
        "/api/v1/admin/rollup?refresh=true", headers=_h(token)
    ).json()
    assert forced["snapshot_at"] is not None


def test_rollup_counts_pending_correction_requests_in_sql(
    api_client: TestClient, db_factory
) -> None:
    """``correction_requests_pending`` is a dialect-aware SQL COUNT over the
    audit rows: pending + status-less rows count, resolved ones don't."""
    token = _admin_token(api_client, db_factory)
    db = db_factory()
    try:
        db.add_all(
            [
                AuditLog(
                    action="correction_request.submitted",
                    entity_type="submission",
                    entity_id="sub-pending",
                    actor_type="client",
                    actor_id="c1",
                    event_metadata={"status": "pending"},
                ),
                # No status key — the old Python default treated this as
                # pending; the SQL count must match.
                AuditLog(
                    action="correction_request.submitted",
                    entity_type="submission",
                    entity_id="sub-nostatus",
                    actor_type="client",
                    actor_id="c2",
                    event_metadata={"note": "sin estado"},
                ),
                AuditLog(
                    action="correction_request.submitted",
                    entity_type="submission",
                    entity_id="sub-resolved",
                    actor_type="client",
                    actor_id="c3",
                    event_metadata={"status": "resolved"},
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    body = api_client.get("/api/v1/admin/rollup", headers=_h(token)).json()
    assert body["inbox"]["correction_requests_pending"] == 2


def test_rollup_vendors_at_risk_orders_red_before_yellow_and_excludes_green(
    api_client: TestClient, db_factory
) -> None:
    seeded = _seed_rollup_world(db_factory)
    token = _admin_token(api_client, db_factory)
    resp = api_client.get("/api/v1/admin/rollup", headers=_h(token))
    assert resp.status_code == 200, resp.text
    risk = resp.json()["vendors_at_risk"]

    assert [r["vendor_id"] for r in risk] == [
        seeded["red_vendor_id"],
        seeded["yellow_vendor_id"],
    ]
    assert [r["semaphore_level"] for r in risk] == ["red", "yellow"]
    assert all(r["semaphore_level"] != "green" for r in risk)
    # The yellow vendor has activity (its approved upload); ISO string.
    yellow_row = risk[1]
    assert yellow_row["last_activity_at"] is not None
    assert yellow_row["client_id"] == seeded["client_id"]
    assert yellow_row["client_name"] == "Cliente Rollup"


def test_client_compliance_returns_per_vendor_rows_worst_first(
    api_client: TestClient, db_factory
) -> None:
    seeded = _seed_rollup_world(db_factory)
    token = _admin_token(api_client, db_factory)
    resp = api_client.get(
        f"/api/v1/admin/clients/{seeded['client_id']}/compliance",
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["client_id"] == seeded["client_id"]
    assert body["client_name"] == "Cliente Rollup"
    assert len(body["vendors"]) == 2

    # Ordering: red first, then yellow.
    assert [v["semaphore_level"] for v in body["vendors"]] == ["red", "yellow"]
    assert body["vendors"][0]["vendor_id"] == seeded["red_vendor_id"]
    assert body["vendors"][1]["vendor_id"] == seeded["yellow_vendor_id"]

    for vendor_row in body["vendors"]:
        for key in (
            "vendor_id",
            "vendor_name",
            "vendor_rfc",
            "workspace_id",
            "workspace_status",
            "semaphore_level",
            "compliance_pct",
            "missing_required_count",
            "rejected_or_correction_count",
            "pending_reviews_count",
            "due_soon_count",
            "last_activity_at",
        ):
            assert key in vendor_row
    red_row = body["vendors"][0]
    yellow_row = body["vendors"][1]
    assert red_row["compliance_pct"] == 0
    assert yellow_row["compliance_pct"] > 0
    assert yellow_row["last_activity_at"] is not None


def test_client_compliance_404s_on_bogus_id(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    resp = api_client.get(
        "/api/v1/admin/clients/no-such-client/compliance", headers=_h(token)
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Cliente no encontrado."


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/rollup",
        "/api/v1/admin/clients/whatever/compliance",
    ],
)
def test_rollup_and_compliance_reject_unauthenticated(
    api_client: TestClient, path: str
) -> None:
    resp = api_client.get(path)
    assert resp.status_code == 401


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/rollup",
        "/api/v1/admin/clients/whatever/compliance",
    ],
)
def test_rollup_and_compliance_accept_review_team(
    api_client: TestClient, db_factory, path: str
) -> None:
    """Review team (platform_admin) is no longer fenced out of the
    compliance surface — the gate must allow it (content may be 200/404,
    never a 403 gate denial)."""
    token = _reviewer_token(api_client, db_factory)
    resp = api_client.get(path, headers=_h(token))
    assert resp.status_code != 403, resp.text


# ---------------------------------------------------------------------------
# P3 (2026-06-10 audit) — user management: list / disable / reset password
# ---------------------------------------------------------------------------


def _seed_directory_user(
    db_factory,
    *,
    email: str,
    full_name: str = "Usuario Directorio",
    role: str | None = None,
    org_name: str | None = None,
    org_kind: str = "client",
    user_status: str = "active",
) -> str:
    """Insert a plain User (optionally with one active membership in a
    fresh org) and return its id."""
    db = db_factory()
    try:
        user = User(
            email=email,
            password_hash=hash_password("Seeded!2026"),
            full_name=full_name,
            status=user_status,
        )
        db.add(user)
        db.flush()
        if role is not None:
            org = Organization(name=org_name or "Org Directorio", kind=org_kind)
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
        return user.id
    finally:
        db.close()


def _user_id_by_email(db_factory, email: str) -> str:
    db = db_factory()
    try:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        return user.id
    finally:
        db.close()


def _seed_user_directory(db_factory) -> dict[str, str]:
    """Three users sharing the ``@seeded.test`` domain so ``q=`` can
    scope assertions away from the login fixture's admin account."""
    return {
        "ana": _seed_directory_user(
            db_factory,
            email="ana@seeded.test",
            full_name="Ana Dir",
            role="client_admin",
            org_name="Cliente Uno",
            org_kind="client",
        ),
        "beto": _seed_directory_user(
            db_factory,
            email="beto@seeded.test",
            full_name="Beto Dir",
            role="platform_admin",
            org_name="LegalShelf Interna",
            org_kind="internal",
        ),
        "carla": _seed_directory_user(
            db_factory,
            email="carla@seeded.test",
            full_name="Carla Distinta",
            user_status="disabled",
        ),
    }


def test_admin_users_list_returns_roles_orgs_and_filters(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    seeded = _seed_user_directory(db_factory)

    # Scope to the seeded trio via q (the login fixture adds its own
    # admin user).
    resp = api_client.get(
        "/api/v1/admin/users?q=@seeded.test", headers=_h(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    by_email = {item["email"]: item for item in body["items"]}
    assert set(by_email) == {
        "ana@seeded.test",
        "beto@seeded.test",
        "carla@seeded.test",
    }

    ana = by_email["ana@seeded.test"]
    assert ana["user_id"] == seeded["ana"]
    assert ana["full_name"] == "Ana Dir"
    assert ana["status"] == "active"
    assert ana["must_change_password"] is False
    assert ana["last_login_at"] is None
    assert ana["created_at"]
    assert ana["roles"] == ["client_admin"]
    assert ana["organizations"] == [
        {
            "id": ana["organizations"][0]["id"],
            "name": "Cliente Uno",
            "kind": "client",
        }
    ]
    # No-membership user → empty roles/orgs, not missing keys.
    carla = by_email["carla@seeded.test"]
    assert carla["roles"] == []
    assert carla["organizations"] == []

    # q= substring of email.
    only_ana = api_client.get(
        "/api/v1/admin/users?q=ana@seeded", headers=_h(token)
    ).json()
    assert only_ana["total"] == 1
    assert only_ana["items"][0]["user_id"] == seeded["ana"]

    # q= substring of full_name (case-insensitive).
    by_name = api_client.get(
        "/api/v1/admin/users?q=distinta", headers=_h(token)
    ).json()
    assert by_name["total"] == 1
    assert by_name["items"][0]["user_id"] == seeded["carla"]

    # status= filter.
    disabled = api_client.get(
        "/api/v1/admin/users?q=@seeded.test&status=disabled",
        headers=_h(token),
    ).json()
    assert disabled["total"] == 1
    assert disabled["items"][0]["user_id"] == seeded["carla"]

    # role= filter (active membership role).
    review_team = api_client.get(
        "/api/v1/admin/users?q=@seeded.test&role=platform_admin", headers=_h(token)
    ).json()
    assert review_team["total"] == 1
    assert review_team["items"][0]["user_id"] == seeded["beto"]


def test_admin_users_total_is_real_count_independent_of_limit(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    _seed_user_directory(db_factory)

    page = api_client.get(
        "/api/v1/admin/users?q=@seeded.test&limit=2", headers=_h(token)
    ).json()
    assert len(page["items"]) == 2
    assert page["total"] == 3

    # offset pages through the remainder.
    rest = api_client.get(
        "/api/v1/admin/users?q=@seeded.test&limit=2&offset=2",
        headers=_h(token),
    ).json()
    assert len(rest["items"]) == 1
    assert rest["total"] == 3
    page_ids = {item["user_id"] for item in page["items"]}
    assert rest["items"][0]["user_id"] not in page_ids


def test_admin_can_disable_and_reactivate_user(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    target_id = _seed_directory_user(db_factory, email="target@seeded.test")

    resp = api_client.patch(
        f"/api/v1/admin/users/{target_id}",
        json={"status": "disabled"},
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"user_id": target_id, "status": "disabled"}
    db = db_factory()
    try:
        assert db.get(User, target_id).status == "disabled"
    finally:
        db.close()
    row = _assert_audit_admin(
        db_factory, action="admin.user_disabled", entity_id=target_id
    )
    assert (row.before or {}).get("status") == "active"
    assert (row.after or {}).get("status") == "disabled"

    resp = api_client.patch(
        f"/api/v1/admin/users/{target_id}",
        json={"status": "active"},
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"user_id": target_id, "status": "active"}
    db = db_factory()
    try:
        assert db.get(User, target_id).status == "active"
    finally:
        db.close()
    row = _assert_audit_admin(
        db_factory, action="admin.user_reactivated", entity_id=target_id
    )
    assert (row.before or {}).get("status") == "disabled"


def test_admin_cannot_disable_own_account(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    own_id = _user_id_by_email(db_factory, "adm@checkwise.test")
    resp = api_client.patch(
        f"/api/v1/admin/users/{own_id}",
        json={"status": "disabled"},
        headers=_h(token),
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "No puedes desactivar tu propia cuenta."
    db = db_factory()
    try:
        assert db.get(User, own_id).status == "active"
    finally:
        db.close()


def test_admin_patch_user_404_on_missing(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    resp = api_client.patch(
        "/api/v1/admin/users/no-such-user",
        json={"status": "disabled"},
        headers=_h(token),
    )
    assert resp.status_code == 404


def test_admin_can_reset_user_password(
    api_client: TestClient, db_factory
) -> None:
    from app.models import PasswordHistory

    token = _admin_token(api_client, db_factory)
    target_id = _seed_directory_user(db_factory, email="reset@seeded.test")
    db = db_factory()
    try:
        old_hash = db.get(User, target_id).password_hash
    finally:
        db.close()

    resp = api_client.post(
        f"/api/v1/admin/users/{target_id}/reset-password", headers=_h(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user_id"] == target_id
    assert body["email"] == "reset@seeded.test"
    assert body["temp_password"]
    assert body["email_status"] in {"sent", "skipped", "failed"}
    assert "email_error" in body

    db = db_factory()
    try:
        target = db.get(User, target_id)
        assert target.must_change_password is True
        assert target.password_hash != old_hash
        history = list(
            db.scalars(
                select(PasswordHistory).where(
                    PasswordHistory.user_id == target_id
                )
            )
        )
        assert len(history) == 1
        assert history[0].password_hash == old_hash
    finally:
        db.close()
    _assert_audit_admin(
        db_factory,
        action="admin.user_password_reset",
        entity_id=target_id,
        before_must_be_none=True,
    )

    # The temp password actually logs in (and is flagged for rotation).
    login = api_client.post(
        "/api/v1/auth/login",
        json={"email": "reset@seeded.test", "password": body["temp_password"]},
    )
    assert login.status_code == 200, login.text


def test_admin_reset_password_409_on_disabled_target(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    target_id = _seed_directory_user(
        db_factory, email="locked@seeded.test", user_status="disabled"
    )
    resp = api_client.post(
        f"/api/v1/admin/users/{target_id}/reset-password", headers=_h(token)
    )
    assert resp.status_code == 409
    assert (
        resp.json()["detail"]
        == "Reactiva al usuario antes de restablecer su contraseña."
    )


def test_admin_reset_password_clears_account_lock(
    api_client: TestClient, db_factory
) -> None:
    """An admin reset is how an operator unsticks a locked-out user, so
    it must clear the lock (else the new temp password wouldn't work
    until the cooldown elapsed)."""
    from datetime import UTC, datetime, timedelta

    token = _admin_token(api_client, db_factory)
    target = _seed_directory_user(db_factory, email="locked@seeded.test")
    db = db_factory()
    try:
        u = db.get(User, target)
        u.locked_until = datetime.now(UTC) + timedelta(minutes=30)
        u.failed_login_count = 5
        db.commit()
    finally:
        db.close()

    resp = api_client.post(
        f"/api/v1/admin/users/{target}/reset-password", headers=_h(token)
    )
    assert resp.status_code == 200, resp.text

    db = db_factory()
    try:
        u = db.get(User, target)
        assert u.locked_until is None
        assert u.failed_login_count == 0
    finally:
        db.close()


def test_admin_reset_password_404_on_missing(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    resp = api_client.post(
        "/api/v1/admin/users/no-such-user/reset-password", headers=_h(token)
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Phase 2 (platform rework) — user detail endpoint
# ---------------------------------------------------------------------------


def test_admin_user_detail_full_picture(
    api_client: TestClient, db_factory
) -> None:
    """Detail returns identity, memberships with the client seat picture,
    active roles, and the user's own audit slice."""
    token = _admin_token(api_client, db_factory)
    created = api_client.post(
        "/api/v1/admin/users",
        json={
            "role": "client",
            "full_name": "Dora Detalle",
            "email": "dora@detalle-cliente.com",
            "client_name": "Cliente Detalle SA",
        },
        headers=_h(token),
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["user_id"]

    resp = api_client.get(f"/api/v1/admin/users/{user_id}", headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["user_id"] == user_id
    assert body["email"] == "dora@detalle-cliente.com"
    assert body["full_name"] == "Dora Detalle"
    assert body["status"] == "active"
    # Freshly provisioned accounts must rotate their temp password.
    assert body["must_change_password"] is True
    assert body["deleted_at"] is None
    assert body["roles"] == ["client_admin"]

    # One active membership in the new client org; the 3-seat model sets
    # seat_limit=3 and this is its only (primary) occupant.
    assert len(body["memberships"]) == 1
    m = body["memberships"][0]
    assert m["organization_kind"] == "client"
    assert m["role"] == "client_admin"
    assert m["is_primary"] is True
    assert m["status"] == "active"
    assert m["seat_limit"] == 3
    assert m["active_seats"] == 1

    # The provisioning event is part of this user's audit slice.
    actions = {ev["action"] for ev in body["recent_activity"]}
    assert "admin.user.provisioned" in actions
    assert body["activity_total"] >= 1


def test_admin_user_detail_surfaces_soft_delete_fields(
    api_client: TestClient, db_factory
) -> None:
    """A live account reports null soft-delete provenance (the columns
    exist and serialize even before Phase 5 wires the delete action)."""
    token = _admin_token(api_client, db_factory)
    target_id = _seed_directory_user(
        db_factory,
        email="vive@seeded.test",
        role="platform_admin",
        org_name="LegalShelf Interna",
        org_kind="internal",
    )
    resp = api_client.get(f"/api/v1/admin/users/{target_id}", headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deleted_at"] is None
    assert body["deleted_by_user_id"] is None
    assert body["deleted_by_email"] is None
    assert body["deletion_reason"] is None
    # Internal org carries no seat cap.
    assert body["memberships"][0]["seat_limit"] is None
    assert body["memberships"][0]["active_seats"] is None


def test_admin_user_detail_404_on_missing(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    resp = api_client.get(
        "/api/v1/admin/users/no-such-user", headers=_h(token)
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Phase 3 (platform rework) — edit identity + duplicate-email resolver
# ---------------------------------------------------------------------------


def _provision_client(
    api_client: TestClient,
    token: str,
    *,
    email: str,
    full_name: str = "Edi Tante",
    client_name: str = "Cliente Edit SA",
) -> str:
    resp = api_client.post(
        "/api/v1/admin/users",
        json={
            "role": "client",
            "full_name": full_name,
            "email": email,
            "client_name": client_name,
        },
        headers=_h(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["user_id"]


def test_admin_update_identity_name_and_phone(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    uid = _provision_client(api_client, token, email="nombre@edit-cliente.com")

    resp = api_client.patch(
        f"/api/v1/admin/users/{uid}/identity",
        json={"full_name": "Nombre Nuevo", "phone": "+52 55 0000 1111"},
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["full_name"] == "Nombre Nuevo"
    assert body["phone"] == "+52 55 0000 1111"
    assert body["email_changed"] is False
    assert body["notification_status"] is None

    detail = api_client.get(
        f"/api/v1/admin/users/{uid}", headers=_h(token)
    ).json()
    assert detail["full_name"] == "Nombre Nuevo"
    assert detail["phone"] == "+52 55 0000 1111"


def test_admin_update_identity_email_change_mirrors_client_and_audits(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    uid = _provision_client(api_client, token, email="viejo@edit-cliente.com")

    resp = api_client.patch(
        f"/api/v1/admin/users/{uid}/identity",
        json={"email": "nuevo@edit-cliente.com"},
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == "nuevo@edit-cliente.com"
    assert body["email_changed"] is True
    # SMTP is unconfigured under test → both notifications skip cleanly.
    assert body["notification_status"] == "skipped"

    # User row + the canonical Client contact both moved to the new email.
    db = db_factory()
    try:
        user = db.scalar(select(User).where(User.id == uid))
        assert user is not None and user.email == "nuevo@edit-cliente.com"
        mirrored = db.scalar(
            select(Client).where(Client.email == "nuevo@edit-cliente.com")
        )
        assert mirrored is not None
    finally:
        db.close()

    audit = api_client.get(
        "/api/v1/admin/audit-log?action=admin.user.identity_updated",
        headers=_h(token),
    ).json()
    assert audit["total"] >= 1


def test_admin_update_identity_rejects_duplicate_email(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    uid_a = _provision_client(
        api_client, token, email="a@edit-cliente.com", client_name="A SA"
    )
    _provision_client(
        api_client, token, email="b@edit-cliente.com", client_name="B SA"
    )
    resp = api_client.patch(
        f"/api/v1/admin/users/{uid_a}/identity",
        json={"email": "b@edit-cliente.com"},
        headers=_h(token),
    )
    assert resp.status_code == 409


def test_admin_update_identity_404_on_missing(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    resp = api_client.patch(
        "/api/v1/admin/users/no-such-user/identity",
        json={"full_name": "X"},
        headers=_h(token),
    )
    assert resp.status_code == 404


def test_provision_duplicate_email_returns_existing_user_summary(
    api_client: TestClient, db_factory
) -> None:
    """The duplicate-email 409 carries a structured summary of the
    existing account so the New User form can offer guided actions."""
    token = _admin_token(api_client, db_factory)
    uid = _provision_client(
        api_client, token, email="dup@edit-cliente.com", client_name="Dup SA"
    )
    again = api_client.post(
        "/api/v1/admin/users",
        json={
            "role": "admin",
            "full_name": "Otro Intento",
            "email": "dup@edit-cliente.com",
        },
        headers=_h(token),
    )
    assert again.status_code == 409, again.text
    detail = again.json()["detail"]
    assert isinstance(detail, dict)
    existing = detail["existing_user"]
    assert existing["user_id"] == uid
    assert existing["email"] == "dup@edit-cliente.com"
    assert existing["status"] == "active"
    assert "client_admin" in existing["roles"]


# ---------------------------------------------------------------------------
# Phase 4 (platform rework) — role / membership management
# ---------------------------------------------------------------------------


def _detail(api_client: TestClient, token: str, user_id: str) -> dict:
    resp = api_client.get(f"/api/v1/admin/users/{user_id}", headers=_h(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_grant_membership_internal_role(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    uid = _seed_directory_user(
        db_factory,
        email="grant@seeded.test",
        role="platform_admin",
        org_name="LegalShelf Interna",
        org_kind="internal",
    )
    org_id = _detail(api_client, token, uid)["memberships"][0]["organization_id"]

    resp = api_client.post(
        f"/api/v1/admin/users/{uid}/memberships",
        json={"organization_id": org_id, "role": "operations_admin"},
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "operations_admin"
    assert body["status"] == "active"
    assert body["is_primary"] is False

    roles = {m["role"] for m in _detail(api_client, token, uid)["memberships"]}
    assert {"platform_admin", "operations_admin"} <= roles

    # Dedup — granting the same active role again is a 409.
    dup = api_client.post(
        f"/api/v1/admin/users/{uid}/memberships",
        json={"organization_id": org_id, "role": "operations_admin"},
        headers=_h(token),
    )
    assert dup.status_code == 409

    # Kind mismatch — client_admin can't live in an internal org.
    mismatch = api_client.post(
        f"/api/v1/admin/users/{uid}/memberships",
        json={"organization_id": org_id, "role": "client_admin"},
        headers=_h(token),
    )
    assert mismatch.status_code == 422


def test_grant_membership_reactivates_removed(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    uid = _seed_directory_user(
        db_factory, email="react@seeded.test", role="platform_admin", org_kind="internal"
    )
    org_id = _detail(api_client, token, uid)["memberships"][0]["organization_id"]

    granted = api_client.post(
        f"/api/v1/admin/users/{uid}/memberships",
        json={"organization_id": org_id, "role": "operations_admin"},
        headers=_h(token),
    ).json()
    mid = granted["membership_id"]
    # Revoke it…
    api_client.delete(
        f"/api/v1/admin/users/{uid}/memberships/{mid}", headers=_h(token)
    )
    # …then grant the same role again — reactivates the SAME row.
    again = api_client.post(
        f"/api/v1/admin/users/{uid}/memberships",
        json={"organization_id": org_id, "role": "operations_admin"},
        headers=_h(token),
    )
    assert again.status_code == 200, again.text
    assert again.json()["membership_id"] == mid
    assert again.json()["status"] == "active"


def test_grant_membership_enforces_client_seat_cap(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    owner = _provision_client(
        api_client, token, email="owner@cap-cli.com", client_name="Cap SA"
    )
    org_id = _detail(api_client, token, owner)["memberships"][0]["organization_id"]

    # Seat 1 is the owner; fill seats 2 and 3.
    for i in (2, 3):
        member = _seed_directory_user(db_factory, email=f"seat{i}@cap-cli.com")
        ok = api_client.post(
            f"/api/v1/admin/users/{member}/memberships",
            json={"organization_id": org_id, "role": "client_admin"},
            headers=_h(token),
        )
        assert ok.status_code == 200, ok.text

    # The 4th grant exceeds the default 3-seat cap.
    overflow = _seed_directory_user(db_factory, email="seat4@cap-cli.com")
    capped = api_client.post(
        f"/api/v1/admin/users/{overflow}/memberships",
        json={"organization_id": org_id, "role": "client_admin"},
        headers=_h(token),
    )
    assert capped.status_code == 409


def test_revoke_membership_and_block_primary(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    owner = _provision_client(
        api_client, token, email="rev-owner@cli.com", client_name="Rev SA"
    )
    memberships = _detail(api_client, token, owner)["memberships"]
    primary = next(m for m in memberships if m["is_primary"])

    # The active Primary Account Owner can't be revoked.
    blocked = api_client.delete(
        f"/api/v1/admin/users/{owner}/memberships/{primary['membership_id']}",
        headers=_h(token),
    )
    assert blocked.status_code == 409

    # A non-primary member can be.
    member = _seed_directory_user(db_factory, email="rev-member@cli.com")
    granted = api_client.post(
        f"/api/v1/admin/users/{member}/memberships",
        json={"organization_id": primary["organization_id"], "role": "client_admin"},
        headers=_h(token),
    ).json()
    removed = api_client.delete(
        f"/api/v1/admin/users/{member}/memberships/{granted['membership_id']}",
        headers=_h(token),
    )
    assert removed.status_code == 200
    assert removed.json()["status"] == "removed"


def test_revoke_membership_invalidates_targets_live_token(
    api_client: TestClient, db_factory
) -> None:
    """CW-AUTHZ-001 (HIGH) — revoking a role bumps the target user's session
    epoch, so the JWT that still carries the revoked role is rejected on the
    next request instead of authorizing until expiry."""
    admin_token = _admin_token(api_client, db_factory)
    owner = _provision_client(
        api_client, admin_token, email="re-owner@cli.com", client_name="Revoke SA"
    )
    org_id = _detail(api_client, admin_token, owner)["memberships"][0][
        "organization_id"
    ]

    # A member granted client_admin who has a usable password + live session.
    member = _seed_directory_user(db_factory, email="re-member@cli.com")
    granted = api_client.post(
        f"/api/v1/admin/users/{member}/memberships",
        json={"organization_id": org_id, "role": "client_admin"},
        headers=_h(admin_token),
    ).json()
    member_token = _login(api_client, "re-member@cli.com", "Seeded!2026")
    assert (
        api_client.get("/api/v1/auth/me", headers=_h(member_token)).status_code == 200
    )

    revoked = api_client.delete(
        f"/api/v1/admin/users/{member}/memberships/{granted['membership_id']}",
        headers=_h(admin_token),
    )
    assert revoked.status_code == 200, revoked.text

    # The pre-revoke token no longer authorizes anything.
    stale = api_client.get("/api/v1/auth/me", headers=_h(member_token))
    assert stale.status_code == 401, stale.text


def test_promote_membership_transfers_primary(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    owner = _provision_client(
        api_client, token, email="promo-owner@cli.com", client_name="Promo SA"
    )
    org_id = _detail(api_client, token, owner)["memberships"][0]["organization_id"]
    successor = _seed_directory_user(db_factory, email="successor@cli.com")
    granted = api_client.post(
        f"/api/v1/admin/users/{successor}/memberships",
        json={"organization_id": org_id, "role": "client_admin"},
        headers=_h(token),
    ).json()

    promoted = api_client.patch(
        f"/api/v1/admin/users/{successor}/memberships/{granted['membership_id']}",
        json={"is_primary": True},
        headers=_h(token),
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["is_primary"] is True

    # The old owner was demoted (one active primary per org invariant).
    owner_primary = _detail(api_client, token, owner)["memberships"][0]["is_primary"]
    assert owner_primary is False


def test_promote_viewer_to_primary_forces_approver(
    api_client: TestClient, db_factory
) -> None:
    """Making a membership the Primary Owner forces it to the Approver
    (client_admin) tier — the client seat model's lockout protection relies
    on 'the Primary Owner is always an Approver'."""
    token = _admin_token(api_client, db_factory)
    owner = _provision_client(
        api_client, token, email="vp-owner@cli.com", client_name="ViewerPrimary SA"
    )
    org_id = _detail(api_client, token, owner)["memberships"][0]["organization_id"]

    # Seed a read-only Viewer membership directly (the grant API only issues
    # Approver/staff roles, so a Viewer can only arise via the seat path).
    db = db_factory()
    try:
        viewer = User(
            email="vp-viewer@cli.com",
            password_hash=hash_password("ViewerPrimary!2026"),
            full_name="Viewer Primary",
            status="active",
        )
        db.add(viewer)
        db.flush()
        viewer_membership = Membership(
            user_id=viewer.id,
            organization_id=org_id,
            role="client_viewer",
            is_primary=False,
            status="active",
        )
        db.add(viewer_membership)
        db.commit()
        viewer_id = viewer.id
        membership_id = viewer_membership.id
    finally:
        db.close()

    promoted = api_client.patch(
        f"/api/v1/admin/users/{viewer_id}/memberships/{membership_id}",
        json={"is_primary": True},
        headers=_h(token),
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["is_primary"] is True
    # Forced to Approver so the org always retains at least one manager.
    assert promoted.json()["role"] == "client_admin"


def test_membership_404_on_foreign_membership(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    uid = _seed_directory_user(
        db_factory, email="m404@seeded.test", role="platform_admin", org_kind="internal"
    )
    resp = api_client.delete(
        f"/api/v1/admin/users/{uid}/memberships/no-such-membership",
        headers=_h(token),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Phase 5 (platform rework) — recoverable soft-delete
# ---------------------------------------------------------------------------


def test_delete_user_soft_deletes_and_frees_seats(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    uid = _provision_client(
        api_client, token, email="del@cli.com", client_name="Del SA"
    )

    # Preview first — owner is the primary of one client org.
    preview = api_client.get(
        f"/api/v1/admin/users/{uid}/deletion-preview", headers=_h(token)
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["active_memberships"] == 1
    assert preview.json()["primary_of_orgs"]  # non-empty

    deleted = api_client.request(
        "DELETE",
        f"/api/v1/admin/users/{uid}",
        json={"reason": "duplicate account"},
        headers=_h(token),
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_at"] is not None

    detail = _detail(api_client, token, uid)
    assert detail["deleted_at"] is not None
    assert detail["status"] == "disabled"
    assert detail["deletion_reason"] == "duplicate account"
    # Membership was freed (removed), so no longer active.
    assert all(m["status"] != "active" for m in detail["memberships"])

    # Hidden from the default directory, visible with include_deleted.
    default_list = api_client.get(
        "/api/v1/admin/users?q=del@cli.com", headers=_h(token)
    ).json()
    assert default_list["total"] == 0
    with_deleted = api_client.get(
        "/api/v1/admin/users?q=del@cli.com&include_deleted=true",
        headers=_h(token),
    ).json()
    assert with_deleted["total"] == 1
    assert with_deleted["items"][0]["deleted_at"] is not None


def test_delete_user_rejects_self_and_double_delete(
    api_client: TestClient, db_factory
) -> None:
    pw, email = _seed_user(
        db_factory, email="selfdel@checkwise.test", role="operations_admin"
    )
    token = _login(api_client, email, pw)
    me_id = _user_id_by_email(db_factory, email)
    # Can't delete yourself.
    own = api_client.delete(f"/api/v1/admin/users/{me_id}", headers=_h(token))
    assert own.status_code == 409

    target = _seed_directory_user(db_factory, email="victim@seeded.test")
    first = api_client.delete(
        f"/api/v1/admin/users/{target}", headers=_h(token)
    )
    assert first.status_code == 200
    again = api_client.delete(
        f"/api/v1/admin/users/{target}", headers=_h(token)
    )
    assert again.status_code == 409  # already deleted


def test_restore_user(api_client: TestClient, db_factory) -> None:
    token = _admin_token(api_client, db_factory)
    target = _seed_directory_user(db_factory, email="restoreme@seeded.test")
    api_client.delete(f"/api/v1/admin/users/{target}", headers=_h(token))

    restored = api_client.post(
        f"/api/v1/admin/users/{target}/restore", headers=_h(token)
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["status"] == "active"
    assert _detail(api_client, token, target)["deleted_at"] is None

    # Restoring a live account is a 409.
    again = api_client.post(
        f"/api/v1/admin/users/{target}/restore", headers=_h(token)
    )
    assert again.status_code == 409


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/v1/admin/users", None),
        ("GET", "/api/v1/admin/users/whatever", None),
        ("GET", "/api/v1/admin/users/whatever/deletion-preview", None),
        ("PATCH", "/api/v1/admin/users/whatever", {"status": "disabled"}),
        ("PATCH", "/api/v1/admin/users/whatever/identity", {"full_name": "X"}),
        ("DELETE", "/api/v1/admin/users/whatever", None),
        ("POST", "/api/v1/admin/users/whatever/restore", None),
        ("POST", "/api/v1/admin/users/whatever/reset-password", None),
        (
            "POST",
            "/api/v1/admin/users/whatever/memberships",
            {"organization_id": "o", "role": "platform_admin"},
        ),
        ("DELETE", "/api/v1/admin/users/whatever/memberships/m", None),
        ("PATCH", "/api/v1/admin/users/whatever/memberships/m", {"is_primary": True}),
    ],
)
def test_user_management_rejects_unauthenticated(
    api_client: TestClient, method: str, path: str, body: dict | None
) -> None:
    resp = api_client.request(method, path, json=body)
    assert resp.status_code == 401


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/v1/admin/users", None),
        ("GET", "/api/v1/admin/users/whatever", None),
        ("GET", "/api/v1/admin/users/whatever/deletion-preview", None),
        ("PATCH", "/api/v1/admin/users/whatever", {"status": "disabled"}),
        ("PATCH", "/api/v1/admin/users/whatever/identity", {"full_name": "X"}),
        ("DELETE", "/api/v1/admin/users/whatever", None),
        ("POST", "/api/v1/admin/users/whatever/restore", None),
        ("POST", "/api/v1/admin/users/whatever/reset-password", None),
        (
            "POST",
            "/api/v1/admin/users/whatever/memberships",
            {"organization_id": "o", "role": "platform_admin"},
        ),
        ("DELETE", "/api/v1/admin/users/whatever/memberships/m", None),
        ("PATCH", "/api/v1/admin/users/whatever/memberships/m", {"is_primary": True}),
    ],
)
def test_user_management_rejects_reviewer_only(
    api_client: TestClient, db_factory, method: str, path: str, body: dict | None
) -> None:
    token = _reviewer_token(api_client, db_factory)
    resp = api_client.request(method, path, json=body, headers=_h(token))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# P3 (2026-06-10 audit) — audit-log offset / real total / prefix / actor_email
# ---------------------------------------------------------------------------


def test_audit_log_offset_pages_and_total_is_real_count(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    for i in range(3):
        client_id = _seed_client_via_db(db_factory, name=f"PageCli{i}")
        api_client.patch(
            f"/api/v1/admin/clients/{client_id}",
            json={"name": f"PageCli{i} Renombrado"},
            headers=_h(token),
        )

    page1 = api_client.get(
        "/api/v1/admin/audit-log?action=admin.client.updated&limit=2",
        headers=_h(token),
    ).json()
    assert len(page1["items"]) == 2
    assert page1["total"] == 3  # real filtered count, not len(items)
    assert page1["limit"] == 2
    assert page1["offset"] == 0

    page2 = api_client.get(
        "/api/v1/admin/audit-log?action=admin.client.updated&limit=2&offset=2",
        headers=_h(token),
    ).json()
    assert len(page2["items"]) == 1
    assert page2["total"] == 3
    assert page2["offset"] == 2
    page1_ids = {item["id"] for item in page1["items"]}
    assert page2["items"][0]["id"] not in page1_ids


def test_audit_log_action_filter_is_prefix_match(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    target_id = _seed_directory_user(db_factory, email="prefix@seeded.test")
    api_client.patch(
        f"/api/v1/admin/users/{target_id}",
        json={"status": "disabled"},
        headers=_h(token),
    )
    # Unrelated action that must NOT match the admin.user prefix.
    client_id = _seed_client_via_db(db_factory, name="PrefixCli")
    api_client.patch(
        f"/api/v1/admin/clients/{client_id}",
        json={"name": "PrefixCli Renombrado"},
        headers=_h(token),
    )

    body = api_client.get(
        "/api/v1/admin/audit-log?action=admin.user", headers=_h(token)
    ).json()
    actions = {item["action"] for item in body["items"]}
    assert "admin.user_disabled" in actions
    assert all(action.startswith("admin.user") for action in actions)

    # An exact value still matches itself (strictly more forgiving).
    exact = api_client.get(
        "/api/v1/admin/audit-log?action=admin.user_disabled",
        headers=_h(token),
    ).json()
    assert {item["action"] for item in exact["items"]} == {
        "admin.user_disabled"
    }


def test_audit_log_resolves_actor_email(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    client_id = _seed_client_via_db(db_factory, name="ActorCli")
    api_client.patch(
        f"/api/v1/admin/clients/{client_id}",
        json={"name": "ActorCli Renombrado"},
        headers=_h(token),
    )

    body = api_client.get(
        "/api/v1/admin/audit-log?action=admin.client.updated",
        headers=_h(token),
    ).json()
    assert body["items"]
    assert body["items"][0]["actor_email"] == "adm@checkwise.test"
    # P1-06b: the target entity (a client) resolves to its human name, not a
    # raw UUID. The patch renamed it, so the label reflects the current name.
    assert body["items"][0]["entity_label"] == "ActorCli Renombrado"

    # A row whose actor_id is not a user id resolves to null.
    db = db_factory()
    try:
        db.add(
            AuditLog(
                action="system.cron.fired",
                entity_type="system",
                entity_id="cron",
                actor_type="system",
                actor_id="not-a-user-id",
            )
        )
        db.commit()
    finally:
        db.close()
    system_rows = api_client.get(
        "/api/v1/admin/audit-log?action=system.cron.fired", headers=_h(token)
    ).json()
    assert system_rows["items"][0]["actor_email"] is None


def test_audit_log_date_to_is_inclusive_of_the_whole_local_day(
    api_client: TestClient, db_factory
) -> None:
    """P1-06c: 'Hasta' must include the entire selected LOCAL day. A bare date
    is read as a full America/Mexico_City calendar day, so an event at 23:30
    local on the 'Hasta' day is returned and one just after midnight the next
    day is not — fixing the old ``created_at <= midnight`` 'hasta m-1' bug."""
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    token = _admin_token(api_client, db_factory)
    tz = ZoneInfo("America/Mexico_City")
    late_same_day = datetime(2026, 3, 15, 23, 30, tzinfo=tz).astimezone(UTC)
    early_next_day = datetime(2026, 3, 16, 0, 30, tzinfo=tz).astimezone(UTC)

    db = db_factory()
    try:
        db.add_all(
            [
                AuditLog(
                    action="system.boundarytest.fired",
                    entity_type="system",
                    entity_id="late-2026-03-15",
                    actor_type="system",
                    actor_id="boundary",
                    created_at=late_same_day,
                ),
                AuditLog(
                    action="system.boundarytest.fired",
                    entity_type="system",
                    entity_id="early-2026-03-16",
                    actor_type="system",
                    actor_id="boundary",
                    created_at=early_next_day,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    # date_to = the "Hasta" day → includes the 23:30 row, excludes next-day.
    hasta = api_client.get(
        "/api/v1/admin/audit-log",
        params={"action": "system.boundarytest.fired", "date_to": "2026-03-15"},
        headers=_h(token),
    ).json()
    hasta_ids = {item["entity_id"] for item in hasta["items"]}
    assert "late-2026-03-15" in hasta_ids
    assert "early-2026-03-16" not in hasta_ids

    # date_from = the next day → includes only the next-day row.
    desde = api_client.get(
        "/api/v1/admin/audit-log",
        params={"action": "system.boundarytest.fired", "date_from": "2026-03-16"},
        headers=_h(token),
    ).json()
    desde_ids = {item["entity_id"] for item in desde["items"]}
    assert "early-2026-03-16" in desde_ids
    assert "late-2026-03-15" not in desde_ids


def test_users_filter_provider_surfaces_workspace_owner(
    api_client: TestClient, db_factory
) -> None:
    """P1-05: role=provider returns ProviderWorkspace-owner accounts (which hold
    no membership), tagged with the synthetic 'provider' role and carrying their
    vendor/client association — and excludes them from membership-role filters."""
    token = _admin_token(api_client, db_factory)
    db = db_factory()
    try:
        client = Client(name="Cliente Prov Test", rfc="CPT260101AB1")
        db.add(client)
        db.flush()
        vendor = Vendor(
            client_id=client.id,
            name="Proveedor Uno",
            rfc="PRV260101XY2",
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()
        prov_user = User(
            email="prov.login@cw.test",
            password_hash="x",
            full_name="Proveedor Uno Login",
            status="active",
        )
        db.add(prov_user)
        db.flush()
        ws = ProviderWorkspace(
            client_id=client.id,
            vendor_id=vendor.id,
            persona_type="moral",
            display_name="Proveedor Uno",
            access_token="tok-prov-1",
            owner_user_id=prov_user.id,
            status="active",
        )
        db.add(ws)
        db.commit()
        prov_user_id = prov_user.id
        vendor_id = vendor.id
        client_name = client.name
    finally:
        db.close()

    # role=provider returns the workspace owner with its vendor/client.
    body = api_client.get(
        "/api/v1/admin/users", params={"role": "provider"}, headers=_h(token)
    ).json()
    by_id = {u["user_id"]: u for u in body["items"]}
    assert prov_user_id in by_id, "provider login should appear under role=provider"
    row = by_id[prov_user_id]
    assert "provider" in row["roles"]
    assert row["provider_workspaces"], "vendor/client association should be present"
    assert row["provider_workspaces"][0]["vendor_id"] == vendor_id
    assert row["provider_workspaces"][0]["client_name"] == client_name

    # The provider login must NOT appear under a membership-role filter.
    cadmin = api_client.get(
        "/api/v1/admin/users",
        params={"role": "client_admin"},
        headers=_h(token),
    ).json()
    assert prov_user_id not in {u["user_id"] for u in cadmin["items"]}


def test_metadata_catalog_documents_the_rulebook(
    api_client: TestClient, db_factory
) -> None:
    """P2-09: the catalog endpoint exposes the rulebook — document types with
    their metadata fields, sources, and review flags — for the explainer."""
    token = _admin_token(api_client, db_factory)
    resp = api_client.get("/api/v1/admin/metadata/catalog", headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rulebook_title"]
    assert body["document_types"], "should list document types"
    # Extraction-method glossary is present and covers the human-review source.
    assert "human_review" in body["extraction_methods"]
    # Each doc type carries fields with the expected shape + a bucketed level.
    first = body["document_types"][0]
    assert first["code"] and first["name"]
    assert first["fields"], "a doc type should expose its metadata fields"
    field = first["fields"][0]
    assert {
        "key",
        "label",
        "requirement_level",
        "extraction_methods",
        "human_review_required",
    }.issubset(field.keys())
    assert field["requirement_level"] in (
        "required",
        "conditional",
        "optional",
        "blank",
    )


def test_calendar_radar_returns_forward_shape(
    api_client: TestClient, db_factory
) -> None:
    """P2-07: the admin calendar radar returns the forward operational shape —
    urgency buckets/bands, an awaiting-review count, and a (possibly empty)
    upcoming list — without erroring on an empty portfolio."""
    token = _admin_token(api_client, db_factory)
    resp = api_client.get("/api/v1/admin/calendar/radar", headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "as_of" in body
    assert isinstance(body["upcoming"], list)
    assert {"week", "fortnight", "month", "later"}.issubset(
        body["urgency_buckets"].keys()
    )
    assert body["urgency_bands"], "urgency band labels for the FE"
    assert isinstance(body["awaiting_review_total"], int)
    assert body["truncated"] is False


def test_calendar_grid_empty_portfolio_shape(
    api_client: TestClient, db_factory
) -> None:
    """The grid returns the full clients×months shape on an empty portfolio
    without erroring — 12-slot month_totals/forecast, integer triage, and no
    obligations until a month/client is selected."""
    token = _admin_token(api_client, db_factory)
    resp = api_client.get("/api/v1/admin/calendar/grid", headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["level"] == "clients"
    assert body["rows"] == []
    assert body["cells"] == []
    assert len(body["month_totals"]) == 12
    assert len(body["forecast"]) == 12
    assert body["triage"]["overdue_total"] == 0
    assert body["triage"]["due_7d_total"] == 0
    assert body["obligations"] == []
    assert body["truncated"] is False


def test_calendar_grid_rolls_clients_into_month_cells(
    api_client: TestClient, db_factory
) -> None:
    """With a seeded client/vendor/workspace the grid produces a client row,
    risk-tinted month cells whose counts sum to the forecast totals, and —
    only when a month or client is selected — the obligation detail."""
    token = _admin_token(api_client, db_factory)
    _seed_workspace(db_factory)

    resp = api_client.get(
        "/api/v1/admin/calendar/grid?year=2026", headers=_h(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["level"] == "clients"
    assert body["clients_scanned"] == 1
    rows = body["rows"]
    assert len(rows) == 1 and rows[0]["name"] == "Cli ws"
    client_id = rows[0]["id"]
    assert rows[0]["semaphore_level"] in {"red", "yellow", "green"}

    cells = body["cells"]
    assert cells, "a seeded moral workspace must place obligations on months"
    risk_vocab = {
        "overdue",
        "action_required",
        "due_soon",
        "in_review",
        "upcoming",
        "on_track",
    }
    for cell in cells:
        assert 1 <= cell["month"] <= 12
        assert cell["count"] >= 1
        assert cell["worst_risk"] in risk_vocab
        # by_institution now carries per-institution {count, worst_risk} so the
        # FE can recolor the grid by a single authority client-side.
        assert sum(v["count"] for v in cell["by_institution"].values()) == cell["count"]
        for v in cell["by_institution"].values():
            assert v["worst_risk"] in risk_vocab
        assert cell["row_id"] == client_id

    # Grid cell counts and the forecast strip come from the same aggregate.
    cell_total = sum(c["count"] for c in cells)
    assert cell_total == sum(body["month_totals"]) == sum(
        f["total"] for f in body["forecast"]
    )
    # Overview without a month selection carries no obligation detail — the
    # detail rows load per-client on drill instead.
    assert body["obligations"] == []
    assert body["clients_total"] == 1

    # The per-month status summary (expected vs delivered) lets the FE render a
    # month without a refetch; expected must equal the month's forecast total.
    assert len(body["month_status"]) == 12
    for ms in body["month_status"]:
        assert ms["expected"] == body["month_totals"][ms["month"] - 1]
        assert 0 <= ms["delivered"] <= ms["expected"]
        for inst_status in ms["by_institution"].values():
            assert inst_status["delivered"] <= inst_status["expected"]

    # A month with load returns its obligations across the portfolio.
    busiest = max(body["forecast"], key=lambda f: f["total"])
    month_resp = api_client.get(
        f"/api/v1/admin/calendar/grid?year=2026&month={busiest['month']}",
        headers=_h(token),
    )
    assert month_resp.status_code == 200, month_resp.text
    month_body = month_resp.json()
    assert month_body["obligations"], "selected month must surface its detail"
    for ob in month_body["obligations"]:
        assert ob["due_month"] == busiest["month"]
        assert ob["client_name"] == "Cli ws"
        assert ob["risk_level"] in risk_vocab

    # Drilling a client switches the grid to its providers×months.
    drill_resp = api_client.get(
        f"/api/v1/admin/calendar/grid?year=2026&client_id={client_id}",
        headers=_h(token),
    )
    assert drill_resp.status_code == 200, drill_resp.text
    drill_body = drill_resp.json()
    assert drill_body["level"] == "providers"
    assert drill_body["client_name"] == "Cli ws"
    assert any(r["name"] == "Vendor ws" for r in drill_body["rows"])
    assert drill_body["obligations"], "drill carries the client's obligations"


def test_calendar_renewals_returns_lane_shape(
    api_client: TestClient, db_factory
) -> None:
    """The renewals lane returns contract-expiry + credential-renewal lists
    (urgency-sorted, possibly empty) without erroring on a thin portfolio."""
    token = _admin_token(api_client, db_factory)
    _seed_workspace(db_factory)
    resp = api_client.get(
        "/api/v1/admin/calendar/renewals?horizon_days=120", headers=_h(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "as_of" in body
    assert isinstance(body["contracts"], list)
    assert isinstance(body["credentials"], list)
    assert body["truncated"] is False
    # Contracts are overdue-first (ascending days_until).
    days = [c["days_until"] for c in body["contracts"]]
    assert days == sorted(days)
    for c in body["contracts"]:
        assert c["status"] in {"overdue", "due_soon", "upcoming"}
    for c in body["credentials"]:
        assert c["status"] in {"overdue", "due_soon"}


def test_calendar_grid_serves_from_snapshot(
    api_client: TestClient, db_factory
) -> None:
    """A forced refresh populates the per-client snapshot; subsequent overview
    loads are served from it (snapshot_at set) and match the live scan exactly —
    the same cells, totals and triage, without re-scanning."""
    token = _admin_token(api_client, db_factory)
    _seed_workspace(db_factory)

    # The live month path (?month=) bypasses the snapshot — use it as the oracle.
    live = api_client.get(
        "/api/v1/admin/calendar/grid?year=2026&month=1", headers=_h(token)
    ).json()

    # Force-refresh builds the snapshot, then the response is served from it.
    forced = api_client.get(
        "/api/v1/admin/calendar/grid?year=2026&refresh=true", headers=_h(token)
    ).json()
    assert forced["snapshot_at"], "a forced refresh is served from the snapshot"

    # A plain overview load is now served from the snapshot (no scan).
    cached = api_client.get(
        "/api/v1/admin/calendar/grid?year=2026", headers=_h(token)
    ).json()
    assert cached["snapshot_at"], "the warm overview is served from the snapshot"

    # Parity: snapshot-served numbers equal the live scan.
    def _cellmap(body: dict) -> dict:
        return {
            (c["row_id"], c["month"]): (c["count"], c["worst_risk"])
            for c in body["cells"]
        }

    assert _cellmap(cached) == _cellmap(live)
    assert cached["month_totals"] == live["month_totals"]
    assert cached["triage"] == live["triage"]
    assert cached["clients_total"] == live["clients_total"]
    # Per-institution cell detail survives the round-trip through the cache.
    for c in cached["cells"]:
        assert sum(v["count"] for v in c["by_institution"].values()) == c["count"]


# ---------------------------------------------------------------------------
# Side co-admins (full operations_admin peers) + owner-lock
# 2026-06-30 — operations-console consolidation. Provisioning a staff
# account now defaults to a full co-administrator (operations_admin); the
# protected platform owner can never be disabled / demoted / deleted /
# password-reset through these routes, even by a peer co-admin.
# ---------------------------------------------------------------------------

OWNER_EMAIL = "jsamano@legalshelf.mx"


def _provision_admin(
    api_client: TestClient,
    token: str,
    *,
    email: str,
    full_name: str = "Co Admin",
    admin_role: str | None = None,
) -> str:
    """Provision a staff account via ``POST /admin/users`` (role=admin).

    Omitting ``admin_role`` exercises the default — a full
    co-administrator (operations_admin)."""
    body: dict = {"role": "admin", "full_name": full_name, "email": email}
    if admin_role is not None:
        body["admin_role"] = admin_role
    resp = api_client.post("/api/v1/admin/users", json=body, headers=_h(token))
    assert resp.status_code == 201, resp.text
    return resp.json()["user_id"]


def _active_membership_roles(db_factory, user_id: str) -> set[str]:
    db = db_factory()
    try:
        return set(
            db.scalars(
                select(Membership.role).where(
                    Membership.user_id == user_id,
                    Membership.status == "active",
                )
            )
        )
    finally:
        db.close()


def test_provision_admin_defaults_to_full_co_admin(
    api_client: TestClient, db_factory
) -> None:
    """A staff account provisioned with no explicit tier is a full
    co-administrator (operations_admin), not the review team."""
    token = _admin_token(api_client, db_factory)
    uid = _provision_admin(api_client, token, email="coadmin@example.com")
    assert _active_membership_roles(db_factory, uid) == {"operations_admin"}


def test_provision_admin_can_request_review_team_tier(
    api_client: TestClient, db_factory
) -> None:
    """``admin_role=platform_admin`` still provisions a review-only
    staffer for callers who want the narrower tier."""
    token = _admin_token(api_client, db_factory)
    uid = _provision_admin(
        api_client,
        token,
        email="reviewer2@example.com",
        admin_role="platform_admin",
    )
    assert _active_membership_roles(db_factory, uid) == {"platform_admin"}


def test_co_admin_can_manage_a_peer_co_admin(
    api_client: TestClient, db_factory
) -> None:
    """Full co-admins are real peers: one operations_admin may disable
    another (non-owner) operations_admin. The protected owner is the only
    account fenced off (asserted below)."""
    token = _admin_token(api_client, db_factory)  # adm@… , operations_admin
    peer = _seed_directory_user(
        db_factory,
        email="peer@seeded.test",
        role="operations_admin",
        org_kind="internal",
    )
    resp = api_client.patch(
        f"/api/v1/admin/users/{peer}",
        json={"status": "disabled"},
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text


def _owner_and_peer(api_client: TestClient, db_factory) -> tuple[str, str]:
    """Seed the protected owner; return (peer co-admin token, owner id)."""
    _seed_user(db_factory, email=OWNER_EMAIL, role="operations_admin")
    owner_id = _user_id_by_email(db_factory, OWNER_EMAIL)
    peer_token = _admin_token(api_client, db_factory)  # a different ops_admin
    return peer_token, owner_id


def test_owner_cannot_be_disabled_by_a_peer_co_admin(
    api_client: TestClient, db_factory
) -> None:
    token, owner_id = _owner_and_peer(api_client, db_factory)
    resp = api_client.patch(
        f"/api/v1/admin/users/{owner_id}",
        json={"status": "disabled"},
        headers=_h(token),
    )
    assert resp.status_code == 403, resp.text
    assert "propietaria" in resp.json()["detail"]
    db = db_factory()
    try:
        assert db.get(User, owner_id).status == "active"
    finally:
        db.close()


def test_owner_password_cannot_be_reset_by_a_peer_co_admin(
    api_client: TestClient, db_factory
) -> None:
    token, owner_id = _owner_and_peer(api_client, db_factory)
    resp = api_client.post(
        f"/api/v1/admin/users/{owner_id}/reset-password", headers=_h(token)
    )
    assert resp.status_code == 403, resp.text


def test_owner_cannot_be_soft_deleted_by_a_peer_co_admin(
    api_client: TestClient, db_factory
) -> None:
    token, owner_id = _owner_and_peer(api_client, db_factory)
    resp = api_client.delete(
        f"/api/v1/admin/users/{owner_id}", headers=_h(token)
    )
    assert resp.status_code == 403, resp.text
    db = db_factory()
    try:
        assert db.get(User, owner_id).deleted_at is None
    finally:
        db.close()


def test_owner_role_cannot_be_revoked_by_a_peer_co_admin(
    api_client: TestClient, db_factory
) -> None:
    token, owner_id = _owner_and_peer(api_client, db_factory)
    membership_id = _detail(api_client, token, owner_id)["memberships"][0][
        "membership_id"
    ]
    resp = api_client.delete(
        f"/api/v1/admin/users/{owner_id}/memberships/{membership_id}",
        headers=_h(token),
    )
    assert resp.status_code == 403, resp.text
    assert _active_membership_roles(db_factory, owner_id) == {"operations_admin"}
