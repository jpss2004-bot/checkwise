from __future__ import annotations

import itertools
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
from app.models import Client, ProviderWorkspace, User, Vendor, entities  # noqa: F401
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

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # Stash the session factory on the client so helpers can seed rows
    # in the same SQLite engine the API uses.
    client = TestClient(app)
    client.app.state.testing_session = testing_session  # type: ignore[attr-defined]
    try:
        yield client
    finally:
        app.dependency_overrides.clear()
        settings.LOCAL_STORAGE_PATH = previous


def _pdf_bytes() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()


# Shared counter so each helper call gets a unique email — lets a single
# test set up two distinct workspaces (each owned by a different user).
_user_seq = itertools.count(1)


def _access_payload(**overrides: object) -> dict:
    """Default workspace identity used by tests.

    The shape mirrors what the old POST /portal/access request body
    looked like, so individual test bodies didn't need to change when
    we removed that endpoint. ``_setup_workspace_session`` consumes
    these fields when seeding the ProviderWorkspace row.
    """
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


def _setup_workspace_session(
    api_client: TestClient,
    *,
    payload: dict | None = None,
    fresh_client: TestClient | None = None,
) -> dict:
    """Seed a User + Client + Vendor + ProviderWorkspace in the test DB,
    then call POST /api/v1/portal/enter as that user so the test
    client picks up the portal session cookie.

    Returns a dict matching the old ``/portal/access`` response shape so
    most tests can keep their existing assertions.
    """
    payload = payload or _access_payload()
    target_client = fresh_client or api_client
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        seq = next(_user_seq)
        user = User(
            email=f"prov-{seq}@checkwise.test",
            password_hash=hash_password("CheckWiseTest!2026"),
            full_name=str(payload["vendor_name"]),
            status="active",
            must_change_password=False,
        )
        db.add(user)
        db.flush()

        existing_client = db.query(Client).filter_by(name=payload["client_name"]).first()
        if existing_client is None:
            client_row = Client(name=str(payload["client_name"]))
            db.add(client_row)
            db.flush()
        else:
            client_row = existing_client

        vendor = Vendor(
            client_id=client_row.id,
            name=str(payload["vendor_name"]),
            rfc=str(payload["vendor_rfc"]).upper(),
            persona_type=str(payload["persona_type"]),
        )
        db.add(vendor)
        db.flush()

        workspace = ProviderWorkspace(
            client_id=client_row.id,
            vendor_id=vendor.id,
            owner_user_id=user.id,
            filial_name=payload.get("filial_name"),  # type: ignore[arg-type]
            persona_type=str(payload["persona_type"]),
            display_name=str(payload["vendor_name"]),
            access_token="placeholder-rotated-on-enter",
        )
        db.add(workspace)
        db.commit()
        ws_id = workspace.id
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
    body = enter.json()

    # Pull the rotated access_token from DB (the cookie holds the JWT, but
    # tests still assert via X-Workspace-Token in some negative cases).
    db = factory()
    try:
        ws_row = db.get(ProviderWorkspace, ws_id)
        rotated_token = ws_row.access_token if ws_row else ""
    finally:
        db.close()

    return {
        "workspace_id": body["workspace_id"],
        "access_token": rotated_token,
        "persona_type": body["persona_type"],
        "client_name": body["client_name"],
        "vendor_name": body["vendor_name"],
        "vendor_rfc": body["vendor_rfc"],
        "filial_name": body["filial_name"],
        "contract_reference": body["contract_reference"],
        "onboarding_completed_at": body["onboarding_completed_at"],
    }


# ---------------------------------------------------------------------------
# Anonymous portal/access endpoint must be gone (CheckWise 1.8)
# ---------------------------------------------------------------------------


def test_anonymous_portal_access_endpoint_is_removed(api_client: TestClient) -> None:
    """POST /portal/access used to allow anonymous workspace creation.
    It MUST return 404/405 now — the only way in is /portal/enter."""
    response = api_client.post("/api/v1/portal/access", json=_access_payload())
    assert response.status_code in {404, 405}


def test_portal_enter_requires_authentication(api_client: TestClient) -> None:
    """Without a bearer JWT, /enter must 401."""
    api_client.cookies.clear()
    response = api_client.post("/api/v1/portal/enter", json={})
    assert response.status_code == 401


