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
    pw, email = _seed_user(db_factory, email="adm@checkwise.test", role="internal_admin")
    return _login(api_client, email, pw)


def _reviewer_token(api_client: TestClient, db_factory) -> str:
    pw, email = _seed_user(db_factory, email="rev@checkwise.test", role="reviewer")
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


def test_overview_rejects_reviewer_only(
    api_client: TestClient, db_factory
) -> None:
    token = _reviewer_token(api_client, db_factory)
    resp = api_client.get("/api/v1/admin/overview", headers=_h(token))
    assert resp.status_code == 403


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
        assert row.actor_type == "internal_admin"
        assert row.actor_id is not None
        meta = row.event_metadata or {}
        assert meta.get("source") == "admin_operations"
        if before_must_be_none:
            assert row.before is None
        return row
    finally:
        db.close()


def test_admin_can_create_client_and_write_audit(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    resp = api_client.post(
        "/api/v1/admin/clients",
        json={
            "name": "Cliente Admin Test",
            "rfc": "CAT260512AB1",
            "email": "ada@test.example",
            "responsible_name": "Ada Lovelace",
        },
        headers=_h(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Cliente Admin Test"
    assert body["rfc"] == "CAT260512AB1"
    assert body["email"] == "ada@test.example"
    _assert_audit_admin(
        db_factory, action="admin.client.created", entity_id=body["id"], before_must_be_none=True
    )


def test_admin_can_update_client_and_write_audit(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    created = api_client.post(
        "/api/v1/admin/clients",
        json={"name": "Cliente A", "email": "a@test.example"},
        headers=_h(token),
    ).json()
    resp = api_client.patch(
        f"/api/v1/admin/clients/{created['id']}",
        json={"name": "Cliente A Renombrado", "status": "inactive"},
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Cliente A Renombrado"
    assert resp.json()["status"] == "inactive"
    row = _assert_audit_admin(
        db_factory, action="admin.client.updated", entity_id=created["id"]
    )
    assert (row.before or {}).get("name") == "Cliente A"
    assert (row.after or {}).get("name") == "Cliente A Renombrado"


def test_admin_client_create_requires_email(
    api_client: TestClient, db_factory
) -> None:
    """Junta 2026-05-23 — RFC + email + nombre son los datos mínimos
    al dar de alta un cliente. Sin email la API responde 422 y no
    persiste nada.
    """
    token = _admin_token(api_client, db_factory)
    resp = api_client.post(
        "/api/v1/admin/clients",
        json={"name": "Sin Email"},
        headers=_h(token),
    )
    assert resp.status_code == 422, resp.text


def test_admin_client_email_normalized_and_returned(
    api_client: TestClient, db_factory
) -> None:
    """Email se normaliza a minúsculas y se devuelve en el payload."""
    token = _admin_token(api_client, db_factory)
    resp = api_client.post(
        "/api/v1/admin/clients",
        json={"name": "Caso Email", "email": "  Mixed.Case@Example.com  "},
        headers=_h(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == "mixed.case@example.com"


# ---------------------------------------------------------------------------
# Vendors
# ---------------------------------------------------------------------------


def test_admin_can_create_vendor_for_existing_client(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    client = api_client.post(
        "/api/v1/admin/clients",
        json={"name": "Cli", "email": "cli@test.example"},
        headers=_h(token),
    ).json()
    resp = api_client.post(
        "/api/v1/admin/vendors",
        json={
            "client_id": client["id"],
            "name": "Proveedor X",
            "rfc": "PVX260512AB1",
            "contact_email": "ops@x.test",
            "persona_type": "moral",
        },
        headers=_h(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["client_id"] == client["id"]
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


def test_admin_can_update_vendor_and_write_audit(
    api_client: TestClient, db_factory
) -> None:
    token = _admin_token(api_client, db_factory)
    client = api_client.post(
        "/api/v1/admin/clients",
        json={"name": "Cli", "email": "cli2@test.example"},
        headers=_h(token),
    ).json()
    vendor = api_client.post(
        "/api/v1/admin/vendors",
        json={"client_id": client["id"], "name": "Proveedor Antes", "rfc": "PVA260512AB1"},
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
    # Create three clients to seed three audit rows.
    ids = []
    for i in range(3):
        body = api_client.post(
            "/api/v1/admin/clients",
            json={"name": f"AuditCli{i}", "email": f"audit{i}@test.example"},
            headers=_h(token),
        ).json()
        ids.append(body["id"])

    # Filter by action — should return exactly the 3 client.created rows.
    resp = api_client.get(
        "/api/v1/admin/audit-log?action=admin.client.created",
        headers=_h(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    actions = {item["action"] for item in body["items"]}
    assert actions == {"admin.client.created"}
    assert len(body["items"]) >= 3

    # Filter by entity_id — should return exactly one row.
    by_entity = api_client.get(
        f"/api/v1/admin/audit-log?entity_id={ids[0]}", headers=_h(token)
    ).json()
    assert len(by_entity["items"]) == 1
    assert by_entity["items"][0]["entity_id"] == ids[0]

    # Respect limit.
    limited = api_client.get(
        "/api/v1/admin/audit-log?limit=2", headers=_h(token)
    ).json()
    assert len(limited["items"]) <= 2
    assert limited["limit"] == 2

    # Filter by entity_type narrows to the right rows.
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
