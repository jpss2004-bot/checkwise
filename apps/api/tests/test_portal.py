from __future__ import annotations

import itertools
from collections.abc import Generator
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants.statuses import DocumentStatus
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    AuditLog,
    Client,
    Document,
    ProviderWorkspace,
    Submission,
    User,
    Vendor,
    entities,  # noqa: F401
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


def _text_pdf_bytes(line: str) -> bytes:
    """Single-page PDF whose text layer carries ``line`` (e.g. an RFC).

    pypdf's writer cannot draw text, so we hand-assemble the file (same
    technique as tests/test_workspace_submissions.py::_text_pdf_bytes).
    Embedding the expected RFC lets the intake's RFC-alignment check pass,
    so a clean canonical upload derives PENDIENTE_REVISION rather than the
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
    """Onboarding lights up the matching slot via the canonical
    ``requirement_code`` lookup.

    Phase 4 dropped the legacy fuzzy-name fallback in
    ``_match_submission``. The onboarding endpoint now goes through
    ``build_workspace_onboarding_slots``, which matches strictly on
    ``requirement_code``. So the test posts the canonical
    ``ONB-REPSE-001`` code instead of relying on name normalisation.
    """
    access = _setup_workspace_session(api_client)
    headers = {"X-Workspace-Token": access["access_token"]}

    # Upload a REPSE-original-flavoured submission using the canonical
    # catalog code for the slot — this is how the workspace upload
    # endpoint feeds submissions today.
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
            "requirement_code": "ONB-REPSE-001",
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


def test_portal_calendar_emits_server_risk_level_on_every_item(
    api_client: TestClient,
) -> None:
    """Wave 1 / A1: the provider calendar now carries a server-computed 6-tier
    ``risk_level`` on every item — the same ``calendar_item_risk`` classifier
    the client and admin calendars use — so urgency is one source of truth
    across all three surfaces instead of being re-derived on the provider FE."""
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
    valid_tiers = {
        "overdue",
        "action_required",
        "due_soon",
        "in_review",
        "upcoming",
        "on_track",
    }
    for item in items:
        assert item.get("risk_level") in valid_tiers, item
        # Wave 2 / A4 — reviewer_note is always present (null unless the
        # obligation was bounced and carries a reviewer message).
        assert "reviewer_note" in item, item


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
        files={"file": ("imss.pdf", _text_pdf_bytes(vendor_rfc), "application/pdf")},
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


def test_cancel_pending_submission_removes_rows_and_audits(
    api_client: TestClient,
) -> None:
    access = _setup_workspace_session(api_client)
    headers = {"X-Workspace-Token": access["access_token"]}
    submitted = _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])
    submission_id = submitted["submission_id"]

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        submission = db.get(Submission, submission_id)
        assert submission is not None
        submission.status = DocumentStatus.PENDIENTE_REVISION.value
        document = db.scalar(
            select(Document).where(Document.submission_id == submission_id)
        )
        assert document is not None
        document.status = DocumentStatus.PENDIENTE_REVISION.value
        db.commit()
    finally:
        db.close()

    detail = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}"
        f"/submissions/{submission_id}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["can_cancel"] is True

    cancel = api_client.delete(
        f"/api/v1/portal/workspaces/{access['workspace_id']}"
        f"/submissions/{submission_id}",
        headers=headers,
    )
    assert cancel.status_code == 204, cancel.text

    detail = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}"
        f"/submissions/{submission_id}",
        headers=headers,
    )
    assert detail.status_code == 404

    db: Session = factory()
    try:
        assert db.get(Submission, submission_id) is None
        assert (
            db.scalar(
                select(Document.id).where(Document.submission_id == submission_id)
            )
            is None
        )
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "provider.submission_cancelled",
                AuditLog.entity_id == submission_id,
            )
        )
        assert audit is not None
        assert audit.actor_type == "provider"
        assert audit.event_metadata["workspace_id"] == access["workspace_id"]
    finally:
        db.close()


def test_cancel_rejects_reviewed_submission(
    api_client: TestClient,
) -> None:
    access = _setup_workspace_session(api_client)
    headers = {"X-Workspace-Token": access["access_token"]}
    submitted = _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])
    submission_id = submitted["submission_id"]

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        submission = db.get(Submission, submission_id)
        assert submission is not None
        submission.status = DocumentStatus.APROBADO.value
        document = db.scalar(
            select(Document).where(Document.submission_id == submission_id)
        )
        assert document is not None
        document.status = DocumentStatus.APROBADO.value
        db.commit()
    finally:
        db.close()

    detail = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}"
        f"/submissions/{submission_id}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["can_cancel"] is False

    cancel = api_client.delete(
        f"/api/v1/portal/workspaces/{access['workspace_id']}"
        f"/submissions/{submission_id}",
        headers=headers,
    )
    assert cancel.status_code == 409

    db = factory()
    try:
        assert db.get(Submission, submission_id) is not None
    finally:
        db.close()


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


# ---------------------------------------------------------------------------
# Phase 2 / Slice 2B — reviewer_note on submission detail
# ---------------------------------------------------------------------------


def test_submission_detail_reviewer_note_null_when_no_decision(
    api_client: TestClient,
) -> None:
    """Slice 2B — a fresh submission with no reviewer decision has
    ``reviewer_note=None``. Frontend uses null to decide whether to
    render the new hero card; this pins the contract.
    """
    access = _setup_workspace_session(api_client)
    submitted = _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])

    detail = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}"
        f"/submissions/{submitted['submission_id']}",
    ).json()
    assert detail["status"] == "pendiente_revision"
    assert detail["reviewer_note"] is None


def test_reviewer_decision_writes_provider_notification_with_severity(
    api_client: TestClient,
) -> None:
    """Slice 4B — every reviewer decision fires a provider-side
    notification with the right semáforo severity. The reviewer
    note round-trips into the body so the provider sees the
    explanation in the inbox without click-through.
    """
    from app.constants.statuses import ReviewerAction
    from app.models import Submission
    from app.services.submission_workflow import apply_reviewer_decision

    access = _setup_workspace_session(api_client)

    # Helper: seed a fresh submission, apply the given reviewer
    # decision against it, return the submission id.
    def _decide(action: ReviewerAction, reason: str | None) -> str:
        submitted = _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])
        sub_id = submitted["submission_id"]
        factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
        db = factory()
        try:
            sub = db.get(Submission, sub_id)
            assert sub is not None
            apply_reviewer_decision(
                db,
                submission=sub,
                action=action,
                reason=reason,
                reviewer_user_id="rev-test-user",
            )
        finally:
            db.close()
        return sub_id

    sub_approved = _decide(ReviewerAction.APPROVE, None)
    sub_rejected = _decide(
        ReviewerAction.REJECT, "El RFC no coincide con el del proveedor."
    )
    sub_clarif = _decide(
        ReviewerAction.REQUEST_CLARIFICATION, "Aclara el periodo cubierto."
    )
    sub_exception = _decide(
        ReviewerAction.MARK_EXCEPTION, "Aplicada por excepción legal."
    )

    resp = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/notifications?limit=200"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    by_sub: dict[str, dict] = {
        item["submission_id"]: item for item in body["items"]
    }

    assert by_sub[sub_approved]["severity"] == "green"
    assert by_sub[sub_approved]["notification_type"] == "document_approve"

    assert by_sub[sub_rejected]["severity"] == "red"
    # Reason round-trips into the body so the provider sees it inline.
    assert "El RFC no coincide" in by_sub[sub_rejected]["body"]

    assert by_sub[sub_clarif]["severity"] == "yellow"
    assert "Aclara el periodo" in by_sub[sub_clarif]["body"]

    assert by_sub[sub_exception]["severity"] == "green"

    # Summary endpoint reports the same unread count.
    summary = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/notifications/summary"
    ).json()
    assert summary["unread_count"] == 4


def test_provider_notifications_enforce_tenant_isolation(
    api_client: TestClient,
) -> None:
    """Slice 4B — workspace B's session cannot read workspace A's
    notification inbox via a crafted path id.

    Setup: seed A, then seed B (the ``_setup_workspace_session``
    helper leaves the cookie pointing at B). Apply a reject against
    A's submission so A's inbox has a row. With the B-session cookie
    active, GET A's notifications endpoint: ``current_portal_workspace``
    matches the path id against the resolved-session workspace and
    must return 404 (never confirm A's existence to B).
    """
    from app.constants.statuses import ReviewerAction
    from app.models import Submission
    from app.services.submission_workflow import apply_reviewer_decision

    access_a = _setup_workspace_session(api_client)
    # Capture A's submission BEFORE switching cookies to B.
    submitted_a = _submit_canonical(api_client, vendor_rfc=access_a["vendor_rfc"])
    workspace_a = access_a["workspace_id"]

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db = factory()
    try:
        sub_a = db.get(Submission, submitted_a["submission_id"])
        assert sub_a is not None
        apply_reviewer_decision(
            db,
            submission=sub_a,
            action=ReviewerAction.REJECT,
            reason="Documento ilegible.",
            reviewer_user_id="rev-test-user",
        )
    finally:
        db.close()

    # Sanity: with A's cookie active, A sees the row.
    own = api_client.get(
        f"/api/v1/portal/workspaces/{workspace_a}/notifications"
    ).json()
    assert any(
        item.get("submission_id") == submitted_a["submission_id"]
        for item in own["items"]
    )

    # Swap to B's session — the helper rebinds the cookie.
    _setup_workspace_session(
        api_client,
        payload=_access_payload(
            vendor_name="Otro Proveedor SA",
            vendor_rfc="OTR250101AB1",
        ),
    )

    # B's session attempts to read A's inbox via a crafted path id.
    cross = api_client.get(
        f"/api/v1/portal/workspaces/{workspace_a}/notifications"
    )
    assert cross.status_code in (403, 404), cross.text
    # Same guarantee for the summary route.
    cross_summary = api_client.get(
        f"/api/v1/portal/workspaces/{workspace_a}/notifications/summary"
    )
    assert cross_summary.status_code in (403, 404), cross_summary.text


def test_provider_notification_mark_read_is_idempotent(
    api_client: TestClient,
) -> None:
    """Slice 4B — a second mark-read on an already-read notification
    must NOT move the timestamp and must not 500."""
    from app.constants.statuses import ReviewerAction
    from app.models import Submission
    from app.services.submission_workflow import apply_reviewer_decision

    access = _setup_workspace_session(api_client)
    submitted = _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db = factory()
    try:
        sub = db.get(Submission, submitted["submission_id"])
        assert sub is not None
        apply_reviewer_decision(
            db,
            submission=sub,
            action=ReviewerAction.APPROVE,
            reason=None,
            reviewer_user_id="rev-test-user",
        )
    finally:
        db.close()

    listing = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/notifications"
    ).json()
    assert listing["unread_count"] == 1
    notification_id = listing["items"][0]["id"]

    first = api_client.post(
        f"/api/v1/portal/workspaces/{access['workspace_id']}"
        f"/notifications/{notification_id}/read"
    )
    assert first.status_code == 200
    first_read_at = first.json()["read_at"]

    second = api_client.post(
        f"/api/v1/portal/workspaces/{access['workspace_id']}"
        f"/notifications/{notification_id}/read"
    )
    assert second.status_code == 200
    assert second.json()["read_at"] == first_read_at  # unchanged

    summary = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/notifications/summary"
    ).json()
    assert summary["unread_count"] == 0


def test_submission_detail_carries_reviewer_note_on_rechazado(
    api_client: TestClient,
) -> None:
    """Slice 2B — when a reviewer rejects with a Spanish reason, the
    detail endpoint surfaces that reason as ``reviewer_note`` so the
    provider page can render it as the hero instead of burying it in
    the timeline. Sourced from the same ``_latest_reviewer_note``
    helper that already feeds calendar/dashboard, so this is a
    contract-propagation test rather than a new query.
    """
    from app.constants.statuses import ReviewerAction
    from app.models import Submission
    from app.services.submission_workflow import apply_reviewer_decision

    access = _setup_workspace_session(api_client)
    submitted = _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])

    reason = "El RFC del comprobante no coincide con el del proveedor."
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db = factory()
    try:
        sub = db.get(Submission, submitted["submission_id"])
        assert sub is not None
        apply_reviewer_decision(
            db,
            submission=sub,
            action=ReviewerAction.REJECT,
            reason=reason,
            reviewer_user_id="rev-test-user",
        )
    finally:
        db.close()

    detail = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}"
        f"/submissions/{submitted['submission_id']}",
    ).json()
    assert detail["status"] == "rechazado"
    assert detail["reviewer_note"] == reason
    assert detail["suggested_action"] == "reupload"


# ---------------------------------------------------------------------------
# Phase 5 / Slice 5A — document download flow
# ---------------------------------------------------------------------------


def test_document_download_attachment_writes_audit(
    api_client: TestClient,
) -> None:
    """``?download=1`` returns the bytes with attachment disposition AND
    writes a ``provider.document_downloaded`` audit row. The audit row
    captures workspace_id, document_id, filename, size, requirement
    code, and period key so a forensic reader can answer "who pulled
    what evidence and when".
    """
    from app.models import AuditLog

    access = _setup_workspace_session(api_client)
    submitted = _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])

    resp = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}"
        f"/submissions/{submitted['submission_id']}/document?download=1"
    )
    assert resp.status_code == 200, resp.text
    # Local backend serves via FileResponse with the requested
    # disposition; the test asserts the header rather than the
    # underlying mechanism.
    assert "attachment" in resp.headers.get("content-disposition", "").lower()

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db = factory()
    try:
        events = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "provider.document_downloaded",
                AuditLog.entity_id == submitted["submission_id"],
            )
            .all()
        )
        assert len(events) == 1
        event = events[0]
        assert event.actor_type == "provider"
        meta = event.event_metadata or {}
        assert meta.get("workspace_id") == access["workspace_id"]
        assert meta.get("filename") == "imss.pdf"
        assert meta.get("requirement_code")
        assert meta.get("period_key") == "2026-M04"
    finally:
        db.close()


def test_document_inline_preview_does_not_audit(
    api_client: TestClient,
) -> None:
    """Default (inline) requests are NOT audited — they fire on every
    iframe reload + every 'abrir en nueva pestaña' click. Auditing
    inline previews would drown the audit log in transient noise; the
    attachment path is the deliberate intent-to-keep signal.
    """
    from app.models import AuditLog

    access = _setup_workspace_session(api_client)
    submitted = _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])

    resp = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}"
        f"/submissions/{submitted['submission_id']}/document"
    )
    assert resp.status_code == 200, resp.text
    assert "inline" in resp.headers.get("content-disposition", "").lower()

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db = factory()
    try:
        count = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "provider.document_downloaded",
                AuditLog.entity_id == submitted["submission_id"],
            )
            .count()
        )
        assert count == 0
    finally:
        db.close()


def test_document_proxy_param_streams_instead_of_redirecting(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preview Blob fetches use ``?proxy=1`` so browser CORS settings
    on presigned storage cannot break the iframe/download flow."""
    from app.api.v1 import portal as portal_api

    access = _setup_workspace_session(api_client)
    submitted = _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])
    real_storage = portal_api.get_storage_service()

    class RedirectingStorage:
        def presigned_download_url(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return "https://storage.example.test/imss.pdf"

        def open_for_read(self, storage_key: str):
            return real_storage.open_for_read(storage_key)

    monkeypatch.setattr(
        portal_api,
        "get_storage_service",
        lambda: RedirectingStorage(),
    )

    base = (
        f"/api/v1/portal/workspaces/{access['workspace_id']}"
        f"/submissions/{submitted['submission_id']}/document"
    )
    redirected = api_client.get(base, follow_redirects=False)
    assert redirected.status_code == 302
    assert redirected.headers["location"] == "https://storage.example.test/imss.pdf"

    proxied = api_client.get(f"{base}?proxy=1")
    assert proxied.status_code == 200, proxied.text
    assert proxied.headers["content-type"].startswith("application/pdf")
    assert proxied.content.startswith(b"%PDF")


# ---------------------------------------------------------------------------
# Phase 5 / Slice 5B — expediente ZIP
# ---------------------------------------------------------------------------


def test_expediente_zip_returns_grouped_layout_and_writes_audit(
    api_client: TestClient,
) -> None:
    """The ZIP endpoint streams a valid archive grouped by
    institution/period and writes a ``provider.expediente_downloaded``
    audit row with file_count + total_bytes metadata.
    """
    import io
    import zipfile

    from app.models import AuditLog

    access = _setup_workspace_session(api_client)
    submitted_1 = _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])
    submitted_2 = _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])
    assert submitted_1 and submitted_2  # quiet F841

    resp = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/expediente.zip"
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("content-type") == "application/zip"
    cd = resp.headers.get("content-disposition", "")
    assert "attachment" in cd.lower()
    assert ".zip" in cd

    # The archive bytes must parse as a real ZIP and contain entries
    # grouped under ``imss/2026-M04/...`` (the canonical submission seed
    # writes IMSS / 2026-M04). Both submissions point at the same slot
    # so the second file gets a collision-disambiguating suffix.
    archive = zipfile.ZipFile(io.BytesIO(resp.content))
    names = archive.namelist()
    assert len(names) == 2, names
    assert all(n.startswith("imss/2026-M04/") for n in names), names

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db = factory()
    try:
        events = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "provider.expediente_downloaded",
                AuditLog.entity_id == access["workspace_id"],
            )
            .all()
        )
        assert len(events) == 1
        meta = events[0].event_metadata or {}
        assert meta.get("scope") == "workspace"
        assert meta.get("file_count") == 2
        assert meta.get("total_bytes", 0) > 0
    finally:
        db.close()


