from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import entities  # noqa: F401


@pytest.fixture
def api_client(tmp_path) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    previous_storage_path = settings.LOCAL_STORAGE_PATH
    settings.LOCAL_STORAGE_PATH = str(tmp_path / "storage")

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        settings.LOCAL_STORAGE_PATH = previous_storage_path


@pytest.fixture
def seeded_api_client(tmp_path) -> Generator[tuple[TestClient, sessionmaker], None, None]:
    """Same as ``api_client`` but pre-seeds the compliance catalog so /submissions
    resolves canonical codes against existing DB rows."""
    from app.db.seed import seed_catalog

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    previous_storage_path = settings.LOCAL_STORAGE_PATH
    settings.LOCAL_STORAGE_PATH = str(tmp_path / "storage")

    bootstrap = testing_session()
    try:
        seed_catalog(bootstrap)
        bootstrap.commit()
    finally:
        bootstrap.close()

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app), testing_session
    finally:
        app.dependency_overrides.clear()
        settings.LOCAL_STORAGE_PATH = previous_storage_path


def test_create_submission_records_document_and_validations(api_client: TestClient) -> None:
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
            "comments": "Carga de prueba",
            "initial_status": "pendiente_revision",
        },
        files={"file": ("opinion.pdf", _rfc_text_pdf_bytes("ABC010203AB1"), "application/pdf")},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "pendiente_revision"
    assert payload["sha256"]
    assert payload["storage_key"].endswith("opinion.pdf")
    assert payload["inspection"]["is_pdf"] is True
    assert payload["inspection"]["is_corrupt"] is False
    assert "human_review_required" in {item["rule_code"] for item in payload["validations"]}
    assert "pdf_inspected" in {item["event_type"] for item in payload["validation_events"]}


