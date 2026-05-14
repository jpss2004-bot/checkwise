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

    # CheckWise 1.7: /access now also sets an httpOnly session cookie.
    # Negative case must simulate a foreign attacker (no cookie + a
    # guessed header), so clear the cookie first.
    api_client.cookies.clear()

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


# ---------------------------------------------------------------------------
# Patch 3 — Correction Flow: submission-detail endpoint
# ---------------------------------------------------------------------------


def _submit_canonical(api_client: TestClient, *, vendor_rfc: str) -> dict:
    """Helper: post a canonical submission for the demo workspace pair."""
    from app.core.compliance_catalog import recurring_for_year

    catalog_item = next(
        item
        for item in recurring_for_year(2026)
        if item.institution == "imss" and item.due_month == 5
    )
    response = api_client.post(
        "/api/v1/submissions",
        data={
            "client_name": "Cliente Piloto CheckWise",
            "vendor_name": "Servicios Demo SA de CV",
            "vendor_rfc": vendor_rfc,
            "period_code": "2026-04",
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
    return response.json()


def test_submission_detail_returns_shape(api_client: TestClient) -> None:
    """Patch 3: detail endpoint returns identity, reasons, events, history."""
    access = api_client.post("/api/v1/portal/access", json=_access_payload()).json()
    headers = {"X-Workspace-Token": access["access_token"]}
    submitted = _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])

    detail = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}"
        f"/submissions/{submitted['submission_id']}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["submission_id"] == submitted["submission_id"]
    assert body["status"] == "pendiente_revision"
    assert body["requirement"]["requirement_code"]
    assert body["requirement"]["requirement_code"].startswith("REC-IMSS-2026-")
    assert body["period"]["period_key"] == "2026-M04"
    assert body["document"]["sha256"] == submitted["sha256"]
    assert any(
        ev["event_type"] == "upload_started" for ev in body["events"]
    )
    assert any(h["to_status"] == "pendiente_revision" for h in body["history"])
    # No prior attempts on the slot yet.
    assert body["previous_attempts"] == []
    # pendiente_revision suggests waiting.
    assert body["suggested_action"] == "wait_for_review"


def test_submission_detail_lists_previous_attempts_for_same_slot(
    api_client: TestClient,
) -> None:
    """Patch 3: repeat submissions on the same (requirement_code, period_key)
    should show the older attempts in the correction page."""
    access = api_client.post("/api/v1/portal/access", json=_access_payload()).json()
    headers = {"X-Workspace-Token": access["access_token"]}

    first = _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])
    second = _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])

    detail = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}"
        f"/submissions/{second['submission_id']}",
        headers=headers,
    ).json()
    assert len(detail["previous_attempts"]) == 1
    assert detail["previous_attempts"][0]["submission_id"] == first["submission_id"]


def test_submission_detail_requires_correct_token(api_client: TestClient) -> None:
    access = api_client.post("/api/v1/portal/access", json=_access_payload()).json()
    submitted = _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])
    # CheckWise 1.7: simulate a foreign attacker — no valid cookie.
    api_client.cookies.clear()
    bad = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}"
        f"/submissions/{submitted['submission_id']}",
        headers={"X-Workspace-Token": "wrong-token"},
    )
    assert bad.status_code == 401


def test_submission_detail_refuses_submission_from_other_workspace(
    api_client: TestClient,
) -> None:
    """Patch 3: a workspace must not be able to read another workspace's submission."""
    access_a = api_client.post("/api/v1/portal/access", json=_access_payload()).json()
    access_b = api_client.post(
        "/api/v1/portal/access",
        json=_access_payload(vendor_name="Proveedor Externo SA", vendor_rfc="EXT260512AB1"),
    ).json()
    submitted_a = _submit_canonical(api_client, vendor_rfc=access_a["vendor_rfc"])

    # access_b tries to read submission of access_a — must 404.
    cross = api_client.get(
        f"/api/v1/portal/workspaces/{access_b['workspace_id']}"
        f"/submissions/{submitted_a['submission_id']}",
        headers={"X-Workspace-Token": access_b["access_token"]},
    )
    assert cross.status_code == 404


# ---------------------------------------------------------------------------
# Patch 4 — Guided upload UX: duplicate pre-check endpoint
# ---------------------------------------------------------------------------


def test_check_duplicate_returns_false_for_unseen_hash(api_client: TestClient) -> None:
    access = api_client.post("/api/v1/portal/access", json=_access_payload()).json()
    headers = {"X-Workspace-Token": access["access_token"]}
    response = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/duplicate-check"
        f"?sha256={'0' * 64}",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["exists"] is False
    assert body["submission_id"] is None


