"""Phase 5 — client acceptance axis (Axis 2).

Covers the SECOND approval axis: the client's business acceptance of a
submission, recorded independently of CheckWise's compliance verdict.

Pins, at the service layer:
* ``apply_client_decision`` updates ONLY the ``client_acceptance`` fields and
  NEVER touches ``Submission.status`` / ``Document.status`` (the orthogonality
  contract — the whole point of the two-axis design).
* accept / reject / reset transitions + the ValidationEvent + AuditLog trail.
* the override rule: a decision that contradicts the validity verdict
  (accept a non-valid doc, or reject a valid one) requires a reason → 422.

And at the HTTP layer (``POST /client/submissions/{id}/decision``):
* an Approver (client_admin) can decide; a Viewer (client_viewer) is 403'd at
  the gate; a cross-tenant submission is a uniform 404.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants.statuses import ClientAcceptance, DocumentStatus, ReviewerAction
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    AuditLog,
    Client,
    Document,
    Institution,
    Membership,
    Organization,
    Period,
    Requirement,
    RequirementVersion,
    Submission,
    User,
    ValidationEvent,
    Vendor,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password
from app.services.submission_workflow import (
    apply_client_decision,
    apply_reviewer_decision,
)


def _set_auto_accept(db_factory, client_id: str, value: bool) -> None:
    db = db_factory()
    try:
        client = db.get(Client, client_id)
        client.auto_accept_valid = value
        db.commit()
    finally:
        db.close()

# ---------------------------------------------------------------------------
# Fixtures + seeding
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
def api_client(db_factory) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


_COUNTER = 0


def _seed_world(
    db_factory,
    *,
    submission_status: str = DocumentStatus.APROBADO.value,
) -> dict[str, str]:
    """One client (+ org), an Approver + a Viewer seat, and one submission.

    Returns ids/credentials so both the service tests and the endpoint tests
    can drive the same world.
    """
    global _COUNTER
    _COUNTER += 1
    n = _COUNTER
    db = db_factory()
    try:
        client = Client(name=f"Cliente {n}", rfc=f"AX{n:02d}260101AB"[:13])
        db.add(client)
        db.flush()

        org = Organization(name=f"Org {n}", kind="client", client_id=client.id)
        db.add(org)
        db.flush()

        approver = User(
            email=f"approver{n}@ax.mx",
            password_hash=hash_password("Approver Pass 1"),
            full_name="Ana Aprobadora",
            status="active",
            must_change_password=False,
        )
        viewer = User(
            email=f"viewer{n}@ax.mx",
            password_hash=hash_password("Viewer Pass 1"),
            full_name="Vera Visor",
            status="active",
            must_change_password=False,
        )
        db.add_all([approver, viewer])
        db.flush()
        db.add_all(
            [
                Membership(
                    user_id=approver.id,
                    organization_id=org.id,
                    role="client_admin",
                    status="active",
                ),
                Membership(
                    user_id=viewer.id,
                    organization_id=org.id,
                    role="client_viewer",
                    status="active",
                ),
            ]
        )

        vendor = Vendor(client_id=client.id, name=f"Vendor {n}", rfc=f"VX{n:02d}260101XY"[:13])
        db.add(vendor)
        db.flush()
        institution = db.scalar(select(Institution).where(Institution.code == "sat"))
        if institution is None:
            institution = Institution(code="sat", name="SAT")
            db.add(institution)
            db.flush()
        requirement = Requirement(
            code=f"ax:test:{n}",
            name=f"Requisito {n}",
            institution_id=institution.id,
            load_type="mensual",
            frequency="mensual",
            risk_level="medium",
            current_version=1,
        )
        db.add(requirement)
        db.flush()
        req_version = RequirementVersion(requirement_id=requirement.id, version=1)
        db.add(req_version)
        db.flush()
        period = Period(
            code=f"2026-AX{n:02d}",
            year=2026,
            period_type="mensual",
            period_key=f"2026-AX{n:02d}",
        )
        db.add(period)
        db.flush()
        submission = Submission(
            client_id=client.id,
            vendor_id=vendor.id,
            institution_id=institution.id,
            requirement_id=requirement.id,
            requirement_version_id=req_version.id,
            period_id=period.id,
            status=submission_status,
            load_type="mensual",
            requirement_code=f"ax:test:{n}",
            period_key=f"2026-AX{n:02d}",
        )
        db.add(submission)
        db.flush()
        db.add(
            Document(
                submission_id=submission.id,
                storage_key=f"local://ax/{submission.id}.pdf",
                original_filename=f"ax-{n}.pdf",
                mime_type="application/pdf",
                size_bytes=1024,
                sha256="c" * 64,
                status=submission_status,
            )
        )
        db.commit()
        return {
            "client_id": client.id,
            "submission_id": submission.id,
            "approver_email": approver.email,
            "viewer_email": viewer.email,
            "approver_pw": "Approver Pass 1",
            "viewer_pw": "Viewer Pass 1",
            "approver_id": approver.id,
        }
    finally:
        db.close()


def _login(client: TestClient, email: str, password: str) -> str:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Service layer — apply_client_decision
# ---------------------------------------------------------------------------


def test_accept_records_acceptance_without_touching_status(db_factory) -> None:
    """The orthogonality contract: accepting a VALID doc sets the acceptance
    fields + trail, and leaves Submission.status / Document.status untouched."""
    ids = _seed_world(db_factory, submission_status=DocumentStatus.APROBADO.value)
    db = db_factory()
    sub = db.get(Submission, ids["submission_id"])

    result = apply_client_decision(
        db, submission=sub, action="accept", reason=None,
        client_user_id=ids["approver_id"],
    )

    assert result.new_acceptance == ClientAcceptance.ACCEPTED.value
    assert result.was_override is False  # accepting a valid doc is aligned
    sub = db.get(Submission, ids["submission_id"])
    assert sub.client_acceptance == ClientAcceptance.ACCEPTED.value
    assert sub.client_decided_by_user_id == ids["approver_id"]
    assert sub.client_decided_at is not None
    # Axis 1 untouched:
    assert sub.status == DocumentStatus.APROBADO.value
    doc = db.scalar(select(Document).where(Document.submission_id == sub.id))
    assert doc.status == DocumentStatus.APROBADO.value
    # Trail written on the acceptance axis:
    ev = db.scalar(
        select(ValidationEvent).where(
            ValidationEvent.submission_id == sub.id,
            ValidationEvent.event_type == "client_decision",
        )
    )
    assert ev is not None and ev.actor_type == "client"
    al = db.scalar(
        select(AuditLog).where(AuditLog.action == "submission.client_decision")
    )
    assert al is not None
    db.close()


def test_reject_then_reset_roundtrip(db_factory) -> None:
    ids = _seed_world(db_factory, submission_status=DocumentStatus.APROBADO.value)
    db = db_factory()
    sub = db.get(Submission, ids["submission_id"])

    # Rejecting a VALID doc is an override → reason required.
    rej = apply_client_decision(
        db, submission=sub, action="reject",
        reason="No cumple nuestro estándar interno", client_user_id=ids["approver_id"],
    )
    assert rej.new_acceptance == ClientAcceptance.REJECTED.value
    assert rej.was_override is True
    assert db.get(Submission, sub.id).client_acceptance == ClientAcceptance.REJECTED.value

    # Reset returns to PENDING (no reason needed).
    res = apply_client_decision(
        db, submission=sub, action="reset", reason=None,
        client_user_id=ids["approver_id"],
    )
    assert res.new_acceptance == ClientAcceptance.PENDING.value
    assert db.get(Submission, sub.id).status == DocumentStatus.APROBADO.value
    db.close()


def test_override_without_reason_is_422(db_factory) -> None:
    """Accepting a NON-valid doc contradicts the verdict → reason required."""
    ids = _seed_world(db_factory, submission_status=DocumentStatus.RECHAZADO.value)
    db = db_factory()
    sub = db.get(Submission, ids["submission_id"])
    with pytest.raises(HTTPException) as exc:
        apply_client_decision(
            db, submission=sub, action="accept", reason="   ",
            client_user_id=ids["approver_id"],
        )
    assert exc.value.status_code == 422
    # Nothing was written — still PENDING.
    assert db.get(Submission, sub.id).client_acceptance == ClientAcceptance.PENDING.value
    db.close()


def test_reject_invalid_doc_is_aligned_no_reason_required(db_factory) -> None:
    """Rejecting a doc CheckWise already marked invalid is NOT an override."""
    ids = _seed_world(db_factory, submission_status=DocumentStatus.RECHAZADO.value)
    db = db_factory()
    sub = db.get(Submission, ids["submission_id"])
    result = apply_client_decision(
        db, submission=sub, action="reject", reason=None,
        client_user_id=ids["approver_id"],
    )
    assert result.was_override is False
    assert db.get(Submission, sub.id).client_acceptance == ClientAcceptance.REJECTED.value
    db.close()


# ---------------------------------------------------------------------------
# HTTP layer — POST /client/submissions/{id}/decision
# ---------------------------------------------------------------------------


def test_endpoint_approver_can_accept(api_client, db_factory) -> None:
    ids = _seed_world(db_factory, submission_status=DocumentStatus.APROBADO.value)
    tok = _login(api_client, ids["approver_email"], ids["approver_pw"])
    r = api_client.post(
        f"/api/v1/client/submissions/{ids['submission_id']}/decision",
        json={"action": "accept"},
        headers=_h(tok),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["new_acceptance"] == ClientAcceptance.ACCEPTED.value
    assert body["override"] is False


def test_endpoint_viewer_is_forbidden(api_client, db_factory) -> None:
    """A client_viewer is 403'd at the ClientApprover gate — acceptance is a
    write, consistent with the Phase 4 Approver/Viewer split."""
    ids = _seed_world(db_factory)
    tok = _login(api_client, ids["viewer_email"], ids["viewer_pw"])
    r = api_client.post(
        f"/api/v1/client/submissions/{ids['submission_id']}/decision",
        json={"action": "accept"},
        headers=_h(tok),
    )
    assert r.status_code == 403, r.text


def test_endpoint_override_without_reason_is_422(api_client, db_factory) -> None:
    ids = _seed_world(db_factory, submission_status=DocumentStatus.RECHAZADO.value)
    tok = _login(api_client, ids["approver_email"], ids["approver_pw"])
    r = api_client.post(
        f"/api/v1/client/submissions/{ids['submission_id']}/decision",
        json={"action": "accept"},
        headers=_h(tok),
    )
    assert r.status_code == 422, r.text


def test_endpoint_cross_tenant_is_404(api_client, db_factory) -> None:
    """An Approver of client A cannot decide on client B's submission — uniform
    404 (never confirm a cross-tenant submission exists)."""
    a = _seed_world(db_factory)
    b = _seed_world(db_factory)
    tok = _login(api_client, a["approver_email"], a["approver_pw"])
    r = api_client.post(
        f"/api/v1/client/submissions/{b['submission_id']}/decision",
        json={"action": "accept"},
        headers=_h(tok),
    )
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# Bulk decision
# ---------------------------------------------------------------------------


def test_bulk_accept_partial_success(api_client, db_factory) -> None:
    """A valid doc accepts; a non-valid one in the same batch fails the
    override-reason rule and is reported — without aborting the rest."""
    valid = _seed_world(db_factory, submission_status=DocumentStatus.APROBADO.value)
    invalid = _seed_world(db_factory, submission_status=DocumentStatus.RECHAZADO.value)
    # Re-point the invalid submission to the SAME client so it's in tenant.
    db = db_factory()
    bad = db.get(Submission, invalid["submission_id"])
    bad.client_id = valid["client_id"]
    db.commit()
    db.close()

    tok = _login(api_client, valid["approver_email"], valid["approver_pw"])
    r = api_client.post(
        "/api/v1/client/submissions/bulk-decision",
        json={
            "action": "accept",
            "submission_ids": [valid["submission_id"], invalid["submission_id"]],
        },
        headers=_h(tok),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decided"] == [valid["submission_id"]]
    assert body["decided_count"] == 1
    assert body["failed_count"] == 1
    assert body["failed"][0]["submission_id"] == invalid["submission_id"]


def test_bulk_viewer_forbidden(api_client, db_factory) -> None:
    ids = _seed_world(db_factory)
    tok = _login(api_client, ids["viewer_email"], ids["viewer_pw"])
    r = api_client.post(
        "/api/v1/client/submissions/bulk-decision",
        json={"action": "accept", "submission_ids": [ids["submission_id"]]},
        headers=_h(tok),
    )
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# Auto-accept-on-valid (reviewer-path hook)
# ---------------------------------------------------------------------------


def test_auto_accept_fires_when_opted_in(db_factory) -> None:
    """A reviewer APPROVE on an opted-in client's submission folds in a system
    ACCEPTED decision — atomically, in the same transaction."""
    ids = _seed_world(
        db_factory, submission_status=DocumentStatus.PENDIENTE_REVISION.value
    )
    _set_auto_accept(db_factory, ids["client_id"], True)
    db = db_factory()
    sub = db.get(Submission, ids["submission_id"])
    apply_reviewer_decision(
        db, submission=sub, action=ReviewerAction.APPROVE, reason=None,
        reviewer_user_id="rev-1",
    )
    sub = db.get(Submission, ids["submission_id"])
    assert sub.status == DocumentStatus.APROBADO.value
    assert sub.client_acceptance == ClientAcceptance.ACCEPTED.value
    # Recorded as a SYSTEM decision (no human approver).
    assert sub.client_decided_by_user_id is None
    ev = db.scalar(
        select(ValidationEvent).where(
            ValidationEvent.submission_id == sub.id,
            ValidationEvent.event_type == "client_decision",
            ValidationEvent.actor_type == "system",
        )
    )
    assert ev is not None
    db.close()


def test_no_auto_accept_when_opted_out(db_factory) -> None:
    ids = _seed_world(
        db_factory, submission_status=DocumentStatus.PENDIENTE_REVISION.value
    )
    # auto_accept_valid defaults False — do not opt in.
    db = db_factory()
    sub = db.get(Submission, ids["submission_id"])
    apply_reviewer_decision(
        db, submission=sub, action=ReviewerAction.APPROVE, reason=None,
        reviewer_user_id="rev-1",
    )
    sub = db.get(Submission, ids["submission_id"])
    assert sub.status == DocumentStatus.APROBADO.value
    assert sub.client_acceptance == ClientAcceptance.PENDING.value
    db.close()


# ---------------------------------------------------------------------------
# Acceptance preferences
# ---------------------------------------------------------------------------


def test_prefs_viewer_reads_approver_toggles(api_client, db_factory) -> None:
    ids = _seed_world(db_factory)
    viewer_tok = _login(api_client, ids["viewer_email"], ids["viewer_pw"])
    approver_tok = _login(api_client, ids["approver_email"], ids["approver_pw"])

    # Viewer may READ the preference.
    g = api_client.get("/api/v1/client/acceptance-preferences", headers=_h(viewer_tok))
    assert g.status_code == 200, g.text
    assert g.json()["auto_accept_valid"] is False

    # Viewer may NOT toggle it.
    v = api_client.patch(
        "/api/v1/client/acceptance-preferences",
        json={"auto_accept_valid": True},
        headers=_h(viewer_tok),
    )
    assert v.status_code == 403, v.text

    # Approver toggles it on; the read reflects it.
    p = api_client.patch(
        "/api/v1/client/acceptance-preferences",
        json={"auto_accept_valid": True},
        headers=_h(approver_tok),
    )
    assert p.status_code == 200, p.text
    assert p.json()["auto_accept_valid"] is True
    g2 = api_client.get(
        "/api/v1/client/acceptance-preferences", headers=_h(approver_tok)
    )
    assert g2.json()["auto_accept_valid"] is True
