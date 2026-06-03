"""Deterministic per-template block layouts.

Each report preset (``app.services.reports.templates``) maps here to a fixed,
ordered list of block specs that mirror the preset's own ``recommended_prompt``
intent. Filling them with the real production fetchers (``fetch_for_block`` —
no LLM) yields a report that is:

  * always fully populated (no "no data" placeholders for an in-scope report),
  * identical every run (deterministic),
  * instant (no AI round-trip),
  * key-free (works without ANTHROPIC_API_KEY).

This is BOTH halves of the product's report story now:

  * the deterministic fallback when AI generation is unavailable or
    under-delivers (the hybrid generate path), and
  * the canonical "amazing" look every template guarantees.

``ai_recommendation`` is the only block that genuinely needs an LLM; in the
deterministic path it is replaced by a data-grounded ``text`` recommendation
(``__recommendation__`` pseudo-entry) so the report still closes with a
"here's what to do" section. Provider templates close with the canonical
``prioritized_actions`` block instead, which is already LLM-free.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants.statuses import DocumentStatus
from app.models import Submission, Vendor
from app.services.reports.blocks.data_fetchers import fetch_for_block
from app.services.reports.context import ReportScope

# A layout is an ordered list of (block_type, config). ``__recommendation__``
# is a pseudo-type the builder renders as a data-grounded text block.
_MATRIX_COLUMNS = ["sat", "imss", "infonavit", "stps_repse", "risk_score"]

LAYOUTS: dict[str, list[tuple[str, dict]]] = {
    # ── Admin · internal_only (need a client/vendor scope to populate) ──
    "admin-daily-queue": [
        ("executive_summary", {"focus": "audit", "include_metrics": True}),
        ("kpi_strip", {"metrics": [
            {"label": "En revisión", "metric_key": "in_review_count", "format": "number"},
            {"label": "Vencidos", "metric_key": "overdue_count", "format": "number"},
            {"label": "Próximo en", "metric_key": "days_to_next_deadline", "format": "duration_days"},
        ]}),
        ("vendor_risk_matrix", {"filter": {}, "columns": _MATRIX_COLUMNS, "sort": "risk_desc", "max_rows": 15}),
        ("__recommendation__", {"audience_tone": "internal", "priority_count": 3}),
    ],
    "admin-high-risk-vendors": [
        ("executive_summary", {"focus": "risk", "include_metrics": False}),
        ("kpi_strip", {"metrics": [
            {"label": "Proveedores", "metric_key": "vendors_total", "format": "number"},
            {"label": "En riesgo", "metric_key": "vendors_at_risk", "format": "number"},
        ]}),
        ("vendor_risk_matrix", {"filter": {}, "columns": _MATRIX_COLUMNS, "sort": "risk_desc", "max_rows": 20}),
        ("__recommendation__", {"audience_tone": "internal", "priority_count": 3}),
    ],
    "admin-monthly-operational": [
        ("compliance_overview", {"top_n_vendors": 12}),
        ("compliance_by_institution", {}),
        ("executive_summary", {"focus": "compliance", "include_metrics": True}),
        ("vendor_risk_matrix", {"filter": {}, "columns": _MATRIX_COLUMNS, "sort": "risk_desc", "max_rows": 12}),
        ("__recommendation__", {"audience_tone": "internal", "priority_count": 5}),
    ],

    # ── Client · client_facing ──
    "client-monthly-executive": [
        ("compliance_overview", {"top_n_vendors": 12}),
        ("compliance_by_institution", {}),
        ("compliance_radar", {"top_n_vendors": 8, "include_history": False}),
        ("executive_summary", {"focus": "compliance", "include_metrics": False}),
        ("vendor_risk_matrix", {"filter": {}, "columns": _MATRIX_COLUMNS, "sort": "risk_desc", "max_rows": 10}),
        ("__recommendation__", {"audience_tone": "client", "priority_count": 3}),
    ],
    "client-vendor-risk-matrix": [
        ("executive_summary", {"focus": "risk", "include_metrics": False}),
        ("kpi_strip", {"metrics": [
            {"label": "Proveedores", "metric_key": "vendors_total", "format": "number"},
            {"label": "En riesgo", "metric_key": "vendors_at_risk", "format": "number"},
        ]}),
        ("vendor_risk_matrix", {"filter": {}, "columns": _MATRIX_COLUMNS, "sort": "risk_desc", "max_rows": 10}),
        ("__recommendation__", {"audience_tone": "client", "priority_count": 3}),
    ],
    "client-missing-evidence": [
        ("executive_summary", {"focus": "expediente", "include_metrics": False}),
        ("kpi_strip", {"metrics": [
            {"label": "Vencidos", "metric_key": "overdue_count", "format": "number"},
            {"label": "En revisión", "metric_key": "in_review_count", "format": "number"},
            {"label": "Cumplimiento", "metric_key": "approved_pct", "format": "percent"},
            {"label": "En riesgo", "metric_key": "vendors_at_risk", "format": "number"},
        ]}),
        ("compliance_by_institution", {}),
        ("vendor_risk_matrix", {"filter": {}, "columns": _MATRIX_COLUMNS, "sort": "risk_desc", "max_rows": 10}),
        ("__recommendation__", {"audience_tone": "client", "priority_count": 3}),
    ],

    # ── Provider · vendor_facing (need a vendor scope) ──
    "provider-current-state": [
        ("compliance_state", {}),
        ("compliance_by_institution", {}),
        ("attention_list", {"max_rows": 10}),
        ("upcoming_deadlines", {"top": 6}),
        ("prioritized_actions", {"max_actions": 3}),
    ],
    "provider-missing-documents": [
        ("compliance_state", {}),
        ("attention_list", {"filter": {"states": [
            "missing", "in_review", "uploaded", "rejected",
            "needs_correction", "possible_mismatch", "expired",
        ]}, "max_rows": 10}),
        ("prioritized_actions", {"max_actions": 3, "filter": {"types": ["complete_onboarding", "upcoming"]}}),
    ],
    "provider-recent-rejections": [
        ("compliance_state", {}),
        ("attention_list", {"filter": {"states": ["rejected", "needs_correction", "possible_mismatch"]}, "max_rows": 10}),
        ("prioritized_actions", {"max_actions": 3, "filter": {
            "priorities": ["high"], "types": ["reupload", "clarify", "verify_mismatch"],
        }}),
    ],
}

_RISK_STATUSES = [
    DocumentStatus.POSIBLE_MISMATCH.value,
    DocumentStatus.REQUIERE_ACLARACION.value,
    DocumentStatus.RECHAZADO.value,
    DocumentStatus.VENCIDO.value,
]


def has_layout(preset_id: str) -> bool:
    return preset_id in LAYOUTS


def _recommendation_block(db: Session, scope: ReportScope, tone: str) -> dict:
    """A data-grounded closing recommendation (LLM-free).

    References the actual at-risk vendor names + in-review count so the
    recommendation is concrete, not boilerplate."""
    risk_names: list[str] = []
    in_review = 0
    vendors_total = 0
    if scope.client_id:
        vendors_total = int(db.scalar(
            select(func.count(Vendor.id)).where(Vendor.client_id == scope.client_id)
        ) or 0)
        risk_vendor_ids = set(db.scalars(
            select(Submission.vendor_id).where(
                Submission.client_id == scope.client_id,
                Submission.status.in_(_RISK_STATUSES),
            )
        ))
        for vid in risk_vendor_ids:
            v = db.get(Vendor, vid)
            if v:
                risk_names.append(v.name)
        in_review = int(db.scalar(
            select(func.count(Submission.id)).where(
                Submission.client_id == scope.client_id,
                Submission.status == DocumentStatus.PENDIENTE_REVISION.value,
            )
        ) or 0)

    audience_word = "el equipo interno" if tone == "internal" else "la dirección"
    parts: list[str] = []
    if risk_names:
        listed = ", ".join(sorted(risk_names)[:3])
        parts.append(
            f"Priorizar seguimiento con {len(risk_names)} proveedor(es) con observación "
            f"abierta — {listed}{'…' if len(risk_names) > 3 else ''}: solicitar el reenvío "
            "de los documentos rechazados o con inconsistencia de RFC."
        )
    if in_review:
        parts.append(
            f"Cerrar la bandeja de revisión: {in_review} documento(s) esperan dictamen; "
            "atenderlos libera el avance de cumplimiento del periodo."
        )
    parts.append(
        "Confirmar las renovaciones próximas a vencer (CSF cada 90 días, REPSE/patronal) "
        "antes de su fecha límite para evitar caer en estado vencido."
    )
    body = (
        f"Acciones recomendadas para {audience_word}"
        + (f", sobre un portafolio de {vendors_total} proveedores" if vendors_total else "")
        + ":\n\n• " + "\n• ".join(parts)
    )
    return {
        "id": str(uuid.uuid4()),
        "type": "text",
        "config": {"heading": "Recomendación de CheckWise", "body": body},
    }


def build_deterministic_blocks(
    db: Session, *, preset_id: str, scope: ReportScope
) -> list[dict]:
    """Build the populated block list for a preset, deterministically.

    Every data-driven block is filled by the real fetcher at the report's
    scope. Blocks whose fetcher returns ``None`` for the given scope (e.g. a
    portfolio block on a vendor scope) are dropped rather than rendered as an
    empty placeholder."""
    layout = LAYOUTS.get(preset_id)
    if layout is None:
        return []

    blocks: list[dict] = []
    for btype, config in layout:
        if btype == "__recommendation__":
            blocks.append(_recommendation_block(db, scope, config.get("audience_tone", "client")))
            continue
        data = fetch_for_block(block_type=btype, config=config, scope=scope, db=db)
        if data is None and btype not in ("text", "divider"):
            # Block doesn't apply to this scope — skip so we never show an
            # empty placeholder in a finished, non-editable report.
            continue
        blocks.append({
            "id": str(uuid.uuid4()),
            "type": btype,
            "config": config,
            "data": data,
        })
    return blocks


__all__ = ["LAYOUTS", "has_layout", "build_deterministic_blocks"]
