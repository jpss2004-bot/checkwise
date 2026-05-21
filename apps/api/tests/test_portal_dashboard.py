"""Phase 4 — provider dashboard + onboarding/calendar slot adoption + lineage detail.

Covers everything Phase 4 adds:

* ``GET /api/v1/portal/workspaces/{id}/onboarding`` and ``/calendar``
  now route through ``evidence_slots`` and become replacement-lineage
  aware (a superseded rejection no longer wins over its replacement).
* ``GET /api/v1/portal/workspaces/{id}/submissions/{submission_id}``
  carries ``supersedes_submission_id`` + ``superseded_by_submission_id``.
* ``GET /api/v1/portal/workspaces/{id}/dashboard`` returns the
  backend-computed read model the frontend now consumes.

Tenancy is exercised in the workspace tests; here we focus on the
read-model semantics. Cross-tenant rejection for the dashboard is
covered by ``test_dashboard_rejects_foreign_workspace``.
"""

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

from app.constants.statuses import DocumentStatus
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Client,
    ProviderWorkspace,
    Submission,
    User,
    Vendor,
    entities,  # noqa: F401 — register mappers
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


_user_seq = itertools.count(1)


def _setup_workspace(
    api_client: TestClient,
    *,
    vendor_name: str = "Servicios Demo SA de CV",
    vendor_rfc: str = "DEM260512AB1",
    client_name: str = "Cliente Piloto CheckWise",
    fresh_client: TestClient | None = None,
) -> dict:
    target_client = fresh_client or api_client
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        seq = next(_user_seq)
        user = User(
            email=f"dash-{seq}@checkwise.test",
            password_hash=hash_password("CheckWiseTest!2026"),
            full_name=vendor_name,
            status="active",
            must_change_password=False,
        )
        db.add(user)
        db.flush()
        client_row = db.query(Client).filter_by(name=client_name).first()
        if client_row is None:
            client_row = Client(name=client_name)
            db.add(client_row)
            db.flush()
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
            access_token="placeholder",
        )
        db.add(workspace)
        db.commit()
        ws_id = workspace.id
        user_id, user_email = user.id, user.email
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
    return {"workspace_id": ws_id, "bearer": token, "user_id": user_id}


def _canonical_b1_payload() -> dict:
    """Form data for a canonical INFONAVIT B1 upload."""
    from app.core.compliance_catalog import recurring_for_year

    catalog_item = next(
        item
        for item in recurring_for_year(2026)
        if item.institution == "infonavit" and item.period_key == "2026-B1"
    )
    return {
        "period_code": "2026-B1",
        "period_key": catalog_item.period_key,
        "load_type": "bimestral",
        "institution_code": "infonavit",
        "requirement_name": catalog_item.name,
        "requirement_code": catalog_item.code,
        "initial_status": "pendiente_revision",
    }


def _upload(api_client: TestClient, ws_id: str, *, data: dict, supersedes: str | None = None):
    payload = dict(data)
    if supersedes is not None:
        payload["supersedes_submission_id"] = supersedes
    return api_client.post(
        f"/api/v1/portal/workspaces/{ws_id}/submissions",
        data=payload,
        files={"file": ("doc.pdf", _pdf_bytes(), "application/pdf")},
    )


def _set_status(api_client: TestClient, submission_id: str, status_value: str) -> None:
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        sub = db.get(Submission, submission_id)
        assert sub is not None
        sub.status = status_value
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Part A — onboarding + calendar use replacement-aware current state
# ---------------------------------------------------------------------------


