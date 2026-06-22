"""compliance_overview block — registration + the portfolio-audience gate.

The block is a deterministic cliente-report band (hero KPIs + per-provider
bar). The critical safety property: it rolls up *every* vendor under a
client, so it must never be served to a vendor_facing / external_signed
report — whose scope still carries the workspace's client_id and would
otherwise leak sibling providers' counts and identities to one provider.

These tests assert the gate fires before any DB access (so they need no
fixtures) and that the block is wired into the catalog + dispatcher with
no AI summary.
"""

from __future__ import annotations

from app.constants.reports import ReportAudience
from app.services.reports.block_catalog import KNOWN_BLOCK_TYPES, catalog_by_type
from app.services.reports.blocks.ai_summaries import has_ai_summary
from app.services.reports.blocks.data_fetchers import (
    _FETCHERS,
    fetch_compliance_overview,
    fetch_compliance_radar,
)
from app.services.reports.context import ReportScope


def test_portfolio_blocks_gated_to_client_and_internal_audiences() -> None:
    overview_cfg = {"top_n_vendors": 12}
    radar_cfg = {"top_n_vendors": 8, "include_history": False}

    # vendor_facing / external_signed carry a client_id (the workspace's
    # client) but must NOT receive the portfolio rollup. The gate returns
    # None before touching the DB, so db=None is safe here.
    for aud in (ReportAudience.VENDOR_FACING, ReportAudience.EXTERNAL_SIGNED):
        scope = ReportScope(
            organization_id="org",
            audience=aud,
            client_id="c1",
            vendor_id="v1",
        )
        assert fetch_compliance_overview(overview_cfg, scope, db=None) is None
        assert fetch_compliance_radar(radar_cfg, scope, db=None) is None


def test_overview_returns_none_for_clientless_scope() -> None:
    # client_facing but no client_id resolved → nothing to roll up.
    scope = ReportScope(
        organization_id="org",
        audience=ReportAudience.CLIENT_FACING,
        client_id=None,
        vendor_id=None,
    )
    assert fetch_compliance_overview({"top_n_vendors": 12}, scope, db=None) is None


def test_compliance_overview_registered() -> None:
    assert "compliance_overview" in KNOWN_BLOCK_TYPES
    assert "compliance_overview" in _FETCHERS
    entry = catalog_by_type()["compliance_overview"]
    assert "top_n_vendors" in entry.input_schema["properties"]


def test_compliance_overview_has_no_ai_summary() -> None:
    # Deterministic by design — nothing for the LLM to (mis)write.
    assert has_ai_summary("compliance_overview") is False