def test_create_submission_rejects_non_pdf(api_client: TestClient) -> None:
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
        files={"file": ("opinion.txt", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 400
    assert "solo se aceptan archivos PDF" in response.json()["detail"]


def test_duplicate_hash_is_reported(api_client: TestClient) -> None:
    data = {
        "client_name": "Cliente Piloto",
        "vendor_name": "Proveedor REPSE SA de CV",
        "vendor_rfc": "ABC010203AB1",
        "period_code": "2026-05",
        "load_type": "mensual",
        "institution_code": "sat",
        "requirement_name": "Opinión de cumplimiento SAT positiva",
        "initial_status": "pendiente_revision",
    }
    pdf = _pdf_bytes()

    first = api_client.post(
        "/api/v1/submissions",
        data=data,
        files={"file": ("opinion.pdf", pdf, "application/pdf")},
    )
    second = api_client.post(
        "/api/v1/submissions",
        data=data,
        files={"file": ("opinion.pdf", pdf, "application/pdf")},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    duplicate_validation = next(
        item for item in second.json()["validations"] if item["rule_code"] == "duplicate_hash"
    )
    assert duplicate_validation["result"] == "warning"


def test_submission_accepts_bimestral_load_type(api_client: TestClient) -> None:
    """Patch 3: INFONAVIT bimestral must clear the LOAD_TYPES whitelist."""
    response = api_client.post(
        "/api/v1/submissions",
        data={
            "client_name": "Cliente Piloto",
            "vendor_name": "Proveedor REPSE SA de CV",
            "vendor_rfc": "ABC010203AB1",
            "period_code": "2026-B1",
            "load_type": "bimestral",
            "institution_code": "infonavit",
            "requirement_name": "Comprobante de pago bancario",
            "initial_status": "pendiente_revision",
        },
        files={"file": ("infonavit.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 202, response.text


def test_submission_accepts_anual_load_type(api_client: TestClient) -> None:
    """Patch 3: SAT anual must clear the LOAD_TYPES whitelist."""
    response = api_client.post(
        "/api/v1/submissions",
        data={
            "client_name": "Cliente Piloto",
            "vendor_name": "Proveedor REPSE SA de CV",
            "vendor_rfc": "ABC010203AB1",
            "period_code": "2025-A",
            "load_type": "anual",
            "institution_code": "sat",
            "requirement_name": "Acuse declaración anual de impuestos",
            "initial_status": "pendiente_revision",
        },
        files={"file": ("anual.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 202, response.text


def test_submission_canonical_codes_succeed_and_skip_legacy_events(
    api_client: TestClient,
) -> None:
    """Patch 3: canonical requirement_code + period_key submissions should not
    emit ``legacy_requirement_intake`` / ``legacy_period_intake`` events."""
    from app.core.compliance_catalog import recurring_for_year

    catalog_item = next(
        item
        for item in recurring_for_year(2026)
        if item.institution == "imss" and item.due_month == 2
    )
    response = api_client.post(
        "/api/v1/submissions",
        data={
            "client_name": "Cliente Piloto",
            "vendor_name": "Proveedor REPSE SA de CV",
            "vendor_rfc": "ABC010203AB1",
            "period_code": "2026-01",
            "period_key": catalog_item.period_key,
            "load_type": "mensual",
            "institution_code": "imss",
            "requirement_name": catalog_item.name,
            "requirement_code": catalog_item.code,
            "initial_status": "pendiente_revision",
        },
        files={"file": ("imss.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 202, response.text
    event_types = {event["event_type"] for event in response.json()["validation_events"]}
    assert "legacy_requirement_intake" not in event_types
    assert "legacy_period_intake" not in event_types


def test_submission_without_canonical_codes_emits_deprecation_events(
    api_client: TestClient,
) -> None:
    """Patch 3: free-text-only submissions must emit deprecation events so we
    can measure migration progress through validation_events."""
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
        files={"file": ("op.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 202, response.text
    event_types = {event["event_type"] for event in response.json()["validation_events"]}
    assert "legacy_requirement_intake" in event_types
    assert "legacy_period_intake" in event_types


def test_seeded_canonical_submission_does_not_create_new_requirement(
    seeded_api_client,
) -> None:
    """Patch 2 (seeding): when the catalog is already in the DB, a canonical
    submission must reuse the seeded ``Requirement`` row instead of letting
    the on-the-fly fallback create another one."""
    from sqlalchemy import select

    from app.core.compliance_catalog import recurring_for_year
    from app.models import Requirement

    client, session_factory = seeded_api_client

    # Count requirements after seed.
    db = session_factory()
    try:
        before = len(db.scalars(select(Requirement.id)).all())
    finally:
        db.close()
    assert before > 0  # seed produced rows

    catalog_item = next(
        item
        for item in recurring_for_year(2026)
        if item.institution == "imss" and item.due_month == 2
    )
    response = client.post(
        "/api/v1/submissions",
        data={
            "client_name": "Cliente Piloto",
            "vendor_name": "Proveedor REPSE SA de CV",
            "vendor_rfc": "ABC010203AB1",
            "period_code": "2026-01",
            "period_key": catalog_item.period_key,
            "load_type": "mensual",
            "institution_code": "imss",
            "requirement_name": catalog_item.name,
            "requirement_code": catalog_item.code,
            "initial_status": "pendiente_revision",
        },
        files={"file": ("imss.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 202, response.text

    db = session_factory()
    try:
        after = len(db.scalars(select(Requirement.id)).all())
    finally:
        db.close()
    # No NEW Requirement row created — the canonical code resolved to the
    # seeded row.
    assert after == before


def test_submission_unknown_requirement_code_returns_422(api_client: TestClient) -> None:
    """Patch 3: a submitted requirement_code that the catalog does not know
    must error 422 rather than silently creating a phantom requirement."""
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
            "requirement_code": "REC-FAKE-9999-99-not-real",
            "initial_status": "pendiente_revision",
        },
        files={"file": ("fake.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 422
    assert "requirement_code desconocido" in response.json()["detail"]


def test_encrypted_pdf_requires_clarification(api_client: TestClient) -> None:
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
        files={"file": ("opinion.pdf", _pdf_bytes(password="secret"), "application/pdf")},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "requiere_aclaracion"
    assert payload["inspection"]["is_encrypted"] is True


def _pdf_bytes(password: str | None = None) -> bytes:
    from io import BytesIO

    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    if password:
        writer.encrypt(password)
    writer.write(output)
    return output.getvalue()


def _rfc_text_pdf_bytes(line: str) -> bytes:
    """Single-page PDF whose text layer carries ``line`` (e.g. an RFC).

    pypdf's writer cannot draw text, so we hand-assemble the file (same
    technique as tests/test_workspace_submissions.py::_text_pdf_bytes).
    Embedding the expected RFC lets the intake's RFC-alignment check pass,
    so a clean upload derives PENDIENTE_REVISION rather than the
    REQUIERE_ACLARACION a textless PDF now triggers (hardening 7705c35).
    ``line`` must be ASCII without parentheses (PDF string literal).
    """
    stream = b"BT /F1 18 Tf 72 720 Td (" + line.encode("ascii") + b") Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 6\n0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
        + str(xref_pos).encode()
        + b"\n%%EOF\n"
    )
    return bytes(out)
