"""Phase 6 / Slice 6A — renewal rule layer.

Pure-helper coverage. No DB, no FastAPI client — these tests pin the
contract of the four pieces that ship in Slice 6A:

* ``OnboardingRequirement.renewal_frequency_days`` is set on the four
  renewal-bearing rows (CSF moral, CSF física, REPSE original,
  registro patronal original) and unset on everything else.
* ``onboarding_renewal_frequency_days`` returns the field verbatim
  (no transformation).
* ``renewal_anchor_date`` only honors approved submissions and reads
  the day from ``updated_at`` (the workflow service touches it on
  every status transition).
* ``next_renewal_due_date`` adds the cadence in days and returns
  ``None`` when either input is missing.
* ``renewal_status`` buckets the due date into ``overdue`` /
  ``due_soon`` (within 30 days) / ``ok``.

Slice 6B will add notification-emit coverage. Slice 6C will add
scheduler / idempotency coverage. Both will use the helpers under
test here.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.constants.statuses import DocumentStatus
from app.core.compliance_catalog import (
    expediente_for_persona,
    lookup_onboarding_by_code,
    onboarding_renewal_frequency_days,
)
from app.services.evidence_slots import (
    next_renewal_due_date,
    renewal_anchor_date,
    renewal_status,
)

# ---------------------------------------------------------------------------
# Catalog field — the four seeded rows
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code,expected_days",
    [
        ("ONB-CORP-M-002", 90),  # CSF moral
        ("ONB-CORP-F-002", 90),  # CSF física
        ("ONB-REPSE-001", 1095),  # REPSE original — 3 years
        ("ONB-PATR-001", 1095),  # registro patronal — 3 years
    ],
)
def test_renewal_frequency_set_on_renewal_bearing_rows(
    code: str, expected_days: int
) -> None:
    req = lookup_onboarding_by_code(code)
    assert req is not None, code
    assert req.renewal_frequency_days == expected_days
    # Accessor must return the same value verbatim.
    assert onboarding_renewal_frequency_days(req) == expected_days


def test_renewal_frequency_unset_on_one_time_onboarding_rows() -> None:
    """Every other onboarding row stays one-time (no renewal cadence).

    The CSF moral / física / REPSE / patronal rows are the only ones
    that should carry a cadence in Slice 6A. The opt-in ``-002`` /
    ``-003`` "updates" / "renewals" rows for REPSE and patronal are
    provider-driven uploads, not schedule-driven, and must stay None.
    """
    renewal_codes = {
        "ONB-CORP-M-002",
        "ONB-CORP-F-002",
        "ONB-REPSE-001",
        "ONB-PATR-001",
    }
    for persona in ("moral", "fisica"):
        for req in expediente_for_persona(persona):  # type: ignore[arg-type]
            if req.code in renewal_codes:
                continue
            assert req.renewal_frequency_days is None, req.code


# ---------------------------------------------------------------------------
# renewal_anchor_date — approved-only, reads updated_at
# ---------------------------------------------------------------------------


def _stub_submission(*, status: str, updated_at: datetime) -> SimpleNamespace:
    """Minimal stand-in for a Submission row — only the two attributes
    ``renewal_anchor_date`` reads.
    """
    return SimpleNamespace(status=status, updated_at=updated_at)


def test_renewal_anchor_date_none_for_missing_submission() -> None:
    assert renewal_anchor_date(None) is None


@pytest.mark.parametrize(
    "status",
    [
        DocumentStatus.PENDIENTE.value,
        DocumentStatus.RECIBIDO.value,
        DocumentStatus.PENDIENTE_REVISION.value,
        DocumentStatus.PREVALIDADO.value,
        DocumentStatus.POSIBLE_MISMATCH.value,
        DocumentStatus.RECHAZADO.value,
        DocumentStatus.REQUIERE_ACLARACION.value,
        DocumentStatus.EXCEPCION_LEGAL.value,
        DocumentStatus.VENCIDO.value,
        DocumentStatus.NO_APLICA.value,
    ],
)
def test_renewal_anchor_date_none_for_non_approved_status(status: str) -> None:
    sub = _stub_submission(status=status, updated_at=datetime(2026, 5, 1, 12, 0))
    assert renewal_anchor_date(sub) is None


def test_renewal_anchor_date_returns_updated_at_date_for_approved() -> None:
    sub = _stub_submission(
        status=DocumentStatus.APROBADO.value,
        updated_at=datetime(2026, 3, 15, 9, 45, 12),
    )
    anchor = renewal_anchor_date(sub)
    assert anchor is not None
    assert anchor.year == 2026
    assert anchor.month == 3
    assert anchor.day == 15


# ---------------------------------------------------------------------------
# next_renewal_due_date — pure cadence math
# ---------------------------------------------------------------------------


def test_next_due_none_when_anchor_missing() -> None:
    assert next_renewal_due_date(anchor=None, frequency_days=90) is None


def test_next_due_none_when_frequency_missing() -> None:
    sub = _stub_submission(
        status=DocumentStatus.APROBADO.value,
        updated_at=datetime(2026, 1, 1, 0, 0),
    )
    anchor = renewal_anchor_date(sub)
    assert next_renewal_due_date(anchor=anchor, frequency_days=None) is None
    assert next_renewal_due_date(anchor=anchor, frequency_days=0) is None


@pytest.mark.parametrize("frequency_days", [90, 365, 1095])
def test_next_due_adds_frequency_in_days(frequency_days: int) -> None:
    sub = _stub_submission(
        status=DocumentStatus.APROBADO.value,
        updated_at=datetime(2026, 2, 1, 12, 0),
    )
    anchor = renewal_anchor_date(sub)
    due = next_renewal_due_date(anchor=anchor, frequency_days=frequency_days)
    assert anchor is not None and due is not None
    assert (due - anchor) == timedelta(days=frequency_days)


# ---------------------------------------------------------------------------
# renewal_status — 30-day window bucket
# ---------------------------------------------------------------------------


def test_renewal_status_none_when_due_none() -> None:
    sub = _stub_submission(
        status=DocumentStatus.APROBADO.value,
        updated_at=datetime(2026, 5, 1, 0, 0),
    )
    anchor = renewal_anchor_date(sub)
    due = next_renewal_due_date(anchor=anchor, frequency_days=None)
    assert renewal_status(due, datetime(2026, 5, 1).date()) is None


@pytest.mark.parametrize(
    "days_offset,expected",
    [
        # CSF (90-day cadence) — anchor + 90 days = due date.
        # We anchor at today - X and ask for status.
        (30, "ok"),         # approved 30 days ago → due in 60 days → ok
        (59, "ok"),         # approved 59 days ago → due in 31 days → ok
        (60, "due_soon"),   # approved 60 days ago → due in 30 days → due_soon
        (83, "due_soon"),   # approved 83 days ago → due in 7 days → due_soon
        (89, "due_soon"),   # approved 89 days ago → due in 1 day → due_soon
        (90, "due_soon"),   # approved exactly 90 days ago → due today → due_soon
        (91, "overdue"),    # approved 91 days ago → due 1 day ago → overdue
        (180, "overdue"),   # well past
    ],
)
def test_renewal_status_csf_cadence(days_offset: int, expected: str) -> None:
    """CSF is the smallest cadence (90 days) and is the row most likely
    to exercise the boundaries (the REPSE / patronal 1095-day cadence
    crosses the same boundaries — same math, different scale)."""
    today = datetime(2026, 6, 1).date()
    anchor_dt = datetime(2026, 6, 1, 12, 0) - timedelta(days=days_offset)
    sub = _stub_submission(
        status=DocumentStatus.APROBADO.value,
        updated_at=anchor_dt,
    )
    anchor = renewal_anchor_date(sub)
    due = next_renewal_due_date(anchor=anchor, frequency_days=90)
    assert renewal_status(due, today) == expected


def test_renewal_status_ok_when_far_from_due() -> None:
    """Status is ``ok`` only when more than 30 days remain."""
    today = datetime(2026, 6, 1).date()
    # Approved 1 day ago → due in 89 days → ok
    anchor_dt = datetime(2026, 6, 1, 12, 0) - timedelta(days=1)
    sub = _stub_submission(
        status=DocumentStatus.APROBADO.value,
        updated_at=anchor_dt,
    )
    anchor = renewal_anchor_date(sub)
    due = next_renewal_due_date(anchor=anchor, frequency_days=90)
    assert renewal_status(due, today) == "ok"


def test_renewal_status_repse_cadence_overdue() -> None:
    """REPSE / patronal share a 1095-day cadence — sanity-check the
    boundary at the larger scale."""
    today = datetime(2029, 6, 1).date()
    # Approved 1096 days ago → due 1 day ago → overdue.
    anchor_dt = datetime(2029, 6, 1, 12, 0) - timedelta(days=1096)
    sub = _stub_submission(
        status=DocumentStatus.APROBADO.value,
        updated_at=anchor_dt,
    )
    anchor = renewal_anchor_date(sub)
    due = next_renewal_due_date(anchor=anchor, frequency_days=1095)
    assert renewal_status(due, today) == "overdue"
