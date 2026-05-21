"""Phase 1 — tenant-safe workspace-scoped provider upload.

Covers ``POST /api/v1/portal/workspaces/{workspace_id}/submissions``:
the replacement for the legacy ``POST /api/v1/submissions``. Tenant
identity (client / vendor / contract) is derived from the authenticated
``ProviderWorkspace`` instead of browser-posted form fields.

Tests in this module assert:

* Happy path for the authenticated owner.
* Unauthenticated and foreign-workspace callers are rejected.
* A spoofed form body (``client_name=EVIL CO`` etc.) is ignored: the
  resulting submission still binds to ``workspace.client_id`` and
  ``workspace.vendor_id``.
* Canonical ``requirement_code`` / ``period_key`` persist.
* The full audit trail (``validation_events``, ``DocumentInspection``,
  ``DocumentStatusHistory``, ``AuditLog``) is written with the
  ``workspace_portal_intake`` marker.
* Legacy ``POST /api/v1/submissions`` keeps working as a regression
  smoke check.
"""

from __future__ import annotations

import itertools
from collections.abc import Generator
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (  # noqa: F401 — ensure mappers register
    AuditLog,
    Client,
    Document,
    DocumentInspection,
    DocumentStatusHistory,
    ProviderWorkspace,
    Submission,
    User,
    ValidationEvent,
    Vendor,
    entities,
)
from app.services.auth import hash_password, issue_access_token


@pytest.fixture
def api_client(tmp_path) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    previous = settings.LOCAL_STORAGE_PATH
    settings.LOCAL_STORAGE_PATH = str(tmp_path / "storage")
    previous_export_path = settings.METADATA_EXPORT_PATH
    previous_auto_export = settings.AUTO_METADATA_EXPORT_ENABLED
    settings.METADATA_EXPORT_PATH = str(tmp_path / "metadata_exports")
    settings.AUTO_METADATA_EXPORT_ENABLED = True

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.app.state.testing_session = testing_session  # type: ignore[attr-defined]
    try:
        yield client
    finally:
        app.dependency_overrides.clear()
        settings.LOCAL_STORAGE_PATH = previous
        settings.METADATA_EXPORT_PATH = previous_export_path
        settings.AUTO_METADATA_EXPORT_ENABLED = previous_auto_export


def _pdf_bytes() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()


_user_seq = itertools.count(1)


