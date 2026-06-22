"""Timezone-correct time helpers for a Mexico-only product.

CheckWise serves Mexico (America/Mexico_City, UTC-6/-5). Two rules:

- Stored/emitted timestamps must be tz-aware UTC -> use ``utc_now()``.
- User-facing deadline/calendar/risk date math must be computed in Mexico
  local date -> use ``today_mx()`` instead of ``date.today()`` (which resolves
  against the server process timezone, UTC on Render, and flips a day early in
  the evening Mexico time).

This module is intentionally dependency-free (stdlib only) so it can be
imported anywhere without risking import cycles.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

MEXICO_TZ = ZoneInfo("America/Mexico_City")


def utc_now() -> datetime:
    """Return the current time as a tz-aware UTC datetime."""
    return datetime.now(UTC)


def today_mx() -> date:
    """Return today's calendar date in Mexico City local time.

    Use for compliance deadlines, calendars and any user-facing date math so
    day-relative buckets do not flip a day early near midnight Mexico time.
    """
    return datetime.now(MEXICO_TZ).date()
