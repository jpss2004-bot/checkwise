"""Stage 2.5 (BL-T8) — Compliance-% safety net regression test.

Locks the structural guarantee that prevents the
"upload-anything-then-100 %" risk the provider feedback transcript
called out. A submission whose classifier flagged a potential
mismatch must not silently count toward ``compliance_pct``, and the
semaphore must read red while any required slot is in an actionable-
blocking state.

These tests exercise the pure-data branches of
``dashboard_compute.compute_semaphore`` directly so the contract is
locked at the SlotState level, not at the HTTP-response level. A
future refactor that accidentally adds POSSIBLE_MISMATCH to
RESOLVED_SLOT_STATES (or removes it from ACTIONABLE_SLOT_STATES)
fails these tests immediately.
"""

from __future__ import annotations

from app.services.dashboard_compute import (
    ACTIONABLE_SLOT_STATES,
    RESOLVED_SLOT_STATES,
    compute_semaphore,
)
from app.services.evidence_slots import SlotKey, SlotState, SlotView


def _slot(state: SlotState, *, required: bool = True, code: str = "ONB-X-001") -> SlotView:
    """Build a SlotView populated with the minimum fields the semaphore reads."""
    return SlotView(
        slot_key=SlotKey(
            workspace_id="ws-1",
            client_id="c-1",
            vendor_id="v-1",
            requirement_code=code,
            period_key=None,
        ),
        state=state,
        requirement_code=code,
        period_key=None,
        requirement_name="Test requirement",
        institution="sat",
        required=required,
        current_submission_id="s-1" if state is not SlotState.MISSING else None,
        current_status=None,
        submitted_at_iso=None,
        superseded_count=0,
    )


# ─── State-set contracts ───────────────────────────────────────────


def test_possible_mismatch_is_actionable_not_resolved() -> None:
    """POSSIBLE_MISMATCH must NEVER count toward ``on_track``.

    This is the single most important contract for trust: a document
    the classifier flagged as a possible-wrong-document cannot reach
    APPROVED without explicit reviewer action. If a future refactor
    moves POSSIBLE_MISMATCH into RESOLVED_SLOT_STATES, a provider
    could upload a manual, get flagged, and still see 100 %.
    """
    assert SlotState.POSSIBLE_MISMATCH in ACTIONABLE_SLOT_STATES
    assert SlotState.POSSIBLE_MISMATCH not in RESOLVED_SLOT_STATES


def test_rejected_and_needs_correction_are_also_actionable() -> None:
    assert SlotState.REJECTED in ACTIONABLE_SLOT_STATES
    assert SlotState.NEEDS_CORRECTION in ACTIONABLE_SLOT_STATES
    assert SlotState.REJECTED not in RESOLVED_SLOT_STATES
    assert SlotState.NEEDS_CORRECTION not in RESOLVED_SLOT_STATES


def test_only_approved_exception_not_applicable_resolve() -> None:
    """The three states that count toward ``on_track``. Any other set
    membership would change the meaning of ``compliance_pct``."""
    assert RESOLVED_SLOT_STATES == frozenset(
        {
            SlotState.APPROVED,
            SlotState.EXCEPTION,
            SlotState.NOT_APPLICABLE,
        }
    )


def test_in_review_and_uploaded_are_not_resolved() -> None:
    """Slots in flight don't count as 100 % until a reviewer acts."""
    assert SlotState.IN_REVIEW not in RESOLVED_SLOT_STATES
    assert SlotState.UPLOADED not in RESOLVED_SLOT_STATES
    assert SlotState.MISSING not in RESOLVED_SLOT_STATES
    assert SlotState.EXPIRED not in RESOLVED_SLOT_STATES


# ─── End-to-end semaphore contracts ────────────────────────────────


def test_one_mismatched_slot_forces_red_and_blocks_100pct() -> None:
    """The textbook failure mode the transcript warned about.

    A workspace with three required slots — two approved, one in
    POSSIBLE_MISMATCH — must read as red semaphore AND
    ``compliance_pct < 100``. If either fails, the "upload anything
    and reach 100 %" risk is back.
    """
    slots = [
        _slot(SlotState.APPROVED, code="ONB-A"),
        _slot(SlotState.APPROVED, code="ONB-B"),
        _slot(SlotState.POSSIBLE_MISMATCH, code="ONB-C"),
    ]
    result = compute_semaphore(slots, [])
    assert result["level"] == "red"
    assert result["compliance_pct"] < 100, result
    assert result["on_track"] == 2
    assert result["total_tracked"] == 3


def test_all_required_approved_reaches_100pct_and_green() -> None:
    slots = [
        _slot(SlotState.APPROVED, code="ONB-A"),
        _slot(SlotState.APPROVED, code="ONB-B"),
    ]
    result = compute_semaphore(slots, [])
    assert result["compliance_pct"] == 100
    assert result["level"] == "green"


def test_in_review_alone_is_yellow_not_green() -> None:
    """A slot waiting for review is not "compliant" yet."""
    slots = [
        _slot(SlotState.APPROVED, code="ONB-A"),
        _slot(SlotState.IN_REVIEW, code="ONB-B"),
    ]
    result = compute_semaphore(slots, [])
    # 1/2 = 50% — not yet green
    assert result["compliance_pct"] == 50
    assert result["level"] == "yellow"


def test_optional_slot_in_mismatch_does_not_force_red() -> None:
    """Only required-slot blockers drive the semaphore to red. An
    optional document in POSSIBLE_MISMATCH does not count against
    the headline state."""
    slots = [
        _slot(SlotState.APPROVED, code="ONB-A", required=True),
        _slot(SlotState.POSSIBLE_MISMATCH, code="ONB-B", required=False),
    ]
    result = compute_semaphore(slots, [])
    # The optional mismatch doesn't enter the `required` filter, so
    # the headline reaches green at 1/1.
    assert result["compliance_pct"] == 100
    assert result["level"] == "green"