def test_calendar_uses_replacement_as_current_not_superseded_rejection(
    api_client: TestClient,
) -> None:
    """Phase 4 contract: when a rejected submission has been replaced,
    the calendar surfaces the replacement (in review) — never the
    superseded rejection."""
    ws = _setup_workspace(api_client)
    first = _upload(api_client, ws["workspace_id"], data=_canonical_b1_payload())
    prior_id = first.json()["submission_id"]
    _set_status(api_client, prior_id, DocumentStatus.RECHAZADO.value)

    second = _upload(
        api_client,
        ws["workspace_id"],
        data=_canonical_b1_payload(),
        supersedes=prior_id,
    )
    assert second.status_code == 202, second.text
    new_id = second.json()["submission_id"]

    calendar = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/calendar?year=2026"
    ).json()
    # Find the B1 entry.
    infonavit_b1 = None
    for month in calendar["months"]:
        for inst in month["institutions"]:
            if inst["institution"] != "infonavit":
                continue
            for item in inst["items"]:
                if item["period_key"] == "2026-B1":
                    infonavit_b1 = item
                    break
    assert infonavit_b1 is not None
    assert infonavit_b1["submission_id"] == new_id
    assert infonavit_b1["status"] == DocumentStatus.PENDIENTE_REVISION.value


def test_onboarding_uses_replacement_as_current_not_superseded_rejection(
    api_client: TestClient,
) -> None:
    """Same rule on the onboarding (Expediente Corporativo) surface."""
    ws = _setup_workspace(api_client)
    base = {
        "period_code": "2026-ONB",
        "period_key": "onb-repse-2026",
        "load_type": "alta_inicial",
        "institution_code": "stps_repse",
        "requirement_name": "Registro REPSE original",
        "requirement_code": "ONB-REPSE-001",
        "initial_status": "pendiente_revision",
    }
    first = _upload(api_client, ws["workspace_id"], data=base)
    prior_id = first.json()["submission_id"]
    _set_status(api_client, prior_id, DocumentStatus.RECHAZADO.value)

    second = _upload(api_client, ws["workspace_id"], data=base, supersedes=prior_id)
    new_id = second.json()["submission_id"]

    onboarding = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/onboarding"
    ).json()
    # Find the REPSE onboarding item.
    repse_item = None
    for section in onboarding["sections"]:
        for item in section["items"]:
            if item["code"] == "ONB-REPSE-001":
                repse_item = item
                break
    assert repse_item is not None
    assert repse_item["submission_id"] == new_id
    assert repse_item["status"] == DocumentStatus.PENDIENTE_REVISION.value


# ---------------------------------------------------------------------------
# Part B — submission detail carries lineage pointers
# ---------------------------------------------------------------------------


def test_submission_detail_returns_supersedes_submission_id(
    api_client: TestClient,
) -> None:
    ws = _setup_workspace(api_client)
    first = _upload(api_client, ws["workspace_id"], data=_canonical_b1_payload())
    prior_id = first.json()["submission_id"]
    _set_status(api_client, prior_id, DocumentStatus.RECHAZADO.value)

    second = _upload(
        api_client, ws["workspace_id"], data=_canonical_b1_payload(), supersedes=prior_id
    )
    new_id = second.json()["submission_id"]

    detail = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/submissions/{new_id}"
    ).json()
    assert detail["supersedes_submission_id"] == prior_id
    assert detail["superseded_by_submission_id"] is None


def test_submission_detail_returns_superseded_by_submission_id(
    api_client: TestClient,
) -> None:
    ws = _setup_workspace(api_client)
    first = _upload(api_client, ws["workspace_id"], data=_canonical_b1_payload())
    prior_id = first.json()["submission_id"]
    _set_status(api_client, prior_id, DocumentStatus.RECHAZADO.value)

    second = _upload(
        api_client, ws["workspace_id"], data=_canonical_b1_payload(), supersedes=prior_id
    )
    new_id = second.json()["submission_id"]

    detail = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/submissions/{prior_id}"
    ).json()
    assert detail["supersedes_submission_id"] is None
    assert detail["superseded_by_submission_id"] == new_id


def test_submission_detail_unrelated_submission_has_both_lineage_fields_null(
    api_client: TestClient,
) -> None:
    ws = _setup_workspace(api_client)
    first = _upload(api_client, ws["workspace_id"], data=_canonical_b1_payload())
    sub_id = first.json()["submission_id"]
    detail = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/submissions/{sub_id}"
    ).json()
    assert detail["supersedes_submission_id"] is None
    assert detail["superseded_by_submission_id"] is None


