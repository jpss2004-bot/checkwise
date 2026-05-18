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
        "Genera un resumen ejecutivo mensual de cumplimiento del "
        "portafolio para la dirección del cliente: empieza con un "
        "resumen ejecutivo enfocado en cumplimiento, sigue con un "
        "KPI strip con porcentaje de cumplimiento, total de "
        "proveedores, proveedores en riesgo y próximos vencimientos, "
        "y cierra con 3 recomendaciones priorizadas para la dirección."
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
        "proveedor: empieza con un resumen ejecutivo enfocado en "
        "cumplimiento, un KPI strip con porcentaje de cumplimiento, "
        "documentos en revisión, documentos vencidos y días hasta el "
        "próximo vencimiento, y una recomendación final de 3 acciones "
        "priorizadas que el proveedor debe atender."
    ),
)


_PROVIDER_MISSING_DOCUMENTS = ReportPreset(
    id="provider-missing-documents",
    title="Documentos faltantes",
    description=(
        "Lista de obligaciones del periodo con evidencia pendiente, "
        "agrupada por institución y prioridad."
    ),
    audience=ReportAudience.VENDOR_FACING,
    required_roles=(),
    recommended_prompt=(
        "Genera un reporte de documentos faltantes para este proveedor: "
        "resumen ejecutivo enfocado en expediente, un KPI strip con "
        "total de obligaciones, documentos vencidos y en revisión, y "
        "una recomendación final de 3 acciones priorizadas indicando "
        "qué subir primero y a qué institución corresponde."
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
        "Genera un reporte de rechazos recientes para este proveedor: "
        "resumen ejecutivo enfocado en auditoría que liste documentos "
        "con incidencias del periodo, un KPI strip con totales por "
        "estatus y una recomendación final de 3 acciones correctivas "
        "priorizadas."
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
