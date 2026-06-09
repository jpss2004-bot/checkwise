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
from datetime import date, timedelta
from enum import StrEnum
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.statuses import DocumentStatus
from app.core.compliance_catalog import (
    OnboardingRequirement,
    RecurringRequirement,
    expediente_for_persona,
    normalize_persona_type,
    recurring_for_year,
    recurring_for_year_v2,
)
from app.core.config import settings
from app.models import Institution, ProviderWorkspace, Submission


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
    # Catalog frequency for recurring slots — "mensual" / "bimestral"
    # / "cuatrimestral" / "anual". ``None`` on onboarding slots, which
    # are non-periodic by definition. Surfaces in upload-URL builders
    # so the wizard's "Tipo de carga" field locks correctly instead of
    # falling back to the hardcoded "mensual" default. Defaults to None
    # for back-compat with tests that built SlotView via positional
    # ordering before this field existed.
    load_type: str | None = None


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


def current_onboarding_submission_for_workspace(
    db: Session,
    *,
    workspace: ProviderWorkspace,
    requirement_code: str,
    prefetched_submissions: list[Submission] | None = None,
) -> Submission | None:
    """Return the current onboarding submission for ``requirement_code``.

    Onboarding slots are keyed by ``(client_id, vendor_id,
    requirement_code)`` only — they have no period (the catalog row
    carries ``period_key=None``). The canonical
    :func:`current_submission_for_slot` lookup requires *both*
    ``requirement_code`` and ``period_key``, so it always returns
    ``None`` for onboarding rows. This helper plugs that gap by
    matching on ``requirement_code`` alone, then walking the same
    supersession lineage rules :func:`_pick_current_submission` uses.

    Returns the leaf of the supersession chain — the latest
    submission that no other submission supersedes. ``None`` when no
    submission exists for the slot.

    ``prefetched_submissions`` (the batch path) lets a caller supply
    this workspace's submissions so we filter in memory instead of
    issuing a query per requirement_code.
    """
    if prefetched_submissions is not None:
        candidates = [
            s
            for s in prefetched_submissions
            if s.requirement_code == requirement_code
        ]
    else:
        candidates = list(
            db.scalars(
                select(Submission).where(
                    Submission.client_id == workspace.client_id,
                    Submission.vendor_id == workspace.vendor_id,
                    Submission.requirement_code == requirement_code,
                )
            )
        )
    return _pick_current_submission(candidates)


def _slot_view_from_candidates(
    *,
    slot_key: SlotKey,
    requirement_name: str | None,
    institution: str | None,
    load_type: str | None = None,
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
        load_type=load_type,
        required=required,
        current_submission_id=current.id if current is not None else None,
        current_status=current.status if current is not None else None,
        submitted_at_iso=(
            current.created_at.isoformat() if current is not None else None
        ),
        superseded_count=len(superseded_ids),
    )


def _workspace_submissions(
    db: Session,
    workspace: ProviderWorkspace,
    prefetched: list[Submission] | None,
) -> list[Submission]:
    """Every submission for a workspace's ``(client_id, vendor_id)``.

    When ``prefetched`` is supplied it is used verbatim and **no query
    runs** — this is the batch path: a caller rendering many vendors
    (e.g. the client portfolio) fetches all of a client's submissions in
    one query, buckets them by ``vendor_id``, and hands each builder the
    matching bucket. That collapses the old ``2 × N`` per-vendor scans
    (each a full ``submissions`` scan) into a single query. The caller
    owns the contract that the bucket holds exactly this workspace's
    rows. With ``prefetched=None`` we fall back to the original
    per-workspace query, so every existing single-workspace caller is
    unaffected.
    """
    if prefetched is not None:
        return prefetched
    return list(
        db.scalars(
            select(Submission).where(
                Submission.client_id == workspace.client_id,
                Submission.vendor_id == workspace.vendor_id,
            )
        )
    )


