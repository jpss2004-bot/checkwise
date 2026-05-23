"""Phase 6 / Slice 6B — renewal notification dispatcher.

DB-backed coverage of ``app.services.renewal_dispatch``. Tests pin:

* threshold computation across the locked cadence
  (30/14/7/0/-7/-14/-21/-28);
* idempotency under repeated dispatch on the same day;
* catch-up emit when multiple thresholds were missed;
* cycle reset when a new approved submission lands;
* skip reasons (``no_frequency``, ``no_anchor``, ``no_thresholds``);
* tenant isolation across workspaces;
* payload shape on both client and provider notifications.

SQLite in-memory + a small fixture set mirroring
``tests/test_evidence_slots.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants.statuses import DocumentStatus
from app.db.base import Base
from app.models import (
    Client,
    ClientNotification,
    Institution,
    Period,
    ProviderNotification,
    ProviderWorkspace,
    RenewalReminder,
    Requirement,
    RequirementVersion,
    Submission,
    Vendor,
    entities,  # noqa: F401 — register mappers
)
from app.services.renewal_dispatch import (
    ALL_THRESHOLDS,
    DispatchOutcome,
    dispatch_renewals_for_workspace,
    thresholds_crossed,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


SessionFactory = Callable[[], Session]


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
def workspace(db_factory: SessionFactory) -> Generator[ProviderWorkspace, None, None]:
    db = db_factory()
    try:
        client = Client(name="Cliente Renew")
        db.add(client)
        db.flush()
        vendor = Vendor(
            client_id=client.id,
            name="Vendor Renew",
            rfc="RNW260101AB1",
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()
        ws = ProviderWorkspace(
            client_id=client.id,
            vendor_id=vendor.id,
            persona_type="moral",
            display_name="Vendor Renew",
            access_token="token-renew",
        )
        db.add(ws)
        db.commit()
        ws_id = ws.id
    finally:
        db.close()

    db = db_factory()
    try:
        ws_obj = db.get(ProviderWorkspace, ws_id)
        assert ws_obj is not None
        yield ws_obj
    finally:
        db.close()


def _seed_institution(db: Session, code: str = "sat") -> Institution:
    inst = db.scalar(select(Institution).where(Institution.code == code))
    if inst is None:
        inst = Institution(code=code, name=code.upper())
        db.add(inst)
        db.flush()
    return inst


def _seed_requirement(
    db: Session, *, code: str, institution_code: str = "sat"
) -> tuple[Requirement, RequirementVersion]:
    inst = _seed_institution(db, institution_code)
    req = db.scalar(select(Requirement).where(Requirement.code == code))
    if req is not None:
        version = db.scalar(
            select(RequirementVersion).where(
                RequirementVersion.requirement_id == req.id
            )
        )
        assert version is not None
        return req, version
    req = Requirement(
        code=code,
        name=code,
        institution_id=inst.id,
        load_type="mensual",
        frequency="mensual",
        risk_level="medium",
        current_version=1,
    )
    db.add(req)
    db.flush()
    version = RequirementVersion(requirement_id=req.id, version=1)
    db.add(version)
    db.flush()
    return req, version


def _seed_onboarding_period(db: Session) -> Period:
    """Seed a synthetic onboarding period to satisfy the
    ``submissions.period_id`` NOT NULL constraint.

    Onboarding submissions do not carry a ``period_key`` (the
    dispatcher matches by ``requirement_code`` alone), but the DB
    schema still requires a non-null ``period_id`` on every
    submission row. One shared synthetic period works for every
    onboarding fixture insert.
    """
    code = "onb-test"
    period = db.scalar(select(Period).where(Period.code == code))
    if period is not None:
        return period
    period = Period(code=code, period_type="onboarding", period_key=code)
    db.add(period)
    db.flush()
    return period


def _seed_approved_submission(
    db_factory: SessionFactory,
    workspace: ProviderWorkspace,
    *,
    requirement_code: str,
    updated_at: datetime,
    institution_code: str = "sat",
) -> str:
    """Insert an approved onboarding submission for the workspace.

    Approved-only (the only kind that anchors a renewal cycle). The
    workflow service refreshes ``updated_at`` on transitions in
    production; here we set it directly to control the anchor date.
    """
    db = db_factory()
    try:
        req, version = _seed_requirement(
            db, code=f"req-{requirement_code}", institution_code=institution_code
        )
        period = _seed_onboarding_period(db)
        sub = Submission(
            client_id=workspace.client_id,
            vendor_id=workspace.vendor_id,
            institution_id=req.institution_id,
            requirement_id=req.id,
            requirement_version_id=version.id,
            period_id=period.id,
            load_type="mensual",
            status=DocumentStatus.APROBADO.value,
            requirement_code=requirement_code,
            period_key=None,
            created_at=updated_at,
            updated_at=updated_at,
        )
        db.add(sub)
        db.commit()
        return sub.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# thresholds_crossed — pure cadence math
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "days_remaining,expected",
    [
        (60, []),                                            # far out
        (31, []),                                            # one day before first nudge
        (30, [30]),                                          # first nudge
        (15, [30]),                                          # 30 already crossed, 14 not yet
        (14, [30, 14]),
        (8, [30, 14]),
        (7, [30, 14, 7]),
        (1, [30, 14, 7]),
        (0, [30, 14, 7, 0]),                                 # day of
        (-1, [30, 14, 7, 0]),
        (-7, [30, 14, 7, 0, -7]),
        (-28, [30, 14, 7, 0, -7, -14, -21, -28]),            # last weekly nag
        (-100, [30, 14, 7, 0, -7, -14, -21, -28]),           # past final nag — saturates
    ],
)
def test_thresholds_crossed(days_remaining: int, expected: list[int]) -> None:
    assert thresholds_crossed(days_remaining) == expected


def test_threshold_set_matches_locked_cadence() -> None:
    """Pin the 8-step cadence so a future tweak is a deliberate test edit."""
    assert ALL_THRESHOLDS == (30, 14, 7, 0, -7, -14, -21, -28)


# ---------------------------------------------------------------------------
# dispatch — happy path + idempotency
# ---------------------------------------------------------------------------


def _count(db: Session, model) -> int:
    return len(list(db.scalars(select(model))))


def _outcome_for(
    outcomes: list[DispatchOutcome], code: str
) -> DispatchOutcome:
    for o in outcomes:
        if o.requirement_code == code:
            return o
    raise AssertionError(f"No outcome for {code}")


def test_dispatch_fires_threshold_30_then_idempotent_on_same_day(
    db_factory: SessionFactory, workspace: ProviderWorkspace
) -> None:
    """CSF approved 60 days ago, dispatched today → fires threshold 30
    (due in 30 days). Second dispatch same day → no new rows.
    """
    today = date(2026, 6, 1)
    anchor_dt = datetime(2026, 6, 1) - timedelta(days=60)
    _seed_approved_submission(
        db_factory,
        workspace,
        requirement_code="ONB-CORP-M-002",
        updated_at=anchor_dt,
    )

    db = db_factory()
    try:
        outcomes = dispatch_renewals_for_workspace(db, workspace, today=today)
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        csf = _outcome_for(outcomes, "ONB-CORP-M-002")
        assert csf.thresholds_fired == [30]
        assert csf.thresholds_skipped_existing == []
        assert csf.skip_reason is None
        assert _count(db, RenewalReminder) == 1
        assert _count(db, ClientNotification) == 1
        assert _count(db, ProviderNotification) == 1

        reminder = db.scalar(select(RenewalReminder))
        assert reminder is not None
        assert reminder.severity == "yellow"
        assert reminder.threshold_days == 30
        assert reminder.requirement_code == "ONB-CORP-M-002"
        assert reminder.cycle_anchor_date == anchor_dt.date()

        client_notif = db.scalar(select(ClientNotification))
        assert client_notif is not None
        assert client_notif.notification_type == "renewal_due_soon"
        assert client_notif.severity == "yellow"
        assert client_notif.payload["threshold_days"] == 30
        assert client_notif.payload["requirement_code"] == "ONB-CORP-M-002"
        assert client_notif.payload["cycle_anchor_date"] == anchor_dt.date().isoformat()

        provider_notif = db.scalar(select(ProviderNotification))
        assert provider_notif is not None
        assert provider_notif.notification_type == "renewal_due_soon"
        assert provider_notif.severity == "yellow"
        assert provider_notif.payload["threshold_days"] == 30
    finally:
        db.close()

    # Second dispatch on the same day — no new rows.
    db = db_factory()
    try:
        outcomes2 = dispatch_renewals_for_workspace(db, workspace, today=today)
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        csf2 = _outcome_for(outcomes2, "ONB-CORP-M-002")
        assert csf2.thresholds_fired == []
        assert csf2.thresholds_skipped_existing == [30]
        assert _count(db, RenewalReminder) == 1
        assert _count(db, ClientNotification) == 1
        assert _count(db, ProviderNotification) == 1
    finally:
        db.close()


def test_dispatch_catches_up_when_multiple_thresholds_missed(
    db_factory: SessionFactory, workspace: ProviderWorkspace
) -> None:
    """First-ever dispatch on day-5 (due in 5 days) fires {30, 14, 7}
    in one pass. Each fires both a client + provider notification.
    """
    today = date(2026, 6, 1)
    anchor_dt = datetime(2026, 6, 1) - timedelta(days=85)  # due in 5 days
    _seed_approved_submission(
        db_factory,
        workspace,
        requirement_code="ONB-CORP-M-002",
        updated_at=anchor_dt,
    )

    db = db_factory()
    try:
        outcomes = dispatch_renewals_for_workspace(db, workspace, today=today)
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        csf = _outcome_for(outcomes, "ONB-CORP-M-002")
        assert sorted(csf.thresholds_fired) == [7, 14, 30]
        assert _count(db, RenewalReminder) == 3
        assert _count(db, ClientNotification) == 3
        assert _count(db, ProviderNotification) == 3
        # All three reminders share the same anchor.
        anchors = {
            r.cycle_anchor_date for r in db.scalars(select(RenewalReminder))
        }
        assert anchors == {anchor_dt.date()}
    finally:
        db.close()


def test_dispatch_red_severity_at_day_of_and_overdue(
    db_factory: SessionFactory, workspace: ProviderWorkspace
) -> None:
    """At day-of (days_remaining=0) the 0 threshold fires red. After
    one week overdue (days_remaining=-7) the -7 threshold fires red.
    """
    today = date(2026, 6, 1)
    # CSF approved exactly 90 days ago → due today.
    anchor_dt = datetime(2026, 6, 1) - timedelta(days=90)
    _seed_approved_submission(
        db_factory,
        workspace,
        requirement_code="ONB-CORP-M-002",
        updated_at=anchor_dt,
    )

    db = db_factory()
    try:
        dispatch_renewals_for_workspace(db, workspace, today=today)
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        # On day-of we cross 30, 14, 7, and 0 simultaneously (this is
        # also the first dispatch). The 0 row is red, the others yellow.
        reminders = list(db.scalars(select(RenewalReminder)))
        by_threshold = {r.threshold_days: r.severity for r in reminders}
        assert by_threshold == {30: "yellow", 14: "yellow", 7: "yellow", 0: "red"}

        # Notifications mirror.
        client_overdue = list(
            db.scalars(
                select(ClientNotification).where(
                    ClientNotification.notification_type == "renewal_overdue"
                )
            )
        )
        assert len(client_overdue) == 1
        assert client_overdue[0].severity == "red"
        assert client_overdue[0].payload["threshold_days"] == 0

        provider_overdue = list(
            db.scalars(
                select(ProviderNotification).where(
                    ProviderNotification.notification_type == "renewal_overdue"
                )
            )
        )
        assert len(provider_overdue) == 1
        assert provider_overdue[0].severity == "red"
    finally:
        db.close()

    # Advance 7 days — the -7 weekly nag should fire (and only that).
    later = date(2026, 6, 8)
    db = db_factory()
    try:
        outcomes = dispatch_renewals_for_workspace(db, workspace, today=later)
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        csf = _outcome_for(outcomes, "ONB-CORP-M-002")
        assert csf.thresholds_fired == [-7]
        thresholds = {
            r.threshold_days for r in db.scalars(select(RenewalReminder))
        }
        assert thresholds == {30, 14, 7, 0, -7}
    finally:
        db.close()


def test_dispatch_silent_past_final_weekly_nag(
    db_factory: SessionFactory, workspace: ProviderWorkspace
) -> None:
    """Once the -28 weekly nag has fired, no further emits occur even
    months later.
    """
    today = date(2026, 6, 1)
    # 200 days past the 90-day cadence → way past -28 already.
    anchor_dt = datetime(2026, 6, 1) - timedelta(days=290)
    _seed_approved_submission(
        db_factory,
        workspace,
        requirement_code="ONB-CORP-M-002",
        updated_at=anchor_dt,
    )

    db = db_factory()
    try:
        dispatch_renewals_for_workspace(db, workspace, today=today)
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        # All 8 thresholds fire at once on first run.
        assert _count(db, RenewalReminder) == 8
        assert _count(db, ClientNotification) == 8
        assert _count(db, ProviderNotification) == 8
    finally:
        db.close()

    # Run again much later — saturated, no new emits.
    db = db_factory()
    try:
        outcomes = dispatch_renewals_for_workspace(
            db, workspace, today=date(2027, 1, 1)
        )
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        csf = _outcome_for(outcomes, "ONB-CORP-M-002")
        assert csf.thresholds_fired == []
        # All 8 are in skipped_existing because they cross now too but
        # the unique constraint blocks the re-insert.
        assert len(csf.thresholds_skipped_existing) == 8
        assert _count(db, RenewalReminder) == 8
    finally:
        db.close()


def test_dispatch_resets_on_new_approved_submission(
    db_factory: SessionFactory, workspace: ProviderWorkspace
) -> None:
    """A fresh approval changes the anchor → a fresh cycle. The new
    cycle's threshold slots are independent of the prior cycle's, so
    they fire as the new cycle progresses.
    """
    today = date(2026, 6, 1)
    # Cycle 1: approved 60 days ago → due in 30 → threshold 30 fires.
    anchor1 = datetime(2026, 6, 1) - timedelta(days=60)
    _seed_approved_submission(
        db_factory,
        workspace,
        requirement_code="ONB-CORP-M-002",
        updated_at=anchor1,
    )
    db = db_factory()
    try:
        dispatch_renewals_for_workspace(db, workspace, today=today)
        db.commit()
    finally:
        db.close()

    # Cycle 2: provider re-uploads and gets approved today. The new
    # current_submission_for_slot returns the newer row (latest by
    # created_at when no supersedes link), so the anchor shifts.
    anchor2_dt = datetime(2026, 6, 1)
    db = db_factory()
    try:
        req, version = _seed_requirement(
            db, code="req-ONB-CORP-M-002", institution_code="sat"
        )
        period = _seed_onboarding_period(db)
        new_sub = Submission(
            client_id=workspace.client_id,
            vendor_id=workspace.vendor_id,
            institution_id=req.institution_id,
            requirement_id=req.id,
            requirement_version_id=version.id,
            period_id=period.id,
            load_type="mensual",
            status=DocumentStatus.APROBADO.value,
            requirement_code="ONB-CORP-M-002",
            period_key=None,
            created_at=anchor2_dt,
            updated_at=anchor2_dt,
        )
        db.add(new_sub)
        db.commit()
    finally:
        db.close()

    # 60 days into the new cycle.
    later = date(2026, 6, 1) + timedelta(days=60)
    db = db_factory()
    try:
        outcomes = dispatch_renewals_for_workspace(db, workspace, today=later)
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        csf = _outcome_for(outcomes, "ONB-CORP-M-002")
        # Threshold 30 fires NEW under the new anchor (different
        # cycle_anchor_date in the unique key → no collision).
        assert csf.thresholds_fired == [30]
        anchors = {
            r.cycle_anchor_date for r in db.scalars(select(RenewalReminder))
        }
        assert anchor1.date() in anchors
        assert anchor2_dt.date() in anchors
        assert len(anchors) == 2
        # Total reminder rows: 1 (cycle1, threshold 30) + 1 (cycle2,
        # threshold 30) = 2.
        assert _count(db, RenewalReminder) == 2
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Skip reasons
# ---------------------------------------------------------------------------


def test_dispatch_no_anchor_when_no_approved_submission(
    db_factory: SessionFactory, workspace: ProviderWorkspace
) -> None:
    """No approved CSF → renewal cycle has not started → skip_reason
    'no_anchor' on every renewal-bearing requirement; nothing emits.
    """
    db = db_factory()
    try:
        outcomes = dispatch_renewals_for_workspace(
            db, workspace, today=date(2026, 6, 1)
        )
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        csf = _outcome_for(outcomes, "ONB-CORP-M-002")
        assert csf.skip_reason == "no_anchor"
        assert csf.thresholds_fired == []
        repse = _outcome_for(outcomes, "ONB-REPSE-001")
        assert repse.skip_reason == "no_anchor"
        patr = _outcome_for(outcomes, "ONB-PATR-001")
        assert patr.skip_reason == "no_anchor"
        assert _count(db, RenewalReminder) == 0
        assert _count(db, ClientNotification) == 0
        assert _count(db, ProviderNotification) == 0
    finally:
        db.close()


def test_dispatch_no_frequency_for_one_time_onboarding_rows(
    db_factory: SessionFactory, workspace: ProviderWorkspace
) -> None:
    """Onboarding requirements without ``renewal_frequency_days``
    (contract, acta constitutiva, etc.) get skip_reason 'no_frequency'.
    """
    db = db_factory()
    try:
        outcomes = dispatch_renewals_for_workspace(
            db, workspace, today=date(2026, 6, 1)
        )
        db.commit()
    finally:
        db.close()

    # Contract / acta / etc. all carry no renewal_frequency_days.
    contract = _outcome_for(outcomes, "ONB-CONT-001")
    assert contract.skip_reason == "no_frequency"


def test_dispatch_no_thresholds_when_far_from_due(
    db_factory: SessionFactory, workspace: ProviderWorkspace
) -> None:
    """Approved 1 day ago, REPSE 1095-day cadence → due in 1094 days
    → no thresholds crossed → skip_reason 'no_thresholds'.
    """
    today = date(2026, 6, 1)
    anchor_dt = datetime(2026, 6, 1) - timedelta(days=1)
    _seed_approved_submission(
        db_factory,
        workspace,
        requirement_code="ONB-REPSE-001",
        updated_at=anchor_dt,
        institution_code="stps_repse",
    )

    db = db_factory()
    try:
        outcomes = dispatch_renewals_for_workspace(db, workspace, today=today)
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        repse = _outcome_for(outcomes, "ONB-REPSE-001")
        assert repse.skip_reason == "no_thresholds"
        assert repse.cycle_anchor_date == anchor_dt.date()
        assert repse.due_date == anchor_dt.date() + timedelta(days=1095)
        # No emits.
        renewal_due_soon = list(
            db.scalars(
                select(ClientNotification).where(
                    ClientNotification.notification_type == "renewal_due_soon"
                )
            )
        )
        assert renewal_due_soon == []
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_dispatch_isolates_workspaces(
    db_factory: SessionFactory, workspace: ProviderWorkspace
) -> None:
    """A reminder for workspace A does not block workspace B from
    firing the same threshold under its own anchor. Workspace B has
    no approved submissions so it should emit nothing regardless of
    what workspace A emits.
    """
    ws_a_id = workspace.id
    ws_a_client_id = workspace.client_id

    # Set up a second workspace.
    db = db_factory()
    try:
        client_b = Client(name="Cliente B")
        db.add(client_b)
        db.flush()
        vendor_b = Vendor(
            client_id=client_b.id,
            name="Vendor B",
            rfc="VBB260101AB1",
            persona_type="moral",
        )
        db.add(vendor_b)
        db.flush()
        ws_b = ProviderWorkspace(
            client_id=client_b.id,
            vendor_id=vendor_b.id,
            persona_type="moral",
            display_name="Vendor B",
            access_token="token-b",
        )
        db.add(ws_b)
        db.commit()
        ws_b_id = ws_b.id
        ws_b_client_id = ws_b.client_id
    finally:
        db.close()

    today = date(2026, 6, 1)
    anchor_dt = datetime(2026, 6, 1) - timedelta(days=60)
    _seed_approved_submission(
        db_factory,
        workspace,
        requirement_code="ONB-CORP-M-002",
        updated_at=anchor_dt,
    )

    # Dispatch each workspace in its own session — mirrors the CLI's
    # per-workspace commit boundary and keeps each ORM object bound
    # to exactly one session.
    db = db_factory()
    try:
        ws_a_obj = db.get(ProviderWorkspace, ws_a_id)
        assert ws_a_obj is not None
        dispatch_renewals_for_workspace(db, ws_a_obj, today=today)
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        ws_b_obj = db.get(ProviderWorkspace, ws_b_id)
        assert ws_b_obj is not None
        dispatch_renewals_for_workspace(db, ws_b_obj, today=today)
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        # Workspace A: 1 reminder (threshold 30).
        reminders_a = list(
            db.scalars(
                select(RenewalReminder).where(
                    RenewalReminder.workspace_id == ws_a_id
                )
            )
        )
        assert len(reminders_a) == 1
        assert reminders_a[0].threshold_days == 30

        # Workspace B: 0 reminders — it has no approved CSF.
        reminders_b = list(
            db.scalars(
                select(RenewalReminder).where(
                    RenewalReminder.workspace_id == ws_b_id
                )
            )
        )
        assert reminders_b == []

        # Workspace A's client got one notification.
        notifs_a = list(
            db.scalars(
                select(ClientNotification).where(
                    ClientNotification.client_id == ws_a_client_id
                )
            )
        )
        assert len(notifs_a) == 1

        # Workspace B's client got nothing.
        notifs_b = list(
            db.scalars(
                select(ClientNotification).where(
                    ClientNotification.client_id == ws_b_client_id
                )
            )
        )
        assert notifs_b == []
    finally:
        db.close()
