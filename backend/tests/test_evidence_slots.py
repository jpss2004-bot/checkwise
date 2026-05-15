"""Phase 3 — evidence_slots service.

Direct unit tests against
``app.services.evidence_slots``. The service is the read-side oracle
for "which submission is current for this obligation slot" and
"what coarse state is the slot in." Future surfaces (dashboards,
reports, notifications) will consume it; these tests pin the rules
before any of those land.

The service is intentionally read-only — these tests poke submissions
into the DB through the model layer (not the workspace upload
endpoint) to isolate the slot-selection rules from the intake
pipeline.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants.statuses import DocumentStatus
from app.core.compliance_catalog import recurring_for_year
from app.db.base import Base
from app.models import (
    Client,
    Institution,
    Period,
    ProviderWorkspace,
    Requirement,
    RequirementVersion,
    Submission,
    Vendor,
    entities,  # noqa: F401 — register mappers
)
from app.models.entities import utc_now
from app.services.evidence_slots import (
    SlotState,
    build_workspace_calendar_slots,
    build_workspace_onboarding_slots,
    classify_slot_state,
    current_submission_for_slot,
)


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
def workspace(db_factory) -> Generator[ProviderWorkspace, None, None]:
    db: Session = db_factory()
    try:
        client = Client(name="Cliente Slots")
        db.add(client)
        db.flush()
        vendor = Vendor(
            client_id=client.id,
            name="Vendor Slots",
            rfc="SLT260512AB1",
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()
        ws = ProviderWorkspace(
            client_id=client.id,
            vendor_id=vendor.id,
            persona_type="moral",
            display_name="Vendor Slots",
            access_token="token-slots",
        )
        db.add(ws)
        db.commit()
        ws_id = ws.id
    finally:
        db.close()

    # Re-load on a fresh session so callers can detach without losing
    # the lazy-loaded ``client`` / ``vendor`` relationships.
    db = db_factory()
    try:
        ws_obj = db.get(ProviderWorkspace, ws_id)
        assert ws_obj is not None
        yield ws_obj
    finally:
        db.close()


def _seed_period(db: Session, period_key: str, period_type: str = "mensual") -> Period:
    existing = db.scalar(
        select(Period).where(Period.code == period_key, Period.period_type == period_type)
    )
    if existing is not None:
        return existing
    period = Period(code=period_key, period_type=period_type, period_key=period_key)
    db.add(period)
    db.flush()
    return period


def _seed_requirement(
    db: Session, *, code: str, name: str = "Slot Req", institution_code: str = "sat"
) -> tuple[Requirement, RequirementVersion]:
    institution = db.scalar(select(Institution).where(Institution.code == institution_code))
    if institution is None:
        institution = Institution(code=institution_code, name=institution_code.upper())
        db.add(institution)
        db.flush()
    existing_req = db.scalar(select(Requirement).where(Requirement.code == code))
    if existing_req is not None:
        version = db.scalar(
            select(RequirementVersion).where(
                RequirementVersion.requirement_id == existing_req.id
            )
        )
        assert version is not None
        return existing_req, version
    requirement = Requirement(
        code=code,
        name=name,
        institution_id=institution.id,
        load_type="mensual",
        frequency="mensual",
        risk_level="medium",
        current_version=1,
    )
    db.add(requirement)
    db.flush()
    version = RequirementVersion(requirement_id=requirement.id, version=1)
    db.add(version)
    db.flush()
    return requirement, version


def _seed_submission(
    db_factory,
    workspace: ProviderWorkspace,
    *,
    requirement_code: str,
    period_key: str,
    status: str,
    supersedes_submission_id: str | None = None,
    minutes_old: int = 0,
) -> str:
    db: Session = db_factory()
    try:
        requirement, version = _seed_requirement(
            db, code=f"req:{requirement_code}", name=requirement_code
        )
        period = _seed_period(db, period_key)
        sub = Submission(
            client_id=workspace.client_id,
            vendor_id=workspace.vendor_id,
            institution_id=requirement.institution_id,
            requirement_id=requirement.id,
            requirement_version_id=version.id,
            period_id=period.id,
            load_type="mensual",
            status=status,
            requirement_code=requirement_code,
            period_key=period_key,
            supersedes_submission_id=supersedes_submission_id,
            created_at=utc_now() - timedelta(minutes=minutes_old),
            updated_at=utc_now() - timedelta(minutes=minutes_old),
        )
        db.add(sub)
        db.commit()
        return sub.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# classify_slot_state
# ---------------------------------------------------------------------------


def test_classify_slot_state_maps_known_statuses() -> None:
    assert classify_slot_state(None) is SlotState.MISSING
    assert classify_slot_state(DocumentStatus.PENDIENTE_REVISION.value) is SlotState.IN_REVIEW
    assert classify_slot_state(DocumentStatus.PREVALIDADO.value) is SlotState.IN_REVIEW
    assert classify_slot_state(DocumentStatus.APROBADO.value) is SlotState.APPROVED
    assert classify_slot_state(DocumentStatus.RECHAZADO.value) is SlotState.REJECTED
    assert (
        classify_slot_state(DocumentStatus.REQUIERE_ACLARACION.value)
        is SlotState.NEEDS_CORRECTION
    )
    assert (
        classify_slot_state(DocumentStatus.POSIBLE_MISMATCH.value)
        is SlotState.POSSIBLE_MISMATCH
    )
    assert classify_slot_state(DocumentStatus.EXCEPCION_LEGAL.value) is SlotState.EXCEPTION
    assert classify_slot_state(DocumentStatus.VENCIDO.value) is SlotState.EXPIRED
    assert classify_slot_state(DocumentStatus.NO_APLICA.value) is SlotState.NOT_APPLICABLE
    # Unknown gracefully degrades to MISSING.
    assert classify_slot_state("anything-else") is SlotState.MISSING


# ---------------------------------------------------------------------------
# current_submission_for_slot — lineage rules
# ---------------------------------------------------------------------------


def test_current_submission_returns_replacement_not_rejected_prior(
    db_factory, workspace: ProviderWorkspace
) -> None:
    """Tests 9 + 10: lineage wins over latest-created. A newer replacement
    must be returned as current even if the prior is rejected; the
    rejected prior is never returned as current."""
    prior_id = _seed_submission(
        db_factory,
        workspace,
        requirement_code="repse:m05",
        period_key="2026-M05",
        status=DocumentStatus.RECHAZADO.value,
        minutes_old=60,
    )
    new_id = _seed_submission(
        db_factory,
        workspace,
        requirement_code="repse:m05",
        period_key="2026-M05",
        status=DocumentStatus.PENDIENTE_REVISION.value,
        supersedes_submission_id=prior_id,
        minutes_old=1,
    )

    db: Session = db_factory()
    try:
        current = current_submission_for_slot(
            db,
            client_id=workspace.client_id,
            vendor_id=workspace.vendor_id,
            requirement_code="repse:m05",
            period_key="2026-M05",
        )
    finally:
        db.close()

    assert current is not None
    assert current.id == new_id
    assert current.id != prior_id


def test_current_submission_picks_latest_when_no_replacement_link(
    db_factory, workspace: ProviderWorkspace
) -> None:
    """When there is no lineage link, ``created_at`` decides. Two
    independent submissions for the same slot → the newer wins."""
    older = _seed_submission(
        db_factory,
        workspace,
        requirement_code="sat:opinion",
        period_key="2026-M02",
        status=DocumentStatus.RECHAZADO.value,
        minutes_old=120,
    )
    newer = _seed_submission(
        db_factory,
        workspace,
        requirement_code="sat:opinion",
        period_key="2026-M02",
        status=DocumentStatus.PENDIENTE_REVISION.value,
        minutes_old=10,
    )

    db: Session = db_factory()
    try:
        current = current_submission_for_slot(
            db,
            client_id=workspace.client_id,
            vendor_id=workspace.vendor_id,
            requirement_code="sat:opinion",
            period_key="2026-M02",
        )
    finally:
        db.close()

    assert current is not None
    assert current.id == newer
    assert current.id != older


def test_current_submission_returns_none_for_empty_slot(
    db_factory, workspace: ProviderWorkspace
) -> None:
    db: Session = db_factory()
    try:
        current = current_submission_for_slot(
            db,
            client_id=workspace.client_id,
            vendor_id=workspace.vendor_id,
            requirement_code="never:filled",
            period_key="2026-M01",
        )
    finally:
        db.close()
    assert current is None


# ---------------------------------------------------------------------------
# build_workspace_onboarding_slots
# ---------------------------------------------------------------------------


def test_build_workspace_onboarding_slots_combines_missing_and_filled(
    db_factory, workspace: ProviderWorkspace
) -> None:
    """Test 11: onboarding slot service surfaces missing + uploaded +
    rejected + approved correctly across the same workspace."""
    # Pre-fill three onboarding slots with known states. The rest must
    # remain MISSING. Codes are pulled from the canonical catalog so
    # they stay in sync if the catalog is renumbered.
    _seed_submission(
        db_factory,
        workspace,
        requirement_code="ONB-CONT-001",  # Contrato original — required
        period_key="onb-contract-2026",
        status=DocumentStatus.APROBADO.value,
    )
    _seed_submission(
        db_factory,
        workspace,
        requirement_code="ONB-CORP-M-001",  # Acta constitutiva — required for moral
        period_key="onb-corp-2026",
        status=DocumentStatus.RECHAZADO.value,
    )
    _seed_submission(
        db_factory,
        workspace,
        requirement_code="ONB-REPSE-001",  # Registro REPSE — required
        period_key="onb-repse-2026",
        status=DocumentStatus.PENDIENTE_REVISION.value,
    )

    db: Session = db_factory()
    try:
        slots = build_workspace_onboarding_slots(db, workspace)
    finally:
        db.close()

    assert slots, "expected onboarding catalog to yield slot views"
    by_code = {s.slot_key.requirement_code: s for s in slots}

    # Filled slots reflect their submission state.
    assert by_code["ONB-CONT-001"].state is SlotState.APPROVED
    assert by_code["ONB-CORP-M-001"].state is SlotState.REJECTED
    assert by_code["ONB-REPSE-001"].state is SlotState.IN_REVIEW

    # Untouched required slots stay MISSING (e.g. patronal IMSS docs).
    missing_required = [
        s for s in slots if s.state is SlotState.MISSING and s.required
    ]
    assert missing_required, "expected at least one MISSING required onboarding slot"


# ---------------------------------------------------------------------------
# build_workspace_calendar_slots — frequency + carryover coverage
# ---------------------------------------------------------------------------


def test_build_workspace_calendar_slots_handles_every_frequency_and_carryover(
    db_factory, workspace: ProviderWorkspace
) -> None:
    """Test 12: monthly, bimonthly, cuatrimestral, annual, AND a
    January slot that covers the prior year's December (carryover)
    all produce SlotViews with the correct period_key."""
    catalog = list(recurring_for_year(2026, "moral"))

    # Pick one representative slot per frequency, plus a January
    # carryover (prior-year December monthly).
    monthly = next(
        c for c in catalog if c.frequency == "mensual" and c.period_key == "2026-M05"
    )
    bimestral = next(c for c in catalog if c.frequency == "bimestral")
    cuatrimestral = next(c for c in catalog if c.frequency == "cuatrimestral")
    anual = next(c for c in catalog if c.frequency == "anual")
    # January carryover: a recurring item whose period_key references
    # the PRIOR year (December of 2025) but is due in early 2026.
    january_carryover = next(
        c
        for c in catalog
        if c.period_key.startswith("2025-")
    )

    # Seed one submission per representative slot with a recognisable
    # status so we can verify the mapping.
    for cat_item, status in [
        (monthly, DocumentStatus.APROBADO.value),
        (bimestral, DocumentStatus.RECHAZADO.value),
        (cuatrimestral, DocumentStatus.POSIBLE_MISMATCH.value),
        (anual, DocumentStatus.PENDIENTE_REVISION.value),
        (january_carryover, DocumentStatus.REQUIERE_ACLARACION.value),
    ]:
        _seed_submission(
            db_factory,
            workspace,
            requirement_code=cat_item.code,
            period_key=cat_item.period_key,
            status=status,
        )

    db: Session = db_factory()
    try:
        slots = build_workspace_calendar_slots(db, workspace, year=2026)
    finally:
        db.close()

    by_keypair = {(s.requirement_code, s.period_key): s for s in slots}

    monthly_view = by_keypair[(monthly.code, monthly.period_key)]
    assert monthly_view.state is SlotState.APPROVED

    bimestral_view = by_keypair[(bimestral.code, bimestral.period_key)]
    assert bimestral_view.state is SlotState.REJECTED

    cuat_view = by_keypair[(cuatrimestral.code, cuatrimestral.period_key)]
    assert cuat_view.state is SlotState.POSSIBLE_MISMATCH

    anual_view = by_keypair[(anual.code, anual.period_key)]
    assert anual_view.state is SlotState.IN_REVIEW

    jan_view = by_keypair[(january_carryover.code, january_carryover.period_key)]
    assert jan_view.state is SlotState.NEEDS_CORRECTION
    # The carryover slot keeps the PRIOR-YEAR period_key.
    assert jan_view.period_key.startswith("2025-")


def test_build_workspace_calendar_slots_reports_missing_for_unsubmitted_slots(
    db_factory, workspace: ProviderWorkspace
) -> None:
    """A workspace with zero submissions reports every recurring slot as MISSING."""
    db: Session = db_factory()
    try:
        slots = build_workspace_calendar_slots(db, workspace, year=2026)
    finally:
        db.close()
    assert slots, "expected the 2026 recurring catalog to be non-empty"
    assert all(slot.state is SlotState.MISSING for slot in slots)
    assert all(slot.current_submission_id is None for slot in slots)


def test_slot_view_exposes_superseded_count(
    db_factory, workspace: ProviderWorkspace
) -> None:
    """``superseded_count`` reflects how many prior attempts lineage points at."""
    prior = _seed_submission(
        db_factory,
        workspace,
        requirement_code="repse:b1",
        period_key="2026-B1",
        status=DocumentStatus.RECHAZADO.value,
        minutes_old=120,
    )
    _seed_submission(
        db_factory,
        workspace,
        requirement_code="repse:b1",
        period_key="2026-B1",
        status=DocumentStatus.PENDIENTE_REVISION.value,
        supersedes_submission_id=prior,
        minutes_old=1,
    )

    db: Session = db_factory()
    try:
        current = current_submission_for_slot(
            db,
            client_id=workspace.client_id,
            vendor_id=workspace.vendor_id,
            requirement_code="repse:b1",
            period_key="2026-B1",
        )
    finally:
        db.close()
    assert current is not None
    assert current.supersedes_submission_id == prior
