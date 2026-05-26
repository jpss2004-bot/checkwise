"""Phase 7 / Slice N4 — shadow renewal emitter.

The emitter produces envelopes and writes the new
``notification_dispatch`` + ``audit_log`` rows. It does NOT touch
``ClientNotification``, ``ProviderNotification``, ``RenewalReminder``,
email, or WhatsApp — the legacy dispatcher remains the user-visible
authoritative path until a follow-up slice flips the cron.

Tests pin:

  * threshold → event_type map is in lockstep with
    ``ALL_THRESHOLDS`` (so cadence + catalog never silently drift);
  * dispatch row severity per crossing matches the catalog
    (t-30 → info, t-7 → important, t-0+ → critical);
  * shadow channel statuses encode the routing decision —
    ``would_send`` / ``would_skip`` with the canonical skip reason;
  * idempotency: re-running the emitter on the same day adds no
    new dispatch rows.
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
    SKIP_INFO_TIER,
    SKIP_PHONE_NOT_VERIFIED,
    THRESHOLD_TO_EVENT_TYPE,
    emit_renewals_for_workspace,
)
from app.services.renewal_dispatch import ALL_THRESHOLDS

SessionFactory = Callable[[], Session]


# ---------------------------------------------------------------------------
# Fixtures (mirror tests/test_renewal_dispatch.py to keep parity tight)
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


def _seed_users_for_workspace(
    db_factory: SessionFactory,
    *,
    client_id: str,
    with_provider_owner: bool = True,
    with_client_admin: bool = True,
    contact_preference: str = "both",
    phone_verified: bool = True,
) -> tuple[str | None, str | None]:
    """Insert provider-owner + client_admin Users with realistic prefs.

    Returns ``(provider_user_id, client_admin_id)``. Either may be
    ``None`` if the caller asked to skip that role.
    """
    db = db_factory()
    try:
        client_org = Organization(
            name="Client Co", kind="client", client_id=client_id
        )
        provider_org = Organization(name="LegalShelf", kind="internal")
        db.add_all([client_org, provider_org])
        db.flush()

        provider_id: str | None = None
        admin_id: str | None = None

        if with_provider_owner:
            provider_user = User(
                email="provider@ws.mx",
                full_name="Provider Owner",
                status="active",
                contact_preference=contact_preference,
                phone_e164="+525500000001" if phone_verified else None,
                phone_verified_at=utc_now() if phone_verified else None,
            )
            db.add(provider_user)
            db.flush()
            provider_id = provider_user.id

        if with_client_admin:
            admin_user = User(
                email="admin@client.mx",
                full_name="Client Admin",
                status="active",
                contact_preference=contact_preference,
                phone_e164="+525500000002" if phone_verified else None,
                phone_verified_at=utc_now() if phone_verified else None,
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
            admin_id = admin_user.id

        db.commit()
        return provider_id, admin_id
    finally:
        db.close()


@pytest.fixture
def workspace(
    db_factory: SessionFactory,
) -> Generator[ProviderWorkspace, None, None]:
    db = db_factory()
    try:
        client = Client(name="Cliente Emit")
        db.add(client)
        db.flush()
        vendor = Vendor(
            client_id=client.id,
            name="Vendor Emit",
            rfc="EMT260101AB1",
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()

        client_id = client.id

        # The provider user lives on the LegalShelf side conceptually
        # but is created here so workspace.owner_user_id is populated
        # — this is the state after N8 wires onboarding alta.
        provider_user_id, _ = _seed_users_for_workspace(
            db_factory, client_id=client_id
        )

        ws = ProviderWorkspace(
            client_id=client_id,
            vendor_id=vendor.id,
            persona_type="moral",
            display_name="Vendor Emit",
            access_token="token-emit",
            owner_user_id=provider_user_id,
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


def _seed_onboarding_period(db: Session) -> Period:
    code = "onb-test"
    period = db.scalar(select(Period).where(Period.code == code))
    if period is not None:
        return period
    period = Period(code=code, period_type="onboarding", period_key=code)
    db.add(period)
    db.flush()
    return period


def _seed_requirement(
    db: Session, *, code: str, institution_code: str = "sat"
) -> tuple[Requirement, RequirementVersion]:
    inst = db.scalar(select(Institution).where(Institution.code == institution_code))
    if inst is None:
        inst = Institution(code=institution_code, name=institution_code.upper())
        db.add(inst)
        db.flush()
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


def _seed_approved_submission(
    db_factory: SessionFactory,
    workspace: ProviderWorkspace,
    *,
    requirement_code: str,
    updated_at: datetime,
) -> None:
    db = db_factory()
    try:
        req, version = _seed_requirement(db, code=f"req-{requirement_code}")
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
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Threshold/catalog parity
# ---------------------------------------------------------------------------


def test_threshold_map_in_lockstep_with_legacy_cadence() -> None:
    """Cadence and catalog stay aligned — fail loud if either edits."""
    assert set(THRESHOLD_TO_EVENT_TYPE.keys()) == set(ALL_THRESHOLDS)


def test_event_types_resolve_for_every_threshold() -> None:
    """Catalog has a row for each mapped event_type."""
    from app.services.notifications.catalog import EVENT_TYPES

    for event_type in THRESHOLD_TO_EVENT_TYPE.values():
        assert event_type in EVENT_TYPES, f"{event_type} missing from catalog"


# ---------------------------------------------------------------------------
# Emit happy path — one threshold fires, dispatch rows materialize
# ---------------------------------------------------------------------------


def test_emit_writes_dispatch_rows_for_both_recipients(
    db_factory: SessionFactory, workspace: ProviderWorkspace
) -> None:
    """CSF approved 60 days ago, emit today → threshold 30 fires for
    both provider and client_admin recipients."""
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
        outcomes = emit_renewals_for_workspace(db, workspace, today=today)
        db.commit()
    finally:
        db.close()

    by_code = {o.requirement_code: o for o in outcomes}
    csf = by_code["ONB-CORP-M-002"]
    assert csf.thresholds_queued == [30]
    assert csf.skip_reason is None

    db = db_factory()
    try:
        rows = db.execute(select(NotificationDispatch)).scalars().all()
    finally:
        db.close()

    # One row per recipient (provider_owner + client_admin) per
    # crossing — 2 rows total.
    assert len(rows) == 2
    by_role = {r.recipient_role: r for r in rows}
    assert set(by_role) == {"provider_owner", "client_admin"}
    for row in rows:
        assert row.event_type == "renewal.threshold.t-30"
        assert row.severity == "info"
        assert row.dedupe_key.endswith(":t:30")


# ---------------------------------------------------------------------------
# Severity per threshold matches catalog
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "days_since_anchor,expected_threshold,expected_severity",
    [
        (60, 30, "info"),      # 30d before due
        (76, 14, "info"),      # 14d before due
        (83, 7, "important"),  # 7d before due
        (90, 0, "critical"),   # day of
        (97, -7, "critical"),  # 7d overdue
    ],
)
def test_dispatch_row_severity_per_threshold(
    db_factory: SessionFactory,
    workspace: ProviderWorkspace,
    days_since_anchor: int,
    expected_threshold: int,
    expected_severity: str,
) -> None:
    today = date(2026, 6, 1)
    anchor_dt = datetime(2026, 6, 1) - timedelta(days=days_since_anchor)
    _seed_approved_submission(
        db_factory,
        workspace,
        requirement_code="ONB-CORP-M-002",
        updated_at=anchor_dt,
    )

    db = db_factory()
    try:
        emit_renewals_for_workspace(db, workspace, today=today)
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        rows = (
            db.execute(
                select(NotificationDispatch)
                .where(
                    NotificationDispatch.dedupe_key.endswith(
                        f":t:{expected_threshold}"
                    )
                )
            )
            .scalars()
            .all()
        )
    finally:
        db.close()

    assert rows, f"no dispatch row for threshold {expected_threshold}"
    for row in rows:
        assert row.severity == expected_severity


# ---------------------------------------------------------------------------
# Shadow channel decisions — would_send / would_skip
# ---------------------------------------------------------------------------


def test_shadow_decision_info_tier_is_in_app_only(
    db_factory: SessionFactory, workspace: ProviderWorkspace
) -> None:
    """The de-spam decision lands on the dispatch row at N4."""
    today = date(2026, 6, 1)
    anchor_dt = datetime(2026, 6, 1) - timedelta(days=60)  # → t-30, info
    _seed_approved_submission(
        db_factory,
        workspace,
        requirement_code="ONB-CORP-M-002",
        updated_at=anchor_dt,
    )

    db = db_factory()
    try:
        emit_renewals_for_workspace(db, workspace, today=today)
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        rows = db.execute(select(NotificationDispatch)).scalars().all()
    finally:
        db.close()

    for row in rows:
        assert row.email_status == "would_skip"
        assert row.email_reason == SKIP_INFO_TIER
        assert row.whatsapp_status == "would_skip"
        assert row.whatsapp_reason == SKIP_INFO_TIER


def test_shadow_decision_critical_with_verified_phone_would_send_all(
    db_factory: SessionFactory, workspace: ProviderWorkspace
) -> None:
    today = date(2026, 6, 1)
    anchor_dt = datetime(2026, 6, 1) - timedelta(days=90)  # → t-0, critical
    _seed_approved_submission(
        db_factory,
        workspace,
        requirement_code="ONB-CORP-M-002",
        updated_at=anchor_dt,
    )

    db = db_factory()
    try:
        emit_renewals_for_workspace(db, workspace, today=today)
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        rows = (
            db.execute(
                select(NotificationDispatch).where(
                    NotificationDispatch.event_type == "renewal.threshold.t-0"
                )
            )
            .scalars()
            .all()
        )
    finally:
        db.close()

    assert len(rows) == 2  # provider + client_admin
    for row in rows:
        assert row.email_status == "would_send"
        assert row.email_reason is None
        assert row.whatsapp_status == "would_send"
        assert row.whatsapp_reason is None


def test_shadow_decision_records_phone_not_verified(
    db_factory: SessionFactory,
) -> None:
    """User with pref=both but no verified phone → would_skip on WA."""
    # Build a workspace whose owner has no verified phone — distinct
    # from the module-level ``workspace`` fixture which always seeds
    # verified users.
    db = db_factory()
    try:
        client = Client(name="Cliente Unverified")
        db.add(client)
        db.flush()
        vendor = Vendor(
            client_id=client.id,
            name="Vendor Unverified",
            rfc="UNV260101AB1",
            persona_type="moral",
        )
        db.add(vendor)
        db.commit()
        client_id = client.id
    finally:
        db.close()

    provider_id, _ = _seed_users_for_workspace(
        db_factory,
        client_id=client_id,
        phone_verified=False,
        contact_preference="both",
    )

    db = db_factory()
    try:
        ws = ProviderWorkspace(
            client_id=client_id,
            vendor_id=db.scalar(
                select(Vendor.id).where(Vendor.client_id == client_id)
            ),
            persona_type="moral",
            display_name="Vendor Unverified",
            access_token="token-unverified",
            owner_user_id=provider_id,
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
    finally:
        db.close()

    anchor_dt = datetime(2026, 6, 1) - timedelta(days=90)  # → t-0, critical
    _seed_approved_submission(
        db_factory,
        ws_obj,
        requirement_code="ONB-CORP-M-002",
        updated_at=anchor_dt,
    )

    db = db_factory()
    try:
        emit_renewals_for_workspace(db, ws_obj, today=date(2026, 6, 1))
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        row = db.scalar(
            select(NotificationDispatch).where(
                NotificationDispatch.event_type == "renewal.threshold.t-0",
                NotificationDispatch.recipient_role == "provider_owner",
            )
        )
    finally:
        db.close()

    assert row is not None
    # Email still fires for critical (unmuteable).
    assert row.email_status == "would_send"
    # WhatsApp blocked by phone not verified.
    assert row.whatsapp_status == "would_skip"
    assert row.whatsapp_reason == SKIP_PHONE_NOT_VERIFIED


# ---------------------------------------------------------------------------
# Idempotency under replay
# ---------------------------------------------------------------------------


def test_emit_is_idempotent_on_replay(
    db_factory: SessionFactory, workspace: ProviderWorkspace
) -> None:
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
        first = emit_renewals_for_workspace(db, workspace, today=today)
        db.commit()
    finally:
        db.close()
    db = db_factory()
    try:
        second = emit_renewals_for_workspace(db, workspace, today=today)
        db.commit()
    finally:
        db.close()

    def find(out, code):
        for o in out:
            if o.requirement_code == code:
                return o
        raise AssertionError(code)

    first_csf = find(first, "ONB-CORP-M-002")
    second_csf = find(second, "ONB-CORP-M-002")
    assert first_csf.thresholds_queued == [30]
    assert second_csf.thresholds_queued == []
    assert second_csf.thresholds_deduped == [30]

    db = db_factory()
    try:
        rows = db.execute(select(NotificationDispatch)).scalars().all()
    finally:
        db.close()
    # Still only 2 rows (one per recipient) — the second pass deduped.
    assert len(rows) == 2