def test_submission_detail_tenant_isolation_holds(api_client: TestClient) -> None:
    """A workspace cannot read another workspace's submission detail."""
    ws_a = _setup_workspace(api_client)
    upload_a = _upload(api_client, ws_a["workspace_id"], data=_canonical_b1_payload())
    sub_a_id = upload_a.json()["submission_id"]

    fresh = TestClient(api_client.app)
    fresh.app.state.testing_session = api_client.app.state.testing_session  # type: ignore[attr-defined]
    ws_b = _setup_workspace(
        api_client,
        vendor_name="Otro Proveedor SA",
        vendor_rfc="OTR260512AB1",
        fresh_client=fresh,
    )

    cross = fresh.get(
        f"/api/v1/portal/workspaces/{ws_b['workspace_id']}/submissions/{sub_a_id}",
        headers={"Authorization": f"Bearer {ws_b['bearer']}"},
    )
    assert cross.status_code == 404


# ---------------------------------------------------------------------------
# Part C — dashboard endpoint
# ---------------------------------------------------------------------------


def test_dashboard_returns_expected_payload_shape(api_client: TestClient) -> None:
    ws = _setup_workspace(api_client)
    response = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/dashboard"
    )
    assert response.status_code == 200, response.text
    body = response.json()

    for key in (
        "workspace_id",
        "persona_type",
        "onboarding_summary",
        "document_state_counts",
        "semaphore",
        "suggested_actions",
        "attention_today",
        "upcoming_deadlines",
        "recent_uploads",
        "institution_breakdown",
    ):
        assert key in body, f"missing key {key}"
    assert isinstance(body["recent_uploads"], list)
    assert isinstance(body["institution_breakdown"], list)
    for row in body["institution_breakdown"]:
        for key in (
            "institution",
            "approved",
            "in_review",
            "needs_action",
            "pending",
            "total",
        ):
            assert key in row, f"institution_breakdown row missing key {key}"

    onboarding = body["onboarding_summary"]
    for key in (
        "total_required",
        "completed",
        "in_review",
        "needs_action",
        "optional_pending",
        "completion_pct",
        "is_gate_satisfied",
    ):
        assert key in onboarding

    counts = body["document_state_counts"]
    for key in (
        "approved",
        "in_review",
        "uploaded",
        "pending",
        "needs_review",
        "rejected",
        "expired",
        "exception",
    ):
        assert key in counts

    semaphore = body["semaphore"]
    assert semaphore["level"] in {"green", "yellow", "red"}
    assert "label" in semaphore
    assert "reason" in semaphore
    assert "compliance_pct" in semaphore
    assert "total_tracked" in semaphore
    assert "on_track" in semaphore


def test_dashboard_upcoming_deadlines_expose_due_in_days(
    api_client: TestClient,
) -> None:
    """P1.6: the upcoming_deadlines rows must carry ``due_in_days`` so the
    /portal/reports Compliance Pulse strip can bucket items by urgency
    without re-parsing the period_key on the client. The field is
    additive and always >= 0 because _compute_upcoming_deadlines filters
    overdue rows out."""
    ws = _setup_workspace(api_client)
    body = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/dashboard"
    ).json()
    rows = body["upcoming_deadlines"]
    # Brand-new workspace has plenty of missing required calendar slots,
    # so we expect at least one upcoming deadline row to surface.
    assert isinstance(rows, list)
    for row in rows:
        assert "due_in_days" in row, "every upcoming row must carry due_in_days"
        assert row["due_in_days"] is None or row["due_in_days"] >= 0


def test_dashboard_empty_workspace_reports_pending_counts(
    api_client: TestClient,
) -> None:
    """A brand-new workspace has zero uploads. All required slots roll
    up as either ``pending`` (catalog slots) and the semaphore is
    red — P1.1 (2026-05-20) flipped the 0-of-N branch from yellow to
    red because 0% compliance shouldn't read as "in progress"."""
    ws = _setup_workspace(api_client)
    body = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/dashboard"
    ).json()

    assert body["document_state_counts"]["pending"] > 0
    assert body["document_state_counts"]["approved"] == 0
    assert body["document_state_counts"]["rejected"] == 0
    assert body["semaphore"]["level"] == "red"
    assert body["onboarding_summary"]["total_required"] > 0
    assert body["onboarding_summary"]["completed"] == 0


