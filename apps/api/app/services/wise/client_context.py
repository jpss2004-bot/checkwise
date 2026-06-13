"""Wise copilot — cliente (buyer) portfolio context.

Parallel to :mod:`app.services.wise.context`. Where the portal context
models ONE vendor's onboarding state, this module models the buyer
side: a client_admin (or internal_admin acting for that client) looking
at a PORTFOLIO of vendors with portfolio-level compliance shape.

Three top-level surfaces:

* :class:`WiseClientContext` — frozen dataclass carrying the per-request
  portfolio snapshot.
* :func:`build_client_context` — assembles it from the DB using the
  same evidence-slot service the cliente dashboard uses.
* :func:`render_client_state_block` — renders it as a Spanish prompt
  block for Claude Haiku. Kept tight (~80 lines of text) so a 50-vendor
  portfolio still fits comfortably in the model's input budget.

Phase 5 (2026-06-02) — landed alongside the cliente Wise dock as part
of the user-testing M1 milestone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

# These dashboard helpers live in the portal route module today
# (``_compute_semaphore``, ``_empty_document_counts``,
# ``_bucket_document_state``). Cross-API-module import is a known
# smell — a follow-up will hoist them into ``app.services.dashboard``
# so both surfaces import from the same canonical home. For M1 we
# accept the import to keep the cliente Wise context in lockstep with
# the cliente dashboard's semáforo math.
from app.api.v1.portal import (
    _bucket_document_state,
    _compute_semaphore,
    _empty_document_counts,
)
from app.models import Client, ProviderWorkspace, Vendor
from app.services.evidence_slots import (
    SlotState,
    build_workspace_calendar_slots,
    build_workspace_onboarding_slots,
)
from app.services.wise.context import (
    WiseWorkspaceContext,
    build_workspace_context,
    render_workspace_block,
)


@dataclass(frozen=True)
class WiseClientVendorRow:
    """One vendor's compact snapshot for the LLM portfolio block.

    Deliberately smaller than :class:`ClientVendorRow` (the API row) —
    fields here are picked for ranking + narrative grounding, not for
    UI rendering. The model never sees timestamps; it sees "hace 3
    días" etc. rendered inline.
    """

    vendor_id: str
    vendor_name: str
    vendor_rfc: str | None
    workspace_id: str
    compliance_pct: int
    semaphore_level: str  # "green" | "yellow" | "red"
    pending_reviews_count: int
    missing_required_count: int
    rejected_or_correction_count: int
    # P0 grounding (2026-06-12) — the NAMES behind the counts, so Wise
    # can answer "¿qué le falta a X?" with concrete documents instead
    # of "le faltan 3". Recurring slots carry their period inline
    # ("Opinión IMSS (2026-M05)"). Render caps how many are shown.
    missing_names: tuple[str, ...] = ()
    attention_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class WiseClientContext:
    """Portfolio-shaped state digest for the cliente Wise dock.

    Mirrors :class:`WiseWorkspaceContext` on the portal side. Built
    fresh per ``/client/wise/ask`` call from the canonical evidence-
    slot service so the numbers cannot drift from what the cliente
    dashboard shows.
    """

    client_id: str
    client_name: str
    client_rfc: str | None
    target_year: int
    today_iso: str

    vendor_count: int
    active_workspace_count: int
    green_count: int
    yellow_count: int
    red_count: int
    overall_compliance_pct: int
    pending_reviews_total: int
    rejected_or_correction_total: int
    missing_required_total: int

    vendors: list[WiseClientVendorRow] = field(default_factory=list)


def build_client_context(
    db: Session,
    client_row: Client,
    *,
    today: date | None = None,
) -> WiseClientContext:
    """Assemble the cliente Wise context from the canonical slot service.

    Walks every :class:`ProviderWorkspace` linked to the client and
    aggregates per-vendor counts into a portfolio summary. The result
    is a frozen dataclass safe to render multiple times without
    re-hitting the DB.
    """
    today = today or date.today()
    target_year = today.year

    workspaces = list(
        db.scalars(
            select(ProviderWorkspace)
            .where(ProviderWorkspace.client_id == client_row.id)
            .order_by(ProviderWorkspace.created_at.desc())
        )
    )
    vendor_ids = [w.vendor_id for w in workspaces]
    vendors_map: dict[str, Vendor] = {}
    if vendor_ids:
        vendors_map = {
            v.id: v
            for v in db.scalars(select(Vendor).where(Vendor.id.in_(vendor_ids)))
        }

    rows: list[WiseClientVendorRow] = []
    green = yellow = red = 0
    pending_total = rejected_total = missing_total = 0
    compliance_sum = 0
    active_count = 0

    for workspace in workspaces:
        vendor = vendors_map.get(workspace.vendor_id)
        if vendor is None:
            continue

        onboarding_slots = build_workspace_onboarding_slots(db, workspace)
        calendar_slots = build_workspace_calendar_slots(db, workspace, target_year)
        counts = _empty_document_counts()
        for view in onboarding_slots + calendar_slots:
            _bucket_document_state(counts, view.state)
        semaphore = _compute_semaphore(onboarding_slots, calendar_slots)

        required_views = [s for s in onboarding_slots if s.required] + [
            s for s in calendar_slots if s.required
        ]
        actionable_states = {
            SlotState.REJECTED,
            SlotState.NEEDS_CORRECTION,
            SlotState.POSSIBLE_MISMATCH,
            SlotState.EXPIRED,
        }
        missing_names: list[str] = []
        attention_names: list[str] = []
        pending = 0
        for view in required_views:
            label = view.requirement_name or view.requirement_code or "—"
            if view.period_key:
                label = f"{label} ({view.period_key})"
            if view.state is SlotState.MISSING:
                missing_names.append(label)
            elif view.state in actionable_states:
                attention_names.append(label)
            elif view.state in (SlotState.IN_REVIEW, SlotState.UPLOADED):
                pending += 1
        missing = len(missing_names)
        rejected = len(attention_names)

        rows.append(
            WiseClientVendorRow(
                vendor_id=vendor.id,
                vendor_name=vendor.name,
                vendor_rfc=vendor.rfc,
                workspace_id=workspace.id,
                compliance_pct=semaphore.compliance_pct,
                semaphore_level=semaphore.level,
                pending_reviews_count=pending,
                missing_required_count=missing,
                rejected_or_correction_count=rejected,
                missing_names=tuple(missing_names),
                attention_names=tuple(attention_names),
            )
        )

        if semaphore.level == "green":
            green += 1
        elif semaphore.level == "yellow":
            yellow += 1
        elif semaphore.level == "red":
            red += 1
        pending_total += pending
        rejected_total += rejected
        missing_total += missing
        compliance_sum += semaphore.compliance_pct
        active_count += 1

    overall_compliance_pct = (
        compliance_sum // active_count if active_count > 0 else 0
    )

    return WiseClientContext(
        client_id=client_row.id,
        client_name=client_row.name,
        client_rfc=getattr(client_row, "rfc", None),
        target_year=target_year,
        today_iso=today.isoformat(),
        vendor_count=len(workspaces),
        active_workspace_count=active_count,
        green_count=green,
        yellow_count=yellow,
        red_count=red,
        overall_compliance_pct=overall_compliance_pct,
        pending_reviews_total=pending_total,
        rejected_or_correction_total=rejected_total,
        missing_required_total=missing_total,
        vendors=rows,
    )


def build_vendor_focus(
    db: Session,
    client_row: Client,
    vendor_id: str,
) -> WiseWorkspaceContext | None:
    """Resolve the on-screen vendor into a full workspace context.

    Used when the cliente is on ``/client/vendors/{id}`` — the dock
    ships the vendor id and we ground Wise with the SAME per-vendor
    detail the portal Wise sees (named slots + states + due dates +
    recent uploads + reviewer notes), so "¿qué le falta a este
    proveedor?" gets a document-level answer.

    Tenant-guarded: the vendor must belong to ``client_row`` and have
    an active workspace; otherwise returns None and the caller omits
    the focus block.
    """
    workspace = db.scalar(
        select(ProviderWorkspace).where(
            ProviderWorkspace.client_id == client_row.id,
            ProviderWorkspace.vendor_id == vendor_id,
        )
    )
    if workspace is None:
        return None
    return build_workspace_context(db, workspace)


def render_vendor_focus_block(ctx: WiseWorkspaceContext) -> str:
    """Render the on-screen vendor as a prompt block.

    Reuses the portal-side workspace renderer (single source of truth
    for slot lines, due dates, and reviewer notes) under a cliente-
    shaped heading so the model knows this is the vendor the client
    is looking at, not the client's own state.
    """
    body = render_workspace_block(ctx)
    body = body.replace(
        "# Estado actual del proveedor",
        (
            "El cliente está viendo el detalle de ESTE proveedor. Si "
            "pregunta por \"este proveedor\" o pregunta sin nombrar a "
            "uno, se refiere a él:"
        ),
        1,
    )
    return "# Proveedor en pantalla\n\n" + body


# ─── LLM rendering ─────────────────────────────────────────────────


_SEMAPHORE_LABEL = {
    "green": "verde",
    "yellow": "amarillo",
    "red": "rojo",
}

# How many document names to inline per bucket in a vendor row. The
# counts are always exact; names beyond the cap collapse to "+N más"
# so a 50-vendor portfolio block stays within budget.
_MAX_NAMED_DOCS_PER_BUCKET = 4


def _names_suffix(names: tuple[str, ...]) -> str:
    """Render ": A, B, C (+2 más)" after a count, or "" when empty."""
    if not names:
        return ""
    shown = list(names[:_MAX_NAMED_DOCS_PER_BUCKET])
    overflow = len(names) - len(shown)
    suffix = f" (+{overflow} más)" if overflow > 0 else ""
    return ": " + ", ".join(shown) + suffix


def render_client_state_block(ctx: WiseClientContext) -> str:
    """Render the portfolio snapshot as a Markdown block for the LLM.

    Stable ordering (vendors sorted by red→yellow→green then by name)
    so the model can reliably point at "el peor proveedor" or "el
    primero de la lista" without us shipping a separate ranking.
    """
    parts: list[str] = []
    parts.append("# Cliente actual")
    parts.append("")
    parts.append(f"- Nombre: {ctx.client_name}")
    if ctx.client_rfc:
        parts.append(f"- RFC: `{ctx.client_rfc}`")
    parts.append(f"- Año fiscal de referencia: {ctx.target_year}")
    parts.append(f"- Fecha de hoy: {ctx.today_iso}")
    parts.append("")
    parts.append("# Resumen del portafolio")
    parts.append("")
    parts.append(f"- Proveedores totales: {ctx.vendor_count}")
    parts.append(f"- Proveedores con workspace activo: {ctx.active_workspace_count}")
    parts.append(f"- Cumplimiento promedio: {ctx.overall_compliance_pct}%")
    parts.append(
        f"- Semáforo: {ctx.green_count} verdes · "
        f"{ctx.yellow_count} amarillos · {ctx.red_count} rojos"
    )
    parts.append(f"- Revisiones en curso (todos los proveedores): {ctx.pending_reviews_total}")
    parts.append(
        f"- Documentos rechazados o con observación pendientes de corregir: "
        f"{ctx.rejected_or_correction_total}"
    )
    parts.append(f"- Documentos requeridos faltantes: {ctx.missing_required_total}")
    parts.append("")

    if ctx.vendors:
        ordered = sorted(
            ctx.vendors,
            key=lambda v: (
                {"red": 0, "yellow": 1, "green": 2}.get(v.semaphore_level, 3),
                v.vendor_name.casefold(),
            ),
        )
        parts.append("# Proveedores (peor a mejor)")
        parts.append("")
        for row in ordered:
            rfc = f" ({row.vendor_rfc})" if row.vendor_rfc else ""
            sem_label = _SEMAPHORE_LABEL.get(row.semaphore_level, row.semaphore_level)
            missing = _names_suffix(row.missing_names)
            attention = _names_suffix(row.attention_names)
            parts.append(
                f"- **{row.vendor_name}**{rfc} — {row.compliance_pct}% "
                f"({sem_label}). "
                f"Faltan {row.missing_required_count}{missing}; "
                f"{row.rejected_or_correction_count} con observación{attention}; "
                f"{row.pending_reviews_count} en revisión. "
                f"vendor_id=`{row.vendor_id}`"
            )
    else:
        parts.append("# Proveedores")
        parts.append("")
        parts.append(
            "(El portafolio aún no tiene proveedores con workspace activo.)"
        )

    return "\n".join(parts)
