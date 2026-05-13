from __future__ import annotations

from collections.abc import Generator
from io import BytesIO

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

    previous = settings.LOCAL_STORAGE_PATH
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
        settings.LOCAL_STORAGE_PATH = previous


def _pdf_bytes() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()


def _access_payload(**overrides: object) -> dict:
    base = {
        "client_name": "Cliente Piloto CheckWise",
        "filial_name": "Filial Norte",
        "vendor_name": "Servicios Demo SA de CV",
        "vendor_rfc": "DEM260512AB1",
        "persona_type": "moral",
        "contract_reference": "CTR-001",
    }
    base.update(overrides)
    return base


def test_portal_access_creates_workspace_and_returns_token(api_client: TestClient) -> None:
    response = api_client.post("/api/v1/portal/access", json=_access_payload())
    assert response.status_code == 201
    payload = response.json()
    assert payload["workspace_id"]
    assert payload["access_token"]
    assert payload["persona_type"] == "moral"
    assert payload["client_name"] == "Cliente Piloto CheckWise"
    assert payload["filial_name"] == "Filial Norte"


def test_portal_workspace_requires_correct_token(api_client: TestClient) -> None:
    access = api_client.post("/api/v1/portal/access", json=_access_payload()).json()
    workspace_id = access["workspace_id"]

    bad = api_client.get(
        f"/api/v1/portal/workspaces/{workspace_id}",
        headers={"X-Workspace-Token": "wrong-token"},
    )
    assert bad.status_code == 401

    good = api_client.get(
        f"/api/v1/portal/workspaces/{workspace_id}",
        headers={"X-Workspace-Token": access["access_token"]},
    )
    assert good.status_code == 200
    assert good.json()["workspace_id"] == workspace_id


def test_portal_onboarding_reflects_existing_submission(api_client: TestClient) -> None:
    access = api_client.post("/api/v1/portal/access", json=_access_payload()).json()
    headers = {"X-Workspace-Token": access["access_token"]}

    # Upload a REPSE-original-flavoured submission.
    sub = api_client.post(
        "/api/v1/submissions",
        data={
            "client_name": "Cliente Piloto CheckWise",
            "vendor_name": "Servicios Demo SA de CV",
            "vendor_rfc": "DEM260512AB1",
            "period_code": "2026-05",
            "load_type": "alta_inicial",
            "institution_code": "stps_repse",
            "requirement_name": "Registro REPSE original",
            "initial_status": "pendiente_revision",
        },
        files={"file": ("repse.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert sub.status_code == 202

    onboarding = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/onboarding",
        headers=headers,
    ).json()

    repse_section = next(s for s in onboarding["sections"] if s["section"] == "Registro REPSE")
    received_items = [
        item for item in repse_section["items"] if item["status"] != "pendiente"
    ]
    assert received_items, "expected at least one received item under Registro REPSE"
    assert onboarding["summary"]["received_required"] >= 1
    assert onboarding["summary"]["total_required"] > 0


def test_portal_calendar_shape(api_client: TestClient) -> None:
    access = api_client.post("/api/v1/portal/access", json=_access_payload()).json()
    headers = {"X-Workspace-Token": access["access_token"]}
    response = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/calendar?year=2026",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["year"] == 2026
    assert len(payload["months"]) == 12
    assert all(
        sum(inst["expected"] for inst in m["institutions"]) == m["expected"]
        for m in payload["months"]
    )


def test_portal_calendar_emits_period_key_on_every_item(api_client: TestClient) -> None:
    """Patch 3: provider calendar must expose period_key so the wizard can
    submit canonical keys back to /submissions."""
    access = api_client.post("/api/v1/portal/access", json=_access_payload()).json()
    headers = {"X-Workspace-Token": access["access_token"]}
    payload = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/calendar?year=2026",
        headers=headers,
    ).json()
    items = [
        item
        for month in payload["months"]
        for inst in month["institutions"]
        for item in inst["items"]
    ]
    assert items
    for item in items:
        assert item["period_key"], item


def test_portal_calendar_canonical_match_does_not_overflow_across_months(
    api_client: TestClient,
) -> None:
    """Patch 3 regression: an INFONAVIT B1 upload must light up only the B1
    slot in the calendar, not every 2026-bearing INFONAVIT slot."""
    from app.core.compliance_catalog import recurring_for_year

    access = api_client.post("/api/v1/portal/access", json=_access_payload()).json()
    headers = {"X-Workspace-Token": access["access_token"]}

    catalog_item = next(
        item
        for item in recurring_for_year(2026)
        if item.institution == "infonavit" and item.period_key == "2026-B1"
    )

    submitted = api_client.post(
        "/api/v1/submissions",
        data={
            "client_name": "Cliente Piloto CheckWise",
            "vendor_name": "Servicios Demo SA de CV",
            "vendor_rfc": "DEM260512AB1",
            "period_code": "2026-B1",
            "period_key": catalog_item.period_key,
            "load_type": "bimestral",
            "institution_code": "infonavit",
            "requirement_name": catalog_item.name,
            "requirement_code": catalog_item.code,
            "initial_status": "pendiente_revision",
        },
        files={"file": ("inf.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert submitted.status_code == 202, submitted.text

    calendar = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/calendar?year=2026",
        headers=headers,
    ).json()

    matches = [
        (month["month"], item)
        for month in calendar["months"]
        for inst in month["institutions"]
        if inst["institution"] == "infonavit"
        for item in inst["items"]
        if item["submission_id"] is not None and item["code"] == catalog_item.code
    ]
    # Exactly the B1 slot (due in March, month=3) lights up.
    assert len(matches) == 1, matches
    assert matches[0][0] == 3
