"""Unit tests for ``app.core.period_range``.

Junta 2026-05-25 — the audit-package date range used to compare
period_keys lexicographically, which silently dropped bimestral and
cuatrimestral rows whenever the user filtered with a monthly range.
These tests pin the new semantic overlap behaviour so a future
refactor cannot regress it.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.core.period_range import (
    filter_period_from_to_range,
    period_date_range,
    period_overlaps_range,
)

# ---------------------------------------------------------------------------
# period_date_range — canonical key resolution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key,expected",
    [
        ("2026-M01", (date(2026, 1, 1), date(2026, 1, 31))),
        ("2026-M02", (date(2026, 2, 1), date(2026, 2, 28))),
        ("2024-M02", (date(2024, 2, 1), date(2024, 2, 29))),  # leap year
        ("2026-M04", (date(2026, 4, 1), date(2026, 4, 30))),
        ("2026-M12", (date(2026, 12, 1), date(2026, 12, 31))),
        ("2026-B1", (date(2026, 1, 1), date(2026, 2, 28))),
        ("2026-B3", (date(2026, 5, 1), date(2026, 6, 30))),
        ("2026-B6", (date(2026, 11, 1), date(2026, 12, 31))),
        ("2026-Q1", (date(2026, 1, 1), date(2026, 4, 30))),
        ("2026-Q2", (date(2026, 5, 1), date(2026, 8, 31))),
        ("2026-Q3", (date(2026, 9, 1), date(2026, 12, 31))),
        ("2026-A", (date(2026, 1, 1), date(2026, 12, 31))),
        ("2021-A", (date(2021, 1, 1), date(2021, 12, 31))),
    ],
)
def test_period_date_range_canonical_formats(
    key: str, expected: tuple[date, date]
) -> None:
    assert period_date_range(key) == expected


@pytest.mark.parametrize(
    "key",
    [
        "",
        None,
        "not-a-key",
        "2026",
        "2026-",
        "2026-M",
        "2026-M00",
        "2026-M13",
        "2026-Mxx",
        "2026-B0",
        "2026-B7",
        "2026-Bx",
        "2026-Q0",
        "2026-Q4",
        "2026-Z1",
        "ABCD-M01",
        "20-M01",
    ],
)
def test_period_date_range_returns_none_for_garbage(key: str | None) -> None:
    assert period_date_range(key) is None


# ---------------------------------------------------------------------------
# period_overlaps_range — the semantic test the audit package depends on
# ---------------------------------------------------------------------------


def test_overlap_no_constraints_includes_everything() -> None:
    assert period_overlaps_range("2026-M01", None, None) is True
    assert period_overlaps_range("anything-shaped", None, None) is True


def test_overlap_unknown_format_is_permissive() -> None:
    """Legacy or hand-edited period_keys we cannot parse must still
    appear in the audit package — silently dropping them would
    lose evidence the operator can see in the UI."""
    assert (
        period_overlaps_range(
            "weird-legacy-key", date(2026, 1, 1), date(2026, 12, 31)
        )
        is True
    )


def test_overlap_monthly_inside_monthly_range() -> None:
    # User range M01-M03 (Jan-Mar). Each monthly key inside is included.
    rs, re_ = filter_period_from_to_range("2026-M01", "2026-M03")
    assert period_overlaps_range("2026-M01", rs, re_) is True
    assert period_overlaps_range("2026-M02", rs, re_) is True
    assert period_overlaps_range("2026-M03", rs, re_) is True
    assert period_overlaps_range("2026-M04", rs, re_) is False
    assert period_overlaps_range("2025-M12", rs, re_) is False


def test_overlap_bimestral_with_monthly_range() -> None:
    """The bug we fixed: a bimestral row (Jan-Feb) MUST be included
    when the user picks a January-only filter, because the period
    overlaps that window."""
    rs, re_ = filter_period_from_to_range("2026-M01", "2026-M01")
    assert period_overlaps_range("2026-B1", rs, re_) is True
    # B2 = Mar-Apr does NOT overlap January.
    assert period_overlaps_range("2026-B2", rs, re_) is False


def test_overlap_cuatrimestral_with_monthly_range() -> None:
    """Q1 = Jan-Apr overlaps any monthly window inside that span."""
    rs, re_ = filter_period_from_to_range("2026-M03", "2026-M03")
    assert period_overlaps_range("2026-Q1", rs, re_) is True
    assert period_overlaps_range("2026-Q2", rs, re_) is False
    assert period_overlaps_range("2026-Q3", rs, re_) is False


def test_overlap_annual_with_monthly_range() -> None:
    """The annual key always overlaps any window inside its year."""
    rs, re_ = filter_period_from_to_range("2026-M06", "2026-M06")
    assert period_overlaps_range("2026-A", rs, re_) is True
    # The 2025 annual doesn't reach into 2026.
    assert period_overlaps_range("2025-A", rs, re_) is False


def test_overlap_open_start_includes_earlier_periods() -> None:
    """``period_from=None`` means 'no lower bound'."""
    _, re_ = filter_period_from_to_range(None, "2026-M03")
    assert period_overlaps_range("2025-M12", None, re_) is True
    assert period_overlaps_range("2026-M03", None, re_) is True
    assert period_overlaps_range("2026-M04", None, re_) is False


def test_overlap_open_end_includes_later_periods() -> None:
    rs, _ = filter_period_from_to_range("2026-M03", None)
    assert period_overlaps_range("2026-M02", rs, None) is False
    assert period_overlaps_range("2026-M03", rs, None) is True
    assert period_overlaps_range("2027-M01", rs, None) is True


def test_overlap_range_spanning_year_boundary() -> None:
    """User picks November 2025 → March 2026. Both monthly and
    bimestral periods that touch that window must be included."""
    rs, re_ = filter_period_from_to_range("2025-M11", "2026-M03")
    assert period_overlaps_range("2025-M11", rs, re_) is True
    assert period_overlaps_range("2025-M12", rs, re_) is True
    assert period_overlaps_range("2026-M01", rs, re_) is True
    assert period_overlaps_range("2026-M03", rs, re_) is True
    assert period_overlaps_range("2026-M04", rs, re_) is False
    # B6 of 2025 = Nov-Dec 2025; overlaps M11/M12.
    assert period_overlaps_range("2025-B6", rs, re_) is True
    # Q1 2026 = Jan-Apr; overlaps M01-M03.
    assert period_overlaps_range("2026-Q1", rs, re_) is True


# ---------------------------------------------------------------------------
# filter_period_from_to_range — boundary conversion
# ---------------------------------------------------------------------------


def test_filter_pair_expands_to_full_month_window() -> None:
    """A single-month filter resolves to that whole month."""
    rs, re_ = filter_period_from_to_range("2026-M03", "2026-M03")
    assert rs == date(2026, 3, 1)
    assert re_ == date(2026, 3, 31)


def test_filter_pair_works_with_bimestre_input() -> None:
    """Although the UI sends monthly keys today, the helper accepts
    any canonical format on either side."""
    rs, re_ = filter_period_from_to_range("2026-B1", "2026-B3")
    assert rs == date(2026, 1, 1)
    assert re_ == date(2026, 6, 30)


def test_filter_pair_returns_none_for_garbage() -> None:
    """Unrecognised inputs fall back to ``None`` so the overlap test
    treats them as 'no constraint'."""
    rs, re_ = filter_period_from_to_range("garbage", None)
    assert rs is None
    assert re_ is None
