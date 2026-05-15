"""Phase 3 — evidence slot + obligation state engine.

This service answers one question for every place CheckWise needs to
reason about provider compliance:

    "For this workspace's obligation slot, which submission is current,
    and what state is the slot in?"

An *evidence slot* is the logical seat an obligation occupies for a
single provider in a single period:

    (client_id, vendor_id, requirement_code, period_key)

For legacy rows that pre-date canonical keys it falls back to the
plain SQLAlchemy FKs (``requirement_id`` / ``period_id``). The
service is read-only: it never writes to the DB. Replacement linkage
is established at intake time (see
``app.services.submission_service.finalize_intake_submission``); this
service just walks that lineage to surface "the current submission".

Out of scope here:
    * Scheduled expiry transitions.
    * Notification dispatch.
    * Dashboard mock replacement.
    * Report generation.
    * OCR / AI extraction.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.statuses import DocumentStatus
from app.core.compliance_catalog import (
    OnboardingRequirement,
    RecurringRequirement,
    expediente_for_persona,
    recurring_for_year,
)
from app.models import ProviderWorkspace, Submission


class SlotState(StrEnum):
    """Coarse compliance state for an evidence slot.

    These are derived from ``DocumentStatus`` on the current submission
    plus the presence/absence of a submission at all. Future surfaces
    (dashboards, reports) should branch on ``SlotState``, not on raw
    status codes, so legend changes don't propagate into UI logic.
    """

    MISSING = "missing"
    UPLOADED = "uploaded"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CORRECTION = "needs_correction"
    POSSIBLE_MISMATCH = "possible_mismatch"
    EXCEPTION = "exception"
    EXPIRED = "expired"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class SlotKey:
    """Canonical identity of an obligation slot for a provider.

    ``requirement_code`` + ``period_key`` are the canonical pair. The
    plain FKs are an optional legacy fallback — use them only when
    canonical keys are absent on the DB row (older rows pre-date the
    Reconciliation Patch).
    """

    workspace_id: str
    client_id: str
    vendor_id: str
    requirement_code: str | None
    period_key: str | None
    requirement_id: str | None = None
    period_id: str | None = None


@dataclass(frozen=True)
class SlotView:
    """Computed compliance view for one slot.

    Pure data — never mutates. ``current_submission`` is the latest
    leaf of the supersession chain (or None if no submission exists).
    """

    slot_key: SlotKey
    state: SlotState
    # Identity helpers so callers can render the slot without re-loading.
    requirement_code: str | None
    period_key: str | None
    requirement_name: str | None
    institution: str | None
    required: bool
    # When a submission exists for this slot. None means the slot is
    # ``missing`` (no upload yet).
    current_submission_id: str | None
    current_status: str | None
    submitted_at_iso: str | None
    # Lineage hint: how many prior attempts (superseded rows) are on
    # this slot. ``0`` for a brand-new upload, ``1+`` after a replacement.
    superseded_count: int


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _slot_candidates(
    db: Session,
    *,
    client_id: str,
    vendor_id: str,
    requirement_code: str | None,
    period_key: str | None,
    requirement_id: str | None,
    period_id: str | None,
) -> list[Submission]:
    """Pull every submission that could populate this slot.

    Canonical match first: ``requirement_code`` + ``period_key`` together
    are the canonical join. When canonical keys are missing on either
    the catalog item or the stored row, we fall back to the plain FK
    join so legacy submissions still surface.
    """
    stmt = select(Submission).where(
        Submission.client_id == client_id,
        Submission.vendor_id == vendor_id,
    )
    # Prefer canonical keys. Both must be set on the input AND on the
    # row for the canonical filter to apply.
    if requirement_code and period_key:
        stmt = stmt.where(
            Submission.requirement_code == requirement_code,
            Submission.period_key == period_key,
        )
    elif requirement_id and period_id:
        stmt = stmt.where(
            Submission.requirement_id == requirement_id,
            Submission.period_id == period_id,
        )
    else:
        # Without either pair we can't safely identify a slot.
        return []
    return list(db.scalars(stmt))


def _pick_current_submission(candidates: list[Submission]) -> Submission | None:
    """Return the "current" submission for the slot (None if empty).

    The current submission is the leaf of the supersession chain — i.e.
    no other candidate points at it via ``supersedes_submission_id``.
    When multiple leaves exist (parallel re-uploads, unusual but
    possible) the most recent by ``created_at`` wins.
    """
    if not candidates:
        return None
    superseded_ids = {
        c.supersedes_submission_id for c in candidates if c.supersedes_submission_id
    }
    leaves = [c for c in candidates if c.id not in superseded_ids]
    if not leaves:
        # Defensive fallback: every candidate has been superseded by
        # someone outside the set. Sort the full list to keep the
        # caller working rather than returning None.
        leaves = list(candidates)
    leaves.sort(key=lambda sub: sub.created_at, reverse=True)
    return leaves[0]


# Mapping from canonical document status → coarse slot state.
# ``pendiente_revision`` / ``recibido`` / ``prevalidado`` are reviewer-
# queue states, all expressed as ``in_review`` to the slot consumer.
_STATUS_TO_SLOT_STATE: dict[str, SlotState] = {
    DocumentStatus.PENDIENTE.value: SlotState.MISSING,
    DocumentStatus.RECIBIDO.value: SlotState.UPLOADED,
    DocumentStatus.PENDIENTE_REVISION.value: SlotState.IN_REVIEW,
    DocumentStatus.PREVALIDADO.value: SlotState.IN_REVIEW,
    DocumentStatus.POSIBLE_MISMATCH.value: SlotState.POSSIBLE_MISMATCH,
    DocumentStatus.APROBADO.value: SlotState.APPROVED,
    DocumentStatus.RECHAZADO.value: SlotState.REJECTED,
    DocumentStatus.REQUIERE_ACLARACION.value: SlotState.NEEDS_CORRECTION,
    DocumentStatus.EXCEPCION_LEGAL.value: SlotState.EXCEPTION,
    DocumentStatus.VENCIDO.value: SlotState.EXPIRED,
    DocumentStatus.NO_APLICA.value: SlotState.NOT_APPLICABLE,
}


def classify_slot_state(status: str | None) -> SlotState:
    """Map a stored ``DocumentStatus`` value to the coarse :class:`SlotState`.

    Returns :attr:`SlotState.MISSING` when ``status`` is ``None``
    (no submission exists yet for the slot). Unknown status strings
    also fall back to ``MISSING`` — better to surface "missing" than
    to silently pretend an unknown row was in review.
    """
    if status is None:
        return SlotState.MISSING
    return _STATUS_TO_SLOT_STATE.get(status, SlotState.MISSING)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def current_submission_for_slot(
    db: Session,
    *,
    client_id: str,
    vendor_id: str,
    requirement_code: str | None = None,
    period_key: str | None = None,
    requirement_id: str | None = None,
    period_id: str | None = None,
) -> Submission | None:
    """Return the current submission for an obligation slot, or None.

    "Current" follows replacement lineage: it is the leaf of the
    supersession chain — the latest submission that no other submission
    supersedes.

    Canonical lookup uses ``(requirement_code, period_key)``. Pass
    ``(requirement_id, period_id)`` instead for legacy rows that
    pre-date canonical keys.
    """
    candidates = _slot_candidates(
        db,
        client_id=client_id,
        vendor_id=vendor_id,
        requirement_code=requirement_code,
        period_key=period_key,
        requirement_id=requirement_id,
        period_id=period_id,
    )
    return _pick_current_submission(candidates)


def _slot_view_from_candidates(
    *,
    slot_key: SlotKey,
    requirement_name: str | None,
    institution: str | None,
    required: bool,
    candidates: list[Submission],
) -> SlotView:
    current = _pick_current_submission(candidates)
    superseded_ids = {
        c.supersedes_submission_id for c in candidates if c.supersedes_submission_id
    }
    return SlotView(
        slot_key=slot_key,
        state=classify_slot_state(current.status if current is not None else None),
        requirement_code=slot_key.requirement_code,
        period_key=slot_key.period_key,
        requirement_name=requirement_name,
        institution=institution,
        required=required,
        current_submission_id=current.id if current is not None else None,
        current_status=current.status if current is not None else None,
        submitted_at_iso=(
            current.created_at.isoformat() if current is not None else None
        ),
        superseded_count=len(superseded_ids),
    )


def build_workspace_onboarding_slots(
    db: Session, workspace: ProviderWorkspace
) -> list[SlotView]:
    """Project the Expediente Corporativo catalog onto this workspace's submissions.

    One :class:`SlotView` per onboarding requirement for the workspace's
    persona type. Slots with no submission report
    ``state=SlotState.MISSING``; slots with submissions follow the
    supersession lineage to pick the current one.
    """
    catalog = expediente_for_persona(workspace.persona_type)  # type: ignore[arg-type]
    # Pull every submission for the workspace once, then bucket per slot
    # in Python. This avoids N+1 lookups for catalogs in the dozens.
    all_for_workspace = list(
        db.scalars(
            select(Submission).where(
                Submission.client_id == workspace.client_id,
                Submission.vendor_id == workspace.vendor_id,
            )
        )
    )
    by_code: dict[str, list[Submission]] = {}
    for sub in all_for_workspace:
        if not sub.requirement_code:
            continue
        by_code.setdefault(sub.requirement_code, []).append(sub)

    views: list[SlotView] = []
    for req in catalog:
        candidates = by_code.get(req.code, [])
        slot_key = SlotKey(
            workspace_id=workspace.id,
            client_id=workspace.client_id,
            vendor_id=workspace.vendor_id,
            requirement_code=req.code,
            # Onboarding slots have no recurring period. Catalog rows
            # don't carry a period_key — submissions filed against them
            # do, but the slot itself is identified by ``requirement_code``.
            period_key=None,
        )
        views.append(
            _slot_view_from_candidates(
                slot_key=slot_key,
                requirement_name=req.name,
                institution=req.institution,
                required=req.required,
                candidates=candidates,
            )
        )
    return views


def build_workspace_calendar_slots(
    db: Session, workspace: ProviderWorkspace, year: int
) -> list[SlotView]:
    """Project the recurring REPSE calendar onto this workspace's submissions.

    Covers every frequency the calendar carries (monthly, bimonthly,
    cuatrimestral, annual) plus prior-year carryover slots (e.g.
    January upload of last year's December) by reading
    :data:`RecurringRequirement.period_key` directly.
    """
    catalog: list[RecurringRequirement] = list(
        recurring_for_year(year, workspace.persona_type)  # type: ignore[arg-type]
    )
    all_for_workspace = list(
        db.scalars(
            select(Submission).where(
                Submission.client_id == workspace.client_id,
                Submission.vendor_id == workspace.vendor_id,
            )
        )
    )
    by_slot: dict[tuple[str, str], list[Submission]] = {}
    for sub in all_for_workspace:
        if not sub.requirement_code or not sub.period_key:
            continue
        by_slot.setdefault((sub.requirement_code, sub.period_key), []).append(sub)

    views: list[SlotView] = []
    for req in catalog:
        candidates = by_slot.get((req.code, req.period_key), [])
        slot_key = SlotKey(
            workspace_id=workspace.id,
            client_id=workspace.client_id,
            vendor_id=workspace.vendor_id,
            requirement_code=req.code,
            period_key=req.period_key,
        )
        views.append(
            _slot_view_from_candidates(
                slot_key=slot_key,
                requirement_name=req.name,
                institution=req.institution,
                required=True,
                candidates=candidates,
            )
        )
    return views


__all__ = [
    "SlotState",
    "SlotKey",
    "SlotView",
    "classify_slot_state",
    "current_submission_for_slot",
    "build_workspace_onboarding_slots",
    "build_workspace_calendar_slots",
    # Re-exported catalog dataclasses for callers that want to traverse
    # without importing the catalog module directly.
    "OnboardingRequirement",
    "RecurringRequirement",
]
