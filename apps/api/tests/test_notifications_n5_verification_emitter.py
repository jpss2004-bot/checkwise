"""Phase 7 / Slice N5 — verification lifecycle emitter (shadow mode).

Tests pin:

  * ``submission.received`` and ``submission.in_review`` are info-tier
    and fire to provider_owner only (no client_admin row);
  * reviewer decisions map cleanly to catalog event types
    (approve → submission.approved, reject → submission.rejected,
    request_clarification → submission.clarification_requested);
  * ``submission.approved`` fans out to both provider + client_admin;
  * critical decisions (rejected / clarification) fire would_send on
    email for the provider regardless of preference;
  * ``mark_exception`` action returns ``None`` and writes nothing;
  * dedupe_key includes the action so a flipped decision (reject →
    approve) produces a fresh dispatch row;
  * the same call twice is fully deduped on replay.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants.statuses import DocumentStatus, ReviewerAction
from app.db.base import Base
from app.models import (
    Client,
    Institution,
    Membership,
    NotificationDispatch,
    Organization,
    Period,
    ProviderWorkspace,
    Requirement,
    RequirementVersion,
    Submission,
    User,
    Vendor,
    entities,  # noqa: F401 — register mappers
)
from app.models.entities import utc_now
from app.services.notifications import (
    REVIEWER_ACTION_EVENT_TYPE,
    emit_reviewer_decision,
    emit_submission_in_review,
    emit_submission_received,
)

SessionFactory = Callable[[], Session]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_factory() -> SessionFactory:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def submission_setup(
    db_factory: SessionFactory,
) -> Generator[dict, None, None]:
    """Seed a workspace + submission with both recipients resolvable.

    Returns ``{"submission_id", "provider_user_id", "client_admin_id",
    "workspace_id"}``.
    """
    db = db_factory()
    try:
        # Tenant + client_admin User.
        client = Client(name="Cliente Verif")
        db.add(client)
        db.flush()
        client_org = Organization(
            name="Cliente Verif", kind="client", client_id=client.id
        )
        db.add(client_org)
        db.flush()
        admin_user = User(
            email="admin@verif.mx",
            full_name="Verif Admin",
            status="active",
            contact_preference="both",
            phone_e164="+525500000001",
            phone_verified_at=utc_now(),
        )
        db.add(admin_user)
        db.flush()
        db.add(
            Membership(
                user_id=admin_user.id,
                organization_id=client_org.id,
                role="client_admin",
                status="active",
            )
        )

        provider_user = User(
            email="provider@verif.mx",
            full_name="Verif Provider",
            status="active",
            contact_preference="both",
            phone_e164="+525500000002",
            phone_verified_at=utc_now(),
        )
        db.add(provider_user)
        db.flush()

        vendor = Vendor(
            client_id=client.id,
            name="Vendor Verif",
            rfc="VRF260101AB1",
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()

        workspace = ProviderWorkspace(
            client_id=client.id,
            vendor_id=vendor.id,
            persona_type="moral",
            display_name="Vendor Verif",
            access_token="token-verif",
            owner_user_id=provider_user.id,
        )
        db.add(workspace)
        db.flush()

        institution = Institution(code="sat", name="SAT")
        db.add(institution)
        db.flush()
        req = Requirement(
            code="req-verif",
            name="Documento Verif",
            institution_id=institution.id,
            load_type="mensual",
            frequency="mensual",
            risk_level="medium",
            current_version=1,
        )
        db.add(req)
        db.flush()
        rv = RequirementVersion(requirement_id=req.id, version=1)
        db.add(rv)
        db.flush()
        period = Period(
            code="onb-verif", period_type="onboarding", period_key="onb-verif"
        )
        db.add(period)
        db.flush()

        submission = Submission(
            client_id=client.id,
            vendor_id=vendor.id,
            institution_id=institution.id,
            requirement_id=req.id,
            requirement_version_id=rv.id,
            period_id=period.id,
            load_type="mensual",
            status=DocumentStatus.PENDIENTE_REVISION.value,
            requirement_code="req-verif-canon",
            period_key="2026-M05",
            created_at=datetime(2026, 5, 26),
            updated_at=datetime(2026, 5, 26),
        )
        db.add(submission)
        db.commit()
        ctx = {
            "submission_id": submission.id,
            "provider_user_id": provider_user.id,
            "client_admin_id": admin_user.id,
            "workspace_id": workspace.id,
        }
    finally:
        db.close()
    yield ctx


# ---------------------------------------------------------------------------
# Action map sanity
# ---------------------------------------------------------------------------


def test_action_map_covers_three_supported_reviewer_actions() -> None:
    assert set(REVIEWER_ACTION_EVENT_TYPE.keys()) == {
        ReviewerAction.APPROVE.value,
        ReviewerAction.REJECT.value,
        ReviewerAction.REQUEST_CLARIFICATION.value,
    }


def test_action_map_skips_mark_exception_intentionally() -> None:
    assert ReviewerAction.MARK_EXCEPTION.value not in REVIEWER_ACTION_EVENT_TYPE


# ---------------------------------------------------------------------------
# submission.received (info, provider_owner only)
# ---------------------------------------------------------------------------


def test_received_fires_provider_only(
    db_factory: SessionFactory, submission_setup: dict
) -> None:
    db = db_factory()
    try:
        submission = db.get(Submission, submission_setup["submission_id"])
        assert submission is not None
        result = emit_submission_received(db, submission=submission)
        db.commit()
    finally:
        db.close()

    assert result is not None
    assert {o.role for o in result.outcomes} == {"provider_owner"}

    db = db_factory()
    try:
        rows = db.execute(select(NotificationDispatch)).scalars().all()
    finally:
        db.close()

    assert len(rows) == 1
    row = rows[0]
    assert row.event_type == "submission.received"
    assert row.severity == "info"
    assert row.recipient_role == "provider_owner"
    assert row.user_id == submission_setup["provider_user_id"]
    # info-tier — no outbound channel even though prefs allow.
    assert row.email_status == "would_skip"
    assert row.email_reason == "info_tier"
    assert row.whatsapp_status == "would_skip"
    assert row.whatsapp_reason == "info_tier"


def test_in_review_fires_provider_only(
    db_factory: SessionFactory, submission_setup: dict
) -> None:
    db = db_factory()
    try:
        submission = db.get(Submission, submission_setup["submission_id"])
        assert submission is not None
        emit_submission_in_review(db, submission=submission)
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        rows = db.execute(select(NotificationDispatch)).scalars().all()
    finally:
        db.close()

    assert len(rows) == 1
    assert rows[0].event_type == "submission.in_review"
    assert rows[0].severity == "info"


# ---------------------------------------------------------------------------
# Reviewer decisions
# ---------------------------------------------------------------------------


def test_approve_fans_out_to_provider_and_client_admin(
    db_factory: SessionFactory, submission_setup: dict
) -> None:
    db = db_factory()
    try:
        submission = db.get(Submission, submission_setup["submission_id"])
        result = emit_reviewer_decision(
            db, submission=submission, action="approve"
        )
        db.commit()
    finally:
        db.close()

    assert result is not None
    assert {o.role for o in result.outcomes} == {
        "provider_owner",
        "client_admin",
    }

    db = db_factory()
    try:
        rows = db.execute(select(NotificationDispatch)).scalars().all()
    finally:
        db.close()
    assert len(rows) == 2
    for row in rows:
        assert row.event_type == "submission.approved"
        assert row.severity == "important"
        # important + pref=both + verified phone → would_send on both.
        assert row.email_status == "would_send"
        assert row.whatsapp_status == "would_send"


def test_reject_fires_provider_only_critical(
    db_factory: SessionFactory, submission_setup: dict
) -> None:
    db = db_factory()
    try:
        submission = db.get(Submission, submission_setup["submission_id"])
        result = emit_reviewer_decision(
            db,
            submission=submission,
            action="reject",
            reason="Falta firma del representante legal.",
        )
        db.commit()
    finally:
        db.close()

    assert result is not None
    assert {o.role for o in result.outcomes} == {"provider_owner"}

    db = db_factory()
    try:
        row = db.scalar(select(NotificationDispatch))
    finally:
        db.close()
    assert row is not None
    assert row.event_type == "submission.rejected"
    assert row.severity == "critical"
    assert row.payload["reason"] == "Falta firma del representante legal."
    # Critical email is unmuteable.
    assert row.email_status == "would_send"


def test_clarification_request_is_critical(
    db_factory: SessionFactory, submission_setup: dict
) -> None:
    db = db_factory()
    try:
        submission = db.get(Submission, submission_setup["submission_id"])
        emit_reviewer_decision(
            db,
            submission=submission,
            action="request_clarification",
            reason="¿Es el comprobante del mes correcto?",
        )
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        row = db.scalar(select(NotificationDispatch))
    finally:
        db.close()
    assert row is not None
    assert row.event_type == "submission.clarification_requested"
    assert row.severity == "critical"


def test_mark_exception_returns_none_and_writes_nothing(
    db_factory: SessionFactory, submission_setup: dict
) -> None:
    db = db_factory()
    try:
        submission = db.get(Submission, submission_setup["submission_id"])
        result = emit_reviewer_decision(
            db, submission=submission, action="mark_exception"
        )
        db.commit()
    finally:
        db.close()

    assert result is None
    db = db_factory()
    try:
        rows = db.execute(select(NotificationDispatch)).scalars().all()
    finally:
        db.close()
    assert rows == []


def test_unknown_action_returns_none(
    db_factory: SessionFactory, submission_setup: dict
) -> None:
    db = db_factory()
    try:
        submission = db.get(Submission, submission_setup["submission_id"])
        result = emit_reviewer_decision(
            db, submission=submission, action="reopen"
        )
    finally:
        db.close()
    assert result is None


# ---------------------------------------------------------------------------
# Dedupe semantics
# ---------------------------------------------------------------------------


def test_same_action_twice_is_deduped(
    db_factory: SessionFactory, submission_setup: dict
) -> None:
    """A reviewer-decision endpoint retried after a transient failure
    must not double-emit."""
    db = db_factory()
    try:
        submission = db.get(Submission, submission_setup["submission_id"])
        emit_reviewer_decision(db, submission=submission, action="approve")
        db.commit()
    finally:
        db.close()
    db = db_factory()
    try:
        submission = db.get(Submission, submission_setup["submission_id"])
        second = emit_reviewer_decision(
            db, submission=submission, action="approve"
        )
        db.commit()
    finally:
        db.close()

    assert second is not None
    assert second.queued == 0
    assert second.deduped == 2

    db = db_factory()
    try:
        rows = db.execute(select(NotificationDispatch)).scalars().all()
    finally:
        db.close()
    assert len(rows) == 2  # only the first emit's rows


def test_flipped_decision_emits_fresh_envelope(
    db_factory: SessionFactory, submission_setup: dict
) -> None:
    """A reviewer who rejects then approves the same submission gets
    one envelope under each action — the dedupe_key includes the
    action, so the second decision is not silently dropped."""
    db = db_factory()
    try:
        submission = db.get(Submission, submission_setup["submission_id"])
        emit_reviewer_decision(db, submission=submission, action="reject")
        db.commit()
    finally:
        db.close()
    db = db_factory()
    try:
        submission = db.get(Submission, submission_setup["submission_id"])
        emit_reviewer_decision(db, submission=submission, action="approve")
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        rows = db.execute(select(NotificationDispatch)).scalars().all()
    finally:
        db.close()
    by_event = {r.event_type for r in rows}
    assert by_event == {"submission.rejected", "submission.approved"}


# ---------------------------------------------------------------------------
# Workspace resolution
# ---------------------------------------------------------------------------


def test_no_workspace_returns_none(db_factory: SessionFactory) -> None:
    """A submission whose (client_id, vendor_id) pair has no
    workspace short-circuits to None — the legacy email helper does
    the same, and this is the cleanest way to keep tests stable
    when a fixture forgets to seed a workspace."""
    db = db_factory()
    try:
        client = Client(name="Cliente Sin Workspace")
        db.add(client)
        db.flush()
        vendor = Vendor(
            client_id=client.id,
            name="Vendor",
            rfc="VND260101AB1",
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()
        institution = Institution(code="sat", name="SAT")
        db.add(institution)
        db.flush()
        req = Requirement(
            code="req-orphan",
            name="r",
            institution_id=institution.id,
            load_type="mensual",
            frequency="mensual",
            risk_level="medium",
            current_version=1,
        )
        db.add(req)
        db.flush()
        rv = RequirementVersion(requirement_id=req.id, version=1)
        db.add(rv)
        db.flush()
        period = Period(
            code="orphan", period_type="onboarding", period_key="orphan"
        )
        db.add(period)
        db.flush()
        submission = Submission(
            client_id=client.id,
            vendor_id=vendor.id,
            institution_id=institution.id,
            requirement_id=req.id,
            requirement_version_id=rv.id,
            period_id=period.id,
            load_type="mensual",
            status=DocumentStatus.PENDIENTE_REVISION.value,
            requirement_code="x",
            period_key=None,
            created_at=datetime(2026, 5, 26),
            updated_at=datetime(2026, 5, 26),
        )
        db.add(submission)
        db.commit()
        sub_id = submission.id
    finally:
        db.close()

    db = db_factory()
    try:
        submission = db.get(Submission, sub_id)
        result = emit_reviewer_decision(
            db, submission=submission, action="approve"
        )
    finally:
        db.close()
    assert result is None
