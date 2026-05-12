from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
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
        files={"file": ("opinion.pdf", b"%PDF-1.4 checkwise", "application/pdf")},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "pendiente_revision"
    assert payload["sha256"]
    assert payload["storage_key"].endswith("opinion.pdf")
    assert "human_review_required" in {item["rule_code"] for item in payload["validations"]}