def test_expediente_zip_413_when_over_file_cap(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-flight cap check returns 413 before any streaming begins."""
    import app.services.expediente_zip as zip_service

    access = _setup_workspace_session(api_client)
    _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])
    _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])

    # Patch the cap to 1 so two submissions exceed it.
    monkeypatch.setattr(zip_service, "MAX_FILES", 1)

    resp = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/expediente.zip"
    )
    assert resp.status_code == 413, resp.text
    body = resp.json()
    assert "límite" in body["detail"].lower()
    assert "documentos" in body["detail"].lower()


def test_expediente_zip_enforces_tenant_isolation(
    api_client: TestClient,
) -> None:
    """Workspace B's session cannot pull workspace A's ZIP via crafted path id."""
    access_a = _setup_workspace_session(api_client)
    workspace_a = access_a["workspace_id"]
    _submit_canonical(api_client, vendor_rfc=access_a["vendor_rfc"])

    # Swap session to B; helper rebinds the cookie.
    _setup_workspace_session(
        api_client,
        payload=_access_payload(
            vendor_name="Otro Proveedor SA",
            vendor_rfc="OTR250101AB1",
        ),
    )

    resp = api_client.get(
        f"/api/v1/portal/workspaces/{workspace_a}/expediente.zip"
    )
    assert resp.status_code in (403, 404), resp.text


def test_expediente_zip_filters_by_institution(
    api_client: TestClient,
) -> None:
    """Slice 5C — ``?institution=imss`` scopes the archive to that
    institution's submissions. The seed canonical helper writes IMSS
    submissions, so an IMSS filter yields 2 files and a SAT filter
    yields 0 (and ships an empty but valid ZIP).
    """
    import io
    import zipfile

    access = _setup_workspace_session(api_client)
    _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])
    _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])

    imss = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/expediente.zip?institution=imss"
    )
    assert imss.status_code == 200, imss.text
    names_imss = zipfile.ZipFile(io.BytesIO(imss.content)).namelist()
    assert len(names_imss) == 2
    assert all(n.startswith("imss/") for n in names_imss)

    sat = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/expediente.zip?institution=sat"
    )
    assert sat.status_code == 200, sat.text
    # No SAT submissions seeded → empty (but valid) ZIP.
    names_sat = zipfile.ZipFile(io.BytesIO(sat.content)).namelist()
    assert names_sat == []


def test_expediente_zip_filters_by_status(
    api_client: TestClient,
) -> None:
    """Slice 5C — ``?status=`` scopes the archive to one status. The
    canonical seed writes ``pendiente_revision`` so the matching
    filter returns both files; an unmatched filter (``aprobado``)
    returns an empty ZIP.
    """
    import io
    import zipfile

    access = _setup_workspace_session(api_client)
    _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])
    _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])

    matches = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/expediente.zip?status=pendiente_revision"
    )
    assert matches.status_code == 200
    assert len(zipfile.ZipFile(io.BytesIO(matches.content)).namelist()) == 2

    empty = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/expediente.zip?status=aprobado"
    )
    assert empty.status_code == 200
    assert zipfile.ZipFile(io.BytesIO(empty.content)).namelist() == []


# ---------------------------------------------------------------------------
# Notification mark-read — audit-log fills (M4 partial)
# ---------------------------------------------------------------------------


def _notify_audit_rows(api_client: TestClient, action: str) -> list[AuditLog]:
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db = factory()
    try:
        return list(
            db.scalars(select(AuditLog).where(AuditLog.action == action))
        )
    finally:
        db.close()


def _workspace_owner_id(api_client: TestClient, workspace_id: str) -> str | None:
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db = factory()
    try:
        ws = db.get(ProviderWorkspace, workspace_id)
        return ws.owner_user_id if ws else None
    finally:
        db.close()


def test_mark_provider_notification_read_writes_audit_event(
    api_client: TestClient,
) -> None:
    """First unread→read transition writes an audit_log row tying the
    notification to the workspace owner. Replays stay silent."""
    from app.constants.statuses import ReviewerAction
    from app.models import Submission
    from app.services.submission_workflow import apply_reviewer_decision

    access = _setup_workspace_session(api_client)
    submitted = _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db = factory()
    try:
        sub = db.get(Submission, submitted["submission_id"])
        assert sub is not None
        apply_reviewer_decision(
            db,
            submission=sub,
            action=ReviewerAction.APPROVE,
            reason=None,
            reviewer_user_id="rev-prov-audit",
        )
    finally:
        db.close()

    listing = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/notifications"
    ).json()
    assert listing["unread_count"] == 1
    notification_id = listing["items"][0]["id"]

    first = api_client.post(
        f"/api/v1/portal/workspaces/{access['workspace_id']}"
        f"/notifications/{notification_id}/read"
    )
    assert first.status_code == 200

    events = _notify_audit_rows(api_client, "provider.notification_marked_read")
    assert len(events) == 1
    event = events[0]
    assert event.entity_type == "provider_notification"
    assert event.entity_id == notification_id
    assert event.actor_type == "provider"
    assert event.actor_id == _workspace_owner_id(
        api_client, access["workspace_id"]
    )
    assert (event.after or {}).get("workspace_id") == access["workspace_id"]

    # Idempotent replay writes nothing more.
    second = api_client.post(
        f"/api/v1/portal/workspaces/{access['workspace_id']}"
        f"/notifications/{notification_id}/read"
    )
    assert second.status_code == 200
    after_replay = _notify_audit_rows(
        api_client, "provider.notification_marked_read"
    )
    assert len(after_replay) == 1


def test_mark_all_provider_notifications_read_writes_audit_event(
    api_client: TestClient,
) -> None:
    """Bulk mark-read writes a single audit row capturing the flipped
    notification ids. A no-op replay writes nothing."""
    from app.constants.statuses import ReviewerAction
    from app.models import Submission
    from app.services.submission_workflow import apply_reviewer_decision

    access = _setup_workspace_session(api_client)
    submitted = _submit_canonical(api_client, vendor_rfc=access["vendor_rfc"])

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db = factory()
    try:
        sub = db.get(Submission, submitted["submission_id"])
        assert sub is not None
        apply_reviewer_decision(
            db,
            submission=sub,
            action=ReviewerAction.APPROVE,
            reason=None,
            reviewer_user_id="rev-prov-bulk",
        )
    finally:
        db.close()

    listing = api_client.get(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/notifications"
    ).json()
    unread_ids = sorted(
        item["id"] for item in listing["items"] if item["read_at"] is None
    )
    assert len(unread_ids) >= 1

    bulk = api_client.post(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/notifications/read-all"
    )
    assert bulk.status_code == 200
    assert bulk.json()["unread_count"] == 0

    events = _notify_audit_rows(
        api_client, "provider.notifications_marked_all_read"
    )
    assert len(events) == 1
    event = events[0]
    assert event.entity_type == "provider_workspace"
    assert event.entity_id == access["workspace_id"]
    assert event.actor_type == "provider"
    assert event.actor_id == _workspace_owner_id(
        api_client, access["workspace_id"]
    )
    payload = event.after or {}
    assert payload.get("marked_count") == len(unread_ids)
    assert sorted(payload.get("notification_ids") or []) == unread_ids

    # No-op replay stays silent.
    noop = api_client.post(
        f"/api/v1/portal/workspaces/{access['workspace_id']}/notifications/read-all"
    )
    assert noop.status_code == 200
    after_noop = _notify_audit_rows(
        api_client, "provider.notifications_marked_all_read"
    )
    assert len(after_noop) == 1