def test_portal_enter_rejects_user_without_workspace(api_client: TestClient) -> None:
    """A logged-in user with no owned workspace must get 404 from /enter."""
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        user = User(
            email="orphan@checkwise.test",
            password_hash=hash_password("CheckWiseTest!2026"),
            full_name="Orphan User",
            status="active",
        )
        db.add(user)
        db.commit()
        token = issue_access_token(
            user_id=user.id, email=user.email, roles=[], orgs=[]
        )
    finally:
        db.close()

    api_client.cookies.clear()
    response = api_client.post(
        "/api/v1/portal/enter",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_portal_enter_rejects_foreign_workspace_id(api_client: TestClient) -> None:
    """If user A asks to enter user B's workspace, must 403."""
    access_b = _setup_workspace_session(
        api_client,
        payload=_access_payload(
            vendor_name="Otro Proveedor SA",
            vendor_rfc="OTR260512AB1",
        ),
    )

    # Create a different user with their own workspace, then try to enter
    # access_b's workspace_id with that other user's token.
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        attacker = User(
            email="attacker@checkwise.test",
            password_hash=hash_password("CheckWiseTest!2026"),
            full_name="Attacker",
            status="active",
        )
        db.add(attacker)
        db.commit()
        attacker_token = issue_access_token(
            user_id=attacker.id, email=attacker.email, roles=[], orgs=[]
        )
    finally:
        db.close()

    api_client.cookies.clear()
    cross = api_client.post(
        "/api/v1/portal/enter",
        json={"workspace_id": access_b["workspace_id"]},
        headers={"Authorization": f"Bearer {attacker_token}"},
    )
    assert cross.status_code == 403


def test_portal_enter_happy_path(api_client: TestClient) -> None:
    """An owner can enter their workspace and gets a session cookie."""
    access = _setup_workspace_session(api_client)
    assert access["workspace_id"]
    assert access["persona_type"] == "moral"
    assert access["client_name"] == "Cliente Piloto CheckWise"
    assert access["filial_name"] == "Filial Norte"

    # Cookie should now be valid; /me must succeed without a header.
    me = api_client.get("/api/v1/portal/me")
    assert me.status_code == 200
    assert me.json()["workspace_id"] == access["workspace_id"]


def test_portal_workspace_requires_correct_token(api_client: TestClient) -> None:
    access = _setup_workspace_session(api_client)
    workspace_id = access["workspace_id"]

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
    access = _setup_workspace_session(api_client)
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
    access = _setup_workspace_session(api_client)
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
    access = _setup_workspace_session(api_client)
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

    access = _setup_workspace_session(api_client)
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
    access = _setup_workspace_session(api_client)
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
    access = _setup_workspace_session(api_client)
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
    access = _setup_workspace_session(api_client)
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
    access_a = _setup_workspace_session(api_client)
    submitted_a = _submit_canonical(api_client, vendor_rfc=access_a["vendor_rfc"])
    access_b = _setup_workspace_session(
        api_client,
        payload=_access_payload(
            vendor_name="Proveedor Externo SA", vendor_rfc="EXT260512AB1"
        ),
    )

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
    access = _setup_workspace_session(api_client)
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
    access = _setup_workspace_session(api_client)
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
    access_a = _setup_workspace_session(api_client)
    submitted_a = _submit_canonical(api_client, vendor_rfc=access_a["vendor_rfc"])
    access_b = _setup_workspace_session(
        api_client,
        payload=_access_payload(
            vendor_name="Otro Proveedor", vendor_rfc="EXT260512AB1"
        ),
    )

    response = api_client.get(
        f"/api/v1/portal/workspaces/{access_b['workspace_id']}/duplicate-check"
        f"?sha256={submitted_a['sha256']}",
        headers={"X-Workspace-Token": access_b["access_token"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["exists"] is False


def test_check_duplicate_rejects_malformed_hash(api_client: TestClient) -> None:
    access = _setup_workspace_session(api_client)
    headers = {"X-Workspace-Token": access["access_token"]}
    response = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/duplicate-check"
        "?sha256=not-a-hash",
        headers=headers,
    )
    assert response.status_code == 400


def test_check_duplicate_requires_workspace_token(api_client: TestClient) -> None:
    access = _setup_workspace_session(api_client)
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


def test_enter_sets_session_cookie(api_client: TestClient) -> None:
    """/enter must issue the httpOnly portal session cookie."""
    _setup_workspace_session(api_client)
    # The cookie was set on the api_client by the /enter call inside the helper.
    cookies = api_client.cookies.jar
    assert any(c.name == COOKIE_NAME for c in cookies), [c.name for c in cookies]


def test_me_reads_session_from_cookie(api_client: TestClient) -> None:
    """/me returns the workspace summary when only the cookie is present."""
    access = _setup_workspace_session(api_client)
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
    _setup_workspace_session(api_client)
    logout = api_client.post("/api/v1/portal/logout")
    assert logout.status_code == 204
    # After logout, /me must 401.
    me = api_client.get("/api/v1/portal/me")
    assert me.status_code == 401


# ---------------------------------------------------------------------------
# Expediente gate (CheckWise 1.8) — status field + complete-onboarding
# ---------------------------------------------------------------------------


def test_me_returns_not_started_for_fresh_workspace(api_client: TestClient) -> None:
    """A workspace with no submissions and no completion timestamp must
    report expediente_status='not_started'."""
    _setup_workspace_session(api_client)
    me = api_client.get("/api/v1/portal/me")
    assert me.status_code == 200
    body = me.json()
    assert body["expediente_status"] == "not_started"
    assert body["onboarding_completed_at"] is None


def test_me_returns_in_progress_after_first_submission(
    api_client: TestClient,
) -> None:
    """Once any submission exists, status flips to 'in_progress'."""
    access = _setup_workspace_session(api_client)
    _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])
    me = api_client.get("/api/v1/portal/me")
    assert me.status_code == 200
    assert me.json()["expediente_status"] == "in_progress"


def test_complete_onboarding_marks_workspace_complete(
    api_client: TestClient,
) -> None:
    """POST /complete-onboarding sets the timestamp + flips status."""
    access = _setup_workspace_session(api_client)
    response = api_client.post(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/complete-onboarding"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["workspace_id"] == access["workspace_id"]
    assert body["expediente_status"] == "complete"
    assert body["onboarding_completed_at"]

    # /me reflects it
    me = api_client.get("/api/v1/portal/me").json()
    assert me["expediente_status"] == "complete"
    assert me["onboarding_completed_at"]


def test_complete_onboarding_is_idempotent(api_client: TestClient) -> None:
    """Calling complete-onboarding twice keeps the original timestamp."""
    access = _setup_workspace_session(api_client)
    first = api_client.post(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/complete-onboarding"
    ).json()
    second = api_client.post(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/complete-onboarding"
    ).json()
    assert first["onboarding_completed_at"] == second["onboarding_completed_at"]


def test_complete_onboarding_rejects_foreign_workspace(
    api_client: TestClient,
) -> None:
    """A user cannot complete another company's expediente by guessing
    workspace_id — current_portal_workspace tenant guard catches it."""
    access_b = _setup_workspace_session(
        api_client,
        payload=_access_payload(
            vendor_name="Otro Proveedor SA", vendor_rfc="OTR260512AB1"
        ),
    )
    # Switch to a different user with their own session.
    fresh = TestClient(api_client.app)
    fresh.app.state.testing_session = api_client.app.state.testing_session  # type: ignore[attr-defined]
    _setup_workspace_session(
        api_client,
        payload=_access_payload(
            vendor_name="Tercer Proveedor", vendor_rfc="TER260512AB1"
        ),
        fresh_client=fresh,
    )
    cross = fresh.post(
        f"/api/v1/portal/workspaces/{access_b['workspace_id']}/complete-onboarding"
    )
    assert cross.status_code in {403, 404}


def test_tenant_guard_rejects_path_mismatch(api_client: TestClient) -> None:
    """Cookie's workspace_id must match path's {workspace_id}.

    Opens two workspaces (one per user); the second client holds the
    cookie for workspace_b. Attempting to read workspace_a via the path
    must 403.
    """
    access_a = _setup_workspace_session(api_client)

    fresh = TestClient(api_client.app)
    fresh.app.state.testing_session = api_client.app.state.testing_session  # type: ignore[attr-defined]
    _setup_workspace_session(
        api_client,
        payload=_access_payload(
            vendor_name="Otro Proveedor SA",
            vendor_rfc="OTR260512AB1",
        ),
        fresh_client=fresh,
    )
    # fresh now holds the cookie for the OTHER workspace.
    cross = fresh.get(f"/api/v1/portal/workspaces/{access_a['workspace_id']}")
    assert cross.status_code == 403
