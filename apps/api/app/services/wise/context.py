"""Wise copilot — server-side context assembly (Phase 3).

Before Phase 3, the dock shipped a curated 500-token state digest to
``/wise/ask``. That was enough to answer "how am I doing?" but
nothing about the documents themselves, the REPSE calendar, or how
CheckWise works. Phase 3 moves context assembly to the backend so
Wise sees:

  * The provider's full workspace state (onboarding slots + current-
    year calendar + last 10 submissions + reviewer notes).
  * The relevant slice of the REPSE catalog (per-requirement
    anatomy, where-to-obtain, common errors) for every slot in the
    expediente — both onboarding and recurring for the active year.
  * A short CheckWise system glossary (statuses, workflow concepts,
    page map, common doc types) so Wise can explain how the
    platform works, not just what's in the user's account.

Everything except the per-user state goes through Anthropic prompt
caching (5-minute TTL) so the catalog + glossary are billed once
and then amortized across all questions from any vendor for the
cache window. See ``app.services.wise.ai`` for how this assembled
context is turned into the actual LLM call.

Pure functions, no FastAPI deps, no I/O beyond what the caller's
DB session does. Trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.compliance_catalog import (
    OnboardingRequirement,
    RecurringRequirement,
    expediente_for_persona,
    normalize_persona_type,
    onboarding_anatomy,
    onboarding_common_errors,
    onboarding_format,
    onboarding_where_to_obtain,
    onboarding_why,
    recurring_anatomy,
    recurring_common_errors,
    recurring_for_year,
    recurring_required_document,
    recurring_where_to_obtain,
)
from app.models import ProviderWorkspace, Submission, ValidationEvent
from app.services.evidence_slots import (
    SlotState,
    SlotView,
    build_workspace_calendar_slots,
    build_workspace_onboarding_slots,
)

# ───────────────────────────────────────────────────────────────────
# Dataclasses
# ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class WiseSlotSnapshot:
    """One row in the workspace's state — onboarding or recurring."""

    kind: str  # "onboarding" | "calendar"
    requirement_code: str
    requirement_name: str
    institution: str
    period_key: str | None
    state: str  # SlotState value
    state_label_es: str  # Spanish label so the model never has to translate
    current_submission_id: str | None
    submitted_at_iso: str | None
    reviewer_note: str | None


@dataclass(frozen=True)
class WiseRecentUploadSnapshot:
    submission_id: str
    requirement_name: str
    institution: str
    period_key: str | None
    status: str
    submitted_at_iso: str
    filename: str | None
    reviewer_note: str | None


@dataclass(frozen=True)
class WiseCatalogEntry:
    """Per-document guidance text the model can reference."""

    code: str
    name: str
    institution: str
    why: str
    format: str
    anatomy: str
    where_to_obtain: str
    common_errors: tuple[str, ...]
    section: str  # "expediente_inicial" | "calendario"
    frequency: str | None = None  # only for recurring


@dataclass(frozen=True)
class WiseWorkspaceContext:
    """Per-user dynamic context. Re-built every request, NOT cached."""

    vendor_name: str
    vendor_rfc: str
    persona_type: str
    client_name: str
    onboarding_completed: bool
    onboarding_completed_at_iso: str | None
    compliance_pct: int
    on_track: int
    total_tracked: int
    needs_action_count: int
    in_review_count: int
    approved_count: int
    pending_count: int
    rejected_count: int
    expired_count: int
    onboarding_slots: tuple[WiseSlotSnapshot, ...]
    calendar_slots: tuple[WiseSlotSnapshot, ...]
    recent_uploads: tuple[WiseRecentUploadSnapshot, ...]


@dataclass(frozen=True)
class WiseStaticContext:
    """Cacheable, vendor-agnostic context. System rules + glossary +
    full catalog guidance for the active year. Re-used across all
    requests; the Anthropic SDK call attaches ``cache_control`` here."""

    glossary: str
    catalog_entries: tuple[WiseCatalogEntry, ...]


