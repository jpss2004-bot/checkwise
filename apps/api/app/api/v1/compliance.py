"""Read-only endpoints serving the REPSE compliance catalog.

The catalog is derived from ``C.Árbol Plataforma Proveedores REPSE VF`` and
encoded in :mod:`app.core.compliance_catalog`. These endpoints expose:

- the full catalog metadata
- the Expediente Corporativo (onboarding) per persona type
- the recurring compliance calendar for a given year

They are intentionally pure-read and require no auth — they describe regulation,
not provider data.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from app.core.compliance_catalog import (
    catalog_metadata,
    expediente_as_dicts,
    recurring_as_dicts,
    recurring_for_year,
    recurring_for_year_v2,
)
from app.core.config import settings
from app.core.period_validation import MAX_YEAR, MIN_YEAR

router = APIRouter(prefix="/compliance", tags=["compliance"])

PersonaQuery = Literal["moral", "fisica"]


@router.get("/catalog")
def get_catalog(year: int = Query(default=2026, ge=MIN_YEAR, le=MAX_YEAR)) -> dict:
    """Full catalog: metadata + onboarding (both persona types) + calendar."""
    return {
        "metadata": catalog_metadata(),
        "year": year,
        "onboarding": {
            "moral": expediente_as_dicts("moral"),
            "fisica": expediente_as_dicts("fisica"),
        },
        "recurring": {
            "moral": recurring_as_dicts(year, "moral"),
            "fisica": recurring_as_dicts(year, "fisica"),
        },
    }


@router.get("/onboarding")
def get_onboarding(persona_type: PersonaQuery = "moral") -> dict:
    """Expediente Corporativo for a single persona type."""
    return {
        "metadata": catalog_metadata(),
        "persona_type": persona_type,
        "requirements": expediente_as_dicts(persona_type),
    }


@router.get("/calendar")
def get_calendar(
    year: int = Query(default=2026, ge=MIN_YEAR, le=MAX_YEAR),
    persona_type: PersonaQuery = "moral",
) -> dict:
    """Recurring REPSE calendar grouped by month and institution."""
    # Session 2 (2026-05-21) — flag-aware. v2 emits ~34 rows/year per
    # persona instead of v1's ~139; the row shape is otherwise compatible
    # with this endpoint's response. Frontend Session 3 will branch on
    # ``accepts_documents.length`` to render the alternatives list.
    items = (
        recurring_for_year_v2(year, persona_type)
        if settings.RECURRING_CATALOG_V2
        else recurring_for_year(year, persona_type)
    )
    months: dict[int, dict] = {
        month: {
            "month": month,
            "institutions": {},
        }
        for month in range(1, 13)
    }
    for req in items:
        bucket = months[req.due_month]["institutions"]
        inst = bucket.setdefault(req.institution, {"institution": req.institution, "items": []})
        inst["items"].append(
            {
                "code": req.code,
                "name": req.name,
                "frequency": req.frequency,
                "period_label": req.period_label,
                "period_key": req.period_key,
            }
        )
    return {
        "metadata": catalog_metadata(),
        "year": year,
        "persona_type": persona_type,
        "months": [
            {
                "month": m["month"],
                "institutions": list(m["institutions"].values()),
            }
            for m in months.values()
        ],
    }
