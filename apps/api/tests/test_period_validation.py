"""Stage 2.5 (BL-T7) — REPSE period validation boundary tests.

Pure-unit tests for ``app.core.period_validation``. Confirms the
``[2021, 2099]`` window catches the cases the transcript called out
(``?year=1945``) while leaving every legitimate REPSE year through.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.period_validation import (
    MAX_YEAR,
    MIN_YEAR,
    validate_period_key,
    validate_year,
)

# ─── validate_year ──────────────────────────────────────────────────


def test_validate_year_none_is_noop() -> None:
    """``None`` slips through — callers handle the "no filter" case."""
    validate_year(None)


def test_validate_year_below_min_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_year(1945)
    assert exc.value.status_code == 422
    assert "2021" in str(exc.value.detail)


def test_validate_year_exact_min_accepted() -> None:
    validate_year(MIN_YEAR)


def test_validate_year_one_below_min_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_year(MIN_YEAR - 1)
    assert exc.value.status_code == 422


def test_validate_year_exact_max_accepted() -> None:
    validate_year(MAX_YEAR)


def test_validate_year_one_above_max_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_year(MAX_YEAR + 1)
    assert exc.value.status_code == 422


def test_validate_year_present_decade_accepted() -> None:
    for year in (2021, 2024, 2026, 2030, 2099):
        validate_year(year)


# ─── validate_period_key ────────────────────────────────────────────


def test_validate_period_key_none_is_noop() -> None:
    validate_period_key(None)


def test_validate_period_key_monthly_recurring_accepted() -> None:
    for key in ("2021-M01", "2026-M05", "2099-M12", "2025-M12"):
        validate_period_key(key)


def test_validate_period_key_bimonthly_accepted() -> None:
    validate_period_key("2025-B6")
    validate_period_key("2026-B1")


def test_validate_period_key_quarterly_accepted() -> None:
    validate_period_key("2026-Q1")
    validate_period_key("2024-Q4")


def test_validate_period_key_annual_accepted() -> None:
    validate_period_key("2025-A")
    validate_period_key("2021-A")


def test_validate_period_key_onboarding_year_suffix_accepted() -> None:
    """Onboarding period_keys carry the year as a trailing fragment."""
    validate_period_key("onb-repse-2026")
    validate_period_key("onb-corp-2024")
    validate_period_key("onb-cont-2021")


def test_validate_period_key_year_below_min_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_period_key("1945-M01")
    assert exc.value.status_code == 422
    assert "2021" in str(exc.value.detail)


def test_validate_period_key_onboarding_with_stale_year_rejected() -> None:
    """Even the onboarding-style suffix shape blocks impossible years."""
    with pytest.raises(HTTPException) as exc:
        validate_period_key("onb-repse-1999")
    assert exc.value.status_code == 422


def test_validate_period_key_no_year_substring_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_period_key("garbage")
    assert exc.value.status_code == 422


def test_validate_period_key_far_future_year_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_period_key("3000-M01")
    assert exc.value.status_code == 422