# ───────────────────────────────────────────────────────────────────
# Spanish labels — kept here so the model sees ready-to-quote copy
# instead of inventing translations from the raw enum.
# ───────────────────────────────────────────────────────────────────


_STATE_LABEL_ES: dict[str, str] = {
    SlotState.MISSING.value: "pendiente (sin subir)",
    SlotState.UPLOADED.value: "recibido (en cola de revisión)",
    SlotState.IN_REVIEW.value: "en revisión legal",
    SlotState.APPROVED.value: "aprobado",
    SlotState.REJECTED.value: "rechazado",
    SlotState.NEEDS_CORRECTION.value: "requiere aclaración del proveedor",
    SlotState.POSSIBLE_MISMATCH.value: "posible inconsistencia detectada",
    SlotState.EXPIRED.value: "vencido",
    SlotState.EXCEPTION.value: "excepción legal aprobada",
    SlotState.NOT_APPLICABLE.value: "no aplica",
}


_INSTITUTION_LABEL_ES: dict[str, str] = {
    "sat": "SAT",
    "imss": "IMSS",
    "infonavit": "INFONAVIT",
    "stps_repse": "STPS / REPSE",
    "interno_cliente": "Interno / Cliente",
}


# ───────────────────────────────────────────────────────────────────
# Public builders
# ───────────────────────────────────────────────────────────────────


def build_workspace_context(
    db: Session,
    workspace: ProviderWorkspace,
    *,
    year: int | None = None,
    recent_uploads_limit: int = 10,
) -> WiseWorkspaceContext:
    """Assemble the per-user dynamic context.

    Reads the same evidence-slot service the dashboard endpoint
    uses, so what Wise tells the user about state matches every
    other surface exactly. No new DB tables, no new services —
    just composing existing read models.
    """
    today = date.today()
    target_year = year or today.year
    persona = normalize_persona_type(workspace.persona_type)

    onboarding_slots = build_workspace_onboarding_slots(db, workspace)
    calendar_slots = build_workspace_calendar_slots(db, workspace, target_year)

    # Reviewer notes per current submission, batch-loaded so we
    # don't N+1 the validation_events table on big workspaces.
    submission_ids = [
        view.current_submission_id
        for view in (*onboarding_slots, *calendar_slots)
        if view.current_submission_id is not None
    ]
    notes_by_submission = _load_reviewer_notes(db, submission_ids)

    onboarding_snapshots = tuple(
        _slot_to_snapshot(view, "onboarding", notes_by_submission)
        for view in onboarding_slots
    )
    calendar_snapshots = tuple(
        _slot_to_snapshot(view, "calendar", notes_by_submission)
        for view in calendar_slots
    )

    counts = _bucket_counts(onboarding_slots, calendar_slots)
    on_track = counts["approved_required"] + counts["exception_required"]
    total_tracked = counts["required"]
    compliance_pct = (
        100 if total_tracked == 0 else round(on_track / total_tracked * 100)
    )

    recent_uploads = _build_recent_uploads(
        db, workspace, notes_by_submission, limit=recent_uploads_limit
    )

    return WiseWorkspaceContext(
        vendor_name=workspace.display_name or "",
        vendor_rfc=workspace.vendor.rfc if workspace.vendor else "",
        persona_type=persona,
        client_name=workspace.client.name if workspace.client else "",
        onboarding_completed=workspace.onboarding_completed_at is not None,
        onboarding_completed_at_iso=(
            workspace.onboarding_completed_at.isoformat()
            if workspace.onboarding_completed_at is not None
            else None
        ),
        compliance_pct=compliance_pct,
        on_track=on_track,
        total_tracked=total_tracked,
        needs_action_count=counts["needs_action"],
        in_review_count=counts["in_review"],
        approved_count=counts["approved"],
        pending_count=counts["pending"],
        rejected_count=counts["rejected"],
        expired_count=counts["expired"],
        onboarding_slots=onboarding_snapshots,
        calendar_slots=calendar_snapshots,
        recent_uploads=recent_uploads,
    )


