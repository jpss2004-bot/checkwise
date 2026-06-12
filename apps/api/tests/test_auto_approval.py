"""Phase E — approval suggestion (live) + auto-approve engine (dark).

Covers the three Phase-E pieces:

* ``approval_suggestion`` block on ``GET /reviewer/submissions/{id}``
  — advisory only, per-criterion flags, Spanish detail sentence.
* Suggestion-acceptance telemetry on the decision endpoint —
  ``accepted_suggestion`` lands in the decision audit metadata.
* ``app.services.auto_approval.maybe_auto_approve`` — dark by
  default, every eligibility gate blocks individually, the unlocked
  happy path reuses the reviewer transition (status + history +
  validation event + audit ``system.auto_approved`` + provider
  notification), and a crash inside the engine never breaks shadow
  persistence (fail-open).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
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
    DocumentInspection,
    DocumentStatusHistory,
    Institution,
    Membership,
    Organization,
    Period,
    ProviderNotification,
    ProviderWorkspace,
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
from app.services.auto_approval import AutoApprovalOutcome, maybe_auto_approve
from app.services.submission_workflow import AUTO_APPROVAL_REASON_ES

# ---------------------------------------------------------------------------
# Fixtures (mirrors tests/test_reviewer.py)
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


def _seed_user(
    db_factory,
    *,
    email: str = "rev-phase-e@x.mx",
    role: str = "reviewer",
    password: str = "Hunter2 Correct horse",
) -> tuple[str, str]:
    db = db_factory()
    try:
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name="Reviewer Phase E",
            status="active",
        )
        db.add(user)
        db.flush()
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


_SEED_COUNTER = 0


def _seed_submission(
    db_factory,
    *,
    status_: str = DocumentStatus.PENDIENTE_REVISION.value,
    cadence: str = "mensual",
    with_inspection: bool = True,
    authenticity_risk: str | None = "clean",
    risk_reasons: list | None = None,
    shadow_confidence: float | None = None,
    requirement_match_confidence: float | None = None,
    shadow_signals: dict | None = None,
    with_workspace: bool = False,
) -> tuple[str, str]:
    """Insert a full submission graph; returns (submission_id, requirement_code).

    Each call mints unique RFCs / requirement codes / period keys so
    multiple submissions can coexist without unique-constraint clashes.
    ``cadence`` drives both the requirement's load_type/frequency and
    the submission's denormalized load_type.
    """
    global _SEED_COUNTER
    _SEED_COUNTER += 1
    suffix = _SEED_COUNTER

    db = db_factory()
    try:
        client = Client(name=f"Cliente AA {suffix}", rfc=f"AA{suffix:03d}260101AB"[:13])
        db.add(client)
        db.flush()
        vendor = Vendor(
            client_id=client.id,
            name=f"Vendor AA {suffix}",
            rfc=f"AV{suffix:03d}260101XY"[:13],
        )
        db.add(vendor)
        db.flush()

        institution = db.scalar(select(Institution).where(Institution.code == "sat"))
        if institution is None:
            institution = Institution(code="sat", name="SAT")
            db.add(institution)
            db.flush()

        req_code = f"aa:test:{cadence}:{suffix}"
        requirement = Requirement(
            code=req_code,
            name=f"Requisito AA {suffix}",
            institution_id=institution.id,
            load_type=cadence,
            frequency=cadence,
            risk_level="medium",
            current_version=1,
        )
        db.add(requirement)
        db.flush()
        req_version = RequirementVersion(requirement_id=requirement.id, version=1)
        db.add(req_version)
        db.flush()

        period_key = f"2026-AA{suffix:03d}"
        period = Period(
            code=period_key,
            year=2026,
            period_type=cadence,
            period_key=period_key,
        )
        db.add(period)
        db.flush()

        submitted_at = utc_now() - timedelta(hours=2)
        submission = Submission(
            client_id=client.id,
            vendor_id=vendor.id,
            institution_id=institution.id,
            requirement_id=requirement.id,
            requirement_version_id=req_version.id,
            period_id=period.id,
            status=status_,
            load_type=cadence,
            requirement_code=req_code,
            period_key=period_key,
            created_at=submitted_at,
            updated_at=submitted_at,
        )
        db.add(submission)
        db.flush()

        document = Document(
            submission_id=submission.id,
            storage_key=f"local://aa/{submission.id}.pdf",
            original_filename=f"aa-{suffix}.pdf",
            mime_type="application/pdf",
            size_bytes=2048,
            sha256="c" * 64,
            status=status_,
        )
        db.add(document)
        db.flush()

        if with_inspection:
            db.add(
                DocumentInspection(
                    document_id=document.id,
                    is_pdf=True,
                    authenticity_risk=authenticity_risk,
                    risk_reasons=risk_reasons,
                    shadow_confidence=shadow_confidence,
                    requirement_match_confidence=requirement_match_confidence,
                    shadow_signals=shadow_signals,
                )
            )

        if with_workspace:
            db.add(
                ProviderWorkspace(
                    client_id=client.id,
                    vendor_id=vendor.id,
                    persona_type="moral",
                    access_token=f"aa-token-{submission.id[:8]}",
                )
            )

        db.commit()
        return submission.id, req_code
    finally:
        db.close()


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _get_detail(api_client: TestClient, db_factory, submission_id: str) -> dict:
    global _SEED_COUNTER
    _SEED_COUNTER += 1
    _, password = _seed_user(
        db_factory, email=f"rev-detail-{_SEED_COUNTER}@x.mx"
    )
    token = _login(api_client, f"rev-detail-{_SEED_COUNTER}@x.mx", password)
    response = api_client.get(
        f"/api/v1/reviewer/submissions/{submission_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# 1) Approval suggestion block (reviewer detail endpoint)
# ---------------------------------------------------------------------------


def test_suggestion_all_criteria_met_suggests_approval(
    api_client: TestClient, db_factory
) -> None:
    submission_id, _ = _seed_submission(
        db_factory, authenticity_risk="clean", shadow_confidence=0.95
    )
    body = _get_detail(api_client, db_factory, submission_id)
    suggestion = body["approval_suggestion"]
    assert suggestion is not None
    assert suggestion["suggested"] is True
    assert suggestion["confidence"] == pytest.approx(0.95)
    assert suggestion["confidence_source"] == "shadow"
    assert suggestion["criteria"] == {
        "match_ok": True,
        "risk_clean": True,
        "recurring": True,
    }
    assert "sugerimos aprobar" in suggestion["detail_es"]
    assert "IA" in suggestion["detail_es"]


def test_suggestion_falls_back_to_heuristic_confidence(
    api_client: TestClient, db_factory
) -> None:
    submission_id, _ = _seed_submission(
        db_factory,
        authenticity_risk="clean",
        shadow_confidence=None,
        requirement_match_confidence=0.93,
    )
    suggestion = _get_detail(api_client, db_factory, submission_id)[
        "approval_suggestion"
    ]
    assert suggestion["suggested"] is True
    assert suggestion["confidence"] == pytest.approx(0.93)
    assert suggestion["confidence_source"] == "heuristic"


def test_suggestion_low_confidence_blocks_with_match_flag(
    api_client: TestClient, db_factory
) -> None:
    submission_id, _ = _seed_submission(
        db_factory, authenticity_risk="clean", shadow_confidence=0.5
    )
    suggestion = _get_detail(api_client, db_factory, submission_id)[
        "approval_suggestion"
    ]
    assert suggestion["suggested"] is False
    assert suggestion["criteria"]["match_ok"] is False
    assert suggestion["criteria"]["risk_clean"] is True
    assert suggestion["criteria"]["recurring"] is True
    assert "confianza" in suggestion["detail_es"]


def test_suggestion_unclean_risk_blocks_with_risk_flag(
    api_client: TestClient, db_factory
) -> None:
    submission_id, _ = _seed_submission(
        db_factory, authenticity_risk="suspicious", shadow_confidence=0.97
    )
    suggestion = _get_detail(api_client, db_factory, submission_id)[
        "approval_suggestion"
    ]
    assert suggestion["suggested"] is False
    assert suggestion["criteria"]["risk_clean"] is False
    assert suggestion["criteria"]["match_ok"] is True


def test_suggestion_unanalyzed_risk_is_not_clean(
    api_client: TestClient, db_factory
) -> None:
    """NULL authenticity_risk (analyzer failed open) must never read as clean."""
    submission_id, _ = _seed_submission(
        db_factory, authenticity_risk=None, shadow_confidence=0.99
    )
    suggestion = _get_detail(api_client, db_factory, submission_id)[
        "approval_suggestion"
    ]
    assert suggestion["suggested"] is False
    assert suggestion["criteria"]["risk_clean"] is False


def test_suggestion_alta_inicial_never_suggests(
    api_client: TestClient, db_factory
) -> None:
    submission_id, _ = _seed_submission(
        db_factory,
        cadence="alta_inicial",
        authenticity_risk="clean",
        shadow_confidence=0.99,
    )
    suggestion = _get_detail(api_client, db_factory, submission_id)[
        "approval_suggestion"
    ]
    assert suggestion["suggested"] is False
    assert suggestion["criteria"]["recurring"] is False
    assert suggestion["criteria"]["match_ok"] is True
    assert suggestion["criteria"]["risk_clean"] is True
    assert "recurrente" in suggestion["detail_es"]


def test_suggestion_null_when_no_inspection(
    api_client: TestClient, db_factory
) -> None:
    submission_id, _ = _seed_submission(db_factory, with_inspection=False)
    body = _get_detail(api_client, db_factory, submission_id)
    assert body["approval_suggestion"] is None


# ---------------------------------------------------------------------------
# 2) Suggestion-acceptance telemetry (decision endpoint)
# ---------------------------------------------------------------------------


def _post_decision(
    api_client: TestClient, db_factory, submission_id: str, payload: dict
) -> dict:
    global _SEED_COUNTER
    _SEED_COUNTER += 1
    email = f"rev-decide-{_SEED_COUNTER}@x.mx"
    _, password = _seed_user(db_factory, email=email)
    token = _login(api_client, email, password)
    response = api_client.post(
        f"/api/v1/reviewer/submissions/{submission_id}/decision",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_accepted_suggestion_lands_in_decision_audit_metadata(
    api_client: TestClient, db_factory
) -> None:
    submission_id, _ = _seed_submission(
        db_factory, authenticity_risk="clean", shadow_confidence=0.95
    )
    _post_decision(
        api_client,
        db_factory,
        submission_id,
        {"action": "approve", "accepted_suggestion": True},
    )

    db = db_factory()
    try:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_id == submission_id,
                AuditLog.action == "submission.reviewer_decision",
            )
        )
        assert audit is not None
        assert (audit.event_metadata or {}).get("suggestion") == {
            "shown": True,
            "accepted": True,
        }
    finally:
        db.close()


def test_rejected_suggestion_records_accepted_false(
    api_client: TestClient, db_factory
) -> None:
    submission_id, _ = _seed_submission(
        db_factory, authenticity_risk="clean", shadow_confidence=0.95
    )
    _post_decision(
        api_client,
        db_factory,
        submission_id,
        {
            "action": "reject",
            "reason": "RFC no coincide con el proveedor.",
            "accepted_suggestion": False,
        },
    )

    db = db_factory()
    try:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_id == submission_id,
                AuditLog.action == "submission.reviewer_decision",
            )
        )
        assert (audit.event_metadata or {}).get("suggestion") == {
            "shown": True,
            "accepted": False,
        }
    finally:
        db.close()


def test_decision_without_telemetry_writes_no_suggestion_key(
    api_client: TestClient, db_factory
) -> None:
    submission_id, _ = _seed_submission(
        db_factory, authenticity_risk="clean", shadow_confidence=0.95
    )
    _post_decision(api_client, db_factory, submission_id, {"action": "approve"})

    db = db_factory()
    try:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_id == submission_id,
                AuditLog.action == "submission.reviewer_decision",
            )
        )
        assert audit is not None
        assert "suggestion" not in (audit.event_metadata or {})
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 3) Auto-approve engine
# ---------------------------------------------------------------------------


def _enable_auto_approve(monkeypatch, *, codes: str) -> None:
    monkeypatch.setattr(settings, "AUTO_APPROVE_ENABLED", True)
    monkeypatch.setattr(settings, "AUTO_APPROVE_UNLOCKED_REQUIREMENT_CODES", codes)


def _run_engine(db_factory, submission_id: str) -> AutoApprovalOutcome:
    db = db_factory()
    try:
        return maybe_auto_approve(db, submission_id)
    finally:
        db.close()


def _perfect_submission(db_factory, **overrides) -> tuple[str, str]:
    """A submission that passes every auto-approve gate when unlocked."""
    params: dict = {
        "authenticity_risk": "clean",
        "shadow_confidence": 0.99,
        "shadow_signals": {"_tiers": {"triage": {"provider_id": "anthropic:haiku"}}},
        "with_workspace": True,
    }
    params.update(overrides)
    return _seed_submission(db_factory, **params)


def test_auto_approve_is_dark_by_default(db_factory) -> None:
    """Master flag off → attempted False even for a perfect candidate."""
    submission_id, req_code = _perfect_submission(db_factory)
    # Defensive: even with the requirement unlocked, the master flag
    # (default False) must win.
    assert settings.AUTO_APPROVE_ENABLED is False

    outcome = _run_engine(db_factory, submission_id)
    assert outcome.attempted is False
    assert outcome.approved is False
    assert outcome.reason == "disabled"

    db = db_factory()
    try:
        sub = db.get(Submission, submission_id)
        assert sub.status == DocumentStatus.PENDIENTE_REVISION.value
    finally:
        db.close()


def test_auto_approve_unlocked_and_eligible_approves(monkeypatch, db_factory) -> None:
    submission_id, req_code = _perfect_submission(db_factory)
    # Whitespace-tolerant CSV parsing is part of the contract.
    _enable_auto_approve(monkeypatch, codes=f"  otro:codigo , {req_code} ")

    outcome = _run_engine(db_factory, submission_id)
    assert outcome.attempted is True
    assert outcome.approved is True
    assert outcome.reason == "approved"

    db = db_factory()
    try:
        sub = db.get(Submission, submission_id)
        assert sub.status == DocumentStatus.APROBADO.value
        doc = db.scalar(select(Document).where(Document.submission_id == submission_id))
        assert doc.status == DocumentStatus.APROBADO.value

        # History row: system actor + the distinct Spanish auto reason.
        history = db.scalar(
            select(DocumentStatusHistory).where(
                DocumentStatusHistory.submission_id == submission_id,
                DocumentStatusHistory.to_status == DocumentStatus.APROBADO.value,
            )
        )
        assert history is not None
        assert history.actor == "system"
        assert history.reason == AUTO_APPROVAL_REASON_ES
        assert "automáticamente" in history.reason

        # Validation event mirrors a reviewer approval but as system.
        event = db.scalar(
            select(ValidationEvent).where(
                ValidationEvent.submission_id == submission_id,
                ValidationEvent.event_type == "reviewer_decision",
            )
        )
        assert event is not None
        assert event.actor_type == "system"
        assert event.result == "approve"
        assert (event.payload or {}).get("source") == "auto_approval"

        # Audit row: system.auto_approved with the full evidence snapshot.
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_id == submission_id,
                AuditLog.action == "system.auto_approved",
            )
        )
        assert audit is not None
        assert audit.actor_type == "system"
        meta = audit.event_metadata or {}
        assert meta["confidence"] == pytest.approx(0.99)
        assert meta["confidence_source"] == "shadow"
        assert meta["authenticity_risk"] == "clean"
        assert meta["risk_reasons"] == []
        assert meta["tiers"] == {"triage": {"provider_id": "anthropic:haiku"}}
        assert meta["requirement_code"] == req_code
        assert req_code in meta["unlocked_requirement_codes"]
        assert meta["document_id"] is not None

        # Provider notification fired — same side effect a reviewer
        # approval emits — and its body carries the distinct wording.
        notif = db.scalar(
            select(ProviderNotification).where(
                ProviderNotification.submission_id == submission_id,
                ProviderNotification.notification_type == "document_approve",
            )
        )
        assert notif is not None
        assert "automáticamente" in notif.body
    finally:
        db.close()


def test_auto_approve_blocked_when_code_not_in_csv(monkeypatch, db_factory) -> None:
    submission_id, _req_code = _perfect_submission(db_factory)
    _enable_auto_approve(monkeypatch, codes="otro:codigo:distinto")

    outcome = _run_engine(db_factory, submission_id)
    assert outcome.attempted is False
    assert outcome.reason == "requirement_not_unlocked"


def test_auto_approve_blocked_below_min_confidence(monkeypatch, db_factory) -> None:
    submission_id, req_code = _perfect_submission(db_factory, shadow_confidence=0.96)
    _enable_auto_approve(monkeypatch, codes=req_code)

    outcome = _run_engine(db_factory, submission_id)
    assert outcome.attempted is False
    assert outcome.reason == "confidence_below_threshold"

    db = db_factory()
    try:
        assert (
            db.get(Submission, submission_id).status
            == DocumentStatus.PENDIENTE_REVISION.value
        )
    finally:
        db.close()


def test_auto_approve_blocked_when_risk_not_clean(monkeypatch, db_factory) -> None:
    submission_id, req_code = _perfect_submission(
        db_factory, authenticity_risk="suspicious"
    )
    _enable_auto_approve(monkeypatch, codes=req_code)

    outcome = _run_engine(db_factory, submission_id)
    assert outcome.attempted is False
    assert outcome.reason == "authenticity_not_clean"


def test_auto_approve_blocked_when_risk_unanalyzed(monkeypatch, db_factory) -> None:
    submission_id, req_code = _perfect_submission(db_factory, authenticity_risk=None)
    _enable_auto_approve(monkeypatch, codes=req_code)

    outcome = _run_engine(db_factory, submission_id)
    assert outcome.attempted is False
    assert outcome.reason == "authenticity_not_clean"


def test_auto_approve_blocked_by_medium_risk_reason(monkeypatch, db_factory) -> None:
    submission_id, req_code = _perfect_submission(
        db_factory,
        risk_reasons=[
            {
                "code": "llm_authenticity_concern",
                "severity": "medium",
                "detail_es": "IA: tipografía inconsistente.",
            }
        ],
    )
    _enable_auto_approve(monkeypatch, codes=req_code)

    outcome = _run_engine(db_factory, submission_id)
    assert outcome.attempted is False
    assert outcome.reason == "risk_reasons_present"


def test_auto_approve_allows_info_risk_reasons(monkeypatch, db_factory) -> None:
    """Info-severity reasons do not block (only medium/high do)."""
    submission_id, req_code = _perfect_submission(
        db_factory,
        risk_reasons=[
            {"code": "producer_unusual", "severity": "info", "detail_es": "Dato menor."}
        ],
    )
    _enable_auto_approve(monkeypatch, codes=req_code)

    outcome = _run_engine(db_factory, submission_id)
    assert outcome.approved is True


def test_auto_approve_blocked_for_non_recurring_cadence(
    monkeypatch, db_factory
) -> None:
    submission_id, req_code = _perfect_submission(db_factory, cadence="alta_inicial")
    _enable_auto_approve(monkeypatch, codes=req_code)

    outcome = _run_engine(db_factory, submission_id)
    assert outcome.attempted is False
    assert outcome.reason == "cadence_not_recurring"


def test_auto_approve_blocked_for_non_reviewable_status(
    monkeypatch, db_factory
) -> None:
    submission_id, req_code = _perfect_submission(
        db_factory, status_=DocumentStatus.APROBADO.value
    )
    _enable_auto_approve(monkeypatch, codes=req_code)

    outcome = _run_engine(db_factory, submission_id)
    assert outcome.attempted is False
    assert outcome.reason == "status_not_reviewable"


def test_auto_approve_blocked_without_inspection(monkeypatch, db_factory) -> None:
    submission_id, req_code = _seed_submission(
        db_factory, with_inspection=False, with_workspace=True
    )
    _enable_auto_approve(monkeypatch, codes=req_code)

    outcome = _run_engine(db_factory, submission_id)
    assert outcome.attempted is False
    assert outcome.reason == "no_inspection"


def test_maybe_auto_approve_never_raises(monkeypatch, db_factory) -> None:
    """An internal crash is captured and reported, never propagated."""
    submission_id, req_code = _perfect_submission(db_factory)
    _enable_auto_approve(monkeypatch, codes=req_code)

    db = db_factory()
    try:
        with patch(
            "app.services.auto_approval._maybe_auto_approve",
            side_effect=RuntimeError("boom"),
        ):
            outcome = maybe_auto_approve(db, submission_id)
    finally:
        db.close()
    assert outcome.approved is False
    assert outcome.reason == "error:RuntimeError"


# ---------------------------------------------------------------------------
# Shadow-runner wiring — hook placement + fail-open
# ---------------------------------------------------------------------------


@pytest.fixture
def shadow_db_setup(db_factory):
    """Point the shadow runner's SessionLocal at the test engine."""
    from app.db import session as session_module
    from app.services.document_analysis import shadow_runner as runner_module

    TestingSession = db_factory
    original_session_local = session_module.SessionLocal
    original_runner_session = runner_module.SessionLocal
    session_module.SessionLocal = TestingSession
    runner_module.SessionLocal = TestingSession
    yield
    session_module.SessionLocal = original_session_local
    runner_module.SessionLocal = original_runner_session