def build_workspace_onboarding_slots(
    db: Session,
    workspace: ProviderWorkspace,
    *,
    prefetched_submissions: list[Submission] | None = None,
) -> list[SlotView]:
    """Project the Expediente Corporativo catalog onto this workspace's submissions.

    One :class:`SlotView` per onboarding requirement for the workspace's
    persona type. Slots with no submission report
    ``state=SlotState.MISSING``; slots with submissions follow the
    supersession lineage to pick the current one.

    ``prefetched_submissions`` lets a batch caller supply this
    workspace's submissions instead of querying — see
    :func:`_workspace_submissions`.
    """
    # Bugfix (2026-05-21) — defensive normalize. See compliance_catalog.
    # normalize_persona_type for context.
    catalog = expediente_for_persona(normalize_persona_type(workspace.persona_type))
    # Pull every submission for the workspace once, then bucket per slot
    # in Python. This avoids N+1 lookups for catalogs in the dozens.
    all_for_workspace = _workspace_submissions(db, workspace, prefetched_submissions)
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
    db: Session,
    workspace: ProviderWorkspace,
    year: int,
    *,
    prefetched_submissions: list[Submission] | None = None,
    institutions_by_id: dict[str, str] | None = None,
) -> list[SlotView]:
    """Project the recurring REPSE calendar onto this workspace's submissions.

    Covers every frequency the calendar carries (monthly, bimonthly,
    cuatrimestral, annual) plus prior-year carryover slots (e.g.
    January upload of last year's December) by reading
    :data:`RecurringRequirement.period_key` directly.

    Catalog v1 (default) iterates ``recurring_for_year`` and matches
    submissions by exact ``(requirement_code, period_key)``. Catalog
    v2 (Session 2, 2026-05-20) iterates ``recurring_for_year_v2`` —
    one row per (institution, period) carrying an ``accepts_documents``
    list — and matches submissions via a **compatibility join**:
    submissions whose ``(institution_code, period_key)`` matches the
    v2 row's ``(institution, period_key)`` count toward the slot,
    regardless of whether they carry a v2 code or a legacy v1
    per-doc-suffix code. This keeps historical submissions resolved
    after the flag flips so nothing appears unsubmitted to providers.

    The v2 branch implements ``minimum_documents="one"`` semantics
    directly (any candidate satisfies the slot). ``"all"`` semantics
    — every accepted doc type must be present — are stubbed with a
    fallback to the same "one" logic. No production v2 row uses
    ``"all"`` today; when one does, the matching by accepted-doc-name
    lives behind the explicit branch below.
    """
    if settings.RECURRING_CATALOG_V2:
        return _build_workspace_calendar_slots_v2(
            db,
            workspace,
            year,
            prefetched_submissions=prefetched_submissions,
            institutions_by_id=institutions_by_id,
        )

    # Bugfix (2026-05-21) — defensive normalize.
    persona = normalize_persona_type(workspace.persona_type)
    catalog: list[RecurringRequirement] = list(
        recurring_for_year(year, persona)
    )
    all_for_workspace = _workspace_submissions(db, workspace, prefetched_submissions)
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
                load_type=req.frequency,
                required=True,
                candidates=candidates,
            )
        )
    return views


def _build_workspace_calendar_slots_v2(
    db: Session,
    workspace: ProviderWorkspace,
    year: int,
    *,
    prefetched_submissions: list[Submission] | None = None,
    institutions_by_id: dict[str, str] | None = None,
) -> list[SlotView]:
    """Catalog v2 slot resolver — collapsed rows + compatibility join.

    Submission matching key: ``(institution_code, period_key)`` instead
    of ``(requirement_code, period_key)``. The institution code is
    resolved from ``Submission.institution_id`` via the ``Institution``
    table so both v2-coded submissions (``REC-IMSS-2026-01``) and
    legacy v1-coded submissions
    (``REC-IMSS-2026-01-comprobante-de-pago-bancario``) sharing the
    same institution + period both contribute candidates.
    """
    # Bugfix (2026-05-21) — defensive normalize.
    persona = normalize_persona_type(workspace.persona_type)
    catalog: list[RecurringRequirement] = list(
        recurring_for_year_v2(year, persona)
    )

    # One-shot id → code map for the institutions referenced by this
    # workspace's submissions. Keeps the resolver self-contained. A batch
    # caller can hand in a shared map so we don't re-scan ``institutions``
    # once per vendor.
    if institutions_by_id is None:
        institutions_by_id = {
            inst.id: inst.code for inst in db.scalars(select(Institution))
        }

    all_for_workspace = _workspace_submissions(db, workspace, prefetched_submissions)
    by_slot: dict[tuple[str, str], list[Submission]] = {}
    for sub in all_for_workspace:
        if not sub.institution_id or not sub.period_key:
            continue
        inst_code = institutions_by_id.get(sub.institution_id)
        if not inst_code:
            continue
        by_slot.setdefault((inst_code, sub.period_key), []).append(sub)

    views: list[SlotView] = []
    for req in catalog:
        candidates = by_slot.get((req.institution, req.period_key), [])
        slot_key = SlotKey(
            workspace_id=workspace.id,
            client_id=workspace.client_id,
            vendor_id=workspace.vendor_id,
            requirement_code=req.code,
            period_key=req.period_key,
        )
        # ``minimum_documents="all"`` would require per-accepted-doc
        # matching (e.g. group candidates by detected/requirement name
        # and require coverage of every entry in req.accepts_documents
        # before marking the slot APPROVED). No production row uses
        # "all" today; until one does, the "one" path's any-candidate
        # logic is correct for both modes — a real "all" implementation
        # belongs alongside the first row that needs it so the
        # matching contract is informed by a concrete example.
        views.append(
            _slot_view_from_candidates(
                slot_key=slot_key,
                requirement_name=req.name,
                institution=req.institution,
                load_type=req.frequency,
                required=True,
                candidates=candidates,
            )
        )
    return views