def build_static_context(
    *,
    persona_types: tuple[str, ...] = ("moral", "fisica"),
    year: int | None = None,
) -> WiseStaticContext:
    """Build the cacheable static context.

    Includes the CheckWise glossary + catalog guidance for every
    onboarding requirement (both personas, since cache hits require
    byte-identical prefixes) and every recurring requirement for
    the active year.
    """
    target_year = year or date.today().year
    entries: list[WiseCatalogEntry] = []
    seen_codes: set[str] = set()

    for persona in persona_types:
        normalized = normalize_persona_type(persona)
        for req in expediente_for_persona(normalized):
            if req.code in seen_codes:
                continue
            seen_codes.add(req.code)
            entries.append(_onboarding_to_catalog(req))

    for req in recurring_for_year(target_year):
        if req.code in seen_codes:
            continue
        seen_codes.add(req.code)
        entries.append(_recurring_to_catalog(req))

    return WiseStaticContext(
        glossary=_CHECKWISE_GLOSSARY_ES,
        catalog_entries=tuple(entries),
    )


# ───────────────────────────────────────────────────────────────────
# Prompt rendering
# ───────────────────────────────────────────────────────────────────


def render_static_block(ctx: WiseStaticContext) -> str:
    """Render the static (cacheable) portion of the system prompt."""
    parts = [
        "# Glosario operativo de CheckWise",
        "",
        ctx.glossary.strip(),
        "",
        "# Catálogo de documentos REPSE",
        "",
        (
            "Lista de cada documento que CheckWise puede solicitarle al "
            "proveedor, con guía operativa (qué contiene, dónde se "
            "obtiene, errores comunes). Úsala como referencia cuando "
            "el proveedor pregunte sobre un documento específico."
        ),
        "",
    ]
    # Group by institution so the model can scan quickly.
    by_institution: dict[str, list[WiseCatalogEntry]] = {}
    for entry in ctx.catalog_entries:
        by_institution.setdefault(entry.institution, []).append(entry)
    for institution in (
        "sat",
        "imss",
        "infonavit",
        "stps_repse",
        "interno_cliente",
    ):
        items = by_institution.get(institution, [])
        if not items:
            continue
        parts.append(f"## {_INSTITUTION_LABEL_ES.get(institution, institution.upper())}")
        parts.append("")
        for entry in items:
            parts.append(_render_catalog_entry(entry))
            parts.append("")
    return "\n".join(parts).strip()


