"""Server-side block catalog — the planner's "available tools" surface.

Each entry mirrors a frontend BlockDefinition + adds the LLM-facing
description and a JSON Schema for the planner's tool-use call. The
planner is given the catalog as `tools=[...]` in the Anthropic SDK
call; each tool corresponds to one block type, and the tool's input
schema is the block's config shape.

Catalog kept narrow on purpose: only the 5 blocks shipped in Phase 3.2
are listed here. As 3.3b lights up AI-aware blocks, append rather than
edit — the planner's tool list is canon.

Sourced in lockstep with:
- docs/REPORTS_BLOCK_REGISTRY.md
- frontend/lib/reports/registry.ts
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogEntry:
    """One block type the planner can call."""

    type: str
    description: str
    """LLM-facing description. Tells the planner when to use this block."""
    input_schema: dict
    """JSON Schema for the block's config. The planner emits config that
    matches this shape; the executor (3.3b) validates server-side
    before persisting."""
    example_configs: list[dict]
    """Few-shot examples shown to the planner."""


# ─── Block catalog ──────────────────────────────────────────────


TEXT = CatalogEntry(
    type="text",
    description=(
        "Free-form paragraph. Use sparingly between data blocks to set up "
        "context or close with takeaways. Never use as a substitute for a "
        "real data block."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "heading": {"type": "string", "description": "Optional section heading."},
            "body": {"type": "string", "description": "Body paragraph in Spanish."},
        },
        "required": ["body"],
        "additionalProperties": False,
    },
    example_configs=[
        {
            "heading": "Contexto",
            "body": (
                "Durante mayo 2026 todos los proveedores activos enviaron sus "
                "obligaciones REPSE..."
            ),
        },
    ],
)


DIVIDER = CatalogEntry(
    type="divider",
    description=(
        "Visual section break. Use to separate logical sections of a long "
        "report. Optional eyebrow label appears centered on the line."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "label": {"type": "string"},
        },
        "additionalProperties": False,
    },
    example_configs=[{"label": "Detalle por proveedor"}],
)


EXECUTIVE_SUMMARY = CatalogEntry(
    type="executive_summary",
    description=(
        "Cover paragraph that opens a report. Always the first block. State "
        "period + scope. Name the headline number. Name what is at risk. "
        "Three to four sentences in Spanish, executive register."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "focus": {
                "type": "string",
                "enum": ["compliance", "risk", "expediente", "audit", "custom"],
            },
            "custom_prompt": {
                "type": "string",
                "description": "Only when focus='custom'.",
            },
            "include_metrics": {
                "type": "boolean",
                "description": "Render a compact metric strip below the paragraph.",
            },
        },
        "required": ["focus", "include_metrics"],
        "additionalProperties": False,
    },
    example_configs=[
        {"focus": "risk", "include_metrics": True},
        {"focus": "compliance", "include_metrics": True},
    ],
)


KPI_STRIP = CatalogEntry(
    type="kpi_strip",
    description=(
        "Four to six metrics in a horizontal label/value strip. Mono values. "
        "Choose metric_keys that match the report's focus. Never duplicate "
        "metrics already shown in the executive_summary's metric strip."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "metrics": {
                "type": "array",
                "minItems": 1,
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "metric_key": {
                            "type": "string",
                            "enum": [
                                "completion_pct",
                                "vendors_total",
                                "vendors_at_risk",
                                "submissions_period",
                                "overdue_count",
                                "in_review_count",
                                "approved_pct",
                                "avg_review_hours",
                                "days_to_next_deadline",
                            ],
                        },
                        "format": {
                            "type": "string",
                            "enum": ["percent", "number", "duration_days", "duration_hours"],
                        },
                    },
                    "required": ["label", "metric_key", "format"],
                    "additionalProperties": False,
                },
            },
            "period": {"type": "string", "description": "ISO period key, e.g. 2026-M05."},
        },
        "required": ["metrics"],
        "additionalProperties": False,
    },
    example_configs=[
        {
            "metrics": [
                {
                    "label": "Cumplimiento",
                    "metric_key": "completion_pct",
                    "format": "percent",
                },
                {
                    "label": "En riesgo",
                    "metric_key": "vendors_at_risk",
                    "format": "number",
                },
                {
                    "label": "En revisión",
                    "metric_key": "in_review_count",
                    "format": "number",
                },
                {
                    "label": "Próximo en",
                    "metric_key": "days_to_next_deadline",
                    "format": "duration_days",
                },
            ],
            "period": "2026-M05",
        },
    ],
)


VENDOR_RISK_MATRIX = CatalogEntry(
    type="vendor_risk_matrix",
    description=(
        "Cross-vendor portfolio view: rows are vendors, columns are SAT / "
        "IMSS / INFONAVIT / STPS-REPSE plus a derived risk score. Use when "
        "the request mentions multiple vendors or 'todos los proveedores'. "
        "Filter by missing_institution if specified. Sort risk_desc by default."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "filter": {
                "type": "object",
                "properties": {
                    "missing_institution": {
                        "type": "string",
                        "enum": ["sat", "imss", "infonavit", "stps_repse"],
                    },
                    "min_risk_score": {"type": "integer", "minimum": 0, "maximum": 100},
                },
                "additionalProperties": False,
            },
            "columns": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "sat",
                        "imss",
                        "infonavit",
                        "stps_repse",
                        "risk_score",
                        "last_event",
                    ],
                },
                "minItems": 1,
            },
            "sort": {
                "type": "string",
                "enum": ["risk_desc", "risk_asc", "name"],
            },
            "max_rows": {"type": "integer", "minimum": 1, "maximum": 200},
        },
        "required": ["filter", "columns", "sort", "max_rows"],
        "additionalProperties": False,
    },
    example_configs=[
        {
            "filter": {"missing_institution": "sat"},
            "columns": ["sat", "imss", "infonavit", "risk_score"],
            "sort": "risk_desc",
            "max_rows": 50,
        },
    ],
)


AI_RECOMMENDATION = CatalogEntry(
    type="ai_recommendation",
    description=(
        "Standalone block of 1-5 prioritized next-actions, generated by the "
        "compliance analyst from the headline numbers of the rest of the "
        "report. Use when the report should close with 'here is what to do "
        "now'. Always place LAST in the plan so it can reason from the "
        "blocks above it."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "based_on": {
                "type": "array",
                "items": {"type": "string"},
                "description": "IDs of upstream blocks this recommendation reasons from.",
            },
            "priority_count": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "How many ranked actions to emit.",
            },
            "audience_tone": {
                "type": "string",
                "enum": ["internal", "client", "vendor"],
            },
        },
        "required": ["priority_count", "audience_tone"],
        "additionalProperties": False,
    },
    example_configs=[
        {"based_on": [], "priority_count": 3, "audience_tone": "client"},
    ],
)


# ─── Catalog assembly ──────────────────────────────────────────


CATALOG: list[CatalogEntry] = [
    EXECUTIVE_SUMMARY,
    KPI_STRIP,
    VENDOR_RISK_MATRIX,
    AI_RECOMMENDATION,
    TEXT,
    DIVIDER,
]


KNOWN_BLOCK_TYPES: frozenset[str] = frozenset(entry.type for entry in CATALOG)


def catalog_by_type() -> dict[str, CatalogEntry]:
    """Lookup table by block type."""
    return {entry.type: entry for entry in CATALOG}


def planner_tool_list() -> list[dict]:
    """Render the catalog as Anthropic tool-use entries.

    The planner is told to call one tool per block it wants in the
    report. The tool's input_schema is the block's config shape.
    """
    return [
        {
            "name": entry.type,
            "description": entry.description,
            "input_schema": entry.input_schema,
        }
        for entry in CATALOG
    ]