def test_check_duplicate_finds_existing_workspace_submission(api_client: TestClient) -> None:
    access = api_client.post("/api/v1/portal/access", json=_access_payload()).json()
    headers = {"X-Workspace-Token": access["access_token"]}
    submitted = _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])

    response = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/duplicate-check"
        f"?sha256={submitted['sha256']}",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["exists"] is True
    assert body["submission_id"] == submitted["submission_id"]
    assert body["filename"] == "imss.pdf"


def test_check_duplicate_does_not_leak_other_workspace_documents(
    api_client: TestClient,
) -> None:
    """A duplicate uploaded by another vendor must NOT show as a duplicate
    for this workspace's pre-check."""
    access_a = api_client.post("/api/v1/portal/access", json=_access_payload()).json()
    access_b = api_client.post(
        "/api/v1/portal/access",
        json=_access_payload(vendor_name="Otro Proveedor", vendor_rfc="EXT260512AB1"),
    ).json()
    submitted_a = _submit_canonical(api_client, vendor_rfc=access_a["vendor_rfc"])

    response = api_client.get(
        f"/api/v1/portal/workspaces/{access_b['workspace_id']}/duplicate-check"
        f"?sha256={submitted_a['sha256']}",
        headers={"X-Workspace-Token": access_b["access_token"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["exists"] is False


def test_check_duplicate_rejects_malformed_hash(api_client: TestClient) -> None:
    access = api_client.post("/api/v1/portal/access", json=_access_payload()).json()
    headers = {"X-Workspace-Token": access["access_token"]}
    response = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/duplicate-check"
        "?sha256=not-a-hash",
        headers=headers,
    )
    assert response.status_code == 400


def test_check_duplicate_requires_workspace_token(api_client: TestClient) -> None:
    access = api_client.post("/api/v1/portal/access", json=_access_payload()).json()
    # CheckWise 1.7: simulate a foreign attacker — no valid cookie.
    api_client.cookies.clear()
    response = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/duplicate-check"
        f"?sha256={'0' * 64}",
        headers={"X-Workspace-Token": "wrong-token"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# CheckWise 1.7 — session cookie + tenant guard
# ---------------------------------------------------------------------------


COOKIE_NAME = "checkwise_portal_session"


def test_access_sets_session_cookie(api_client: TestClient) -> None:
    """/access must issue the httpOnly portal session cookie."""
    response = api_client.post("/api/v1/portal/access", json=_access_payload())
    assert response.status_code == 201
    # cookie is delivered via Set-Cookie header
    set_cookie = response.headers.get("set-cookie", "")
    assert COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie.lower() or "samesite=lax" in set_cookie.lower()


def test_me_reads_session_from_cookie(api_client: TestClient) -> None:
    """/me returns the workspace summary when only the cookie is present."""
    access = api_client.post("/api/v1/portal/access", json=_access_payload()).json()
    # Don't send the X-Workspace-Token header — cookie alone must work.
    me = api_client.get("/api/v1/portal/me")
    assert me.status_code == 200
    body = me.json()
    assert body["workspace_id"] == access["workspace_id"]
    assert body["vendor_rfc"] == access["vendor_rfc"]


def test_me_returns_401_without_session(api_client: TestClient) -> None:
    api_client.cookies.clear()
    response = api_client.get("/api/v1/portal/me")
    assert response.status_code == 401


def test_logout_clears_session_cookie(api_client: TestClient) -> None:
    api_client.post("/api/v1/portal/access", json=_access_payload())
    logout = api_client.post("/api/v1/portal/logout")
    assert logout.status_code == 204
    # After logout, /me must 401.
    me = api_client.get("/api/v1/portal/me")
    assert me.status_code == 401


def test_tenant_guard_rejects_path_mismatch(api_client: TestClient) -> None:
    """Cookie's workspace_id must match path's {workspace_id}.

    Opens two workspaces in two clients; client_b holds the cookie for
    workspace_b. Attempting to read workspace_a via the path must 403.
    """
    access_a = api_client.post("/api/v1/portal/access", json=_access_payload()).json()

    fresh = TestClient(api_client.app)
    fresh.post(
        "/api/v1/portal/access",
        json=_access_payload(
            vendor_name="Otro Proveedor SA",
            vendor_rfc="OTR260512AB1",
        ),
    )
    # fresh now holds the cookie for the OTHER workspace.
    cross = fresh.get(f"/api/v1/portal/workspaces/{access_a['workspace_id']}")
    assert cross.status_code == 403