# ---------------------------------------------------------------------------
# Phase 6 — renewal rule helpers (Slice 6A foundation)
# ---------------------------------------------------------------------------
#
# These are pure date-math helpers. They never touch the DB. The
# emit-site (Slice 6B) and the scheduler (Slice 6C) consume them; for
# now the only caller is ``scripts/run_renewal_audit.py``, which walks
# real workspaces and prints the computed status so we can verify the
# rule layer against seed data before wiring notifications.
#
# Anchor convention: a renewal cycle starts when a submission becomes
# the standing evidence — i.e. when a reviewer approved it. The
# workflow service touches ``Submission.updated_at`` on every status
# transition, so for an approved submission ``updated_at`` is the
# approval moment. ``renewal_anchor_date`` enforces this contract so
# downstream code doesn't have to remember it.


RenewalStatus = Literal["ok", "due_soon", "overdue"]


def renewal_anchor_date(submission: Submission | None) -> date | None:
    """Return the day a renewal cycle should be measured from.

    The anchor is the day the submission became the standing approved
    evidence for its slot. Returns ``None`` when there is no submission
    or when the submission is not (yet) approved — a rejected or
    in-review submission cannot anchor a renewal cycle.
    """
    if submission is None:
        return None
    if submission.status != DocumentStatus.APROBADO.value:
        return None
    return submission.updated_at.date()


def next_renewal_due_date(
    *,
    anchor: date | None,
    frequency_days: int | None,
) -> date | None:
    """Return the date the next renewal is due, or ``None`` when not applicable.

    ``None`` covers two cases the caller must treat differently and is
    therefore left to the caller to disambiguate:

    * ``frequency_days is None`` — the requirement has no renewal cadence
      (one-time onboarding piece).
    * ``anchor is None`` — the requirement has a cadence but no approved
      submission exists yet, so there is nothing to renew.

    The function does not collapse the two — both rightly produce "no
    next due date to surface", and disambiguating belongs in the
    consumer (e.g. the audit CLI shows "never approved" for the second
    case and skips the first entirely).
    """
    if anchor is None or not frequency_days:
        return None
    return anchor + timedelta(days=frequency_days)


def renewal_status(due: date | None, today: date) -> RenewalStatus | None:
    """Bucket a renewal due date for downstream UI / notification use.

    Returns ``None`` when there is no due date (frequency not set, or
    no approved anchor). Otherwise:

    * ``overdue`` — ``due`` is strictly before ``today``.
    * ``due_soon`` — ``due`` is within 30 days of ``today`` (inclusive).
    * ``ok`` — otherwise.

    The 30-day window matches the locked Phase 6 cadence (30/14/7/day-of
    reminders, yellow until day-of, red on day-of and after). The
    finer-grained 14/7/0 threshold crossings belong in Slice 6B's
    notification emit-site so each crossing fires exactly once via an
    idempotency key — they are not the slot consumer's concern.
    """
    if due is None:
        return None
    delta = (due - today).days
    if delta < 0:
        return "overdue"
    if delta <= 30:
        return "due_soon"
    return "ok"


__all__ = [
    "SlotState",
    "SlotKey",
    "SlotView",
    "classify_slot_state",
    "current_submission_for_slot",
    "current_onboarding_submission_for_workspace",
    "build_workspace_onboarding_slots",
    "build_workspace_calendar_slots",
    # Phase 6 renewal helpers.
    "RenewalStatus",
    "renewal_anchor_date",
    "next_renewal_due_date",
    "renewal_status",
    # Re-exported catalog dataclasses for callers that want to traverse
    # without importing the catalog module directly.
    "OnboardingRequirement",
    "RecurringRequirement",
]