def _shadow_result(confidence: float):
    from app.services.document_analysis.base import AnalysisResult, DocumentSignals

    return AnalysisResult(
        provider_id="anthropic:test",
        prompt_version="base.v1",
        latency_ms=100,
        signals=DocumentSignals(
            detected_institution="sat",
            detected_document_type="csf",
            detected_rfcs=[],
            detected_dates=[],
            period_mentions=[],
            requirement_match_confidence=confidence,
            mismatch_reason=None,
            anomaly_codes=[],
        ),
        error=None,
    )


def test_persist_shadow_result_triggers_auto_approval(
    monkeypatch, db_factory, shadow_db_setup
) -> None:
    """End-to-end: the hook fires after the verdict merge and approves."""
    from app.services.document_analysis.shadow_runner import _persist_shadow_result

    submission_id, req_code = _perfect_submission(db_factory, shadow_confidence=None)
    _enable_auto_approve(monkeypatch, codes=req_code)

    db = db_factory()
    try:
        document_id = db.scalar(
            select(Document.id).where(Document.submission_id == submission_id)
        )
    finally:
        db.close()

    _persist_shadow_result(
        document_id=document_id,
        submission_id=submission_id,
        result=_shadow_result(0.99),
    )

    db = db_factory()
    try:
        sub = db.get(Submission, submission_id)
        assert sub.status == DocumentStatus.APROBADO.value
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_id == submission_id,
                AuditLog.action == "system.auto_approved",
            )
        )
        assert audit is not None
        # The shadow confidence written by THIS persist call is what
        # the evidence snapshot carries (post-merge, shadow-sourced).
        assert (audit.event_metadata or {})["confidence"] == pytest.approx(0.99)
        assert (audit.event_metadata or {})["confidence_source"] == "shadow"
    finally:
        db.close()