def render_workspace_block(ctx: WiseWorkspaceContext) -> str:
    """Render the per-request dynamic block."""
    lines = [
        "# Estado actual del proveedor",
        "",
        f"- Razón social: {ctx.vendor_name}",
        f"- RFC: {ctx.vendor_rfc}",
        f"- Persona: {'moral' if ctx.persona_type == 'moral' else 'física'}",
        f"- Cliente CheckWise: {ctx.client_name}",
        f"- Expediente inicial: {'completo' if ctx.onboarding_completed else 'incompleto'}"
        + (
            f" (cerrado el {ctx.onboarding_completed_at_iso[:10]})"
            if ctx.onboarding_completed_at_iso
            else ""
        ),
        f"- Cumplimiento global: {ctx.compliance_pct}% ({ctx.on_track}/{ctx.total_tracked} obligaciones al día)",
        f"- Aprobados: {ctx.approved_count}",
        f"- En revisión: {ctx.in_review_count}",
        f"- Por atender (rechazado / aclaración / vencido / por subir): {ctx.needs_action_count}",
        f"- Pendientes (sin subir): {ctx.pending_count}",
        f"- Rechazados: {ctx.rejected_count}",
        f"- Vencidos: {ctx.expired_count}",
        "",
    ]

    if ctx.onboarding_slots:
        lines.append("## Expediente inicial (todos los slots obligatorios)")
        lines.append("")
        for slot in ctx.onboarding_slots:
            lines.append(_render_slot_line(slot))
        lines.append("")

    if ctx.calendar_slots:
        active_calendar = [
            s
            for s in ctx.calendar_slots
            if s.state != SlotState.NOT_APPLICABLE.value
        ]
        if active_calendar:
            lines.append("## Calendario REPSE del año actual")
            lines.append("")
            for slot in active_calendar:
                lines.append(_render_slot_line(slot))
            lines.append("")

    if ctx.recent_uploads:
        lines.append("## Últimas cargas del proveedor (hasta 10)")
        lines.append("")
        for upload in ctx.recent_uploads:
            tail = (
                f" — observación del revisor: \"{upload.reviewer_note}\""
                if upload.reviewer_note
                else ""
            )
            lines.append(
                f"- {upload.submitted_at_iso[:10]} | "
                f"{_INSTITUTION_LABEL_ES.get(upload.institution, upload.institution.upper())} | "
                f"{upload.requirement_name}"
                + (f" (periodo {upload.period_key})" if upload.period_key else "")
                + f" | estado: {_STATE_LABEL_ES.get(upload.status, upload.status)}"
                + (f" | archivo: {upload.filename}" if upload.filename else "")
                + tail
            )
        lines.append("")

    return "\n".join(lines).strip()


# ───────────────────────────────────────────────────────────────────
# Internals
# ───────────────────────────────────────────────────────────────────


def _slot_to_snapshot(
    view: SlotView,
    kind: str,
    notes_by_submission: dict[str, str],
) -> WiseSlotSnapshot:
    state_value = view.state.value
    return WiseSlotSnapshot(
        kind=kind,
        requirement_code=view.requirement_code or "",
        requirement_name=view.requirement_name or view.requirement_code or "",
        institution=view.institution or "",
        period_key=view.period_key,
        state=state_value,
        state_label_es=_STATE_LABEL_ES.get(state_value, state_value),
        current_submission_id=view.current_submission_id,
        submitted_at_iso=view.submitted_at_iso,
        reviewer_note=(
            notes_by_submission.get(view.current_submission_id)
            if view.current_submission_id
            else None
        ),
    )


def _render_slot_line(slot: WiseSlotSnapshot) -> str:
    institution = _INSTITUTION_LABEL_ES.get(
        slot.institution, slot.institution.upper() if slot.institution else "—"
    )
    period = f" (periodo {slot.period_key})" if slot.period_key else ""
    note = (
        f" — nota del revisor: \"{slot.reviewer_note}\""
        if slot.reviewer_note
        else ""
    )
    return f"- {institution} · {slot.requirement_name}{period} → {slot.state_label_es}{note}"


def _bucket_counts(
    onboarding_slots: list[SlotView], calendar_slots: list[SlotView]
) -> dict[str, int]:
    approved = 0
    in_review = 0
    needs_action = 0
    pending = 0
    rejected = 0
    expired = 0
    required_total = 0
    approved_required = 0
    exception_required = 0
    for view in (*onboarding_slots, *calendar_slots):
        if view.required:
            required_total += 1
        s = view.state
        if s in (SlotState.APPROVED, SlotState.EXCEPTION, SlotState.NOT_APPLICABLE):
            approved += 1
            if view.required and s is SlotState.APPROVED:
                approved_required += 1
            if view.required and s is SlotState.EXCEPTION:
                exception_required += 1
        elif s in (SlotState.IN_REVIEW, SlotState.UPLOADED):
            in_review += 1
        elif s in (
            SlotState.REJECTED,
            SlotState.NEEDS_CORRECTION,
            SlotState.POSSIBLE_MISMATCH,
        ):
            needs_action += 1
            if s is SlotState.REJECTED:
                rejected += 1
        elif s is SlotState.EXPIRED:
            needs_action += 1
            expired += 1
        elif s is SlotState.MISSING:
            pending += 1
            if view.required:
                needs_action += 1
    return {
        "approved": approved,
        "in_review": in_review,
        "needs_action": needs_action,
        "pending": pending,
        "rejected": rejected,
        "expired": expired,
        "required": required_total,
        "approved_required": approved_required,
        "exception_required": exception_required,
    }


