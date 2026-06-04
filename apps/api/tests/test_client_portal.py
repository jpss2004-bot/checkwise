"""Phase 8 — Client Portal read model tests.

Covers the new ``/client/*`` router: permission gates, scope
resolution, semaphore semantics, lineage visibility, sanitised
activity feed.
"""

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

from app.constants.statuses import DocumentStatus, ReviewerAction
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    AuditLog,
    Client,
    Membership,
    Organization,
    ProviderWorkspace,
    Submission,
    User,
    Vendor,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password
from app.services.submission_workflow import apply_reviewer_decision

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
def api_client(db_factory, tmp_path) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    previous = settings.LOCAL_STORAGE_PATH
    settings.LOCAL_STORAGE_PATH = str(tmp_path / "storage")

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        settings.LOCAL_STORAGE_PATH = previous


_user_seq = itertools.count(1)


def _pdf_bytes() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()


def _seed_client(db_factory, name: str = "Cliente Demo") -> str:
    db = db_factory()
    try:
        client = Client(name=name)
        db.add(client)
        db.commit()
        return client.id
    finally:
        db.close()


def _seed_vendor_with_workspace(
    db_factory,
    *,
    client_id: str,
    vendor_name: str = "Proveedor Demo",
    rfc: str = "DEM260512AB1",
) -> tuple[str, str]:
    db = db_factory()
    try:
        vendor = Vendor(
            client_id=client_id,
            name=vendor_name,
            rfc=rfc.upper(),
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()
        ws = ProviderWorkspace(
            client_id=client_id,
            vendor_id=vendor.id,
            persona_type="moral",
            display_name=vendor_name,
            access_token=f"SECRET-{rfc}",
        )
        db.add(ws)
        db.commit()
        return vendor.id, ws.id
    finally:
        db.close()


def _seed_user_with_role(
    db_factory,
    *,
    role: str | None,
    client_id: str | None = None,
    email_prefix: str = "user",
) -> tuple[str, str, str]:
    """Returns (user_id, email, password).

    role=None ⇒ no memberships.
    role=client_admin ⇒ org(kind=client, client_id=client_id), membership.
    role=internal_admin/reviewer ⇒ org(kind=internal), membership.
    """
    password = "ClientTest!2026"
    seq = next(_user_seq)
    email = f"{email_prefix}-{seq}@checkwise.test"
    db = db_factory()
    try:
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=f"User {seq}",
            status="active",
        )
        db.add(user)
        db.flush()
        if role is not None:
            if role == "client_admin":
                assert client_id is not None, "client_admin needs a client"
                org = Organization(
                    name=f"Org Client {seq}", kind="client", client_id=client_id
                )
            else:
                org = Organization(name=f"Org Internal {seq}", kind="internal")
            db.add(org)
            db.flush()
            db.add(
                Membership(
                    user_id=user.id,
                    organization_id=org.id,
                    role=role,
                    status="active",
                )
            )
        db.commit()
        return user.id, email, password
    finally:
        db.close()


def _login(api_client: TestClient, email: str, password: str) -> str:
    resp = api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _seed_submission_for_workspace(
    api_client: TestClient,
    db_factory,
    ws_id: str,
    *,
    status_value: str | None = None,
    requirement_code: str = "REC-INFONAVIT-2026-03-cuotas-obrero-patronales",
    period_key: str = "2026-B1",
    institution_code: str = "infonavit",
    load_type: str = "bimestral",
    requirement_name: str = "Cuotas obrero patronales",
    period_code: str = "2026-B1",
    supersedes: str | None = None,
) -> str:
    """Insert a submission via the workspace endpoint, then optionally
    override its status with a direct DB poke (to seed terminal states
    without going through the reviewer workflow).
    """
    # Find the owner user for the workspace, mint a session for them,
    # then upload. The seeded workspaces here don't have an owner yet,
    # so create an admin-like user with a workspace owner relationship.
    db: Session = db_factory()
    try:
        ws = db.get(ProviderWorkspace, ws_id)
        assert ws is not None
        if ws.owner_user_id is None:
            seq = next(_user_seq)
            user = User(
                email=f"owner-{seq}@checkwise.test",
                password_hash=hash_password("OwnerTest!2026"),
                full_name=f"Owner {seq}",
                status="active",
                must_change_password=False,
            )
            db.add(user)
            db.flush()
            ws.owner_user_id = user.id
            db.commit()
            owner_email = user.email
        else:
            owner_email = (
                db.scalar(select(User.email).where(User.id == ws.owner_user_id)) or ""
            )
    finally:
        db.close()

    # Enter the workspace.
    token = _login(api_client, owner_email, "OwnerTest!2026")
    api_client.cookies.clear()
    enter = api_client.post(
        "/api/v1/portal/enter",
        json={"workspace_id": ws_id},
        headers=_h(token),
    )
    assert enter.status_code == 200, enter.text

    data = {
        "period_code": period_code,
        "period_key": period_key,
        "load_type": load_type,
        "institution_code": institution_code,
        "requirement_name": requirement_name,
        "requirement_code": requirement_code,
        "initial_status": "pendiente_revision",
    }
    if supersedes:
        data["supersedes_submission_id"] = supersedes
    response = api_client.post(
        f"/api/v1/portal/workspaces/{ws_id}/submissions",
        data=data,
        files={"file": ("doc.pdf", _pdf_bytes(), "application/pdf")},
        headers=_h(token),
    )
    assert response.status_code == 202, response.text
    sub_id = response.json()["submission_id"]

    if status_value:
        db = db_factory()
        try:
            sub = db.get(Submission, sub_id)
            assert sub is not None
            sub.status = status_value
            db.commit()
        finally:
            db.close()

    # Clear the cookies so the next API call isn't accidentally
    # authenticated as the workspace owner.
    api_client.cookies.clear()
    return sub_id


# ---------------------------------------------------------------------------
# Permission gates
# ---------------------------------------------------------------------------


def test_client_overview_unauthenticated_returns_401(api_client: TestClient) -> None:
    resp = api_client.get("/api/v1/client/overview")
    assert resp.status_code == 401


def test_client_overview_rejects_reviewer_only(
    api_client: TestClient, db_factory
) -> None:
    _, email, pw = _seed_user_with_role(db_factory, role="reviewer", email_prefix="rev")
    token = _login(api_client, email, pw)
    resp = api_client.get("/api/v1/client/overview", headers=_h(token))
    assert resp.status_code == 403


def test_client_overview_rejects_user_with_no_role(
    api_client: TestClient, db_factory
) -> None:
    _, email, pw = _seed_user_with_role(db_factory, role=None, email_prefix="nobody")
    token = _login(api_client, email, pw)
    resp = api_client.get("/api/v1/client/overview", headers=_h(token))
    assert resp.status_code == 403


