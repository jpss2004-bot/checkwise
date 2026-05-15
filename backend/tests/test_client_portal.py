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

    # Baseline: nothing uploaded → yellow (missing required slots).
    base = api_client.get("/api/v1/client/overview", headers=_h(token)).json()
    # Validate via the per-vendor row.
    vendors = api_client.get("/api/v1/client/vendors", headers=_h(token)).json()
    assert vendors["items"][0]["semaphore_level"] == "yellow"
    assert base["yellow_count"] == 1

    # Upload + then reject → red.
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
    assert "admin.client.created" not in actions
    assert all("admin" not in item["action"] for item in body["items"])
