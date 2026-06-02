"""Report preset registry — R1.0.

A preset is a starting point for a report: a fixed title, description,
audience, and an LLM-friendly ``recommended_prompt`` the user can hit
"Generate" on without having to write the prompt themselves.

Presets are NOT executed at creation time. Calling
``POST /api/v1/reports/from-preset`` produces an empty v1 ReportVersion
plus a ``plan_json`` hint; the user then hits the existing AI generation
flow to actually fill the blocks. Auto-running generation at creation
time is deferred to R1.0.1 — it requires a small server-side endpoint
that streams the executor against the recommended_prompt.

Each preset declares ``required_roles``: the membership roles that may
list and instantiate it. The API layer's ``GET /reports/_presets``
filters to only the ones the caller may use, so the frontend never has
to know the matrix.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.constants.reports import ReportAudience
from app.constants.roles import MembershipRole


@dataclass(frozen=True)
class ReportPreset:
    """One canned report starting point.

    The ``recommended_prompt`` is what the editor pre-fills into the
    "Generate with AI" textarea on first open. The AI planner sees
    exactly that string — same surface as a user-typed prompt — so the
    preset's behaviour stays fully observable.
    """

    id: str
    title: str
    description: str
    audience: ReportAudience
    required_roles: tuple[MembershipRole, ...]
    recommended_prompt: str


# ─── Admin presets (R1.0) ───────────────────────────────────────
#
# Three internal-only presets. Each targets a real operational
# question the review team answers today. Keep this set tight: the
# bar to add a fourth is "it has been used in production".


_ADMIN_DAILY_QUEUE = ReportPreset(
    id="admin-daily-queue",
    title="Cola diaria de revisión",
    description=(
        "Resumen operativo del día: documentos pendientes de revisión, "
        "vencimientos próximos y tiempo medio de revisión."
    ),
    audience=ReportAudience.INTERNAL_ONLY,
    required_roles=(MembershipRole.INTERNAL_ADMIN, MembershipRole.REVIEWER),
    recommended_prompt=(
        "Genera un reporte operativo del día con: un resumen ejecutivo del "
        "estado de la bandeja, un KPI strip con documentos en revisión, "
        "vencimientos próximos y tiempo medio de revisión, y una lista "
        "priorizada de acciones que el equipo de revisión debe atender hoy."
    ),
)


_ADMIN_HIGH_RISK_VENDORS = ReportPreset(
    id="admin-high-risk-vendors",
    title="Proveedores de alto riesgo",
    description=(
        "Matriz cruzada de proveedores con peor score de cumplimiento "
        "y obligaciones SAT / IMSS / INFONAVIT / STPS-REPSE en riesgo."
    ),
    audience=ReportAudience.INTERNAL_ONLY,
    required_roles=(MembershipRole.INTERNAL_ADMIN, MembershipRole.REVIEWER),
    recommended_prompt=(
        "Genera un reporte de proveedores en riesgo: empieza con un resumen "
        "ejecutivo enfocado en riesgo, incluye un KPI strip con número total "
        "de proveedores y proveedores en riesgo, una matriz cruzada de los "
        "20 proveedores con mayor risk_score mostrando SAT, IMSS, INFONAVIT "
        "y STPS-REPSE, y cierra con 3 acciones priorizadas para el equipo "
        "interno."
    ),
)


_ADMIN_MONTHLY_OPERATIONAL = ReportPreset(
    id="admin-monthly-operational",
    title="Cumplimiento operativo mensual",
    description=(
        "Vista mensual del estado de cumplimiento: porcentaje global, "
        "evolución, proveedores en riesgo y recomendaciones."
    ),
    audience=ReportAudience.INTERNAL_ONLY,
    required_roles=(MembershipRole.INTERNAL_ADMIN, MembershipRole.REVIEWER),
    recommended_prompt=(
        "Genera un reporte mensual operativo de cumplimiento: resumen "
        "ejecutivo con métricas, KPI strip con porcentaje de cumplimiento, "
        "total de proveedores y proveedores en riesgo, matriz cruzada de "
        "proveedores ordenada por risk_score, y una recomendación final de "
        "5 acciones priorizadas para el equipo interno."
    ),
)


# ─── Client presets (R1.1) ──────────────────────────────────────
#
# Three client_facing presets for client_admin role. Each targets a
# real question a client executive answers about their vendor
# portfolio. internal_admin also sees these (per required_roles) so
# staff can author from the same templates on behalf of a client.


_CLIENT_MONTHLY_EXECUTIVE = ReportPreset(
    id="client-monthly-executive",
    title="Resumen ejecutivo mensual",
    description=(
        "Panorama mensual del portafolio: cumplimiento global, "
        "proveedores en riesgo, evolución y recomendaciones para "
        "dirección."
    ),
    audience=ReportAudience.CLIENT_FACING,
    required_roles=(MembershipRole.CLIENT_ADMIN, MembershipRole.INTERNAL_ADMIN),
    recommended_prompt=(
        # M4/M5 (2026-06-02) — Reportes redesign. Be EXTREMELY
        # explicit: enumerate the four blocks the cliente surface
        # needs by name + config, in order. The earlier softer
        # "arranca con… sigue con…" phrasing got Anthropic to stop
        # after one or two tool calls. The numbered must-include
        # list with parallel emission language gets the planner to
        # emit all four in a single response.
        "Genera un resumen ejecutivo mensual de cumplimiento del "
        "portafolio para la dirección del cliente. Devuelve "
        "EXACTAMENTE estos cuatro bloques, en este orden, emitidos "
        "como cuatro tool_use paralelos en una sola respuesta:\n"
        "1. ``compliance_radar`` con ``top_n_vendors=8``, "
        "``include_history=false`` — hero del portafolio.\n"
        "2. ``executive_summary`` con ``focus=compliance``, "
        "``include_metrics=false`` — narrativa en prosa, sin tira "
        "de KPIs (el radar ya las muestra).\n"
        "3. ``vendor_risk_matrix`` con ``sort=risk_desc``, "
        "``max_rows=10``, columnas ``[sat, imss, infonavit, "
        "stps_repse, risk_score]`` — vista cruzada de proveedores "
        "ordenada de mayor a menor riesgo.\n"
        "4. ``ai_recommendation`` con ``priority_count=3``, "
        "``audience_tone=client`` — tres recomendaciones priorizadas "
        "para la dirección.\n\n"
        "NO agregues bloques adicionales. NO omitas ninguno. NO "
        "emitas un ``kpi_strip`` separado."
    ),
)


_CLIENT_VENDOR_RISK_MATRIX = ReportPreset(
    id="client-vendor-risk-matrix",
    title="Matriz de riesgo de proveedores",
    description=(
        "Vista cruzada de los proveedores del portafolio con su score "
        "de riesgo y obligaciones SAT / IMSS / INFONAVIT / STPS-REPSE."
    ),
    audience=ReportAudience.CLIENT_FACING,
    required_roles=(MembershipRole.CLIENT_ADMIN, MembershipRole.INTERNAL_ADMIN),
    recommended_prompt=(
        "Genera una matriz de riesgo de proveedores del portafolio: "
        "un resumen ejecutivo enfocado en riesgo, un KPI strip con "
        "total de proveedores y proveedores en riesgo, una matriz "
        "cruzada de los proveedores ordenada por risk_score "
        "mostrando SAT, IMSS, INFONAVIT y STPS-REPSE, y una "
        "recomendación final de 3 acciones priorizadas para "
        "comunicar con los proveedores que requieren atención."
    ),
)


_CLIENT_MISSING_EVIDENCE = ReportPreset(
    id="client-missing-evidence",
    title="Documentos faltantes por proveedor",
    description=(
        "Detalle de evidencia documental pendiente, agrupada por "
        "proveedor y obligación."
    ),
    audience=ReportAudience.CLIENT_FACING,
    required_roles=(MembershipRole.CLIENT_ADMIN, MembershipRole.INTERNAL_ADMIN),
    recommended_prompt=(
        "Genera un reporte de documentos faltantes del portafolio: "
        "resumen ejecutivo enfocado en expediente, KPI strip con "
        "total de documentos vencidos, en revisión, aprobados y "
        "rechazados, una matriz cruzada de proveedores filtrada por "
        "instituciones con faltantes ordenada por mayor número de "
        "faltantes, y una recomendación final de 3 acciones "
        "priorizadas para que el equipo del cliente coordine con "
        "sus proveedores."
    ),
)


# ─── Provider presets (P1 — vendor_facing) ─────────────────────
#
# Three vendor-facing presets for the role-less provider who owns a
# ProviderWorkspace. ``required_roles`` is intentionally empty: the
# matching logic in ``presets_for_roles`` has a workspace-owner branch
# that picks up presets with no role requirements when the actor is a
# workspace owner, instead of inventing a "vendor" string role.
#
# internal_admin staff can still author from these presets via the
# request body's ``vendor_id`` field (no implicit anchor for them).


_PROVIDER_CURRENT_STATE = ReportPreset(
    id="provider-current-state",
    title="Mi estado de cumplimiento",
    description=(
        "Estado actual del expediente del proveedor: porcentaje de "
        "cumplimiento, documentos en revisión, vencimientos próximos y "
        "siguientes acciones prioritarias."
    ),
    audience=ReportAudience.VENDOR_FACING,
    required_roles=(),
    recommended_prompt=(
        "Genera un reporte del estado actual de cumplimiento de este "
        "proveedor. Empieza SIEMPRE con un bloque compliance_state que "
        "muestre el semáforo (verde/amarillo/rojo), motivo, porcentaje "
        "de cumplimiento y conteos de documentos por estado. Sigue con "
        "un bloque attention_list sin filtros (todos los documentos "
        "que requieren atención inmediata, máximo 10) para que el "
        "proveedor pueda corregir con un click. Agrega un bloque "
        "upcoming_deadlines (top 6) mostrando los próximos "
        "vencimientos por institución en una línea de tiempo visual. "
        "Cierra con un bloque prioritized_actions (3 tarjetas) — NO "
        "uses ai_recommendation; las acciones provienen de la lista "
        "canónica de suggested_actions del workspace y siempre llevan "
        "un botón para subir el documento corregido."
    ),
)


_PROVIDER_MISSING_DOCUMENTS = ReportPreset(
    id="provider-missing-documents",
    title="Brechas de cumplimiento",
    description=(
        "Lista de obligaciones del periodo con evidencia pendiente, "
        "agrupada por institución, con motivo y siguiente acción."
    ),
    audience=ReportAudience.VENDOR_FACING,
    required_roles=(),
    recommended_prompt=(
        "Genera un reporte de brechas de cumplimiento para este "
        "proveedor — muestra exactamente por qué su expediente no está "
        "al 100%. Empieza SIEMPRE con un bloque compliance_state "
        "(semáforo + conteos). Sigue con un bloque attention_list con "
        "``group_by_institution=true`` para que las brechas aparezcan "
        "agrupadas bajo SAT / IMSS / INFONAVIT / STPS · REPSE — cada "
        "renglón muestra estado, título, días al vencimiento y un "
        "botón para subir. Aplica filtros amplios (incluye missing, "
        "in_review, uploaded, rejected, needs_correction, "
        "possible_mismatch, expired) para que el provider vea toda la "
        "brecha, no solo lo urgente. Cierra con un bloque "
        "prioritized_actions (3 tarjetas, filtrado a tipos "
        "complete_onboarding y upcoming) — NO uses ai_recommendation: "
        "las acciones provienen de la lista canónica y siempre llevan "
        "un botón para subir el documento."
    ),
)


_PROVIDER_RECENT_REJECTIONS = ReportPreset(
    id="provider-recent-rejections",
    title="Rechazos recientes",
    description=(
        "Documentos rechazados o con inconsistencias en los últimos "
        "periodos y las acciones correctivas correspondientes."
    ),
    audience=ReportAudience.VENDOR_FACING,
    required_roles=(),
    recommended_prompt=(
        "Genera un reporte de rechazos recientes para este proveedor. "
        "Empieza SIEMPRE con un bloque compliance_state (semáforo + "
        "conteos). Sigue con un bloque attention_list filtrado a estados "
        "rejected / needs_correction / possible_mismatch — cada renglón "
        "muestra el motivo del revisor y un botón para subir la versión "
        "corregida con replaces= preconfigurado. Cierra con un bloque "
        "prioritized_actions (3 tarjetas, filtrado a prioridad high y "
        "tipos reupload / clarify / verify_mismatch) — NO uses "
        "ai_recommendation: las acciones provienen de la lista canónica "
        "y siempre llevan un botón para resubir con el id correcto."
    ),
)


# ─── Registry ───────────────────────────────────────────────────


PRESETS: tuple[ReportPreset, ...] = (
    _ADMIN_DAILY_QUEUE,
    _ADMIN_HIGH_RISK_VENDORS,
    _ADMIN_MONTHLY_OPERATIONAL,
    _CLIENT_MONTHLY_EXECUTIVE,
    _CLIENT_VENDOR_RISK_MATRIX,
    _CLIENT_MISSING_EVIDENCE,
    _PROVIDER_CURRENT_STATE,
    _PROVIDER_MISSING_DOCUMENTS,
    _PROVIDER_RECENT_REJECTIONS,
)


def get_preset(preset_id: str) -> ReportPreset | None:
    for p in PRESETS:
        if p.id == preset_id:
            return p
    return None


def presets_for_roles(
    roles: tuple[str, ...],
    *,
    is_workspace_owner: bool = False,
) -> tuple[ReportPreset, ...]:
    """Return the presets the caller may instantiate.

    Match rules:
    - A preset with non-empty ``required_roles`` is included when the
      caller holds any of those roles.
    - A preset with empty ``required_roles`` is the P1 provider
      shape: included only when ``is_workspace_owner`` is True (the
      caller owns a ``ProviderWorkspace`` and has no other role).

    Empty tuple if no preset matches — the list endpoint then returns
    an empty list, and ``from-preset`` 403s on attempts to instantiate.
    """
    held = set(roles)
    return tuple(
        p
        for p in PRESETS
        if (
            (p.required_roles and held.intersection(r.value for r in p.required_roles))
            or (not p.required_roles and is_workspace_owner)
        )
    )
