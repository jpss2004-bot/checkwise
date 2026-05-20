"""REPSE period validation (Stage 2.5, BL-T7).

REPSE — Registro de Prestadoras de Servicios Especializados u Obras
Especializadas — was created by the 2021 outsourcing reform in
Mexico. No CheckWise obligation can predate 2021, so any year or
period_key arriving from a user surface must reference a year inside
the ``[MIN_YEAR, MAX_YEAR]`` window. Without these guards the
calendar / dashboard / report endpoints happily accept impossible
inputs like ``?year=1945`` and return empty payloads that read as
"everything is fine."

The values live in this module so every endpoint that takes a year
or a period_key from the wire can apply the same constraint. Tests
exercise the boundary cases — see
``backend/tests/test_period_validation.py``.
"""

from __future__ import annotations

import re

from fastapi import HTTPException, status

# Earliest legitimate REPSE year. Hard floor — do not lower without a
# documented legal/product reason.
MIN_YEAR: int = 2021

# Upper bound large enough to accommodate any reasonable forward-looking
# query (preparing next year's expediente, etc.) without inviting
# accidental-or-malicious far-future inputs.
MAX_YEAR: int = 2099

# Recurring period keys emit the year as a 4-digit prefix
# ("2026-M01", "2025-B6", "2026-Q1", "2025-A"). Onboarding period
# keys emit it as a suffix ("onb-repse-2026", "onb-corp-2026"). The
# windowed regex below captures every 4-digit run so we can validate
# either shape with one helper.
_YEAR_RE = re.compile(r"\d{4}")


def validate_year(year: int | None) -> None:
    """Raise 422 when ``year`` is outside the supported REPSE window.

    ``None`` is allowed — callers that accept "all years" or that
    derive the year from elsewhere should keep their existing default
    branch.
    """
    if year is None:
        return
    if year < MIN_YEAR or year > MAX_YEAR:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Las obligaciones REPSE inician en "
                f"{MIN_YEAR}. Selecciona un año entre "
                f"{MIN_YEAR} y {MAX_YEAR}."
            ),
        )


def validate_period_key(period_key: str | None) -> None:
    """Raise 422 when ``period_key`` references a year out of range.

    Accepts ``None`` (callers that take an optional period_key keep
    their existing default branch). For non-None values the function
    finds every 4-digit run in the string and runs the same window
    check as ``validate_year`` on each.

    Recurring keys put the year first ("2026-M01", "2025-B6",
    "2026-Q1", "2025-A"). Onboarding keys put it last
    ("onb-repse-2026", "onb-corp-2026"). Both shapes are accepted as
    long as every year-shaped run lives inside ``[MIN_YEAR,
    MAX_YEAR]``. A string with no 4-digit substring is treated as
    malformed.

    Per-format structural validation (e.g. the M-N month, B-N
    bimester, Q-N quarter) stays with ``compliance_catalog`` helpers;
    this validator only cares about the year window.
    """
    if period_key is None:
        return
    matches = _YEAR_RE.findall(period_key)
    if not matches:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "El periodo debe incluir un año de cuatro dígitos. "
                f"Recibimos: {period_key!r}."
            ),
        )
    for match in matches:
        validate_year(int(match))


__all__ = ["MIN_YEAR", "MAX_YEAR", "validate_year", "validate_period_key"]