def _setup_workspace(
    api_client: TestClient,
    *,
    vendor_name: str = "Servicios Demo SA de CV",
    vendor_rfc: str = "DEM260512AB1",
    client_name: str = "Cliente Piloto CheckWise",
    fresh_client: TestClient | None = None,
) -> dict:
    """Seed User+Client+Vendor+ProviderWorkspace, then call /portal/enter.

    Returns a dict with ``workspace_id``, ``access_token`` (rotated),
    ``client_id``, ``vendor_id``, and ``bearer`` (a fresh JWT for the
    owning user that can be sent via the Authorization header).
    """
    target_client = fresh_client or api_client
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        seq = next(_user_seq)
        user = User(
            email=f"prov-{seq}@checkwise.test",
            password_hash=hash_password("CheckWiseTest!2026"),
            full_name=vendor_name,
            status="active",
            must_change_password=False,
        )
        db.add(user)
        db.flush()

        existing_client = db.query(Client).filter_by(name=client_name).first()
        if existing_client is None:
            client_row = Client(name=client_name)
            db.add(client_row)
            db.flush()
        else:
            client_row = existing_client

        vendor = Vendor(
            client_id=client_row.id,
            name=vendor_name,
            rfc=vendor_rfc.upper(),
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()

        workspace = ProviderWorkspace(
            client_id=client_row.id,
            vendor_id=vendor.id,
            owner_user_id=user.id,
            persona_type="moral",
            display_name=vendor_name,
            access_token="placeholder-rotated-on-enter",
        )
        db.add(workspace)
        db.commit()
        ws_id = workspace.id
        client_id = client_row.id
        vendor_id = vendor.id
        user_id = user.id
        user_email = user.email
    finally:
        db.close()

    token = issue_access_token(user_id=user_id, email=user_email, roles=[], orgs=[])
    target_client.cookies.clear()
    enter = target_client.post(
        "/api/v1/portal/enter",
        json={"workspace_id": ws_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert enter.status_code == 200, enter.text

    db = factory()
    try:
        ws_row = db.get(ProviderWorkspace, ws_id)
        rotated_token = ws_row.access_token if ws_row else ""
    finally:
        db.close()

    return {
        "workspace_id": ws_id,
        "access_token": rotated_token,
        "client_id": client_id,
        "vendor_id": vendor_id,
        "bearer": token,
        "vendor_rfc": vendor_rfc.upper(),
        "client_name": client_name,
        "vendor_name": vendor_name,
    }


def _canonical_intake_payload() -> tuple[dict, object]:
    """Build (form-data, catalog-item) for an INFONAVIT B1 canonical upload."""
    from app.core.compliance_catalog import recurring_for_year

    catalog_item = next(
        item
        for item in recurring_for_year(2026)
        if item.institution == "infonavit" and item.period_key == "2026-B1"
    )
    data = {
        "period_code": "2026-B1",
        "period_key": catalog_item.period_key,
        "load_type": "bimestral",
        "institution_code": "infonavit",
        "requirement_name": catalog_item.name,
        "requirement_code": catalog_item.code,
        "initial_status": "pendiente_revision",
        "comments": "Carga de prueba — Phase 1",
    }
    return data, catalog_item


# ---------------------------------------------------------------------------
# Happy path + auth gates
# ---------------------------------------------------------------------------


def test_workspace_upload_happy_path(api_client: TestClient) -> None:
    """Authenticated owner uploads a canonical PDF to their workspace."""
    ws = _setup_workspace(api_client)
    data, _ = _canonical_intake_payload()
    response = api_client.post(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/submissions",
        data=data,
        files={"file": ("infonavit.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "pendiente_revision"
    assert body["sha256"]
    assert body["storage_key"].endswith("infonavit.pdf")
    assert body["inspection"]["is_pdf"] is True

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        event = db.scalar(
            select(ValidationEvent)
            .where(
                ValidationEvent.submission_id == body["submission_id"],
                ValidationEvent.event_type == "metadata_table_exported",
            )
            .limit(1)
        )
        assert event is not None
        assert event.result == "completed"
        assert event.payload is not None
        assert event.payload["document_type_code"] == "comprobante_pago_bancario_infonavit"
        output_path = event.payload["output_path"]
        latest_path = event.payload["latest_path"]
        assert output_path and output_path.endswith("_metadata.xlsx")
        assert latest_path and latest_path.endswith("latest_metadata.xlsx")
        assert Path(output_path).exists()
        assert Path(latest_path).exists()
    finally:
        db.close()


def test_workspace_upload_rejects_unauthenticated(api_client: TestClient) -> None:
    """No JWT, no cookie, no header → 401 from the tenant guard."""
    ws = _setup_workspace(api_client)
    api_client.cookies.clear()
    data, _ = _canonical_intake_payload()
    response = api_client.post(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/submissions",
        data=data,
        files={"file": ("x.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 401


def test_workspace_upload_rejects_foreign_workspace(api_client: TestClient) -> None:
    """User B's JWT cannot upload to user A's workspace."""
    ws_a = _setup_workspace(api_client)
    fresh = TestClient(api_client.app)
    fresh.app.state.testing_session = api_client.app.state.testing_session  # type: ignore[attr-defined]
    ws_b = _setup_workspace(
        api_client,
        vendor_name="Otro Proveedor SA",
        vendor_rfc="OTR260512AB1",
        fresh_client=fresh,
    )
    data, _ = _canonical_intake_payload()
    # B has a session cookie + bearer JWT; both must reject the path.
    response = fresh.post(
        f"/api/v1/portal/workspaces/{ws_a['workspace_id']}/submissions",
        data=data,
        files={"file": ("x.pdf", _pdf_bytes(), "application/pdf")},
        headers={"Authorization": f"Bearer {ws_b['bearer']}"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Tenant-spoof resistance
# ---------------------------------------------------------------------------


def test_workspace_upload_ignores_spoofed_tenant_identity(api_client: TestClient) -> None:
    """A spoofed body cannot redirect the submission to another tenant.

    The endpoint deliberately does not declare client_name/vendor_name/
    vendor_rfc/contract_reference as Form fields. FastAPI drops the
    extra fields, and the submission binds to workspace.client_id /
    workspace.vendor_id regardless of what the form claims.
    """
    ws = _setup_workspace(api_client)
    data, _ = _canonical_intake_payload()
    spoof = {
        **data,
        "client_name": "Cliente Atacante",
        "vendor_name": "EVIL CO SA de CV",
        "vendor_rfc": "EVL010101XXX",
        "contract_reference": "ATTACKER-CONTRACT-001",
    }
    response = api_client.post(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/submissions",
        data=spoof,
        files={"file": ("x.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 202, response.text
    submission_id = response.json()["submission_id"]

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        sub = db.get(Submission, submission_id)
        assert sub is not None
        # Identity binds to the authenticated workspace, not the spoof.
        assert sub.client_id == ws["client_id"]
        assert sub.vendor_id == ws["vendor_id"]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Canonical key persistence
# ---------------------------------------------------------------------------


def test_workspace_upload_persists_requirement_code_and_period_key(
    api_client: TestClient,
) -> None:
    ws = _setup_workspace(api_client)
    data, catalog_item = _canonical_intake_payload()
    response = api_client.post(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/submissions",
        data=data,
        files={"file": ("inf.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 202, response.text
    submission_id = response.json()["submission_id"]

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        sub = db.get(Submission, submission_id)
        assert sub is not None
        assert sub.requirement_code == catalog_item.code
        assert sub.period_key == catalog_item.period_key
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Auditable side effects
# ---------------------------------------------------------------------------


def test_workspace_upload_writes_validation_events(api_client: TestClient) -> None:
    ws = _setup_workspace(api_client)
    data, _ = _canonical_intake_payload()
    response = api_client.post(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/submissions",
        data=data,
        files={"file": ("inf.pdf", _pdf_bytes(), "application/pdf")},
    )
    submission_id = response.json()["submission_id"]

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        events = list(
            db.scalars(
                select(ValidationEvent).where(ValidationEvent.submission_id == submission_id)
            )
        )
        event_types = {e.event_type for e in events}
        assert {"upload_started", "file_received", "pdf_inspected"} <= event_types
    finally:
        db.close()


def test_workspace_upload_writes_document_inspection(api_client: TestClient) -> None:
    ws = _setup_workspace(api_client)
    data, _ = _canonical_intake_payload()
    response = api_client.post(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/submissions",
        data=data,
        files={"file": ("inf.pdf", _pdf_bytes(), "application/pdf")},
    )
    submission_id = response.json()["submission_id"]

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        doc = db.scalar(select(Document).where(Document.submission_id == submission_id))
        assert doc is not None
        inspection = db.scalar(
            select(DocumentInspection).where(DocumentInspection.document_id == doc.id)
        )
        assert inspection is not None
        assert inspection.is_pdf is True
    finally:
        db.close()


def test_workspace_upload_writes_status_history(api_client: TestClient) -> None:
    ws = _setup_workspace(api_client)
    data, _ = _canonical_intake_payload()
    response = api_client.post(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/submissions",
        data=data,
        files={"file": ("inf.pdf", _pdf_bytes(), "application/pdf")},
    )
    submission_id = response.json()["submission_id"]

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        history = list(
            db.scalars(
                select(DocumentStatusHistory).where(
                    DocumentStatusHistory.submission_id == submission_id
                )
            )
        )
        assert history, "expected at least one DocumentStatusHistory row"
        first = history[0]
        assert first.from_status is None
        assert first.to_status == "pendiente_revision"
        # History reason should clearly identify the workspace intake path.
        assert "workspace" in (first.reason or "").lower()
    finally:
        db.close()


def test_workspace_upload_writes_audit_log_with_workspace_marker(
    api_client: TestClient,
) -> None:
    """Audit log must carry the workspace_portal_intake marker + workspace_id."""
    ws = _setup_workspace(api_client)
    data, _ = _canonical_intake_payload()
    response = api_client.post(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/submissions",
        data=data,
        files={"file": ("inf.pdf", _pdf_bytes(), "application/pdf")},
    )
    submission_id = response.json()["submission_id"]

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_type == "submission",
                AuditLog.entity_id == submission_id,
            )
        )
        assert audit is not None
        meta = audit.event_metadata or {}
        assert meta.get("intake_source") == "workspace_portal_intake"
        assert meta.get("workspace_id") == ws["workspace_id"]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Legacy endpoint regression smoke
# ---------------------------------------------------------------------------


def test_legacy_submissions_endpoint_still_works(api_client: TestClient) -> None:
    """Refactor must not regress the legacy free-text endpoint."""
    response = api_client.post(
        "/api/v1/submissions",
        data={
            "client_name": "Cliente Piloto",
            "vendor_name": "Proveedor REPSE SA de CV",
            "vendor_rfc": "ABC010203AB1",
            "period_code": "2026-05",
            "load_type": "mensual",
            "institution_code": "sat",
            "requirement_name": "Opinión de cumplimiento SAT positiva",
            "initial_status": "pendiente_revision",
        },
        files={"file": ("opinion.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 202, response.text
    submission_id = response.json()["submission_id"]

    # Audit metadata must mark this path as legacy_native_intake.
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_type == "submission",
                AuditLog.entity_id == submission_id,
            )
        )
        assert audit is not None
        assert (audit.event_metadata or {}).get("intake_source") == "legacy_native_intake"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Phase 3 — replacement lineage on workspace uploads
# ---------------------------------------------------------------------------


def _set_status(api_client: TestClient, submission_id: str, status_value: str) -> None:
    """Force a submission into the requested status without going through the
    reviewer workflow. The reviewer flow is exercised in its own test
    module — here we only want the lineage validation, so a direct DB
    poke keeps the test focused.
    """
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        sub = db.get(Submission, submission_id)
        assert sub is not None
        sub.status = status_value
        db.commit()
    finally:
        db.close()


def _upload(
    api_client: TestClient,
    workspace_id: str,
    *,
    data: dict | None = None,
    supersedes_submission_id: str | None = None,
    filename: str = "inf.pdf",
):
    payload, _ = _canonical_intake_payload()
    if data:
        payload = {**payload, **data}
    if supersedes_submission_id is not None:
        payload["supersedes_submission_id"] = supersedes_submission_id
    return api_client.post(
        f"/api/v1/portal/workspaces/{workspace_id}/submissions",
        data=payload,
        files={"file": (filename, _pdf_bytes(), "application/pdf")},
    )


def test_workspace_upload_supersedes_eligible_rejected_prior(
    api_client: TestClient,
) -> None:
    """Happy path: a rejected prior can be replaced by a new upload."""
    ws = _setup_workspace(api_client)
    first = _upload(api_client, ws["workspace_id"])
    assert first.status_code == 202, first.text
    prior_id = first.json()["submission_id"]
    _set_status(api_client, prior_id, "rechazado")

    second = _upload(
        api_client,
        ws["workspace_id"],
        supersedes_submission_id=prior_id,
        filename="inf-fix.pdf",
    )
    assert second.status_code == 202, second.text
    new_id = second.json()["submission_id"]
    assert new_id != prior_id

    # Persisted lineage.
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        new_sub = db.get(Submission, new_id)
        assert new_sub is not None
        assert new_sub.supersedes_submission_id == prior_id
    finally:
        db.close()


def test_workspace_upload_replacement_404_on_foreign_prior(
    api_client: TestClient,
) -> None:
    """A submission filed by another workspace MUST appear as 404 — never
    confirm cross-tenant existence."""
    ws_a = _setup_workspace(api_client)
    fresh = TestClient(api_client.app)
    fresh.app.state.testing_session = api_client.app.state.testing_session  # type: ignore[attr-defined]
    ws_b = _setup_workspace(
        api_client,
        vendor_name="Otro Proveedor SA",
        vendor_rfc="OTR260512AB1",
        fresh_client=fresh,
    )

    foreign = _upload(api_client, ws_a["workspace_id"])
    assert foreign.status_code == 202
    foreign_prior_id = foreign.json()["submission_id"]
    _set_status(api_client, foreign_prior_id, "rechazado")

    # Workspace B tries to "replace" workspace A's submission.
    response = fresh.post(
        f"/api/v1/portal/workspaces/{ws_b['workspace_id']}/submissions",
        data={**_canonical_intake_payload()[0], "supersedes_submission_id": foreign_prior_id},
        files={"file": ("inf.pdf", _pdf_bytes(), "application/pdf")},
        headers={"Authorization": f"Bearer {ws_b['bearer']}"},
    )
    assert response.status_code == 404


def test_workspace_upload_replacement_409_on_terminal_aprobado_prior(
    api_client: TestClient,
) -> None:
    """A submission already in ``aprobado`` cannot be replaced — provider
    must escalate to the reviewer, not silently overwrite."""
    ws = _setup_workspace(api_client)
    first = _upload(api_client, ws["workspace_id"])
    assert first.status_code == 202
    prior_id = first.json()["submission_id"]
    _set_status(api_client, prior_id, "aprobado")

    response = _upload(
        api_client, ws["workspace_id"], supersedes_submission_id=prior_id
    )
    assert response.status_code == 409
    assert "no puede reemplazarse" in response.json()["detail"]


def test_workspace_upload_replacement_409_on_mismatched_requirement_code(
    api_client: TestClient,
) -> None:
    """A rejected submission for one obligation cannot absolve a different one."""
    ws = _setup_workspace(api_client)
    first = _upload(api_client, ws["workspace_id"])
    assert first.status_code == 202
    prior_id = first.json()["submission_id"]
    _set_status(api_client, prior_id, "rechazado")

    # Now upload pointing at a different requirement_code (different
    # INFONAVIT period also works, but a different requirement_code is
    # the clearest test).
    from app.core.compliance_catalog import recurring_for_year

    other = next(
        item
        for item in recurring_for_year(2026)
        if item.institution == "imss" and item.due_month == 5
    )
    response = _upload(
        api_client,
        ws["workspace_id"],
        data={
            "period_code": "2026-04",
            "period_key": other.period_key,
            "load_type": "mensual",
            "institution_code": "imss",
            "requirement_name": other.name,
            "requirement_code": other.code,
        },
        supersedes_submission_id=prior_id,
    )
    assert response.status_code == 409
    assert "requirement_code" in response.json()["detail"]


def test_workspace_upload_replacement_409_on_mismatched_period_key(
    api_client: TestClient,
) -> None:
    """Same requirement_code, different period_key → 409.

    The validator checks ``requirement_code`` first, then ``period_key``.
    To exercise the period_key branch we keep ``requirement_code``
    identical to the prior (the canonical B1 INFONAVIT code) and only
    swap ``period_key`` / ``period_code``. The catalog doesn't enforce
    period_key ↔ requirement_code consistency at intake, so this
    combination reaches the lineage validator and fires the right error.
    """
    ws = _setup_workspace(api_client)
    first = _upload(api_client, ws["workspace_id"])
    assert first.status_code == 202
    prior_id = first.json()["submission_id"]
    _set_status(api_client, prior_id, "rechazado")

    response = _upload(
        api_client,
        ws["workspace_id"],
        data={
            "period_code": "2026-B3",
            "period_key": "2026-B3",
            # requirement_code intentionally NOT overridden — stays B1's
            # canonical code, matching the prior submission.
        },
        supersedes_submission_id=prior_id,
    )
    assert response.status_code == 409
    assert "period_key" in response.json()["detail"]


def test_workspace_upload_replacement_writes_validation_event(
    api_client: TestClient,
) -> None:
    """ValidationEvent ``submission_replacement_linked`` lands on the new
    submission, and ``submission_replaced`` lands on the prior one."""
    ws = _setup_workspace(api_client)
    first = _upload(api_client, ws["workspace_id"])
    prior_id = first.json()["submission_id"]
    _set_status(api_client, prior_id, "requiere_aclaracion")

    second = _upload(
        api_client, ws["workspace_id"], supersedes_submission_id=prior_id
    )
    assert second.status_code == 202, second.text
    new_id = second.json()["submission_id"]

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        new_event = db.scalar(
            select(ValidationEvent).where(
                ValidationEvent.submission_id == new_id,
                ValidationEvent.event_type == "submission_replacement_linked",
            )
        )
        assert new_event is not None
        assert new_event.actor_type == "supplier"
        assert (new_event.payload or {}).get("previous_submission_id") == prior_id

        prior_event = db.scalar(
            select(ValidationEvent).where(
                ValidationEvent.submission_id == prior_id,
                ValidationEvent.event_type == "submission_replaced",
            )
        )
        assert prior_event is not None
        assert prior_event.actor_type == "system"
        assert (prior_event.payload or {}).get("new_submission_id") == new_id
    finally:
        db.close()


def test_workspace_upload_replacement_writes_audit_log(
    api_client: TestClient,
) -> None:
    """A dedicated ``submission.replacement_linked`` audit row is written
    in addition to the regular ``submission.created`` row, and carries
    the workspace + slot identifiers compliance reports need."""
    ws = _setup_workspace(api_client)
    first = _upload(api_client, ws["workspace_id"])
    prior_id = first.json()["submission_id"]
    _set_status(api_client, prior_id, "posible_mismatch")

    second = _upload(
        api_client, ws["workspace_id"], supersedes_submission_id=prior_id
    )
    new_id = second.json()["submission_id"]

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        rows = list(
            db.scalars(
                select(AuditLog).where(
                    AuditLog.entity_type == "submission",
                    AuditLog.entity_id == new_id,
                )
            )
        )
        actions = [r.action for r in rows]
        assert "submission.created" in actions
        assert "submission.replacement_linked" in actions

        link_row = next(r for r in rows if r.action == "submission.replacement_linked")
        meta = link_row.event_metadata or {}
        assert meta.get("previous_submission_id") == prior_id
        assert meta.get("new_submission_id") == new_id
        assert meta.get("requirement_code")
        assert meta.get("period_key")
        assert meta.get("workspace_id") == ws["workspace_id"]
        # Standard intake row carries the lineage flag too.
        created_row = next(r for r in rows if r.action == "submission.created")
        assert (created_row.event_metadata or {}).get("supersedes_submission_id") == prior_id
    finally:
        db.close()