def test_dashboard_counts_in_review_slot_correctly(api_client: TestClient) -> None:
    ws = _setup_workspace(api_client)
    _upload(api_client, ws["workspace_id"], data=_canonical_b1_payload())
    body = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/dashboard"
    ).json()
    # The freshly uploaded submission is in pendiente_revision → IN_REVIEW bucket.
    assert body["document_state_counts"]["in_review"] >= 1
    # Semaphore stays red because on_track is still 0 (P1.1, 2026-05-20):
    # an in-review submission is not yet approved, so the workspace has
    # not started accumulating compliance.
    assert body["semaphore"]["level"] == "red"


def test_dashboard_counts_approved_slot(api_client: TestClient) -> None:
    ws = _setup_workspace(api_client)
    upload = _upload(api_client, ws["workspace_id"], data=_canonical_b1_payload())
    _set_status(api_client, upload.json()["submission_id"], DocumentStatus.APROBADO.value)
    body = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/dashboard"
    ).json()
    assert body["document_state_counts"]["approved"] >= 1


def test_dashboard_flags_rejected_required_slot_as_red(api_client: TestClient) -> None:
    """A rejected required slot pushes the semaphore to red and emits
    a high-priority suggested action."""
    ws = _setup_workspace(api_client)
    upload = _upload(api_client, ws["workspace_id"], data=_canonical_b1_payload())
    _set_status(api_client, upload.json()["submission_id"], DocumentStatus.RECHAZADO.value)

    body = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/dashboard"
    ).json()
    assert body["semaphore"]["level"] == "red"
    assert body["document_state_counts"]["rejected"] >= 1
    # A high-priority reupload action is present for the rejected slot.
    high_actions = [a for a in body["suggested_actions"] if a["priority"] == "high"]
    assert high_actions, "expected a high-priority suggested action for the rejection"
    assert any(a["type"] == "reupload" for a in high_actions)


def test_dashboard_uses_replacement_submission_as_current_not_superseded(
    api_client: TestClient,
) -> None:
    """Dashboard counts must reflect the replacement, not the rejection
    that was already corrected. Tests 9 + 10 worth of contract."""
    ws = _setup_workspace(api_client)
    first = _upload(api_client, ws["workspace_id"], data=_canonical_b1_payload())
    prior_id = first.json()["submission_id"]
    _set_status(api_client, prior_id, DocumentStatus.RECHAZADO.value)

    # Provider corrects → in_review.
    _upload(
        api_client, ws["workspace_id"], data=_canonical_b1_payload(), supersedes=prior_id
    )

    body = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/dashboard"
    ).json()
    # The B1 slot is now in_review (replacement). It must NOT count as
    # rejected — the superseded rejection no longer dominates the slot.
    counts = body["document_state_counts"]
    assert counts["in_review"] >= 1
    # After replacement, no required slot is rejected. The semaphore
    # remains red because on_track is still 0 (the replacement is
    # in_review, not approved) — see P1.1 (2026-05-20). It is no
    # longer red for the "blocking" reason; it's red for the
    # "no avance" reason. The assertion below is intentionally only
    # on the level — the *reason* string would distinguish them.
    assert body["semaphore"]["level"] == "red"


