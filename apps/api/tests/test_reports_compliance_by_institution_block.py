"""compliance_by_institution — registration, scope resolution, bucket map.

The block is scope-adaptive (vendor → own docs, client → portfolio) and
deterministic (no AI). These tests assert it's wired in, returns None
when the scope resolves to neither a vendor nor a client (so it can't be
forced to query unscoped), carries no AI summary, and that the
status→semáforo bucket map covers every DocumentStatus.
"""

from __future__ import annotations

from app.constants.reports import ReportAudience
from app.services.evidence_slots import SlotState
from app.services.reports.block_catalog import KNOWN_BLOCK_TYPES, catalog_by_type
from app.services.reports.blocks.ai_summaries import has_ai_summary
from app.services.reports.blocks.data_fetchers import (
    _FETCHERS,
    _SLOT_INSTITUTION_BUCKET,
    fetch_compliance_by_institution,
)
from app.services.reports.context import ReportScope


def test_by_institution_returns_none_without_vendor_or_client() -> None:
    # An internal report with no client/vendor resolved has nothing to
    # scope to — must not run an unscoped count.
    scope = ReportScope(
        organization_id="org",
        audience=ReportAudience.INTERNAL_ONLY,
        client_id=None,
        vendor_id=None,
    )
    assert fetch_compliance_by_institution({}, scope, db=None) is None


def test_by_institution_registered() -> None:
    assert "compliance_by_institution" in KNOWN_BLOCK_TYPES
    assert "compliance_by_institution" in _FETCHERS
    # Config-less block.
    entry = catalog_by_type()["compliance_by_institution"]
    assert entry.input_schema.get("properties") == {}


def test_by_institution_has_no_ai_summary() -> None:
    assert has_ai_summary("compliance_by_institution") is False


def test_institution_bucket_covers_every_slot_state() -> None:
    # Every SlotState except NOT_APPLICABLE maps to a semáforo bucket so
    # no obligation is silently dropped; NOT_APPLICABLE carries no
    # obligation and is intentionally excluded.
    for state in SlotState:
        if state == SlotState.NOT_APPLICABLE:
            assert state.value not in _SLOT_INSTITUTION_BUCKET
            continue
        assert state.value in _SLOT_INSTITUTION_BUCKET, state
        assert _SLOT_INSTITUTION_BUCKET[state.value] in (
            "al_dia",
            "en_proceso",
            "en_riesgo",
        )
