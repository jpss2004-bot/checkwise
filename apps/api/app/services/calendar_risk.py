"""Single source of truth for one REPSE obligation's severity tier.

Historically this lived as ``_calendar_item_risk`` inside ``app.api.v1.client``
and was consumed by the client calendar and the portfolio aggregate, while the
provider calendar (``app.api.v1.portal``) had *no* server-side risk at all and
re-derived urgency on the frontend. Pulling the classifier into a neutral
service module lets all three calendars — client, provider, and the admin
portfolio grid — compute the six-tier risk vocabulary in exactly one place, so
they can never disagree (and ``portal.py`` can import it without the circular
dependency that blocked sharing ``client.py``'s copy).

This module depends only on ``app.constants.statuses`` + ``datetime`` — no
router imports — so any layer may import it at module load.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from app.constants.statuses import DocumentStatus

# Most-severe-first ordinal for the six tiers. The single source the admin
# cross-portfolio grid, the snapshot rollup, and the per-provider sorts all
# order by; mirrors ``RISK_ORDER`` on the frontend (calendar-shared.ts) so the
# colors and worst-risk math can never drift across calendars or layers.
RISK_ORDER: dict[str, int] = {
    "overdue": 0,
    "action_required": 1,
    "due_soon": 2,
    "in_review": 3,
    "upcoming": 4,
    "on_track": 5,
}


def worst_calendar_risk(risks: Iterable[str]) -> str:
    """Most-severe (lowest-ordinal) risk in a set, defaulting to ``on_track``."""
    worst = "on_track"
    for r in risks:
        if RISK_ORDER.get(r, 9) < RISK_ORDER.get(worst, 9):
            worst = r
    return worst


def calendar_deadline_iso(year: int, due_month: int, due_day: int) -> str:
    """Canonical REPSE deadline as an ISO date string (day-17 cutoff by
    convention; the SAT annual row carries due_day=30 in the catalog)."""
    return f"{year:04d}-{due_month:02d}-{due_day:02d}"

# Statuses where the provider must re-do the document (the reviewer bounced it).
# Mirrors the legacy tuple in ``client.py`` / ``admin.py``; kept here as the
# canonical copy so the risk classifier and its callers read one definition.
REJECTED_OR_CORRECTION_STATUSES = (
    DocumentStatus.RECHAZADO.value,
    DocumentStatus.REQUIERE_ACLARACION.value,
    DocumentStatus.POSIBLE_MISMATCH.value,
)

# Statuses that "satisfy" an obligation — the slot is done and no reminder
# should fire. These map to the ``on_track`` risk tier in
# ``calendar_item_risk``; kept here as the canonical copy so the reporting
# emitter's suppression set and the risk classifier never drift.
SATISFYING_STATUSES = (
    DocumentStatus.APROBADO.value,
    DocumentStatus.EXCEPCION_LEGAL.value,
    DocumentStatus.NO_APLICA.value,
)


def calendar_item_risk(status: str, deadline_iso: str, today: date) -> str:
    """Classify one calendar obligation's current severity.

    Returns a single ordered severity the calendars band/sort/color by, so no
    frontend ever re-derives urgency from raw dates. Most-severe wins:

    * ``on_track``        - resolved (aprobado / excepcion legal / no aplica)
    * ``overdue``         - past its deadline (or VENCIDO) and not resolved
    * ``action_required`` - rejected / needs clarification / possible mismatch
    * ``due_soon``        - due within 14 days and not resolved
    * ``in_review``       - submitted, with reviewer (recibido / prevalidado / en revision)
    * ``upcoming``        - not yet submitted, due in 15+ days

    The ``due_soon`` window (<=14 days, >=0) matches the existing
    ``due_soon_total`` convention so the calendar's surfaces never disagree by a
    few days.
    """
    if status in SATISFYING_STATUSES:
        return "on_track"
    try:
        days_until: int | None = (date.fromisoformat(deadline_iso) - today).days
    except ValueError:
        days_until = None
    if status == DocumentStatus.VENCIDO.value or (
        days_until is not None and days_until < 0
    ):
        return "overdue"
    if status in REJECTED_OR_CORRECTION_STATUSES:
        return "action_required"
    if days_until is not None and 0 <= days_until <= 14:
        return "due_soon"
    if status in (
        DocumentStatus.RECIBIDO.value,
        DocumentStatus.PENDIENTE_REVISION.value,
        DocumentStatus.PREVALIDADO.value,
    ):
        return "in_review"
    return "upcoming"