def _build_recent_uploads(
    db: Session,
    workspace: ProviderWorkspace,
    notes_by_submission: dict[str, str],
    *,
    limit: int,
) -> tuple[WiseRecentUploadSnapshot, ...]:
    stmt = (
        select(Submission)
        .where(
            Submission.client_id == workspace.client_id,
            Submission.vendor_id == workspace.vendor_id,
        )
        .order_by(Submission.created_at.desc())
        .limit(limit)
    )
    out: list[WiseRecentUploadSnapshot] = []
    for sub in db.scalars(stmt):
        requirement_name = ""
        institution_code = ""
        if sub.requirement is not None:
            requirement_name = sub.requirement.name
            institution_code = (
                sub.requirement.institution.code
                if sub.requirement.institution is not None
                else ""
            )
        filename = None
        if sub.documents:
            latest_doc = sorted(
                sub.documents, key=lambda d: d.created_at, reverse=True
            )[0]
            filename = latest_doc.original_filename
        out.append(
            WiseRecentUploadSnapshot(
                submission_id=sub.id,
                requirement_name=requirement_name or sub.requirement_code or "—",
                institution=institution_code,
                period_key=sub.period_key,
                status=sub.status,
                submitted_at_iso=_iso(sub.created_at),
                filename=filename,
                reviewer_note=notes_by_submission.get(sub.id),
            )
        )
    return tuple(out)


def _load_reviewer_notes(
    db: Session, submission_ids: list[str]
) -> dict[str, str]:
    if not submission_ids:
        return {}
    stmt = (
        select(ValidationEvent)
        .where(
            ValidationEvent.submission_id.in_(submission_ids),
            ValidationEvent.event_type == "reviewer_decision",
        )
        .order_by(ValidationEvent.created_at.desc())
    )
    notes: dict[str, str] = {}
    for event in db.scalars(stmt):
        if event.submission_id in notes:
            continue  # already kept the newest
        message = (event.message or "").strip()
        if message:
            notes[event.submission_id] = message
    return notes


def _onboarding_to_catalog(req: OnboardingRequirement) -> WiseCatalogEntry:
    return WiseCatalogEntry(
        code=req.code,
        name=req.name,
        institution=req.institution,
        why=onboarding_why(req),
        format=onboarding_format(req),
        anatomy=onboarding_anatomy(req),
        where_to_obtain=onboarding_where_to_obtain(req),
        common_errors=onboarding_common_errors(req),
        section="expediente_inicial",
        frequency=None,
    )


def _recurring_to_catalog(req: RecurringRequirement) -> WiseCatalogEntry:
    return WiseCatalogEntry(
        code=req.code,
        name=req.name,
        institution=req.institution,
        why="",  # recurring catalog uses required_document below
        format=recurring_required_document(req),
        anatomy=recurring_anatomy(req),
        where_to_obtain=recurring_where_to_obtain(req),
        common_errors=recurring_common_errors(req),
        section="calendario",
        frequency=req.frequency,
    )


def _render_catalog_entry(entry: WiseCatalogEntry) -> str:
    lines = [f"### {entry.name}"]
    lines.append(f"- Código: `{entry.code}`")
    lines.append(
        "- Sección: "
        + ("Expediente inicial" if entry.section == "expediente_inicial" else "Calendario REPSE")
        + (f" ({entry.frequency})" if entry.frequency else "")
    )
    if entry.why:
        lines.append(f"- Para qué sirve: {entry.why}")
    if entry.format:
        lines.append(f"- Documento esperado: {entry.format}")
    if entry.anatomy:
        lines.append(f"- Qué debe contener: {entry.anatomy}")
    if entry.where_to_obtain:
        lines.append(f"- Dónde obtenerlo: {entry.where_to_obtain}")
    if entry.common_errors:
        bullets = "\n  - " + "\n  - ".join(entry.common_errors)
        lines.append(f"- Errores comunes:{bullets}")
    return "\n".join(lines)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