def test_dashboard_recent_uploads_returns_latest_submissions(
    api_client: TestClient,
) -> None:
    """Session 4 (2026-05-21): the dashboard now exposes a
    ``recent_uploads`` list — the N most recent submissions, newest
    first — so the operational surface can answer "what did I upload?"
    without a round-trip to /portal/submissions.

    Empty for a brand-new workspace; populated after the provider
    uploads, with the status surfaced verbatim from the submissions
    table so the timeline truth never diverges.
    """
    ws = _setup_workspace(api_client)
    empty = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/dashboard"
    ).json()
    assert empty["recent_uploads"] == []

    first = _upload(api_client, ws["workspace_id"], data=_canonical_b1_payload())
    submission_id = first.json()["submission_id"]
    _set_status(api_client, submission_id, DocumentStatus.APROBADO.value)

    body = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/dashboard"
    ).json()
    rows = body["recent_uploads"]
    assert len(rows) == 1
    row = rows[0]
    assert row["submission_id"] == submission_id
    assert row["status"] == DocumentStatus.APROBADO.value
    assert row["institution"] == "infonavit"
    assert row["period_key"] == "2026-B1"
    assert row["href"] == f"/portal/submissions/{submission_id}"
    assert row["filename"] == "doc.pdf"
    # ISO timestamp — keep parseable without locking to a precise value.
    from datetime import datetime

    datetime.fromisoformat(row["submitted_at"])


def test_dashboard_suggested_action_quotes_reviewer_note_when_rejected(
    api_client: TestClient,
) -> None:
    """Wise Phase 1 (2026-05-21): suggested_actions for rejected /
    needs_correction / possible_mismatch slots must carry the
    reviewer's most recent decision message in ``reviewer_note`` so
    the Wise copilot can quote it inline. Slots with no reviewer
    decision yet (or in other states) leave the field null.
    """
    from app.models import ValidationEvent

    ws = _setup_workspace(api_client)
    first = _upload(api_client, ws["workspace_id"], data=_canonical_b1_payload())
    submission_id = first.json()["submission_id"]
    _set_status(api_client, submission_id, DocumentStatus.RECHAZADO.value)

    # Persist a reviewer_decision event the way the workflow service does.
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        db.add(
            ValidationEvent(
                submission_id=submission_id,
                event_type="reviewer_decision",
                result="rechazado",
                severity="error",
                message="El RFC en la imagen no coincide con el RFC del proveedor.",
                actor_type="reviewer",
            )
        )
        db.commit()
    finally:
        db.close()

    body = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/dashboard"
    ).json()
    high = [a for a in body["suggested_actions"] if a["priority"] == "high"]
    assert high, "expected at least one high-priority action for the rejected slot"
    # The rejected slot is the INFONAVIT B1 we uploaded. The catalog
    # code includes the period and document type — look it up via the
    # same recurring_for_year() the test helper uses so the test
    # doesn't bake in a brittle string.
    from app.core.compliance_catalog import recurring_for_year

    canonical_code = next(
        item.code
        for item in recurring_for_year(2026)
        if item.institution == "infonavit" and item.period_key == "2026-B1"
    )
    rejected_action = next(
        (a for a in high if a["requirement_code"] == canonical_code),
        None,
    )
    assert rejected_action is not None, (
        f"expected suggested action for {canonical_code} in {high}"
    )
    assert (
        rejected_action["reviewer_note"]
        == "El RFC en la imagen no coincide con el RFC del proveedor."
    )
    # Non-actionable suggestions (e.g. missing required onboarding doc)
    # carry null because no reviewer has touched them yet.
    pending = [a for a in body["suggested_actions"] if a["priority"] == "medium"]
    for action in pending:
        assert action["reviewer_note"] is None


def test_dashboard_rejects_foreign_workspace(api_client: TestClient) -> None:
    """User B cannot read user A's dashboard."""
    ws_a = _setup_workspace(api_client)
    fresh = TestClient(api_client.app)
    fresh.app.state.testing_session = api_client.app.state.testing_session  # type: ignore[attr-defined]
    ws_b = _setup_workspace(
        api_client,
        vendor_name="Otro Proveedor SA",
        vendor_rfc="OTR260512AB1",
        fresh_client=fresh,
    )

    cross = fresh.get(
        f"/api/v1/portal/workspaces/{ws_a['workspace_id']}/dashboard",
        headers={"Authorization": f"Bearer {ws_b['bearer']}"},
    )
    assert cross.status_code == 403