def test_persist_shadow_result_stays_dark_by_default(
    db_factory, shadow_db_setup
) -> None:
    """Flag off → shadow persists normally, nothing approved."""
    from app.services.document_analysis.shadow_runner import _persist_shadow_result

    submission_id, _req_code = _perfect_submission(db_factory, shadow_confidence=None)

    db = db_factory()
    try:
        document_id = db.scalar(
            select(Document.id).where(Document.submission_id == submission_id)
        )
    finally:
        db.close()

    _persist_shadow_result(
        document_id=document_id,
        submission_id=submission_id,
        result=_shadow_result(0.99),
    )

    db = db_factory()
    try:
        sub = db.get(Submission, submission_id)
        assert sub.status == DocumentStatus.PENDIENTE_REVISION.value
        insp = db.scalar(
            select(DocumentInspection).where(
                DocumentInspection.document_id == document_id
            )
        )
        assert insp.shadow_confidence == pytest.approx(0.99)
    finally:
        db.close()


def test_auto_approve_crash_never_breaks_shadow_persistence(
    monkeypatch, db_factory, shadow_db_setup
) -> None:
    """Fail-open: a hook crash leaves the shadow result fully persisted."""
    from app.services.document_analysis.shadow_runner import _persist_shadow_result

    submission_id, req_code = _perfect_submission(db_factory, shadow_confidence=None)
    _enable_auto_approve(monkeypatch, codes=req_code)

    db = db_factory()
    try:
        document_id = db.scalar(
            select(Document.id).where(Document.submission_id == submission_id)
        )
    finally:
        db.close()

    with patch(
        "app.services.auto_approval.maybe_auto_approve",
        side_effect=RuntimeError("boom"),
    ):
        _persist_shadow_result(
            document_id=document_id,
            submission_id=submission_id,
            result=_shadow_result(0.99),
        )

    db = db_factory()
    try:
        insp = db.scalar(
            select(DocumentInspection).where(
                DocumentInspection.document_id == document_id
            )
        )
        assert insp.shadow_provider_id == "anthropic:test"
        assert insp.shadow_confidence == pytest.approx(0.99)
        assert insp.shadow_completed_at is not None
        # And nothing was approved.
        sub = db.get(Submission, submission_id)
        assert sub.status == DocumentStatus.PENDIENTE_REVISION.value
    finally:
        db.close()
