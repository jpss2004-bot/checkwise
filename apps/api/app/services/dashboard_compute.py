"""Vendor / provider dashboard read-model helpers.

Extracted from ``app.api.v1.portal`` so the same semaphore + document-
count rules can be reused outside the HTTP handler. The provider
Reports module (P1.2+) needs the canonical compliance-state payload
to render its new vendor-aware blocks without re-implementing the
slot-reduction logic.

Single source of truth: every consumer (portal endpoint, reports
``compliance_state`` block, future provider blocks) must derive the
semaphore and document counts from these helpers. If the rules
change, they change here.

Shape-stable plain-dict outputs (``build_compliance_state_for_vendor``)
keep the cross-layer contract simple — the block fetcher does not
take a runtime dependency on Pydantic response models from the API
layer.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.compliance_catalog import (
    expediente_for_persona,
    is_v2_recurring_code,
    normalize_persona_type,
)
from app.models.entities import ProviderWorkspace
from app.services.evidence_slots import (
    SlotState,
    SlotView,
    build_workspace_calendar_slots,
    build_workspace_onboarding_slots,
    current_onboarding_submission_for_workspace,
    next_renewal_due_date,
    renewal_anchor_date,
    renewal_status,
)

# ─── Slot-state buckets ─────────────────────────────────────────


#: SlotState values that mean "the provider must act now."
ACTIONABLE_SLOT_STATES: frozenset[SlotState] = frozenset(
    {SlotState.REJECTED, SlotState.NEEDS_CORRECTION, SlotState.POSSIBLE_MISMATCH}
)


#: SlotState values that count as "resolved / no action needed."
RESOLVED_SLOT_STATES: frozenset[SlotState] = frozenset(
    {SlotState.APPROVED, SlotState.EXCEPTION, SlotState.NOT_APPLICABLE}
)


# ─── Document-state counts ──────────────────────────────────────


def empty_document_counts() -> dict[str, int]:
    """Zero-initialised bucket dict matching ``DashboardDocumentStateCounts``.

    Plain dict so block fetchers can return it verbatim as JSON; the
    portal endpoint wraps it in a Pydantic model.
    """
    return {
        "approved": 0,
        "in_review": 0,
        "uploaded": 0,
        "pending": 0,
        "needs_review": 0,
        "rejected": 0,
        "expired": 0,
        "exception": 0,
    }


def bucket_document_state(counts: dict[str, int], state: SlotState) -> None:
    """Bump the count bucket for a slot's coarse state.

    ``MISSING`` → pending. ``NEEDS_CORRECTION`` / ``POSSIBLE_MISMATCH``
    → needs_review (matches the UI bucket the frontend uses).
    ``NOT_APPLICABLE`` is intentionally not counted — the slot has no
    document at all.
    """
    if state is SlotState.APPROVED:
        counts["approved"] += 1
    elif state is SlotState.IN_REVIEW:
        counts["in_review"] += 1
    elif state is SlotState.UPLOADED:
        counts["uploaded"] += 1
    elif state is SlotState.MISSING:
        counts["pending"] += 1
    elif state in (SlotState.NEEDS_CORRECTION, SlotState.POSSIBLE_MISMATCH):
        counts["needs_review"] += 1
    elif state is SlotState.REJECTED:
        counts["rejected"] += 1
    elif state is SlotState.EXPIRED:
        counts["expired"] += 1
    elif state is SlotState.EXCEPTION:
        counts["exception"] += 1
    # NOT_APPLICABLE: skip — no document expected.


# ─── Semaphore ──────────────────────────────────────────────────


SemaphoreLevel = Literal["green", "yellow", "red"]


def compute_semaphore(
    onboarding_slots: list[SlotView], calendar_slots: list[SlotView]
) -> dict:
    """Plain-dict semaphore payload over required slots.

    Rules (mirrored from PROVIDER_DASHBOARD_READ_MODEL.md):

    - Any required slot in ``rejected`` / ``needs_correction`` /
      ``possible_mismatch`` → red.
    - No blocking slot AND no on-track slots → red (P1.1, 2026-05-20):
      a provider with 0/N on track shouldn't read as "in progress";
      that misleads about the actual state.
    - No blocking slot, but any required ``missing`` / ``uploaded`` /
      ``in_review`` / ``expired`` → yellow.
    - Every required slot resolved → green.
    """
    required = [s for s in onboarding_slots if s.required] + [
        s for s in calendar_slots if s.required
    ]
    total_tracked = len(required)
    on_track = sum(1 for s in required if s.state in RESOLVED_SLOT_STATES)
    compliance_pct = (
        100 if total_tracked == 0 else round(on_track / total_tracked * 100)
    )
    has_blocking = any(s.state in ACTIONABLE_SLOT_STATES for s in required)
    has_pending = any(
        s.state
        in (
            SlotState.MISSING,
            SlotState.IN_REVIEW,
            SlotState.UPLOADED,
            SlotState.EXPIRED,
        )
        for s in required
    )
    no_progress = total_tracked > 0 and on_track == 0
    if has_blocking:
        level: SemaphoreLevel = "red"
        label = "Rojo · obligaciones críticas"
        reason = (
            "Hay documentos rechazados o con observaciones que necesitas atender "
            "antes de seguir avanzando."
        )
    elif no_progress:
        level = "red"
        label = "Rojo · sin avance"
        reason = (
            "Tu expediente tiene obligaciones pendientes y ninguna aprobada "
            "todavía. Sube el primer documento para arrancar el conteo."
        )
    elif has_pending:
        level = "yellow"
        label = "Amarillo · puntos por atender"
        reason = (
            "Tu expediente está en marcha, pero todavía quedan documentos por "
            "subir o por revisar."
        )
    else:
        level = "green"
        label = "Verde · al día"
        reason = "Todas tus obligaciones obligatorias están aprobadas."
    return {
        "level": level,
        "label": label,
        "reason": reason,
        "compliance_pct": compliance_pct,
        "total_tracked": total_tracked,
        "on_track": on_track,
    }


# ─── Vendor-scoped compliance state (P1.2) ─────────────────────


def resolve_workspace_for_vendor(
    db: Session, vendor_id: str
) -> ProviderWorkspace | None:
    """Pick the active ``ProviderWorkspace`` for a given vendor.

    Deterministic: lowest-id wins when more than one active workspace
    points at the same vendor (mirrors ``_actor_from`` in the reports
    API). Returns ``None`` if no active workspace exists — the caller
    surfaces that as an empty / error state.
    """
    return db.scalar(
        select(ProviderWorkspace)
        .where(
            ProviderWorkspace.vendor_id == vendor_id,
            ProviderWorkspace.status == "active",
        )
        .order_by(ProviderWorkspace.id)
        .limit(1)
    )


def build_compliance_state_for_vendor(
    db: Session, *, vendor_id: str, year: int | None = None
) -> dict:
    """Compose the semaphore + document-state counts for one vendor.

    Returns a JSON-safe dict shaped as:

    ```
    {
      "semaphore": {level, label, reason, compliance_pct, total_tracked, on_track},
      "document_state_counts": {approved, in_review, uploaded, pending,
                                needs_review, rejected, expired, exception},
      "workspace_id": str | None,
      "persona_type": str | None,
    }
    ```

    When no active workspace exists for the vendor, returns the
    structurally-correct empty shape with ``workspace_id=None`` and
    counts at zero. The block fetcher decides whether to surface that
    as an empty-state UI or an error.
    """
    workspace = resolve_workspace_for_vendor(db, vendor_id)
    if workspace is None:
        return {
            "semaphore": {
                "level": "green",
                "label": "Sin datos",
                "reason": "No hay espacio de proveedor activo para esta vista.",
                "compliance_pct": 0,
                "total_tracked": 0,
                "on_track": 0,
            },
            "document_state_counts": empty_document_counts(),
            "workspace_id": None,
            "persona_type": None,
        }

    target_year = year or date.today().year
    onboarding_slots = build_workspace_onboarding_slots(db, workspace)
    calendar_slots = build_workspace_calendar_slots(db, workspace, target_year)

    counts = empty_document_counts()
    for view in onboarding_slots + calendar_slots:
        bucket_document_state(counts, view.state)

    return {
        "semaphore": compute_semaphore(onboarding_slots, calendar_slots),
        "document_state_counts": counts,
        "workspace_id": workspace.id,
        "persona_type": workspace.persona_type,
    }


# ─── Reupload hrefs (P1.3) ─────────────────────────────────────


def onboarding_reupload_href(view: SlotView) -> str:
    """Build the ``/portal/upload`` URL for an onboarding slot.

    Mirrors ``_onboarding_reupload_href`` in ``app.api.v1.portal``.
    Threads requirement name + institution so the wizard locks Step 1
    instead of falling back to its hardcoded defaults
    (provider-portal UX pass, 2026-05-25).
    """
    parts = [f"requirement_code={quote(view.requirement_code or '')}"]
    if view.requirement_name:
        parts.append(f"requirement={quote(view.requirement_name)}")
    if view.institution:
        parts.append(f"institution={quote(view.institution)}")
    if view.current_submission_id and view.state in ACTIONABLE_SLOT_STATES:
        parts.append(f"replaces={view.current_submission_id}")
    parts.append("from=onboarding")
    return "/portal/upload?" + "&".join(parts)


def calendar_reupload_href(view: SlotView) -> str:
    """Build the ``/portal/upload`` URL for a calendar (periodic) slot.

    Mirrors ``_calendar_reupload_href`` in ``app.api.v1.portal``.
    Threads requirement name + institution + load_type so the upload
    wizard locks every Step 1 field instead of falling back to its
    hardcoded ``sat`` / ``mensual`` / arbitrary-6th-catalog-entry
    defaults (provider-portal UX pass, 2026-05-25).

    Session 3 (2026-05-21) — when ``requirement_code`` matches the v2
    shape, appends ``&v2=1`` so the wizard switches to the
    alternatives radio picker.
    """
    parts: list[str] = []
    if view.requirement_code:
        parts.append(f"requirement_code={quote(view.requirement_code)}")
    if view.requirement_name:
        parts.append(f"requirement={quote(view.requirement_name)}")
    if view.institution:
        parts.append(f"institution={quote(view.institution)}")
    if view.load_type:
        parts.append(f"load_type={quote(view.load_type)}")
    if view.period_key:
        parts.append(f"period_key={quote(view.period_key)}")
        parts.append(f"period_label={quote(view.period_key)}")
    if view.current_submission_id and view.state in ACTIONABLE_SLOT_STATES:
        parts.append(f"replaces={view.current_submission_id}")
    if view.requirement_code and is_v2_recurring_code(view.requirement_code):
        parts.append("v2=1")
    qs = "&".join(parts)
    return f"/portal/upload?{qs}" if qs else "/portal/upload"


def client_vendor_focus_href(
    vendor_id: str,
    *,
    requirement_code: str | None = None,
    period_key: str | None = None,
) -> str:
    """Client-routable deep link into a provider's detail page (CW-04).

    The client monitors compliance and cannot upload — so report/list CTAs
    shown to a CLIENT audience point here instead of the provider-only
    ``/portal/upload`` wizard. Lands on the "Documentos por atender" card
    (``#documentos``) and highlights the matching requirement row.
    """
    parts: list[str] = []
    if requirement_code:
        parts.append(f"focus={quote(requirement_code)}")
    if period_key:
        parts.append(f"period={quote(period_key)}")
    qs = "&".join(parts)
    base = f"/client/vendors/{vendor_id}"
    return f"{base}?{qs}#documentos" if qs else f"{base}#documentos"


# ─── Due-in-days estimate ──────────────────────────────────────


def due_in_days_for_period(period_key: str | None, today: date) -> int | None:
    """Estimate days-to-deadline from a canonical ``period_key``.

    The catalog encodes deadlines as "due in month X of year Y" with a
    conventional 17th-of-month cutoff. We can't recover the exact
    ``due_month`` from the slot view, so we use the period_key's own
    month/year as a conservative proxy: the document is due in the
    same period it covers. Returns None if the key isn't parseable.

    Format support: ``YYYY-MNN`` (monthly), ``YYYY-BNN`` (bimestral —
    pairs map to even months), ``YYYY-QNN`` (cuatrimestral — multiplied
    by 4), and ``YYYY-A`` (annual → December).
    """
    if not period_key:
        return None
    try:
        year = int(period_key[:4])
    except ValueError:
        return None
    month: int | None = None
    if "-M" in period_key:
        try:
            month = int(period_key.split("-M", 1)[1])
        except ValueError:
            month = None
    elif "-B" in period_key:
        try:
            bm = int(period_key.split("-B", 1)[1])
            month = bm * 2
        except ValueError:
            month = None
    elif "-Q" in period_key:
        try:
            q = int(period_key.split("-Q", 1)[1])
            month = q * 4
        except ValueError:
            month = None
    elif period_key.endswith("-A"):
        month = 12
    if month is None or not 1 <= month <= 12:
        return None
    try:
        deadline = date(year, month, 17)
    except ValueError:
        return None
    return (deadline - today).days


# ─── Attention items (P1.3) ────────────────────────────────────


def compute_attention_items(
    onboarding_slots: list[SlotView],
    calendar_slots: list[SlotView],
    today: date,
) -> list[dict]:
    """Plain-dict attention list — mirrors portal._compute_attention_today.

    Two passes, single output:

    1. Every required slot in an actionable state (``rejected`` /
       ``needs_correction`` / ``possible_mismatch``) OR ``expired`` —
       always surface regardless of date.
    2. Required calendar slots due within 14 days that are still
       ``missing`` / ``in_review`` / ``uploaded`` (not yet resolved or
       blocking).

    Sorted overdue-first (negative ``due_in_days``), then ascending,
    nulls last. Capped at 10 items. Each item carries a pre-computed
    ``href`` derived from the canonical slot identity — never from
    LLM output.
    """
    items: list[dict] = []

    for view in onboarding_slots + calendar_slots:
        if not view.required:
            continue
        if (
            view.state not in ACTIONABLE_SLOT_STATES
            and view.state is not SlotState.EXPIRED
        ):
            continue
        is_onboarding = view.slot_key.period_key is None
        href = (
            onboarding_reupload_href(view)
            if is_onboarding
            else calendar_reupload_href(view)
        )
        items.append(
            {
                "id": f"att-{view.requirement_code}-{view.period_key or 'onb'}",
                "title": (
                    view.requirement_name or view.requirement_code or "Obligación"
                ),
                "institution": view.institution or "—",
                "state": view.state.value,
                "due_in_days": due_in_days_for_period(view.period_key, today),
                "href": href,
                "requirement_code": view.requirement_code,
                "period_key": view.period_key,
                "current_submission_id": view.current_submission_id,
            }
        )

    for view in calendar_slots:
        if not view.required:
            continue
        if view.state in ACTIONABLE_SLOT_STATES or view.state is SlotState.EXPIRED:
            continue  # already added above
        if view.state in (
            SlotState.APPROVED,
            SlotState.EXCEPTION,
            SlotState.NOT_APPLICABLE,
        ):
            continue
        due_in = due_in_days_for_period(view.period_key, today)
        if due_in is None or due_in < 0 or due_in > 14:
            continue
        items.append(
            {
                "id": f"att-{view.requirement_code}-{view.period_key}",
                "title": (
                    view.requirement_name or view.requirement_code or "Obligación"
                ),
                "institution": view.institution or "—",
                "state": view.state.value,
                "due_in_days": due_in,
                "href": calendar_reupload_href(view),
                "requirement_code": view.requirement_code,
                "period_key": view.period_key,
                "current_submission_id": view.current_submission_id,
            }
        )

    items.sort(
        key=lambda i: (
            i["due_in_days"] is None,
            i["due_in_days"] if i["due_in_days"] is not None else 0,
        )
    )
    return items[:10]


def build_attention_items_for_vendor(
    db: Session,
    *,
    vendor_id: str,
    today: date | None = None,
) -> dict:
    """Compose the attention-list payload for one vendor.

    Returns:

    ```
    {
      "items": [{id, title, institution, state, due_in_days, href,
                 requirement_code, period_key, current_submission_id}],
      "workspace_id": str | None,
      "fetched_at": str,           # ISO8601 — when the slot snapshot
                                   # was taken. Block can show this so
                                   # the user knows whether the data is
                                   # stale.
    }
    ```

    No active workspace → empty items, ``workspace_id=None``.
    """
    workspace = resolve_workspace_for_vendor(db, vendor_id)
    fetched_at = datetime.utcnow().isoformat() + "Z"
    if workspace is None:
        return {
            "items": [],
            "workspace_id": None,
            "fetched_at": fetched_at,
        }

    target_today = today or date.today()
    onboarding_slots = build_workspace_onboarding_slots(db, workspace)
    calendar_slots = build_workspace_calendar_slots(
        db, workspace, target_today.year
    )

    items = compute_attention_items(onboarding_slots, calendar_slots, target_today)
    return {
        "items": items,
        "workspace_id": workspace.id,
        "fetched_at": fetched_at,
    }


# ─── Upcoming deadlines (P1.4) ─────────────────────────────────


def compute_upcoming_deadlines(
    calendar_slots: list[SlotView],
    today: date,
    *,
    top: int = 5,
) -> list[dict]:
    """Plain-dict upcoming-deadlines list — mirrors
    ``portal._compute_upcoming_deadlines``.

    Rules:

    - Required calendar slots only.
    - Skip resolved states (approved / exception / not_applicable).
    - Skip undated or already-overdue slots
      (``due_in_days is None or < 0``).
    - Sort ascending by ``due_in_days``.
    - Cap at ``top`` (default 5, matches the dashboard hero behaviour).

    Each item also exposes ``due_in_days`` (which the portal endpoint
    doesn't surface) so the renderer can lay items on a visual
    urgency timeline without re-parsing the period_key.
    """
    rows: list[tuple[int, dict]] = []
    for view in calendar_slots:
        if not view.required:
            continue
        if view.state in RESOLVED_SLOT_STATES:
            continue
        due_in = due_in_days_for_period(view.period_key, today)
        if due_in is None or due_in < 0:
            continue
        deadline_month = today.month
        if view.period_key and "-M" in view.period_key:
            try:
                deadline_month = int(view.period_key.split("-M", 1)[1])
            except ValueError:
                deadline_month = today.month
        rows.append(
            (
                due_in,
                {
                    "id": f"due-{view.requirement_code}-{view.period_key}",
                    "title": (
                        view.requirement_name
                        or view.requirement_code
                        or "Obligación"
                    ),
                    "institution": view.institution or "—",
                    "period_key": view.period_key,
                    "due_month": deadline_month,
                    "due_in_days": due_in,
                    "state": view.state.value,
                    "href": calendar_reupload_href(view),
                    "requirement_code": view.requirement_code,
                },
            )
        )
    rows.sort(key=lambda r: r[0])
    return [r[1] for r in rows[:top]]


# Urgency bands the renderer maps to visual segments. Public for
# tests + (eventually) the frontend block can render the same labels.
URGENCY_BANDS: tuple[dict, ...] = (
    {"key": "week", "label": "Esta semana", "max_days": 7},
    {"key": "fortnight", "label": "2 semanas", "max_days": 14},
    {"key": "month", "label": "Este mes", "max_days": 30},
    {"key": "later", "label": "Más adelante", "max_days": None},
)


def bucket_upcoming_by_urgency(items: list[dict]) -> dict[str, int]:
    """Count how many ``upcoming_deadlines`` items fall in each urgency
    band. Drives the renderer's timeline / sparkline strip.

    Each item must carry ``due_in_days`` (always present for items
    produced by ``compute_upcoming_deadlines``). Items missing the
    field land in ``later`` so the bucket counts are always
    well-formed.
    """
    counts = {band["key"]: 0 for band in URGENCY_BANDS}
    for it in items:
        due = it.get("due_in_days")
        if due is None:
            counts["later"] += 1
            continue
        placed = False
        for band in URGENCY_BANDS:
            cap = band["max_days"]
            if cap is None or due <= cap:
                counts[band["key"]] += 1
                placed = True
                break
        if not placed:
            counts["later"] += 1
    return counts


def build_upcoming_deadlines_for_vendor(
    db: Session,
    *,
    vendor_id: str,
    today: date | None = None,
    top: int = 5,
) -> dict:
    """Compose the upcoming-deadlines payload for one vendor.

    Returns:

    ```
    {
      "items": [{id, title, institution, period_key, due_month,
                 due_in_days, state, href, requirement_code}],
      "urgency_buckets": {"week": int, "fortnight": int,
                          "month": int, "later": int},
      "workspace_id": str | None,
      "fetched_at": str,
      "as_of": str,                # ISO date of ``today``
    }
    ```
    """
    workspace = resolve_workspace_for_vendor(db, vendor_id)
    fetched_at = datetime.utcnow().isoformat() + "Z"
    if workspace is None:
        return {
            "items": [],
            "urgency_buckets": {b["key"]: 0 for b in URGENCY_BANDS},
            "workspace_id": None,
            "fetched_at": fetched_at,
            "as_of": (today or date.today()).isoformat(),
        }

    target_today = today or date.today()
    calendar_slots = build_workspace_calendar_slots(
        db, workspace, target_today.year
    )
    items = compute_upcoming_deadlines(calendar_slots, target_today, top=top)
    return {
        "items": items,
        "urgency_buckets": bucket_upcoming_by_urgency(items),
        "workspace_id": workspace.id,
        "fetched_at": fetched_at,
        "as_of": target_today.isoformat(),
    }


# ─── Suggested / prioritized actions (P1.5) ────────────────────


def action_title_for_state(view: SlotView) -> str:
    """Canonical title for a remediation action, by slot state.

    Mirrors ``portal._action_title_for_state``. Public so the block
    fetcher can build the same headline the dashboard hero shows.
    """
    if view.state is SlotState.REJECTED:
        return f"Corrige el documento rechazado: {view.requirement_name}"
    if view.state is SlotState.NEEDS_CORRECTION:
        return f"Aclara el documento: {view.requirement_name}"
    if view.state is SlotState.POSSIBLE_MISMATCH:
        return f"Verifica el documento: {view.requirement_name}"
    return view.requirement_name or "Acción requerida"


def action_body_for_state(view: SlotView) -> str:
    """Canonical one-paragraph body for a remediation action.

    Mirrors ``portal._action_body_for_state``. Deterministic — no LLM
    in the loop. The block's renderer can layer an optional AI
    rewrite on top in a future slice without changing the contract.
    """
    if view.state is SlotState.REJECTED:
        return (
            "El revisor rechazó esta entrega. Vuelve a cargar una versión "
            "corregida; CheckWise enlazará la nueva carga con la anterior."
        )
    if view.state is SlotState.NEEDS_CORRECTION:
        return (
            "El revisor pidió una aclaración. Sube una nueva versión o "
            "responde la observación."
        )
    if view.state is SlotState.POSSIBLE_MISMATCH:
        return (
            "Las señales automáticas detectaron una posible inconsistencia. "
            "Verifica el archivo y vuelve a cargar si fue equivocado."
        )
    return ""


def compute_renewal_actions(
    db: Session,
    workspace: ProviderWorkspace,
    today: date,
) -> list[dict]:
    """Phase 6D — renewal-driven action items for the dashboard rail.

    Walks the workspace's renewal-bearing onboarding requirements
    (CSF / REPSE / registro patronal — the rows that carry
    ``renewal_frequency_days`` in the catalog), resolves the standing
    approved submission, and emits one suggested-action dict per
    requirement whose renewal status is ``due_soon`` or ``overdue``.

    Action shape matches the rest of the suggested-actions pipeline
    (id / type="renewal" / title / body / priority / href /
    requirement_code / period_key=None). Overdue items use
    ``priority="high"`` to compete with blocking/expired actions;
    due_soon items use ``priority="medium"`` to compete with
    missing-onboarding and the 5-day upcoming-calendar tier.

    Returns items in this order so callers that simply concatenate
    get a sensible priority sort:
      * overdue (most-recently-due first)
      * due_soon (soonest-due first)

    Read-only. The dispatcher writes notifications + reminders; this
    function only reads the same state the cron job derives its
    emit-set from, so the dashboard never lies about what was sent.
    """
    persona = normalize_persona_type(workspace.persona_type)
    overdue: list[tuple[int, dict]] = []
    due_soon: list[tuple[int, dict]] = []

    for req in expediente_for_persona(persona):
        if req.renewal_frequency_days is None:
            continue
        sub = current_onboarding_submission_for_workspace(
            db, workspace=workspace, requirement_code=req.code
        )
        anchor = renewal_anchor_date(sub)
        due = next_renewal_due_date(
            anchor=anchor, frequency_days=req.renewal_frequency_days
        )
        status = renewal_status(due, today)
        if status not in ("due_soon", "overdue") or due is None:
            continue
        days_remaining = (due - today).days
        href = f"/portal/upload?requirement_code={req.code}&from=renewal"
        if status == "overdue":
            days_overdue = -days_remaining
            overdue.append(
                (
                    days_remaining,
                    {
                        "id": f"act-{req.code}-renewal-overdue",
                        "type": "renewal",
                        "title": (
                            f"Renueva tu {req.name} — vencido"
                            if days_overdue > 0
                            else f"Renueva tu {req.name} — vence hoy"
                        ),
                        "body": (
                            f"Tu {req.name} venció el {due.isoformat()} "
                            f"(hace {days_overdue} día(s)). Sube la versión "
                            "actualizada lo antes posible para regularizar "
                            "tu expediente."
                            if days_overdue > 0
                            else (
                                f"Tu {req.name} vence hoy. Sube la versión "
                                "actualizada para que tu cliente no marque "
                                "el expediente como vencido."
                            )
                        ),
                        "priority": "high",
                        "href": href,
                        "requirement_code": req.code,
                        "period_key": None,
                    },
                )
            )
        else:  # due_soon
            due_soon.append(
                (
                    days_remaining,
                    {
                        "id": f"act-{req.code}-renewal-due-soon",
                        "type": "renewal",
                        "title": (
                            f"Renueva tu {req.name} — faltan "
                            f"{days_remaining} día(s)"
                        ),
                        "body": (
                            f"Tu {req.name} vence el {due.isoformat()}. "
                            "Sube la versión actualizada para mantener tu "
                            "expediente al corriente."
                        ),
                        "priority": "medium",
                        "href": href,
                        "requirement_code": req.code,
                        "period_key": None,
                    },
                )
            )

    # Overdue: most-recently-due first (largest negative days_remaining
    # is "barely overdue"; smallest negative is "long overdue"). Newer
    # overdue items go first because they're more actionable —
    # a 28-day-overdue CSF is past the point a same-day upload can
    # close.
    overdue.sort(key=lambda pair: pair[0], reverse=True)
    # Due-soon: soonest-due first.
    due_soon.sort(key=lambda pair: pair[0])

    return [item for _, item in overdue] + [item for _, item in due_soon]


def compute_suggested_actions(
    onboarding_slots: list[SlotView],
    calendar_slots: list[SlotView],
    today: date,
    *,
    onboarding_completed: bool = False,
    renewal_actions: list[dict] | None = None,
) -> list[dict]:
    """Plain-dict suggested-actions list — mirrors
    ``portal._compute_suggested_actions``.

    Five-pass priority pipeline (the renewal passes were added in
    Phase 6D; earlier callers that don't pass ``renewal_actions``
    see identical behavior):

    1. Required actionable slots (rejected / needs_correction /
       possible_mismatch) → ``priority="high"``, type matches state.
    2. Missing required onboarding slots → ``complete_onboarding`` /
       ``priority="medium"``. **Skipped when the workspace's
       ``onboarding_completed_at`` is set (P1.3, 2026-05-20):** once
       the operator marks the initial expediente complete, surfacing
       onboarding docs as "next steps" misleads the provider into
       thinking their workspace regressed.
    2.5. Expired (vencido) calendar slots → ``regularize`` / ``high``.
    2.6. Overdue renewals from ``renewal_actions`` (Phase 6D) →
         alongside expired, ``priority="high"``.
    3. Required calendar slots due within 14 days, still missing →
       ``upcoming`` / ``medium`` if ≤ 5 days, ``low`` otherwise.
    3.5. Due-soon renewals from ``renewal_actions`` (Phase 6D) →
         after upcoming-calendar, ``priority="medium"``.

    The renewal passes preserve the order ``compute_renewal_actions``
    returned (overdue most-recent first, due_soon soonest first), so
    callers that pre-sort get a deterministic interleave.

    Capped at 5 entries (matches the dashboard hero behaviour).
    """
    actions: list[dict] = []
    # 1. Blocking states.
    for view in onboarding_slots + calendar_slots:
        if not view.required:
            continue
        if view.state not in ACTIONABLE_SLOT_STATES:
            continue
        is_onboarding = view.slot_key.period_key is None
        action_type = (
            "verify_mismatch"
            if view.state is SlotState.POSSIBLE_MISMATCH
            else "clarify"
            if view.state is SlotState.NEEDS_CORRECTION
            else "reupload"
        )
        actions.append(
            {
                "id": f"act-{view.requirement_code}-{view.period_key or 'onb'}",
                "type": action_type,
                "title": action_title_for_state(view),
                "body": action_body_for_state(view),
                "priority": "high",
                "href": (
                    onboarding_reupload_href(view)
                    if is_onboarding
                    else calendar_reupload_href(view)
                ),
                "requirement_code": view.requirement_code,
                "period_key": view.period_key,
            }
        )
    # 2. Missing onboarding — suppressed once onboarding is complete.
    if not onboarding_completed:
        for view in onboarding_slots:
            if not view.required or view.state is not SlotState.MISSING:
                continue
            actions.append(
                {
                    "id": f"act-{view.requirement_code}-missing",
                    "type": "complete_onboarding",
                    "title": f"Sube tu documento: {view.requirement_name}",
                    "body": (
                        "Este documento es obligatorio para terminar tu expediente "
                        "inicial."
                    ),
                    "priority": "medium",
                    "href": onboarding_reupload_href(view),
                    "requirement_code": view.requirement_code,
                    "period_key": None,
                }
            )
    # 2.5. Expired (vencido) calendar slots — high priority.
    # P1-c (2026-05-20): the catalog window already closed without an
    # acuse. Surface a "regularize" CTA so the provider sees the
    # missed obligation in their action list instead of it sitting
    # silently as EXPIRED only on the dashboard slot resolver.
    for view in calendar_slots:
        if not view.required or view.state is not SlotState.EXPIRED:
            continue
        actions.append(
            {
                "id": f"act-{view.requirement_code}-{view.period_key}-expired",
                "type": "regularize",
                "title": f"Regulariza el documento vencido: {view.requirement_name}",
                "body": (
                    "El plazo de esta obligación pasó sin que se subiera "
                    "el acuse. Trabaja con tu contador para regularizarla "
                    "y carga el comprobante aquí."
                ),
                "priority": "high",
                "href": calendar_reupload_href(view),
                "requirement_code": view.requirement_code,
                "period_key": view.period_key,
            }
        )
    # 2.6. Overdue renewals (Phase 6D) — same priority tier as
    # expired calendar items. ``compute_renewal_actions`` returns
    # overdue rows first, so we filter on priority to drop them
    # in here.
    if renewal_actions:
        for action in renewal_actions:
            if action.get("priority") == "high":
                actions.append(action)
    # 3. Upcoming calendar (within 14 days).
    for view in calendar_slots:
        if not view.required or view.state is not SlotState.MISSING:
            continue
        due_in = due_in_days_for_period(view.period_key, today)
        if due_in is None or due_in < 0 or due_in > 14:
            continue
        actions.append(
            {
                "id": f"act-{view.requirement_code}-{view.period_key}-upcoming",
                "type": "upcoming",
                "title": f"Próximo vencimiento: {view.requirement_name}",
                "body": (
                    f"Tienes {due_in} día(s) para subir este documento del "
                    f"periodo {view.period_key}."
                ),
                "priority": "medium" if due_in <= 5 else "low",
                "href": calendar_reupload_href(view),
                "requirement_code": view.requirement_code,
                "period_key": view.period_key,
            }
        )
    # 3.5. Due-soon renewals (Phase 6D) — medium priority, alongside
    # missing onboarding + 5-day upcoming.
    if renewal_actions:
        for action in renewal_actions:
            if action.get("priority") == "medium":
                actions.append(action)
    return actions[:5]


def build_suggested_actions_for_vendor(
    db: Session,
    *,
    vendor_id: str,
    today: date | None = None,
) -> dict:
    """Compose the suggested-actions payload for one vendor.

    Returns:

    ```
    {
      "items": [{id, type, title, body, priority, href,
                 requirement_code, period_key}],
      "workspace_id": str | None,
      "fetched_at": str,
      "as_of": str,
    }
    ```
    """
    workspace = resolve_workspace_for_vendor(db, vendor_id)
    fetched_at = datetime.utcnow().isoformat() + "Z"
    if workspace is None:
        return {
            "items": [],
            "workspace_id": None,
            "fetched_at": fetched_at,
            "as_of": (today or date.today()).isoformat(),
        }

    target_today = today or date.today()
    onboarding_slots = build_workspace_onboarding_slots(db, workspace)
    calendar_slots = build_workspace_calendar_slots(
        db, workspace, target_today.year
    )

    renewal_actions = compute_renewal_actions(db, workspace, target_today)
    items = compute_suggested_actions(
        onboarding_slots,
        calendar_slots,
        target_today,
        onboarding_completed=workspace.onboarding_completed_at is not None,
        renewal_actions=renewal_actions,
    )
    return {
        "items": items,
        "workspace_id": workspace.id,
        "fetched_at": fetched_at,
        "as_of": target_today.isoformat(),
    }