def test_client_admin_can_access_overview_for_own_client(
    api_client: TestClient, db_factory
) -> None:
    client_id = _seed_client(db_factory, "Cliente A")
    _seed_vendor_with_workspace(db_factory, client_id=client_id)
    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.get("/api/v1/client/overview", headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["client_id"] == client_id
    assert body["client_name"] == "Cliente A"
    assert body["vendors_total"] == 1


def test_client_admin_cannot_see_another_client(
    api_client: TestClient, db_factory
) -> None:
    own_id = _seed_client(db_factory, "Cliente A")
    other_id = _seed_client(db_factory, "Cliente B")
    _seed_vendor_with_workspace(db_factory, client_id=other_id)
    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=own_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.get(
        f"/api/v1/client/overview?client_id={other_id}", headers=_h(token)
    )
    assert resp.status_code == 403


def test_internal_admin_can_inspect_with_explicit_client_id(
    api_client: TestClient, db_factory
) -> None:
    client_id = _seed_client(db_factory, "Cliente Inspeccionado")
    _seed_vendor_with_workspace(db_factory, client_id=client_id)
    _, email, pw = _seed_user_with_role(
        db_factory, role="internal_admin", email_prefix="adm"
    )
    token = _login(api_client, email, pw)
    # Without client_id and without a client_admin membership, expect a 400.
    plain = api_client.get("/api/v1/client/overview", headers=_h(token))
    assert plain.status_code == 400
    # With explicit client_id, the inspection succeeds.
    inspected = api_client.get(
        f"/api/v1/client/overview?client_id={client_id}", headers=_h(token)
    )
    assert inspected.status_code == 200, inspected.text
    assert inspected.json()["client_id"] == client_id


# ---------------------------------------------------------------------------
# /vendors
# ---------------------------------------------------------------------------


def test_client_vendors_scopes_and_redacts_access_token(
    api_client: TestClient, db_factory
) -> None:
    client_id = _seed_client(db_factory)
    _seed_vendor_with_workspace(db_factory, client_id=client_id)
    other_id = _seed_client(db_factory, "Otro cliente")
    _seed_vendor_with_workspace(
        db_factory, client_id=other_id, vendor_name="Otro proveedor", rfc="OTR260512AB1"
    )
    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.get("/api/v1/client/vendors", headers=_h(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["client_id"] == client_id
    assert body["total"] == 1
    assert "SECRET" not in resp.text, "access_token must never appear in client vendor list"
    row = body["items"][0]
    assert row["vendor_name"] == "Proveedor Demo"
    assert "access_token" not in row


# ---------------------------------------------------------------------------
# /vendors/{vendor_id}
# ---------------------------------------------------------------------------


def test_vendor_detail_returns_dashboard_shape_for_owned_vendor(
    api_client: TestClient, db_factory
) -> None:
    client_id = _seed_client(db_factory)
    vendor_id, _ = _seed_vendor_with_workspace(db_factory, client_id=client_id)
    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.get(
        f"/api/v1/client/vendors/{vendor_id}", headers=_h(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in (
        "vendor",
        "workspace",
        "onboarding_summary",
        "document_state_counts",
        "semaphore",
        "suggested_actions",
        "attention_today",
        "upcoming_deadlines",
        "recent_submissions",
        "recent_reviewer_notes",
    ):
        assert key in body, f"missing {key}"
    # access_token never appears.
    assert "access_token" not in str(body)


def test_vendor_detail_rejects_foreign_vendor(
    api_client: TestClient, db_factory
) -> None:
    own = _seed_client(db_factory, "Mío")
    foreign = _seed_client(db_factory, "Ajeno")
    foreign_vendor, _ = _seed_vendor_with_workspace(
        db_factory, client_id=foreign, vendor_name="Ajeno", rfc="AJE260512AB1"
    )
    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=own, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.get(
        f"/api/v1/client/vendors/{foreign_vendor}", headers=_h(token)
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /calendar
# ---------------------------------------------------------------------------


def test_client_calendar_aggregates_months(
    api_client: TestClient, db_factory
) -> None:
    client_id = _seed_client(db_factory)
    _seed_vendor_with_workspace(db_factory, client_id=client_id)
    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.get("/api/v1/client/calendar?year=2026", headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["client_id"] == client_id
    assert body["year"] == 2026
    assert len(body["months"]) == 12
    # Every month is well-formed.
    for m in body["months"]:
        assert "month_label" in m
        assert "due_total" in m
        assert "items" in m
    # At least one month has items (we seeded one workspace).
    populated = [m for m in body["months"] if m["due_total"] > 0]
    assert populated, "expected the seeded vendor to populate at least one month"


# ---------------------------------------------------------------------------
# /submissions — filters + replacement lineage
# ---------------------------------------------------------------------------


def test_client_submissions_filters_by_vendor_status_period(
    api_client: TestClient, db_factory
) -> None:
    client_id = _seed_client(db_factory)
    vendor_id, ws_id = _seed_vendor_with_workspace(db_factory, client_id=client_id)
    _seed_submission_for_workspace(api_client, db_factory, ws_id)
    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)

    base = api_client.get(
        f"/api/v1/client/submissions?vendor_id={vendor_id}", headers=_h(token)
    )
    assert base.status_code == 200, base.text
    items = base.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["vendor_id"] == vendor_id
    assert item["status"] == DocumentStatus.PENDIENTE_REVISION.value
    assert item["period_key"] == "2026-B1"

    # Filter by mismatched status — no rows.
    rejected = api_client.get(
        "/api/v1/client/submissions?status=rechazado", headers=_h(token)
    ).json()
    assert rejected["items"] == []

    # Filter by mismatched period — no rows.
    mismatched = api_client.get(
        "/api/v1/client/submissions?period_key=2099-M01", headers=_h(token)
    ).json()
    assert mismatched["items"] == []


def test_client_submissions_filters_by_institution(
    api_client: TestClient, db_factory
) -> None:
    """Phase 3 / Slice 3A — the new ``?institution=`` filter scopes the
    response to submissions whose requirement maps to that institution
    (sat / imss / infonavit / stps_repse / interno_cliente). Each
    ClientSubmissionItem also carries its institution code so the
    client portal table can render an institution column without a
    follow-up lookup.
    """
    client_id = _seed_client(db_factory)
    _, ws_id = _seed_vendor_with_workspace(db_factory, client_id=client_id)
    # Two submissions on the same workspace under different
    # institutions. ``_seed_submission_for_workspace`` already accepts
    # an institution_code override.
    _seed_submission_for_workspace(
        api_client,
        db_factory,
        ws_id,
        requirement_code="REC-IMSS-2026-05-cuotas-obrero-patronales",
        period_key="2026-M04",
        period_code="2026-M04",
        institution_code="imss",
        load_type="mensual",
        requirement_name="Cuotas obrero patronales",
    )
    _seed_submission_for_workspace(
        api_client,
        db_factory,
        ws_id,
        requirement_code="REC-SAT-2026-05-declaracion-iva",
        period_key="2026-M04",
        period_code="2026-M04",
        institution_code="sat",
        load_type="mensual",
        requirement_name="Declaración IVA",
    )
    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)

    # No filter → both rows back, each carrying its institution.
    all_resp = api_client.get(
        "/api/v1/client/submissions", headers=_h(token)
    ).json()
    institutions = {item["institution"] for item in all_resp["items"]}
    assert institutions == {"imss", "sat"}

    # Filter by ``imss`` → only the IMSS row.
    imss_only = api_client.get(
        "/api/v1/client/submissions?institution=imss", headers=_h(token)
    ).json()
    assert len(imss_only["items"]) == 1
    assert imss_only["items"][0]["institution"] == "imss"
    assert imss_only["items"][0]["requirement_name"] == "Cuotas obrero patronales"

    # Filter by ``sat`` → only the SAT row.
    sat_only = api_client.get(
        "/api/v1/client/submissions?institution=sat", headers=_h(token)
    ).json()
    assert len(sat_only["items"]) == 1
    assert sat_only["items"][0]["institution"] == "sat"

    # Filter by an unknown code → empty (no 400; future catalog
    # additions can ship without breaking the client portal).
    unknown = api_client.get(
        "/api/v1/client/submissions?institution=does_not_exist",
        headers=_h(token),
    ).json()
    assert unknown["items"] == []


def test_client_submissions_carries_replacement_lineage(
    api_client: TestClient, db_factory
) -> None:
    client_id = _seed_client(db_factory)
    _, ws_id = _seed_vendor_with_workspace(db_factory, client_id=client_id)
    prior = _seed_submission_for_workspace(
        api_client, db_factory, ws_id, status_value=DocumentStatus.RECHAZADO.value
    )
    replacement = _seed_submission_for_workspace(
        api_client, db_factory, ws_id, supersedes=prior
    )
    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.get("/api/v1/client/submissions", headers=_h(token))
    assert resp.status_code == 200, resp.text
    by_id = {item["submission_id"]: item for item in resp.json()["items"]}
    assert by_id[replacement]["supersedes_submission_id"] == prior
    assert by_id[replacement]["superseded_by_submission_id"] is None
    assert by_id[prior]["supersedes_submission_id"] is None
    assert by_id[prior]["superseded_by_submission_id"] == replacement


# ---------------------------------------------------------------------------
# Semaphore semantics match the provider dashboard
# ---------------------------------------------------------------------------


def test_red_yellow_green_semantics_match_provider_dashboard(
    api_client: TestClient, db_factory
) -> None:
    client_id = _seed_client(db_factory)
    _, ws_id = _seed_vendor_with_workspace(db_factory, client_id=client_id)
    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)

    # Baseline: nothing uploaded → red, "sin avance" branch
    # (P1.1, 2026-05-20). A workspace with required obligations and 0
    # on-track now reads as red rather than the older "yellow / in
    # progress" — the prior behaviour misled providers about their
    # actual state on day one. See compute_semaphore in
    # services/dashboard_compute.py.
    base = api_client.get("/api/v1/client/overview", headers=_h(token)).json()
    # Validate via the per-vendor row.
    vendors = api_client.get("/api/v1/client/vendors", headers=_h(token)).json()
    assert vendors["items"][0]["semaphore_level"] == "red"
    assert base["red_count"] == 1

    # Upload + then reject → still red (blocking-state branch takes
    # precedence over the no-progress branch).
    sub_id = _seed_submission_for_workspace(api_client, db_factory, ws_id)
    db = db_factory()
    try:
        sub = db.get(Submission, sub_id)
        assert sub is not None
        sub.status = DocumentStatus.RECHAZADO.value
        db.commit()
    finally:
        db.close()
    red = api_client.get("/api/v1/client/vendors", headers=_h(token)).json()
    assert red["items"][0]["semaphore_level"] == "red"


# ---------------------------------------------------------------------------
# /activity sanitised feed
# ---------------------------------------------------------------------------


def test_client_activity_returns_sanitised_events(
    api_client: TestClient, db_factory
) -> None:
    client_id = _seed_client(db_factory)
    _, ws_id = _seed_vendor_with_workspace(db_factory, client_id=client_id)
    sub_id = _seed_submission_for_workspace(api_client, db_factory, ws_id)

    # Reviewer decides on the submission — produces a reviewer_decision
    # ValidationEvent the activity feed surfaces.
    db = db_factory()
    try:
        sub = db.get(Submission, sub_id)
        assert sub is not None
        apply_reviewer_decision(
            db,
            submission=sub,
            action=ReviewerAction.REJECT,
            reason="Documento ilegible.",
            reviewer_user_id="rev-user-1",
        )
    finally:
        db.close()

    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.get("/api/v1/client/activity", headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    actions = {item["action"] for item in body["items"]}
    # We should see the upload + the reviewer decision; admin metadata
    # is never in the feed.
    assert "submission.uploaded" in actions
    assert "reviewer.decision" in actions
    assert "metadata.ready" in actions
    assert "admin.client.created" not in actions
    assert all("admin" not in item["action"] for item in body["items"])


def test_client_notifications_are_created_and_readable(
    api_client: TestClient, db_factory
) -> None:
    client_id = _seed_client(db_factory)
    _, ws_id = _seed_vendor_with_workspace(db_factory, client_id=client_id)
    sub_id = _seed_submission_for_workspace(api_client, db_factory, ws_id)

    db = db_factory()
    try:
        sub = db.get(Submission, sub_id)
        assert sub is not None
        apply_reviewer_decision(
            db,
            submission=sub,
            action=ReviewerAction.APPROVE,
            reason=None,
            reviewer_user_id="rev-user-1",
        )
    finally:
        db.close()

    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.get("/api/v1/client/notifications", headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    types = {item["notification_type"] for item in body["items"]}
    assert "provider_uploaded" in types
    assert "metadata_ready" in types
    assert "document_approve" in types
    assert body["unread_count"] >= 3

    first_id = body["items"][0]["id"]
    mark_one = api_client.post(
        f"/api/v1/client/notifications/{first_id}/read", headers=_h(token)
    )
    assert mark_one.status_code == 200, mark_one.text
    assert mark_one.json()["read_at"] is not None

    mark_all = api_client.post("/api/v1/client/notifications/read-all", headers=_h(token))
    assert mark_all.status_code == 200, mark_all.text
    assert mark_all.json()["unread_count"] == 0


def test_client_notifications_carry_severity_per_emit_site(
    api_client: TestClient, db_factory
) -> None:
    """Phase 4 / Slice 4A — every emit-site sets an explicit semáforo
    severity and it round-trips through the API response. Tests cover
    the three actionable reviewer decisions plus the upload + metadata
    events that fire automatically.
    """
    client_id = _seed_client(db_factory)
    _, ws_id = _seed_vendor_with_workspace(db_factory, client_id=client_id)

    # Helper: seed a submission, apply a reviewer decision, return the
    # severity propagated to the reviewer-decision notification.
    def _seed_and_decide(action: ReviewerAction, reason: str | None) -> str:
        sub_id = _seed_submission_for_workspace(api_client, db_factory, ws_id)
        db = db_factory()
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

    sub_approved = _seed_and_decide(ReviewerAction.APPROVE, None)
    sub_rejected = _seed_and_decide(
        ReviewerAction.REJECT, "Documento ilegible."
    )
    sub_clarif = _seed_and_decide(
        ReviewerAction.REQUEST_CLARIFICATION, "Aclara el periodo."
    )
    sub_exception = _seed_and_decide(
        ReviewerAction.MARK_EXCEPTION, "Aplicada por excepción legal."
    )

    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.get(
        "/api/v1/client/notifications?limit=200", headers=_h(token)
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]

    # Index every notification by (submission_id, notification_type) so
    # the assertions read naturally.
    by_key = {(it["submission_id"], it["notification_type"]): it for it in items}

    # Every submission produced an upload event with yellow severity.
    for sid in (sub_approved, sub_rejected, sub_clarif, sub_exception):
        upload = by_key[(sid, "provider_uploaded")]
        assert upload["severity"] == "yellow", upload

    # Reviewer decisions per the locked Phase 4 vocabulary.
    assert by_key[(sub_approved, "document_approve")]["severity"] == "green"
    assert by_key[(sub_rejected, "document_reject")]["severity"] == "red"
    assert (
        by_key[(sub_clarif, "document_request_clarification")]["severity"]
        == "yellow"
    )
    assert (
        by_key[(sub_exception, "document_mark_exception")]["severity"] == "green"
    )

    # Metadata-ready notifications fire as background automation and
    # carry the neutral ``info`` severity so they don't compete with
    # actionable rows.
    metadata_rows = [it for it in items if it["notification_type"] == "metadata_ready"]
    assert metadata_rows, "expected at least one metadata_ready notification"
    assert all(it["severity"] == "info" for it in metadata_rows)


def test_client_metadata_endpoint_exposes_master_download_state(
    api_client: TestClient, db_factory
) -> None:
    client_id = _seed_client(db_factory)
    _, ws_id = _seed_vendor_with_workspace(db_factory, client_id=client_id)
    _seed_submission_for_workspace(api_client, db_factory, ws_id)
    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)

    resp = api_client.get("/api/v1/client/metadata", headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["client_id"] == client_id
    assert body["master_available"] is True
    assert body["documents"]

    download = api_client.get("/api/v1/client/metadata/download", headers=_h(token))
    assert download.status_code == 200, download.text
    assert download.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ---------------------------------------------------------------------------
# Phase 5 / Slice 5C — client-scoped vendor expediente ZIP
# ---------------------------------------------------------------------------


def test_client_vendor_expediente_zip_returns_documents(
    api_client: TestClient, db_factory
) -> None:
    """A client_admin can stream a vendor's expediente as a ZIP.

    The ZIP is grouped by institution/period (same layout the
    provider sees) and the response carries an attachment
    Content-Disposition with the vendor's RFC in the filename so a
    multi-vendor download set stays grep-friendly.
    """
    import io
    import zipfile

    client_id = _seed_client(db_factory)
    vendor_id, ws_id = _seed_vendor_with_workspace(db_factory, client_id=client_id)
    # Drop one real submission into the workspace via the canonical
    # upload helper; that path writes bytes to LOCAL_STORAGE_PATH so
    # the ZIP composition has something to read.
    _seed_submission_for_workspace(api_client, db_factory, ws_id)
    assert ws_id  # quiet F841

    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)

    resp = api_client.get(
        f"/api/v1/client/vendors/{vendor_id}/expediente.zip",
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("content-type") == "application/zip"
    cd = resp.headers.get("content-disposition", "").lower()
    assert "attachment" in cd
    assert ".zip" in cd

    archive = zipfile.ZipFile(io.BytesIO(resp.content))
    names = archive.namelist()
    assert len(names) == 1
    # ``_seed_submission_for_workspace`` defaults to INFONAVIT / 2026-B1.
    assert names[0].startswith("infonavit/2026-B1/")


def test_client_vendor_expediente_zip_enforces_client_isolation(
    api_client: TestClient, db_factory
) -> None:
    """A client_admin from client B must not be able to pull client
    A's vendor expediente. The endpoint resolves the active client
    scope first, then 404s when the requested vendor doesn't belong
    to it — same shape as the existing /client/vendors/{id} guard.
    """
    client_a_id = _seed_client(db_factory, name="Cliente A")
    vendor_a_id, ws_a_id = _seed_vendor_with_workspace(
        db_factory, client_id=client_a_id
    )
    _seed_submission_for_workspace(api_client, db_factory, ws_a_id)

    client_b_id = _seed_client(db_factory, name="Cliente B")
    _seed_vendor_with_workspace(db_factory, client_id=client_b_id)

    # Mint a client_admin user for client B and try to pull A's
    # vendor expediente through their session.
    _, email_b, pw_b = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_b_id, email_prefix="cb"
    )
    token_b = _login(api_client, email_b, pw_b)
    resp = api_client.get(
        f"/api/v1/client/vendors/{vendor_a_id}/expediente.zip",
        headers=_h(token_b),
    )
    assert resp.status_code == 404, resp.text


def test_client_vendor_expediente_zip_writes_audit(
    api_client: TestClient, db_factory
) -> None:
    """Audit row distinguishes the client-side pull from the
    provider-side one. The action name + actor_type let a forensic
    reader filter to "evidence pulled by the client" without
    iterating the metadata dict.
    """
    from app.models import AuditLog

    client_id = _seed_client(db_factory)
    vendor_id, ws_id = _seed_vendor_with_workspace(db_factory, client_id=client_id)
    _seed_submission_for_workspace(api_client, db_factory, ws_id)
    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)

    resp = api_client.get(
        f"/api/v1/client/vendors/{vendor_id}/expediente.zip",
        headers=_h(token),
    )
    assert resp.status_code == 200

    db = db_factory()
    try:
        events = (
            db.query(AuditLog)
            .filter(AuditLog.action == "client.vendor_expediente_downloaded")
            .all()
        )
        assert len(events) == 1
        event = events[0]
        assert event.actor_type == "client_admin"
        meta = event.event_metadata or {}
        assert meta.get("scope") == "client_vendor"
        assert meta.get("client_id") == client_id
        assert meta.get("vendor_id") == vendor_id
        assert meta.get("file_count") == 1
        # No filters → ``filters`` serializes to ``None``.
        assert meta.get("filters") is None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Junta 2026-05-23 — admin bulk ZIP per vendor
# ---------------------------------------------------------------------------


def test_admin_vendor_expediente_zip_returns_documents(
    api_client: TestClient, db_factory
) -> None:
    """An internal_admin can stream a vendor's expediente as a ZIP.

    Mirrors the client-side test but enters through the admin
    surface — no client_id resolution gate, just the
    internal_admin membership check. Same ZIP layout
    (institution/period folders) and same RFC-stamped filename so
    a multi-vendor download set stays grep-friendly for ops.
    """
    import io
    import zipfile

    client_id = _seed_client(db_factory)
    vendor_id, ws_id = _seed_vendor_with_workspace(db_factory, client_id=client_id)
    _seed_submission_for_workspace(api_client, db_factory, ws_id)
    assert ws_id  # quiet F841

    _, email, pw = _seed_user_with_role(
        db_factory, role="internal_admin", email_prefix="adm"
    )
    token = _login(api_client, email, pw)

    resp = api_client.get(
        f"/api/v1/admin/vendors/{vendor_id}/expediente.zip",
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("content-type") == "application/zip"
    cd = resp.headers.get("content-disposition", "").lower()
    assert "attachment" in cd
    assert ".zip" in cd

    archive = zipfile.ZipFile(io.BytesIO(resp.content))
    names = archive.namelist()
    assert len(names) == 1
    assert names[0].startswith("infonavit/2026-B1/")


def test_admin_vendor_expediente_zip_denies_non_admin(
    api_client: TestClient, db_factory
) -> None:
    """Reviewer and client_admin roles must NOT reach the admin ZIP
    endpoint. ``internal_admin`` is the only role allowed; the
    audit metadata key ``actor_type=internal_admin`` would be a lie
    otherwise.
    """
    client_id = _seed_client(db_factory)
    vendor_id, _ = _seed_vendor_with_workspace(db_factory, client_id=client_id)

    for role, prefix in (("reviewer", "rev"), ("client_admin", "ca")):
        kwargs: dict = {"role": role, "email_prefix": prefix}
        if role == "client_admin":
            kwargs["client_id"] = client_id
        _, email, pw = _seed_user_with_role(db_factory, **kwargs)
        token = _login(api_client, email, pw)
        resp = api_client.get(
            f"/api/v1/admin/vendors/{vendor_id}/expediente.zip",
            headers=_h(token),
        )
        assert resp.status_code == 403, (role, resp.text)


def test_admin_vendor_expediente_zip_writes_audit(
    api_client: TestClient, db_factory
) -> None:
    """Audit row distinguishes the admin pull from the client and
    provider equivalents via ``actor_type=internal_admin`` and
    ``action=admin.vendor_expediente_downloaded``.
    """
    from app.models import AuditLog

    client_id = _seed_client(db_factory)
    vendor_id, ws_id = _seed_vendor_with_workspace(db_factory, client_id=client_id)
    _seed_submission_for_workspace(api_client, db_factory, ws_id)
    _, email, pw = _seed_user_with_role(
        db_factory, role="internal_admin", email_prefix="adm"
    )
    token = _login(api_client, email, pw)

    resp = api_client.get(
        f"/api/v1/admin/vendors/{vendor_id}/expediente.zip",
        headers=_h(token),
    )
    assert resp.status_code == 200

    db = db_factory()
    try:
        events = (
            db.query(AuditLog)
            .filter(AuditLog.action == "admin.vendor_expediente_downloaded")
            .all()
        )
        assert len(events) == 1
        event = events[0]
        assert event.actor_type == "internal_admin"
        meta = event.event_metadata or {}
        assert meta.get("scope") == "admin_vendor"
        assert meta.get("vendor_id") == vendor_id
        assert meta.get("client_id") == client_id
        assert meta.get("file_count") == 1
        assert meta.get("filters") is None
    finally:
        db.close()


def test_admin_vendor_expediente_zip_404_for_unknown_vendor(
    api_client: TestClient, db_factory
) -> None:
    _, email, pw = _seed_user_with_role(
        db_factory, role="internal_admin", email_prefix="adm"
    )
    token = _login(api_client, email, pw)
    resp = api_client.get(
        "/api/v1/admin/vendors/does-not-exist/expediente.zip",
        headers=_h(token),
    )
    assert resp.status_code == 404


def test_admin_vendor_expediente_zip_404_when_no_workspace(
    api_client: TestClient, db_factory
) -> None:
    """A vendor with no ProviderWorkspace cannot produce a ZIP; the
    endpoint must return 404 with a Spanish message rather than
    streaming an empty archive."""
    from app.models import Vendor

    client_id = _seed_client(db_factory)
    db = db_factory()
    try:
        vendor = Vendor(
            client_id=client_id,
            name="Sin workspace",
            rfc="NWS260101AB1",
            persona_type="moral",
        )
        db.add(vendor)
        db.commit()
        vendor_id = vendor.id
    finally:
        db.close()

    _, email, pw = _seed_user_with_role(
        db_factory, role="internal_admin", email_prefix="adm"
    )
    token = _login(api_client, email, pw)
    resp = api_client.get(
        f"/api/v1/admin/vendors/{vendor_id}/expediente.zip",
        headers=_h(token),
    )
    assert resp.status_code == 404
    assert "workspace" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Junta 2026-05-23 — audit package (cross-vendor ZIP for inspectors)
# ---------------------------------------------------------------------------


def _seed_approved_submission_for_workspace(
    api_client: TestClient,
    db_factory,
    ws_id: str,
    **kwargs,
) -> str:
    """Wrapper that seeds a submission and flips its status to
    ``aprobado`` directly. The audit-package endpoint defaults to
    approved-only, so the test fixtures need at least one approved
    row to assert the happy path."""
    return _seed_submission_for_workspace(
        api_client,
        db_factory,
        ws_id,
        status_value=DocumentStatus.APROBADO.value,
        **kwargs,
    )


def test_client_audit_package_preview_returns_counts(
    api_client: TestClient, db_factory
) -> None:
    """The /preview endpoint returns aggregated file/byte counts plus
    breakdowns by vendor and institution; it does NOT write an
    audit row (cheap read used by the UI live counter)."""
    from app.models import AuditLog

    client_id = _seed_client(db_factory)
    _, ws_a = _seed_vendor_with_workspace(
        db_factory, client_id=client_id, vendor_name="Proveedor A", rfc="AAA260101AB1"
    )
    _, ws_b = _seed_vendor_with_workspace(
        db_factory, client_id=client_id, vendor_name="Proveedor B", rfc="BBB260101AB2"
    )
    _seed_approved_submission_for_workspace(api_client, db_factory, ws_a)
    _seed_approved_submission_for_workspace(api_client, db_factory, ws_b)

    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)

    resp = api_client.get(
        "/api/v1/client/audit-package/preview",
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["file_count"] == 2
    assert body["vendor_count"] == 2
    assert body["over_file_cap"] is False
    assert body["over_bytes_cap"] is False
    assert body["file_cap"] == 200
    # Preview must not pollute the audit log.
    db = db_factory()
    try:
        downloads = (
            db.query(AuditLog)
            .filter(AuditLog.action == "client.audit_package_downloaded")
            .count()
        )
        assert downloads == 0
    finally:
        db.close()


def test_client_audit_package_zip_defaults_to_approved_only(
    api_client: TestClient, db_factory
) -> None:
    """With no ``statuses`` filter the ZIP must only contain
    aprobado documents; pendiente_revision rows are dropped."""
    import io
    import zipfile

    client_id = _seed_client(db_factory)
    _, ws = _seed_vendor_with_workspace(db_factory, client_id=client_id)
    _seed_approved_submission_for_workspace(api_client, db_factory, ws)
    # A second submission stays in review (different period) — must
    # NOT appear in the default approved-only package.
    _seed_submission_for_workspace(
        api_client,
        db_factory,
        ws,
        period_key="2026-B2",
        period_code="2026-B2",
    )

    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)

    resp = api_client.get(
        "/api/v1/client/audit-package.zip?skip_manifest=true",
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("content-type") == "application/zip"
    cd = resp.headers.get("content-disposition", "").lower()
    assert "attachment" in cd
    assert cd.startswith("attachment; filename=\"auditoria-")

    archive = zipfile.ZipFile(io.BytesIO(resp.content))
    names = archive.namelist()
    assert len(names) == 1
    # Layout is vendor/institucion/periodo/filename — three path
    # segments before the file. INDICE.pdf is suppressed via
    # skip_manifest so we know each entry is a real document.
    assert names[0].count("/") == 3


def test_client_audit_package_zip_status_override_includes_in_review(
    api_client: TestClient, db_factory
) -> None:
    """Passing ``statuses=pendiente_revision&statuses=aprobado``
    explicitly should include in-review rows alongside approved."""
    import io
    import zipfile

    client_id = _seed_client(db_factory)
    _, ws = _seed_vendor_with_workspace(db_factory, client_id=client_id)
    # Two distinct submissions on the same workspace; different
    # periods so the (requirement_code, period_key) tuple stays
    # unique.
    _seed_approved_submission_for_workspace(api_client, db_factory, ws)
    _seed_submission_for_workspace(
        api_client,
        db_factory,
        ws,
        period_key="2026-B2",
        period_code="2026-B2",
    )

    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.get(
        "/api/v1/client/audit-package.zip"
        "?statuses=aprobado&statuses=pendiente_revision&skip_manifest=true",
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    archive = zipfile.ZipFile(io.BytesIO(resp.content))
    assert len(archive.namelist()) == 2


def test_client_audit_package_includes_bimestral_under_monthly_range(
    api_client: TestClient, db_factory
) -> None:
    """Regression — Junta 2026-05-25 bug.

    Before the fix the audit-package endpoint compared period_keys
    lexicographically, so a bimestral row (``2026-B1`` = Jan-Feb)
    was silently dropped whenever the user picked a monthly range
    (e.g. ``period_from=2026-M01`` / ``period_to=2026-M01``)
    because ``B`` lexically sorts before ``M``. This test seeds one
    monthly and one bimestral submission, applies a January-only
    filter, and asserts BOTH rows make it into the ZIP.
    """
    import io
    import zipfile

    client_id = _seed_client(db_factory)
    _, ws = _seed_vendor_with_workspace(db_factory, client_id=client_id)
    # Monthly Jan 2026 (INFONAVIT default uses 2026-B1, so override
    # to a SAT monthly row).
    _seed_approved_submission_for_workspace(
        api_client,
        db_factory,
        ws,
        requirement_code="REC-SAT-2026-05-declaracion-iva",
        period_key="2026-M01",
        period_code="2026-M01",
        institution_code="sat",
        load_type="mensual",
        requirement_name="Declaración IVA",
    )
    # Bimestral B1 = Jan-Feb 2026. The default seed already produces
    # an INFONAVIT bimestral; explicit period_key just for clarity.
    _seed_approved_submission_for_workspace(
        api_client,
        db_factory,
        ws,
        period_key="2026-B1",
        period_code="2026-B1",
    )

    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)

    # Filter for January 2026 only. Pre-fix this dropped the
    # bimestral row entirely because "2026-B1" < "2026-M01"
    # lexically.
    resp = api_client.get(
        "/api/v1/client/audit-package.zip"
        "?period_from=2026-M01&period_to=2026-M01&skip_manifest=true",
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    archive = zipfile.ZipFile(io.BytesIO(resp.content))
    names = archive.namelist()
    assert len(names) == 2, f"Expected both rows, got: {names}"
    # The folder layout is vendor/institucion/periodo/filename — both
    # institutions should be present.
    institutions_present = {n.split("/")[1] for n in names}
    assert institutions_present == {"sat", "infonavit"}


def test_client_audit_package_zip_cross_vendor_layout(
    api_client: TestClient, db_factory
) -> None:
    """Two vendors → two top-level folders in the archive."""
    import io
    import zipfile

    client_id = _seed_client(db_factory)
    _, ws_a = _seed_vendor_with_workspace(
        db_factory, client_id=client_id, vendor_name="Proveedor A", rfc="AAA260101AB1"
    )
    _, ws_b = _seed_vendor_with_workspace(
        db_factory, client_id=client_id, vendor_name="Proveedor B", rfc="BBB260101AB2"
    )
    _seed_approved_submission_for_workspace(api_client, db_factory, ws_a)
    _seed_approved_submission_for_workspace(api_client, db_factory, ws_b)

    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.get(
        "/api/v1/client/audit-package.zip?skip_manifest=true",
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
    top_folders = {n.split("/", 1)[0] for n in names}
    assert len(top_folders) == 2


def test_client_audit_package_writes_audit_row(
    api_client: TestClient, db_factory
) -> None:
    """Each download writes a ``client.audit_package_downloaded`` row
    with full filter metadata so a forensic reader can answer who
    pulled which scope and when."""
    from app.models import AuditLog

    client_id = _seed_client(db_factory)
    _, ws = _seed_vendor_with_workspace(db_factory, client_id=client_id)
    _seed_approved_submission_for_workspace(api_client, db_factory, ws)

    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.get(
        "/api/v1/client/audit-package.zip?skip_manifest=true&institutions=infonavit",
        headers=_h(token),
    )
    assert resp.status_code == 200

    db = db_factory()
    try:
        events = (
            db.query(AuditLog)
            .filter(AuditLog.action == "client.audit_package_downloaded")
            .all()
        )
        assert len(events) == 1
        event = events[0]
        assert event.actor_type == "client_admin"
        meta = event.event_metadata or {}
        assert meta.get("scope") == "client_audit_package"
        assert meta.get("client_id") == client_id
        assert meta.get("file_count") == 1
        assert meta.get("manifest_included") is False
        filters_meta = meta.get("filters") or {}
        assert filters_meta.get("institutions") == ["infonavit"]
        # Default status set is exposed even when caller did not pass
        # it explicitly.
        assert filters_meta.get("statuses") == ["aprobado"]
    finally:
        db.close()


def test_client_audit_package_denies_non_client_admin(
    api_client: TestClient, db_factory
) -> None:
    """Reviewer and unauthenticated callers must be rejected."""
    client_id = _seed_client(db_factory)
    _, _ = _seed_vendor_with_workspace(db_factory, client_id=client_id)

    # No auth.
    resp = api_client.get("/api/v1/client/audit-package.zip")
    assert resp.status_code == 401

    # Reviewer (wrong role) → 403 from /client/* guard.
    _, email, pw = _seed_user_with_role(
        db_factory, role="reviewer", email_prefix="rev"
    )
    token = _login(api_client, email, pw)
    resp = api_client.get(
        "/api/v1/client/audit-package.zip",
        headers=_h(token),
    )
    assert resp.status_code == 403


def test_client_audit_package_preview_filters_by_institution(
    api_client: TestClient, db_factory
) -> None:
    """Passing ``institutions=imss`` must drop INFONAVIT rows from
    the count."""
    client_id = _seed_client(db_factory)
    _, ws = _seed_vendor_with_workspace(db_factory, client_id=client_id)
    _seed_approved_submission_for_workspace(
        api_client,
        db_factory,
        ws,
    )
    _seed_approved_submission_for_workspace(
        api_client,
        db_factory,
        ws,
        requirement_code="REC-IMSS-2026-05-cuotas-obrero-patronales",
        period_key="2026-M04",
        period_code="2026-M04",
        institution_code="imss",
        load_type="mensual",
        requirement_name="Cuotas obrero patronales",
    )

    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.get(
        "/api/v1/client/audit-package/preview?institutions=imss",
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["file_count"] == 1


def test_audit_manifest_html_renders_with_scope_and_counts(db_factory) -> None:
    """Pure unit test on the HTML composer — no Playwright needed."""
    from app.services.audit_package import AuditPackageEntry, AuditPackageFilters
    from app.services.audit_package_manifest import _render_manifest_html

    db = db_factory()
    try:
        client = Client(name="Empresa Demo", rfc="EMP010101AAA")
        db.add(client)
        db.commit()
        client_id = client.id
        client = db.get(Client, client_id)
        assert client is not None
    finally:
        db.close()

    entry = AuditPackageEntry(
        arcname="empresa-demo/imss/2026-B1/cuotas.pdf",
        storage_key="local://demo/x.pdf",
        size_bytes=200_000,
        vendor_id="v-1",
        vendor_name="Proveedor Demo",
        vendor_rfc="PVD010101AAA",
        institution_code="imss",
        institution_name="IMSS",
        period_key="2026-B1",
        requirement_code="REC-IMSS-COP",
        requirement_name="Cuotas obrero-patronales",
        status="aprobado",
        filename="cuotas.pdf",
        submitted_at_iso="2026-04-15T10:00:00+00:00",
    )
    filters = AuditPackageFilters(
        period_from="2026-M01",
        period_to="2026-M03",
        institutions=("imss",),
    )

    from datetime import UTC, datetime

    html_bytes = _render_manifest_html(
        client=client,
        filters=filters,
        entries=[entry],
        generated_at=datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
    )
    html = html_bytes.decode("utf-8")
    assert "Empresa Demo" in html
    assert "EMP010101AAA" in html
    assert "Proveedor Demo" in html
    assert "Cuotas obrero-patronales" in html
    assert "2026-M01 a 2026-M03" in html
    assert "IMSS" in html
    assert "Aprobado" in html
    # The counter strip exposes the file count.
    assert ">1<" in html  # 1 document


# ---------------------------------------------------------------------------
# Junta 2026-05-23 — /client/profile (self-service onboarding)
# ---------------------------------------------------------------------------


def test_client_profile_returns_preloaded_alta_fields(
    api_client: TestClient, db_factory
) -> None:
    """First GET returns the columns the admin populated on alta plus
    the still-null onboarding fields. ``onboarding_completed_at`` is
    null when the client_admin has not saved the form yet."""
    client_id = _seed_client(db_factory)
    # Populate admin-side fields directly on the row to mimic the
    # admin alta flow.
    db = db_factory()
    try:
        row = db.get(Client, client_id)
        assert row is not None
        row.email = "alta@empresa.example"
        row.responsible_name = "Ada Reyes"
        db.commit()
    finally:
        db.close()

    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.get(
        "/api/v1/client/profile",
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == client_id
    assert body["email"] == "alta@empresa.example"
    assert body["responsible_name"] == "Ada Reyes"
    assert body["industry"] is None
    assert body["fiscal_address"] is None
    assert body["onboarding_completed_at"] is None


def test_client_profile_patch_sets_onboarding_completed_at(
    api_client: TestClient, db_factory
) -> None:
    """First PATCH saves the editable fields and stamps
    ``onboarding_completed_at``; subsequent PATCHes preserve the
    original timestamp so revisiting the page doesn't re-trigger
    the dashboard banner."""
    client_id = _seed_client(db_factory)
    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)

    first = api_client.patch(
        "/api/v1/client/profile",
        json={
            "industry": "Construcción",
            "fiscal_address": "Av Reforma 100, CDMX",
            "phone": "+52 55 1234 5678",
            "notes": "Cliente prioritario en Q2.",
        },
        headers=_h(token),
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["industry"] == "Construcción"
    assert body["fiscal_address"] == "Av Reforma 100, CDMX"
    assert body["phone"] == "+52 55 1234 5678"
    assert body["notes"] == "Cliente prioritario en Q2."
    initial_completed = body["onboarding_completed_at"]
    assert initial_completed is not None

    # A second patch with a different field must not reset the
    # timestamp.
    second = api_client.patch(
        "/api/v1/client/profile",
        json={"phone": "+52 55 9999 0000"},
        headers=_h(token),
    )
    assert second.status_code == 200, second.text
    body2 = second.json()
    assert body2["phone"] == "+52 55 9999 0000"
    assert body2["onboarding_completed_at"] == initial_completed


def test_client_profile_patch_writes_audit_row(
    api_client: TestClient, db_factory
) -> None:
    """The PATCH writes a ``client.profile_updated`` audit row with a
    before/after diff plus a ``just_completed_onboarding`` flag so a
    forensic reader can answer who finished the alta and when."""
    from app.models import AuditLog

    client_id = _seed_client(db_factory)
    _, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.patch(
        "/api/v1/client/profile",
        json={"industry": "Servicios"},
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text

    db = db_factory()
    try:
        events = (
            db.query(AuditLog)
            .filter(AuditLog.action == "client.profile_updated")
            .all()
        )
        assert len(events) == 1
        event = events[0]
        assert event.actor_type == "client_admin"
        assert (event.before or {}).get("industry") is None
        assert (event.after or {}).get("industry") == "Servicios"
        assert (event.event_metadata or {}).get(
            "just_completed_onboarding"
        ) is True
    finally:
        db.close()


def test_client_profile_denies_non_client_admin(
    api_client: TestClient, db_factory
) -> None:
    """Reviewer and unauthenticated callers must be rejected."""
    resp = api_client.get("/api/v1/client/profile")
    assert resp.status_code == 401

    _, email, pw = _seed_user_with_role(
        db_factory, role="reviewer", email_prefix="rev"
    )
    token = _login(api_client, email, pw)
    resp = api_client.get(
        "/api/v1/client/profile",
        headers=_h(token),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Notification mark-read — audit-log fills (M4 partial)
# ---------------------------------------------------------------------------


def _notify_audit_rows(db_factory, action: str) -> list[AuditLog]:
    db = db_factory()
    try:
        return list(
            db.scalars(
                select(AuditLog).where(AuditLog.action == action)
            )
        )
    finally:
        db.close()


def test_mark_client_notification_read_writes_audit_event(
    api_client: TestClient, db_factory
) -> None:
    """First unread→read transition writes an audit_log row tying the
    notification to the acting client_admin. A no-op replay writes
    nothing more, so polling clients do not flood the log.
    """
    client_id = _seed_client(db_factory)
    _, ws_id = _seed_vendor_with_workspace(db_factory, client_id=client_id)
    sub_id = _seed_submission_for_workspace(api_client, db_factory, ws_id)

    db = db_factory()
    try:
        sub = db.get(Submission, sub_id)
        assert sub is not None
        apply_reviewer_decision(
            db,
            submission=sub,
            action=ReviewerAction.APPROVE,
            reason=None,
            reviewer_user_id="rev-user-audit",
        )
    finally:
        db.close()

    user_id, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca-audit"
    )
    token = _login(api_client, email, pw)

    listing = api_client.get("/api/v1/client/notifications", headers=_h(token))
    assert listing.status_code == 200, listing.text
    notification_id = listing.json()["items"][0]["id"]

    first = api_client.post(
        f"/api/v1/client/notifications/{notification_id}/read", headers=_h(token)
    )
    assert first.status_code == 200, first.text

    events = _notify_audit_rows(db_factory, "client.notification_marked_read")
    assert len(events) == 1
    event = events[0]
    assert event.entity_type == "client_notification"
    assert event.entity_id == notification_id
    assert event.actor_type == "client_admin"
    assert event.actor_id == user_id
    assert (event.after or {}).get("client_id") == client_id

    # Idempotent replay must not log a second row.
    second = api_client.post(
        f"/api/v1/client/notifications/{notification_id}/read", headers=_h(token)
    )
    assert second.status_code == 200
    after_replay = _notify_audit_rows(db_factory, "client.notification_marked_read")
    assert len(after_replay) == 1


def test_mark_all_client_notifications_read_writes_audit_event(
    api_client: TestClient, db_factory
) -> None:
    """Bulk mark-read writes a single audit row capturing the flipped
    notification ids. A no-op call (everything already read) writes
    nothing.
    """
    client_id = _seed_client(db_factory)
    _, ws_id = _seed_vendor_with_workspace(db_factory, client_id=client_id)
    sub_id = _seed_submission_for_workspace(api_client, db_factory, ws_id)

    db = db_factory()
    try:
        sub = db.get(Submission, sub_id)
        assert sub is not None
        apply_reviewer_decision(
            db,
            submission=sub,
            action=ReviewerAction.APPROVE,
            reason=None,
            reviewer_user_id="rev-user-audit-bulk",
        )
    finally:
        db.close()

    user_id, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca-bulk"
    )
    token = _login(api_client, email, pw)

    # Capture the unread set so we can compare against the audit payload.
    listing = api_client.get("/api/v1/client/notifications", headers=_h(token))
    assert listing.status_code == 200, listing.text
    unread_ids = sorted(
        item["id"] for item in listing.json()["items"] if item["read_at"] is None
    )
    assert len(unread_ids) >= 1

    bulk = api_client.post("/api/v1/client/notifications/read-all", headers=_h(token))
    assert bulk.status_code == 200, bulk.text
    assert bulk.json()["unread_count"] == 0

    events = _notify_audit_rows(db_factory, "client.notifications_marked_all_read")
    assert len(events) == 1
    event = events[0]
    assert event.entity_type == "client"
    assert event.entity_id == client_id
    assert event.actor_type == "client_admin"
    assert event.actor_id == user_id
    payload = event.after or {}
    assert payload.get("marked_count") == len(unread_ids)
    assert sorted(payload.get("notification_ids") or []) == unread_ids

    # No-op replay must not log a second row.
    noop = api_client.post("/api/v1/client/notifications/read-all", headers=_h(token))
    assert noop.status_code == 200
    after_noop = _notify_audit_rows(db_factory, "client.notifications_marked_all_read")
    assert len(after_noop) == 1


# ---------------------------------------------------------------------------
# Client legal-consent gate (v2+) — every client_admin must accept.
# ---------------------------------------------------------------------------


def _client_consent_audit_rows(db_factory, user_id: str) -> list[AuditLog]:
    db = db_factory()
    try:
        return list(
            db.query(AuditLog)
            .filter(
                AuditLog.action == "client.legal_consent_accepted",
                AuditLog.entity_type == "user",
                AuditLog.actor_id == user_id,
            )
            .order_by(AuditLog.created_at.asc())
            .all()
        )
    finally:
        db.close()


def test_client_me_reports_unconsented_then_accept_flips_it(
    api_client: TestClient, db_factory
) -> None:
    from app.api.v1.portal import CURRENT_LEGAL_CONSENT_VERSION

    client_id = _seed_client(db_factory, "Cliente Consent")
    user_id, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="cc"
    )
    token = _login(api_client, email, pw)

    before = api_client.get("/api/v1/client/me", headers=_h(token)).json()
    assert before["legal_consent_accepted_at"] is None
    assert before["legal_consent_version"] is None
    assert before["current_legal_consent_version"] == CURRENT_LEGAL_CONSENT_VERSION

    accept = api_client.post(
        "/api/v1/client/legal-consent",
        headers={**_h(token), "User-Agent": "ConsentTest/1.0"},
    )
    assert accept.status_code == 200, accept.text
    body = accept.json()
    assert body["user_id"] == user_id
    assert body["legal_consent_version"] == CURRENT_LEGAL_CONSENT_VERSION
    assert body["legal_consent_accepted_at"]

    after = api_client.get("/api/v1/client/me", headers=_h(token)).json()
    assert after["legal_consent_accepted_at"] is not None
    assert after["legal_consent_version"] == CURRENT_LEGAL_CONSENT_VERSION

    # Persisted on the user row.
    db = db_factory()
    try:
        user = db.get(User, user_id)
        assert user.legal_consent_version == CURRENT_LEGAL_CONSENT_VERSION
        assert user.legal_consent_accepted_at is not None
    finally:
        db.close()


def test_client_consent_writes_audit_with_ip_and_user_agent(
    api_client: TestClient, db_factory
) -> None:
    from app.api.v1.portal import CURRENT_LEGAL_CONSENT_VERSION

    client_id = _seed_client(db_factory, "Cliente Audit")
    user_id, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca-audit"
    )
    token = _login(api_client, email, pw)

    api_client.post(
        "/api/v1/client/legal-consent",
        headers={**_h(token), "User-Agent": "ConsentUA/2.0"},
    )

    rows = _client_consent_audit_rows(db_factory, user_id)
    assert len(rows) == 1
    meta = rows[0].event_metadata
    assert meta["version"] == CURRENT_LEGAL_CONSENT_VERSION
    assert meta["user_agent"] == "ConsentUA/2.0"
    assert "ip" in meta
    assert rows[0].actor_type == "client_admin"


def test_client_consent_is_idempotent_within_a_version(
    api_client: TestClient, db_factory
) -> None:
    client_id = _seed_client(db_factory, "Cliente Idem")
    user_id, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca-idem"
    )
    token = _login(api_client, email, pw)

    first = api_client.post("/api/v1/client/legal-consent", headers=_h(token)).json()
    second = api_client.post("/api/v1/client/legal-consent", headers=_h(token)).json()
    # Same timestamp returned; no duplicate audit row.
    assert first["legal_consent_accepted_at"] == second["legal_consent_accepted_at"]
    assert len(_client_consent_audit_rows(db_factory, user_id)) == 1


def test_client_consent_version_bump_reprompts(
    api_client: TestClient, db_factory, monkeypatch
) -> None:
    from app.api.v1 import client as client_module

    client_id = _seed_client(db_factory, "Cliente Bump")
    user_id, email, pw = _seed_user_with_role(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca-bump"
    )
    token = _login(api_client, email, pw)

    monkeypatch.setattr(client_module, "CURRENT_LEGAL_CONSENT_VERSION", "vA-test")
    api_client.post("/api/v1/client/legal-consent", headers=_h(token))
    me_a = api_client.get("/api/v1/client/me", headers=_h(token)).json()
    assert me_a["legal_consent_version"] == "vA-test"
    assert me_a["current_legal_consent_version"] == "vA-test"

    # Publish a new version: /me must now report a mismatch (re-prompt).
    monkeypatch.setattr(client_module, "CURRENT_LEGAL_CONSENT_VERSION", "vB-test")
    me_b = api_client.get("/api/v1/client/me", headers=_h(token)).json()
    assert me_b["legal_consent_version"] == "vA-test"
    assert me_b["current_legal_consent_version"] == "vB-test"

    # Re-accepting bumps the stored version and writes a second audit row
    # carrying the previous version for the forensic trail.
    api_client.post("/api/v1/client/legal-consent", headers=_h(token))
    me_c = api_client.get("/api/v1/client/me", headers=_h(token)).json()
    assert me_c["legal_consent_version"] == "vB-test"
    rows = _client_consent_audit_rows(db_factory, user_id)
    assert len(rows) == 2
    assert rows[1].event_metadata["previous_version"] == "vA-test"
