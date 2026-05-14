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
)

router = APIRouter(prefix="/compliance", tags=["compliance"])

PersonaQuery = Literal["moral", "fisica"]


@router.get("/catalog")
def get_catalog(year: int = Query(default=2026, ge=2020, le=2099)) -> dict:
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
    year: int = Query(default=2026, ge=2020, le=2099),
    persona_type: PersonaQuery = "moral",
) -> dict:
    """Recurring REPSE calendar grouped by month and institution."""
    items = recurring_for_year(year, persona_type)
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
