"""Phase 2 — submission/document workflow state machine.

Covers :func:`app.services.submission_workflow.apply_reviewer_decision`
both as a unit (direct service call) and through the reviewer HTTP API
(``POST /api/v1/reviewer/submissions/{id}/decision``). The service is
the single owner of reviewer-driven transitions, so these tests pin:

* Allowed source -> target transitions (approve / reject /
  request_clarification / mark_exception).
* Reason requirement for non-approve actions.
* Terminal-status guard (409 on re-decision).
* Unsupported source statuses (409).
* All four audit-trail side effects: ``Submission.status``,
  ``Document.status``, ``DocumentStatusHistory``, ``ValidationEvent``
  (``reviewer_decision``), ``AuditLog``
  (``submission.reviewer_decision``).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants.statuses import DocumentStatus, ReviewerAction
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    AuditLog,
    Client,
    Document,
    DocumentStatusHistory,
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
from app.models.entities import utc_now
from app.services.auth import hash_password
from app.services.submission_workflow import (
    apply_reviewer_decision,
    is_terminal_status,
)

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


_SEED_COUNTER = 0


def _seed_user(
    db_factory,
    *,
    email: str = "rev@x.mx",
    role: str | None = "reviewer",
    password: str = "Hunter2 Correct horse",
) -> tuple[str, str]:
    """Returns (user_id, password). Mirrors the helper used in test_reviewer.py."""
    db = db_factory()
    try:
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name="Reviewer",
            status="active",
        )
        db.add(user)
        db.flush()
        if role is not None:
            org = Organization(name="LegalShelf", kind="internal")
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
        return user.id, password
    finally:
        db.close()


def _seed_submission(
    db_factory,
    *,
    status_: str = DocumentStatus.PENDIENTE_REVISION.value,
    with_document: bool = True,
) -> str:
    """Insert a Submission (and optional Document) at the requested status.

    Each call mints unique RFCs / requirement codes / period keys so
    multiple submissions can coexist in one test without unique-
    constraint clashes.
    """
    global _SEED_COUNTER
    _SEED_COUNTER += 1
    suffix = _SEED_COUNTER

    db = db_factory()
    try:
        client_rfc = f"WF{suffix:02d}260101AB"[:13]
        client = Client(name=f"Cliente Workflow {suffix}", rfc=client_rfc)
        db.add(client)
        db.flush()

        vendor_rfc = f"WV{suffix:02d}260101XY"[:13]
        vendor = Vendor(client_id=client.id, name=f"Vendor WF {suffix}", rfc=vendor_rfc)
        db.add(vendor)
        db.flush()

        institution = db.scalar(select(Institution).where(Institution.code == "sat"))
        if institution is None:
            institution = Institution(code="sat", name="SAT")
            db.add(institution)
            db.flush()

        req_code = f"wf:test:{suffix}"
        requirement = Requirement(
            code=req_code,
            name=f"Requisito WF {suffix}",
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

        period_key = f"2026-WF{suffix:02d}"
        period = Period(
            code=period_key,
            year=2026,
            period_type="mensual",
            period_key=period_key,
        )
        db.add(period)
        db.flush()

        submitted_at = utc_now() - timedelta(hours=1)
        submission = Submission(
            client_id=client.id,
            vendor_id=vendor.id,
            institution_id=institution.id,
            requirement_id=requirement.id,
            requirement_version_id=req_version.id,
            period_id=period.id,
            status=status_,
            load_type="mensual",
            requirement_code=req_code,
            period_key=period_key,
            created_at=submitted_at,
            updated_at=submitted_at,
        )
        db.add(submission)
        db.flush()

        if with_document:
            document = Document(
                submission_id=submission.id,
                storage_key=f"local://wf/{submission.id}.pdf",
                original_filename=f"wf-{suffix}.pdf",
                mime_type="application/pdf",
                size_bytes=2048,
                sha256="b" * 64,
                # Pre-Phase-2 the reviewer endpoint left this on the intake-
                # time status. Seed it that way so the test can prove the
                # workflow service flips it.
                status=status_,
            )
            db.add(document)

        db.commit()
        return submission.id
    finally:
        db.close()


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


# ---------------------------------------------------------------------------
# Unit tests — call the workflow service directly
# ---------------------------------------------------------------------------


def test_apply_reviewer_decision_approve_from_pendiente_revision(db_factory) -> None:
    """Test 1: approve from pendiente_revision succeeds."""
    user_id, _ = _seed_user(db_factory)
    submission_id = _seed_submission(db_factory)

    db = db_factory()
    try:
        submission = db.get(Submission, submission_id)
        result = apply_reviewer_decision(
            db,
            submission=submission,
            action=ReviewerAction.APPROVE,
            reason=None,
            reviewer_user_id=user_id,
        )
    finally:
        db.close()

    assert result.previous_status == DocumentStatus.PENDIENTE_REVISION.value
    assert result.new_status == DocumentStatus.APROBADO.value
    assert result.action == ReviewerAction.APPROVE.value
    assert result.reason is None


def test_apply_reviewer_decision_reject_requires_reason(db_factory) -> None:
    """Test 2: reject from pendiente_revision requires a reason."""
    user_id, _ = _seed_user(db_factory)
    submission_id = _seed_submission(db_factory)

    db = db_factory()
    try:
        submission = db.get(Submission, submission_id)
        # No reason → 422.
        with pytest.raises(HTTPException) as exc_info:
            apply_reviewer_decision(
                db,
                submission=submission,
                action=ReviewerAction.REJECT,
                reason=None,
                reviewer_user_id=user_id,
            )
        assert exc_info.value.status_code == 422
        # Whitespace-only reason is treated as empty.
        with pytest.raises(HTTPException) as exc_info:
            apply_reviewer_decision(
                db,
                submission=submission,
                action=ReviewerAction.REJECT,
                reason="   ",
                reviewer_user_id=user_id,
            )
        assert exc_info.value.status_code == 422

        # With a real reason it succeeds.
        result = apply_reviewer_decision(
            db,
            submission=submission,
            action=ReviewerAction.REJECT,
            reason="PDF ilegible en página 2.",
            reviewer_user_id=user_id,
        )
    finally:
        db.close()

    assert result.new_status == DocumentStatus.RECHAZADO.value
    assert result.reason == "PDF ilegible en página 2."


def test_apply_reviewer_decision_request_clarification_from_posible_mismatch(
    db_factory,
) -> None:
    """Test 3: request_clarification from posible_mismatch requires a reason."""
    user_id, _ = _seed_user(db_factory)
    submission_id = _seed_submission(
        db_factory, status_=DocumentStatus.POSIBLE_MISMATCH.value
    )

    db = db_factory()
    try:
        submission = db.get(Submission, submission_id)
        with pytest.raises(HTTPException) as exc_info:
            apply_reviewer_decision(
                db,
                submission=submission,
                action=ReviewerAction.REQUEST_CLARIFICATION,
                reason=None,
                reviewer_user_id=user_id,
            )
        assert exc_info.value.status_code == 422

        result = apply_reviewer_decision(
            db,
            submission=submission,
            action=ReviewerAction.REQUEST_CLARIFICATION,
            reason="¿Confirmar periodo?",
            reviewer_user_id=user_id,
        )
    finally:
        db.close()

    assert result.previous_status == DocumentStatus.POSIBLE_MISMATCH.value
    assert result.new_status == DocumentStatus.REQUIERE_ACLARACION.value


def test_apply_reviewer_decision_mark_exception_from_posible_mismatch(
    db_factory,
) -> None:
    """Test 4: mark_exception from posible_mismatch requires a reason and succeeds."""
    user_id, _ = _seed_user(db_factory)
    submission_id = _seed_submission(
        db_factory, status_=DocumentStatus.POSIBLE_MISMATCH.value
    )

    db = db_factory()
    try:
        submission = db.get(Submission, submission_id)
        with pytest.raises(HTTPException) as exc_info:
            apply_reviewer_decision(
                db,
                submission=submission,
                action=ReviewerAction.MARK_EXCEPTION,
                reason=None,
                reviewer_user_id=user_id,
            )
        assert exc_info.value.status_code == 422

        result = apply_reviewer_decision(
            db,
            submission=submission,
            action=ReviewerAction.MARK_EXCEPTION,
            reason="Aceptamos por excepción legal documentada por compliance.",
            reviewer_user_id=user_id,
        )
    finally:
        db.close()

    assert result.new_status == DocumentStatus.EXCEPCION_LEGAL.value


def test_apply_reviewer_decision_409_when_already_aprobado(db_factory) -> None:
    """Test 5: re-deciding an aprobado submission fails 409."""
    user_id, _ = _seed_user(db_factory)
    submission_id = _seed_submission(
        db_factory, status_=DocumentStatus.APROBADO.value
    )

    db = db_factory()
    try:
        submission = db.get(Submission, submission_id)
        with pytest.raises(HTTPException) as exc_info:
            apply_reviewer_decision(
                db,
                submission=submission,
                action=ReviewerAction.REJECT,
                reason="cambio de opinión",
                reviewer_user_id=user_id,
            )
        assert exc_info.value.status_code == 409
    finally:
        db.close()


def test_apply_reviewer_decision_409_when_already_rechazado(db_factory) -> None:
    """Test 6: re-deciding a rechazado submission fails 409."""
    user_id, _ = _seed_user(db_factory)
    submission_id = _seed_submission(
        db_factory, status_=DocumentStatus.RECHAZADO.value
    )

    db = db_factory()
    try:
        submission = db.get(Submission, submission_id)
        with pytest.raises(HTTPException) as exc_info:
            apply_reviewer_decision(
                db,
                submission=submission,
                action=ReviewerAction.APPROVE,
                reason=None,
                reviewer_user_id=user_id,
            )
        assert exc_info.value.status_code == 409
    finally:
        db.close()


def test_apply_reviewer_decision_rejects_unsupported_source_status(
    db_factory,
) -> None:
    """Test 7: invalid source status (e.g. ``pendiente``, ``vencido``) → 409.

    These statuses don't reach a reviewer in the supported flows, so a
    decision attempt is a logic error rather than a routine outcome.
    """
    user_id, _ = _seed_user(db_factory)
    submission_id = _seed_submission(
        db_factory, status_=DocumentStatus.VENCIDO.value
    )

    db = db_factory()
    try:
        submission = db.get(Submission, submission_id)
        with pytest.raises(HTTPException) as exc_info:
            apply_reviewer_decision(
                db,
                submission=submission,
                action=ReviewerAction.APPROVE,
                reason=None,
                reviewer_user_id=user_id,
            )
        assert exc_info.value.status_code == 409
    finally:
        db.close()


def test_apply_reviewer_decision_updates_document_status_too(db_factory) -> None:
    """Tests 8 + 9 + 10: Submission.status, Document.status, history row."""
    user_id, _ = _seed_user(db_factory)
    submission_id = _seed_submission(db_factory)

    db = db_factory()
    try:
        submission = db.get(Submission, submission_id)
        result = apply_reviewer_decision(
            db,
            submission=submission,
            action=ReviewerAction.APPROVE,
            reason=None,
            reviewer_user_id=user_id,
        )
        assert result.new_status == DocumentStatus.APROBADO.value
    finally:
        db.close()

    db = db_factory()
    try:
        sub = db.get(Submission, submission_id)
        assert sub is not None
        # Test 8 — Submission.status mutated.
        assert sub.status == DocumentStatus.APROBADO.value

        # Test 9 — Document.status mutated for the primary document.
        # This is the gap Phase 2 closes: pre-Phase-2 the document row
        # kept its intake-time status indefinitely.
        document = db.scalar(
            select(Document).where(Document.submission_id == submission_id)
        )
        assert document is not None
        assert document.status == DocumentStatus.APROBADO.value

        # Test 10 — DocumentStatusHistory row written.
        history = db.scalars(
            select(DocumentStatusHistory).where(
                DocumentStatusHistory.submission_id == submission_id
            )
        ).all()
        assert any(
            h.from_status == DocumentStatus.PENDIENTE_REVISION.value
            and h.to_status == DocumentStatus.APROBADO.value
            and h.actor == f"reviewer:{user_id}"
            for h in history
        )
    finally:
        db.close()


def test_apply_reviewer_decision_writes_validation_event(db_factory) -> None:
    """Test 11: ValidationEvent ``reviewer_decision`` is written."""
    user_id, _ = _seed_user(db_factory)
    submission_id = _seed_submission(db_factory)

    db = db_factory()
    try:
        submission = db.get(Submission, submission_id)
        apply_reviewer_decision(
            db,
            submission=submission,
            action=ReviewerAction.REJECT,
            reason="Documento incompleto.",
            reviewer_user_id=user_id,
        )
    finally:
        db.close()

    db = db_factory()
    try:
        event = db.scalar(
            select(ValidationEvent).where(
                ValidationEvent.submission_id == submission_id,
                ValidationEvent.event_type == "reviewer_decision",
            )
        )
        assert event is not None
        assert event.result == ReviewerAction.REJECT.value
        assert event.actor_type == "reviewer"
        assert event.message == "Documento incompleto."
        # Payload threads the from/to status for downstream consumers.
        payload = event.payload or {}
        assert payload.get("from_status") == DocumentStatus.PENDIENTE_REVISION.value
        assert payload.get("to_status") == DocumentStatus.RECHAZADO.value
        assert payload.get("reviewer_user_id") == user_id
    finally:
        db.close()


def test_apply_reviewer_decision_writes_audit_log(db_factory) -> None:
    """Test 12: AuditLog is written with reviewer actor + before/after + reason."""
    user_id, _ = _seed_user(db_factory)
    submission_id = _seed_submission(db_factory)

    db = db_factory()
    try:
        submission = db.get(Submission, submission_id)
        apply_reviewer_decision(
            db,
            submission=submission,
            action=ReviewerAction.MARK_EXCEPTION,
            reason="Acuerdo con cliente vigente hasta cierre fiscal.",
            reviewer_user_id=user_id,
        )
    finally:
        db.close()

    db = db_factory()
    try:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_type == "submission",
                AuditLog.entity_id == submission_id,
                AuditLog.action == "submission.reviewer_decision",
            )
        )
        assert audit is not None, "expected an audit_log row for the reviewer decision"
        assert audit.actor_type == "reviewer"
        assert audit.actor_id == user_id
        assert (audit.before or {}).get("status") == DocumentStatus.PENDIENTE_REVISION.value
        assert (audit.after or {}).get("status") == DocumentStatus.EXCEPCION_LEGAL.value
        meta = audit.event_metadata or {}
        assert meta.get("reviewer_action") == ReviewerAction.MARK_EXCEPTION.value
        assert meta.get("reason") == "Acuerdo con cliente vigente hasta cierre fiscal."
        # Document id is recorded so a cross-table audit can join back to the file.
        assert meta.get("document_id")
    finally:
        db.close()


def test_is_terminal_status_helper() -> None:
    """Sanity check on the small helper exposed by the workflow service."""
    assert is_terminal_status(DocumentStatus.APROBADO) is True
    assert is_terminal_status("rechazado") is True
    assert is_terminal_status(DocumentStatus.EXCEPCION_LEGAL) is True
    assert is_terminal_status("pendiente_revision") is False
    assert is_terminal_status("unknown-code") is False


# ---------------------------------------------------------------------------
# HTTP integration — reviewer endpoint still routes through the workflow
# ---------------------------------------------------------------------------


def test_reviewer_endpoint_routes_through_workflow_and_writes_audit_log(
    api_client: TestClient, db_factory
) -> None:
    """Integration check: the reviewer HTTP path now writes audit_log too.

    Pre-Phase-2 the endpoint wrote history + validation_event but NOT
    audit_log. The refactor wires the endpoint through the workflow
    service, so an audit_log row must now appear for every decision the
    HTTP layer accepts.
    """
    user_id, password = _seed_user(db_factory)
    token = _login(api_client, "rev@x.mx", password)
    submission_id = _seed_submission(db_factory)

    response = api_client.post(
        f"/api/v1/reviewer/submissions/{submission_id}/decision",
        json={"action": "reject", "reason": "Falta firma del representante legal."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["new_status"] == DocumentStatus.RECHAZADO.value

    db = db_factory()
    try:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_type == "submission",
                AuditLog.entity_id == submission_id,
                AuditLog.action == "submission.reviewer_decision",
            )
        )
        assert audit is not None
        assert audit.actor_id == user_id
        meta = audit.event_metadata or {}
        assert meta.get("reviewer_action") == "reject"
        assert meta.get("reason") == "Falta firma del representante legal."

        # Submission AND document statuses are now in sync.
        sub = db.get(Submission, submission_id)
        assert sub is not None and sub.status == DocumentStatus.RECHAZADO.value
        doc = db.scalar(select(Document).where(Document.submission_id == submission_id))
        assert doc is not None and doc.status == DocumentStatus.RECHAZADO.value
    finally:
        db.close()