# ───────────────────────────────────────────────────────────────────
# Glossary — short, opinionated, in Spanish. Cached.
# ───────────────────────────────────────────────────────────────────


_CHECKWISE_GLOSSARY_ES = """\
CheckWise es la plataforma de Legal Shelf para gestionar el cumplimiento REPSE
de los proveedores en México. Estos son los conceptos que el proveedor usa
día a día:

**Expediente inicial**: el conjunto de documentos que el proveedor sube una sola
vez al darse de alta (acta constitutiva, REPSE, RFC del proveedor, contratos,
etc.). Se completa una vez y queda como base del cumplimiento.

**Calendario REPSE**: las obligaciones recurrentes (mensuales, bimestrales,
cuatrimestrales o anuales) que tiene que cumplir el proveedor a lo largo del
año — opinión SAT, opinión IMSS, opinión INFONAVIT, acuses, CFDI de nómina,
declaraciones, etc.

**Slot / obligación**: una celda concreta del calendario = un requisito × un
periodo. Por ejemplo, "Opinión IMSS de mayo 2026" es un slot distinto de
"Opinión IMSS de junio 2026". Cada slot tiene un solo estado y un solo
documento "actual" (la última carga válida).

**Estados de documento**:
- `pendiente`: el slot está vacío, no se ha subido nada.
- `recibido`: el proveedor acaba de cargar el archivo.
- `pendiente_revision` / `prevalidado`: la revisión legal está en curso.
- `aprobado`: el documento cumple, el slot cierra al verde.
- `rechazado`: el revisor lo regresó porque no cumple. Hay que volver a cargar.
- `requiere_aclaracion`: el revisor pide una aclaración del proveedor antes de
  decidir.
- `posible_mismatch`: las señales automáticas detectaron una inconsistencia
  (RFC distinto, período incorrecto, archivo bloqueado).
- `vencido`: el plazo conventional (día 17 del mes para mensuales y bimestrales,
  día 30 para anuales SAT) pasó sin que se cargara el acuse.
- `excepcion_legal`: el caso no aplica por una razón documentada (e.g. el
  proveedor no tiene trabajadores).

**Reemplazo / supersesión**: cuando un documento se rechaza o requiere
aclaración, el proveedor vuelve a cargar; CheckWise enlaza la nueva carga con
la anterior (`supersedes_submission_id`) para mantener el historial.

**Semáforo**:
- Verde: todas las obligaciones obligatorias están aprobadas.
- Amarillo: el expediente está en marcha, hay obligaciones pendientes o en
  revisión.
- Rojo: hay obligaciones críticas (rechazos, observaciones, mismatches o
  vencidos) que necesitan atención inmediata.

**Páginas del portal del proveedor**:
- `/portal/dashboard` — vista principal con KPIs, próximas acciones,
  vencimientos y el dock de Wise (este copiloto).
- `/portal/onboarding` — checklist del expediente inicial.
- `/portal/calendar` — calendario REPSE del año, mes por mes.
- `/portal/upload` — formulario para subir un documento contra un slot.
- `/portal/submissions` — listado y detalle por carga (timeline, evento de
  revisión, observaciones).
- `/portal/reports` — reportes ejecutivos generados por CheckWise.

**Soporte**: el proveedor puede usar el botón "Reportar" abajo a la derecha del
portal (no debe confundirse con el dock de Wise abajo a la izquierda), o
escribir directo al equipo de Legal Shelf.
"""
