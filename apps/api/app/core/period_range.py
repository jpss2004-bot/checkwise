"""Canonical period_key → calendar date-range conversion.

Junta 2026-05-25 — the audit-package filter used lexicographic
comparison on the ``period_key`` strings, which works for monthly
keys (``2026-Mxx`` is zero-padded) but silently misorders mixed
formats. ``2026-Q1`` would lexically land *after* ``2026-M12``
even though Q1 spans January through April — bimestral and
cuatrimestral rows fell out of the audit ZIP whenever the user
picked a monthly range.

This module replaces string comparison with a semantic
date-range overlap test that works across every canonical
period_key format the platform mints.

Period key formats
==================

The canonical formats are defined by
:mod:`app.core.compliance_catalog` and produced by the helpers
``_monthly_period_key`` / ``_bimonthly_period_key`` /
``_quarter_period_key`` / ``_annual_period_key``:

- ``YYYY-Mxx`` — single month, ``xx ∈ 01..12``.
- ``YYYY-Bx`` — bimestre, ``x ∈ 1..6``. B1 covers Jan-Feb, B2
  Mar-Apr, …, B6 Nov-Dec.
- ``YYYY-Qx`` — cuatrimestre, ``x ∈ 1..3``. Q1 covers Jan-Apr,
  Q2 May-Aug, Q3 Sep-Dec.
- ``YYYY-A`` — full fiscal year (Jan 1 - Dec 31).

Overlap semantics
=================

When the user picks a range like ``period_from=2026-M01`` and
``period_to=2026-M03`` they expect the audit package to include
every submission whose period **overlaps** that calendar window,
not only the rows whose period_key happens to start inside it.
This matters because a single bimestral row (B1 = Jan-Feb)
naturally overlaps both M01 and M02; a cuatrimestral row (Q1 =
Jan-Apr) overlaps every monthly key from M01 through M04. The
overlap test in :func:`period_overlaps_range` follows the
classical interval intersection rule:

    not (period_end < range_start or period_start > range_end)

Defensive behaviour
===================

Unrecognized formats (legacy rows, hand-edited values, future
period kinds) return ``None`` from :func:`period_date_range` and
are treated as overlapping by :func:`period_overlaps_range`.
Silently dropping unknown rows would lose evidence the user can
see in the UI but cannot download; the cap pre-flight still
counts them so the auditor knows the package isn't underrepresented.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date

__all__ = (
    "period_date_range",
    "period_overlaps_range",
    "filter_period_from_to_range",
)


def period_date_range(period_key: str | None) -> tuple[date, date] | None:
    """Return the inclusive ``(start_date, end_date)`` covered by a
    canonical ``period_key``.

    Returns ``None`` when the input is empty or doesn't match any of
    the four canonical formats. Callers decide how to treat
    unrecognised keys — :func:`period_overlaps_range` is permissive
    by design.
    """
    if not period_key or "-" not in period_key:
        return None
    year_part, rest = period_key.split("-", 1)
    if not year_part.isdigit() or len(year_part) != 4:
        return None
    year = int(year_part)
    if not rest:
        return None

    kind = rest[0]
    suffix = rest[1:]

    if kind == "M":
        if not suffix.isdigit():
            return None
        month = int(suffix)
        if not 1 <= month <= 12:
            return None
        return (date(year, month, 1), _last_day_of_month(year, month))

    if kind == "B":
        if not suffix.isdigit():
            return None
        bm = int(suffix)
        if not 1 <= bm <= 6:
            return None
        start_month = bm * 2 - 1
        end_month = bm * 2
        return (
            date(year, start_month, 1),
            _last_day_of_month(year, end_month),
        )

    if kind == "Q":
        if not suffix.isdigit():
            return None
        q = int(suffix)
        if not 1 <= q <= 3:
            return None
        start_month = q * 4 - 3
        end_month = q * 4
        return (
            date(year, start_month, 1),
            _last_day_of_month(year, end_month),
        )

    if kind == "A" and not suffix:
        return (date(year, 1, 1), date(year, 12, 31))

    return None


def period_overlaps_range(
    period_key: str | None,
    range_start: date | None,
    range_end: date | None,
) -> bool:
    """True when the period's date range intersects ``[range_start,
    range_end]``.

    ``None`` on either bound means "no constraint on that side". An
    unrecognised ``period_key`` is treated as overlapping so legacy
    rows don't silently fall out of audit packages — the operator
    can still see them in the UI and the cap pre-flight counts them.
    """
    if range_start is None and range_end is None:
        return True
    dr = period_date_range(period_key)
    if dr is None:
        return True
    period_start, period_end = dr
    if range_start is not None and period_end < range_start:
        return False
    if range_end is not None and period_start > range_end:
        return False
    return True


def filter_period_from_to_range(
    period_from: str | None,
    period_to: str | None,
) -> tuple[date | None, date | None]:
    """Convert a ``(period_from, period_to)`` user filter pair into a
    calendar ``(start_date, end_date)`` window.

    The window expands to cover the **whole** of each period_key —
    so ``period_from=2026-M03`` resolves to ``2026-03-01`` (start of
    March) and ``period_to=2026-M03`` resolves to ``2026-03-31``
    (end of March). A user picking the same single month for both
    bounds gets exactly that month.

    Unknown formats fall back to ``None`` on that side, which the
    overlap test treats as "no constraint".
    """
    range_start: date | None = None
    range_end: date | None = None

    if period_from:
        dr = period_date_range(period_from)
        if dr is not None:
            range_start = dr[0]

    if period_to:
        dr = period_date_range(period_to)
        if dr is not None:
            range_end = dr[1]

    return range_start, range_end


def _last_day_of_month(year: int, month: int) -> date:
    """Return the last calendar day of ``year``-``month``.

    Uses ``calendar.monthrange`` so leap-year February resolves
    correctly without baking in a leap-year rule here.
    """
    _, last_day = monthrange(year, month)
    return date(year, month, last_day)
