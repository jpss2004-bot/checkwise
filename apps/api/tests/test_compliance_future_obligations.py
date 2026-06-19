"""Reportes #7 (Portal Proveedor, 2ª revisión).

Future-period obligations (deadline not yet reached) must not drag down the
*current* compliance semaphore — they aren't late, they just aren't due yet.
This pins ``_currently_due_calendar_slots``, the filter that the provider
dashboard, client vendor views, wise client-context and the report
``compliance_state`` block all feed into the semaphore computation.
"""

from __future__ import annotations

from datetime import date

from app.api.v1.portal import _currently_due_calendar_slots
from app.services.evidence_slots import SlotKey, SlotState, SlotView

# Fixed "now" so deadline math (17th-of-period cutoff) is deterministic.
_TODAY = date(2026, 6, 19)


def _cal_slot(period_key: str | None) -> SlotView:
    return SlotView(
        slot_key=SlotKey(
            workspace_id="ws",
            client_id="client",
            vendor_id="vendor",
            requirement_code="imss",
            period_key=period_key,
        ),
        state=SlotState.MISSING,
        requirement_code="imss",
        period_key=period_key,
        requirement_name="IMSS",
        institution="imss",
        required=True,
        current_submission_id=None,
        current_status=None,
        submitted_at_iso=None,
        superseded_count=0,
    )


def test_drops_future_period_obligations():
    # 2026-M07 is due 2026-07-17 — 28 days after _TODAY, not due yet.
    future = _cal_slot("2026-M07")
    assert _currently_due_calendar_slots([future], _TODAY) == []


def test_keeps_overdue_and_current_period():
    overdue = _cal_slot("2026-M05")  # due 2026-05-17 — already past
    current = _cal_slot("2026-M06")  # due 2026-06-17 — just before today
    kept = _currently_due_calendar_slots([overdue, current], _TODAY)
    assert kept == [overdue, current]


def test_keeps_unparseable_period_conservatively():
    # Never silently drop a real obligation we can't date.
    none_key = _cal_slot(None)
    junk = _cal_slot("not-a-period")
    kept = _currently_due_calendar_slots([none_key, junk], _TODAY)
    assert kept == [none_key, junk]


def test_mixed_set_partitions_correctly():
    slots = [
        _cal_slot("2026-M05"),  # overdue  -> keep
        _cal_slot("2026-M08"),  # future   -> drop
        _cal_slot(None),  # unknown  -> keep
    ]
    kept = _currently_due_calendar_slots(slots, _TODAY)
    assert [s.period_key for s in kept] == ["2026-M05", None]
