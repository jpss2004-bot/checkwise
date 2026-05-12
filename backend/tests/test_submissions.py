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
        files={"file": ("opinion.pdf", _pdf_bytes(), "application/pdf")},
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
