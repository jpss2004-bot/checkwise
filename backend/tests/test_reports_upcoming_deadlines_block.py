"""Tests for the ``upcoming_deadlines`` block (P1.4).

Layers:

1. ``dashboard_compute.compute_upcoming_deadlines`` — pure helper.
2. ``dashboard_compute.bucket_upcoming_by_urgency`` — bucket mapping.
3. ``dashboard_compute.build_upcoming_deadlines_for_vendor`` — builder
   with empty/active workspace.
4. ``app.services.reports.blocks.upcoming_deadlines.fetch_upcoming_deadlines``
   — filter + top semantics.
5. Catalog registration.
6. Agreement: the new dict-output ``compute_upcoming_deadlines`` and
   the portal Pydantic ``_compute_upcoming_deadlines`` produce the
   same id / title / institution / period_key / due_month / state /
   href tuples for any slot input. Pins the contract.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.portal import (
    _compute_upcoming_deadlines as portal_compute_upcoming_deadlines,
)
from app.constants.reports import ReportAudience
from app.db.base import Base
from app.models import Client, ProviderWorkspace, User, Vendor, entities  # noqa: F401
from app.services.dashboard_compute import (
    URGENCY_BANDS,
    bucket_upcoming_by_urgency,
    build_upcoming_deadlines_for_vendor,
    compute_upcoming_deadlines,
)
from app.services.evidence_slots import SlotKey, SlotState, SlotView
from app.services.reports.block_catalog import (
    CATALOG,
    KNOWN_BLOCK_TYPES,
    catalog_by_type,
    planner_tool_list,
)
from app.services.reports.blocks.upcoming_deadlines import (
    fetch_upcoming_deadlines,
)
from app.services.reports.context import ReportScope

# ─── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
def db_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _cal_slot(
    state: SlotState,
    *,
    period_key: str,
    requirement_code: str = "iva",
    institution: str = "sat",
    required: bool = True,
    submission_id: str | None = None,
) -> SlotView:
    return SlotView(
        slot_key=SlotKey(
            workspace_id="ws-test",
            client_id="client-test",
            vendor_id="vendor-test",
            requirement_code=requirement_code,
            period_key=period_key,
        ),
        state=state,
        requirement_code=requirement_code,
        period_key=period_key,
        requirement_name=f"Documento {requirement_code} {period_key}",
        institution=institution,
        required=required,
        current_submission_id=submission_id,
        current_status=None,
        submitted_at_iso=None,
        superseded_count=0,
    )


def _scope(vendor_id: str | None = "vend-a") -> ReportScope:
    return ReportScope(
        organization_id="org-a",
        audience=ReportAudience.VENDOR_FACING,
        client_id="client-a",
        vendor_id=vendor_id,
        period=None,
    )


def _seed_workspace(db_factory) -> str:
    db = db_factory()
    try:
        client = Client(name="Client A")
        db.add(client)
        db.flush()
        vendor = Vendor(
            client_id=client.id,
            name="Vendor A",
            rfc="V12345678901",
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()
        user = User(
            email="ws_owner@ud.test",
            password_hash="x",
            full_name="WS Owner",
            status="active",
        )
        db.add(user)
        db.flush()
        ws = ProviderWorkspace(
            client_id=client.id,
            vendor_id=vendor.id,
            contract_id=None,
            owner_user_id=user.id,
            filial_name="Filial",
            persona_type="moral",
            display_name="Vendor A",
            access_token=f"tok-{vendor.id}",
            onboarding_completed_at=None,
            status="active",
        )
        db.add(ws)
        db.commit()
        return vendor.id
    finally:
        db.close()


# ─── compute_upcoming_deadlines ────────────────────────────────


def test_upcoming_skips_resolved_and_overdue() -> None:
    today = date(2026, 5, 10)
    calendar = [
        _cal_slot(SlotState.APPROVED, period_key="2026-M05"),       # resolved → skip
        _cal_slot(SlotState.EXCEPTION, period_key="2026-M05"),      # resolved → skip
        _cal_slot(SlotState.NOT_APPLICABLE, period_key="2026-M05"), # resolved → skip
        _cal_slot(SlotState.MISSING, period_key="2026-M03"),         # overdue → skip
        _cal_slot(SlotState.MISSING, period_key="2026-M06"),         # future → keep
    ]
    items = compute_upcoming_deadlines(calendar, today)
    assert [i["period_key"] for i in items] == ["2026-M06"]


def test_upcoming_skips_optional() -> None:
    today = date(2026, 5, 10)
    calendar = [_cal_slot(SlotState.MISSING, period_key="2026-M06", required=False)]
    assert compute_upcoming_deadlines(calendar, today) == []


def test_upcoming_sorted_ascending_by_due_in_days() -> None:
    today = date(2026, 5, 10)
    calendar = [
        _cal_slot(
            SlotState.MISSING, period_key="2026-M08", requirement_code="far"
        ),  # ~99
        _cal_slot(
            SlotState.MISSING, period_key="2026-M05", requirement_code="soon"
        ),  # 7
        _cal_slot(
            SlotState.MISSING, period_key="2026-M06", requirement_code="mid"
        ),  # 38
    ]
    items = compute_upcoming_deadlines(calendar, today)
    assert [i["requirement_code"] for i in items] == ["soon", "mid", "far"]
    # due_in_days is also included so the frontend can render the timeline.
    assert items[0]["due_in_days"] == 7


def test_upcoming_respects_top_parameter() -> None:
    today = date(2026, 5, 10)
    calendar = [
        _cal_slot(
            SlotState.MISSING,
            period_key=f"2026-M{m:02d}",
            requirement_code=f"r{m}",
        )
        for m in (6, 7, 8, 9, 10)
    ]
    items = compute_upcoming_deadlines(calendar, today, top=3)
    assert len(items) == 3


def test_upcoming_exposes_due_month_and_href() -> None:
    today = date(2026, 5, 10)
    items = compute_upcoming_deadlines(
        [_cal_slot(SlotState.MISSING, period_key="2026-M07", requirement_code="iva")],
        today,
    )
    assert items[0]["due_month"] == 7
    assert items[0]["href"].startswith("/portal/upload?")


# ─── bucket_upcoming_by_urgency ────────────────────────────────


def test_buckets_classify_by_band() -> None:
    items = [
        {"due_in_days": 0},
        {"due_in_days": 7},
        {"due_in_days": 8},
        {"due_in_days": 14},
        {"due_in_days": 15},
        {"due_in_days": 30},
        {"due_in_days": 31},
        {"due_in_days": 90},
        {"due_in_days": None},
    ]
    buckets = bucket_upcoming_by_urgency(items)
    # 0..7 → week (2 items: 0, 7).
    assert buckets["week"] == 2
    # 8..14 → fortnight (2 items: 8, 14).
    assert buckets["fortnight"] == 2
    # 15..30 → month (2 items: 15, 30).
    assert buckets["month"] == 2
    # 31+ and None → later (3 items: 31, 90, None).
    assert buckets["later"] == 3


def test_buckets_keys_match_url_band_keys() -> None:
    """The dict keys must match URGENCY_BANDS[*].key — the frontend
    relies on the contract."""
    items: list[dict] = []
    buckets = bucket_upcoming_by_urgency(items)
    assert set(buckets.keys()) == {b["key"] for b in URGENCY_BANDS}


# ─── build_upcoming_deadlines_for_vendor ───────────────────────


def test_builder_empty_for_unknown_vendor(db_factory) -> None:
    db = db_factory()
    try:
        out = build_upcoming_deadlines_for_vendor(db, vendor_id="nope")
    finally:
        db.close()
    assert out["items"] == []
    assert out["workspace_id"] is None
    assert out["fetched_at"]
    assert out["as_of"]
    assert all(v == 0 for v in out["urgency_buckets"].values())


def test_builder_returns_shape_for_seeded_workspace(db_factory) -> None:
    vendor_id = _seed_workspace(db_factory)
    db = db_factory()
    try:
        out = build_upcoming_deadlines_for_vendor(db, vendor_id=vendor_id)
    finally:
        db.close()
    assert out["workspace_id"] is not None
    assert isinstance(out["items"], list)
    assert set(out["urgency_buckets"].keys()) == {
        b["key"] for b in URGENCY_BANDS
    }


# ─── fetcher ────────────────────────────────────────────────────


def test_fetcher_empty_when_no_vendor(db_factory) -> None:
    db = db_factory()
    try:
        out = fetch_upcoming_deadlines({}, _scope(vendor_id=None), db)
    finally:
        db.close()
    assert out["items"] == []
    assert out["workspace_id"] is None
    assert out["total_before_filter"] == 0
    assert out["top"] >= 1


def test_fetcher_filters_by_institution(db_factory) -> None:
    """institution filter narrows; non-listed institutions drop."""
    vendor_id = _seed_workspace(db_factory)
    import app.services.reports.blocks.upcoming_deadlines as ud_module

    sample = {
        "items": [
            {"id": "a", "title": "A", "institution": "sat",
             "period_key": "2026-M06", "due_month": 6, "due_in_days": 38,
             "state": "missing", "href": "/portal/upload?a",
             "requirement_code": "a"},
            {"id": "b", "title": "B", "institution": "imss",
             "period_key": "2026-M06", "due_month": 6, "due_in_days": 38,
             "state": "missing", "href": "/portal/upload?b",
             "requirement_code": "b"},
        ],
        "urgency_buckets": {"week": 0, "fortnight": 0, "month": 0, "later": 2},
        "workspace_id": "ws-x",
        "fetched_at": "2026-05-10T00:00:00Z",
        "as_of": "2026-05-10",
    }
    original = ud_module.build_upcoming_deadlines_for_vendor
    ud_module.build_upcoming_deadlines_for_vendor = (
        lambda db, *, vendor_id, top: sample
    )
    try:
        db = db_factory()
        try:
            out = fetch_upcoming_deadlines(
                {"filter": {"institutions": ["sat"]}},
                _scope(vendor_id=vendor_id),
                db,
            )
        finally:
            db.close()
    finally:
        ud_module.build_upcoming_deadlines_for_vendor = original
    assert [i["institution"] for i in out["items"]] == ["sat"]
    assert out["filter_applied"]["institutions"] == ["sat"]
    assert out["total_before_filter"] == 2
    # Urgency buckets must be recomputed over the filtered set.
    assert sum(out["urgency_buckets"].values()) == 1


def test_fetcher_clamps_top_to_max(db_factory) -> None:
    vendor_id = _seed_workspace(db_factory)
    import app.services.reports.blocks.upcoming_deadlines as ud_module

    sample = {
        "items": [
            {"id": str(i), "title": f"item-{i}", "institution": "sat",
             "period_key": "2026-M06", "due_month": 6, "due_in_days": 38 + i,
             "state": "missing", "href": "/portal/upload?", "requirement_code": f"r-{i}"}
            for i in range(20)
        ],
        "urgency_buckets": {"week": 0, "fortnight": 0, "month": 0, "later": 20},
        "workspace_id": "ws-x",
        "fetched_at": "2026-05-10T00:00:00Z",
        "as_of": "2026-05-10",
    }
    original = ud_module.build_upcoming_deadlines_for_vendor
    ud_module.build_upcoming_deadlines_for_vendor = (
        lambda db, *, vendor_id, top: sample
    )
    try:
        db = db_factory()
        try:
            out = fetch_upcoming_deadlines(
                {"top": 999},
                _scope(vendor_id=vendor_id),
                db,
            )
        finally:
            db.close()
    finally:
        ud_module.build_upcoming_deadlines_for_vendor = original
    assert out["top"] == 12  # MAX_TOP
    assert len(out["items"]) == 12


# ─── catalog ────────────────────────────────────────────────────


def test_upcoming_deadlines_registered_in_catalog() -> None:
    assert "upcoming_deadlines" in KNOWN_BLOCK_TYPES
    entry = catalog_by_type()["upcoming_deadlines"]
    props = entry.input_schema["properties"]
    assert "top" in props and "filter" in props


def test_upcoming_deadlines_in_planner_tools() -> None:
    tools = planner_tool_list()
    names = [t["name"] for t in tools]
    assert "upcoming_deadlines" in names


def test_upcoming_deadlines_appears_after_attention_list() -> None:
    """Append-only ordering: each provider slice extends the catalog
    tail with its new block. P1.4 adds upcoming_deadlines after
    attention_list. We assert relative ordering rather than the
    literal tail so subsequent slices don't have to re-touch this
    test."""
    catalog_types = [entry.type for entry in CATALOG]
    assert catalog_types.index("upcoming_deadlines") > catalog_types.index(
        "attention_list"
    )


# ─── Agreement with portal._compute_upcoming_deadlines ─────────


@pytest.mark.parametrize(
    "calendar_specs",
    [
        # Mix of urgencies, periods.
        [(SlotState.MISSING, "2026-M06"), (SlotState.IN_REVIEW, "2026-M07")],
        # Includes one that should be skipped (resolved).
        [(SlotState.APPROVED, "2026-M06"), (SlotState.MISSING, "2026-M07")],
        # All overdue or resolved → both producers empty.
        [(SlotState.MISSING, "2026-M01"), (SlotState.APPROVED, "2026-M05")],
        # Empty input.
        [],
    ],
)
def test_compute_upcoming_agrees_with_portal_compute_upcoming(
    calendar_specs,
) -> None:
    today = date(2026, 5, 10)
    calendar = [
        _cal_slot(state, period_key=pk, requirement_code=f"r-{idx}")
        for idx, (state, pk) in enumerate(calendar_specs)
    ]
    new_items = compute_upcoming_deadlines(calendar, today)
    portal_items = portal_compute_upcoming_deadlines(calendar, today)

    def _portal_tuple(p):
        return (p.id, p.title, p.institution, p.period_key, p.due_month, p.state, p.href)

    def _new_tuple(n):
        return (n["id"], n["title"], n["institution"], n["period_key"], n["due_month"], n["state"], n["href"])

    assert [_new_tuple(n) for n in new_items] == [
        _portal_tuple(p) for p in portal_items
    ]
