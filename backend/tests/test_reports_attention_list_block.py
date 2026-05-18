"""Tests for the ``attention_list`` block (P1.3).

Layers:

1. ``dashboard_compute`` — pure helpers (``compute_attention_items``,
   ``onboarding_reupload_href``, ``calendar_reupload_href``,
   ``due_in_days_for_period``).
2. The block fetcher in
   ``app.services.reports.blocks.attention_list``: filter semantics,
   max_rows cap, empty shapes.
3. Block catalog registration.
4. Agreement: the new ``compute_attention_items`` (dicts) and the
   in-place portal ``_compute_attention_today`` (Pydantic) produce the
   same id/title/institution/state/due_in_days/href tuples for any
   slot input. Pins the contract until the portal endpoint migrates
   onto the shared service.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.portal import (
    _compute_attention_today as portal_compute_attention_today,
)
from app.constants.reports import ReportAudience
from app.db.base import Base
from app.models import Client, ProviderWorkspace, User, Vendor, entities  # noqa: F401
from app.services.dashboard_compute import (
    build_attention_items_for_vendor,
    calendar_reupload_href,
    compute_attention_items,
    due_in_days_for_period,
    onboarding_reupload_href,
)
from app.services.evidence_slots import SlotKey, SlotState, SlotView
from app.services.reports.block_catalog import (
    CATALOG,
    KNOWN_BLOCK_TYPES,
    catalog_by_type,
    planner_tool_list,
)
from app.services.reports.blocks.attention_list import fetch_attention_list
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


def _slot(
    state: SlotState,
    *,
    required: bool = True,
    period_key: str | None = None,
    requirement_code: str = "rfc",
    institution: str = "sat",
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
        requirement_name=f"Documento {requirement_code}",
        institution=institution,
        required=required,
        current_submission_id=submission_id,
        current_status=None,
        submitted_at_iso=None,
        superseded_count=0,
    )


def _scope(
    audience: ReportAudience,
    *,
    vendor_id: str | None = "vend-a",
) -> ReportScope:
    return ReportScope(
        organization_id="org-a",
        audience=audience,
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
            email="ws_owner@al.test",
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


# ─── href helpers ──────────────────────────────────────────────


def test_onboarding_href_includes_replaces_only_for_actionable_state() -> None:
    """Replaces= only when the slot is actionable AND has a prior submission."""
    actionable = _slot(SlotState.REJECTED, submission_id="sub-1")
    href = onboarding_reupload_href(actionable)
    assert "replaces=sub-1" in href
    assert "from=onboarding" in href

    no_sub = _slot(SlotState.MISSING)
    href2 = onboarding_reupload_href(no_sub)
    assert "replaces=" not in href2

    has_sub_but_in_review = _slot(SlotState.IN_REVIEW, submission_id="sub-2")
    href3 = onboarding_reupload_href(has_sub_but_in_review)
    assert "replaces=" not in href3  # IN_REVIEW is not actionable


def test_calendar_href_carries_period() -> None:
    view = _slot(
        SlotState.REJECTED,
        period_key="2026-M05",
        submission_id="sub-x",
        requirement_code="iva",
    )
    href = calendar_reupload_href(view)
    assert "period_key=2026-M05" in href
    assert "period_label=2026-M05" in href
    assert "requirement_code=iva" in href
    assert "replaces=sub-x" in href


# ─── due_in_days_for_period ────────────────────────────────────


def test_due_in_days_parses_monthly_period() -> None:
    today = date(2026, 5, 10)
    # Monthly period: deadline conventionally day 17.
    assert due_in_days_for_period("2026-M05", today) == 7
    assert due_in_days_for_period("2026-M04", today) == -23
    assert due_in_days_for_period("2026-M06", today) is not None


def test_due_in_days_parses_annual_and_unparseable() -> None:
    today = date(2026, 5, 10)
    assert due_in_days_for_period("2026-A", today) is not None
    assert due_in_days_for_period(None, today) is None
    assert due_in_days_for_period("garbage", today) is None


# ─── compute_attention_items ───────────────────────────────────


def test_attention_items_surfaces_required_actionable_slots() -> None:
    today = date(2026, 5, 10)
    onboarding = [_slot(SlotState.REJECTED, submission_id="sub-r")]
    calendar = [
        _slot(SlotState.NEEDS_CORRECTION, period_key="2026-M05", submission_id="sub-n"),
        _slot(SlotState.POSSIBLE_MISMATCH, period_key="2026-M05", submission_id="sub-p"),
    ]
    items = compute_attention_items(onboarding, calendar, today)
    states = sorted(i["state"] for i in items)
    assert states == ["needs_correction", "possible_mismatch", "rejected"]
    # Each has a non-empty href.
    for it in items:
        assert it["href"].startswith("/portal/upload?")


def test_attention_items_skips_resolved_and_optional() -> None:
    today = date(2026, 5, 10)
    onboarding = [
        _slot(SlotState.APPROVED),  # resolved → skip
        _slot(SlotState.REJECTED, required=False, submission_id="x"),  # optional → skip
    ]
    items = compute_attention_items(onboarding, [], today)
    assert items == []


def test_attention_items_includes_upcoming_calendar_within_14_days() -> None:
    today = date(2026, 5, 10)
    calendar = [
        _slot(SlotState.MISSING, period_key="2026-M05"),  # due in 7
        _slot(SlotState.MISSING, period_key="2026-M07"),  # due ~68 → skip
    ]
    items = compute_attention_items([], calendar, today)
    assert len(items) == 1
    assert items[0]["due_in_days"] == 7
    assert items[0]["state"] == "missing"


def test_attention_items_caps_at_10() -> None:
    today = date(2026, 5, 10)
    onboarding = [
        _slot(
            SlotState.REJECTED,
            requirement_code=f"req-{i}",
            submission_id=f"sub-{i}",
        )
        for i in range(15)
    ]
    items = compute_attention_items(onboarding, [], today)
    assert len(items) == 10


def test_attention_items_sorts_overdue_first_then_ascending() -> None:
    today = date(2026, 5, 10)
    calendar = [
        _slot(
            SlotState.REJECTED,
            period_key="2026-M07",
            requirement_code="late",
            submission_id="s1",
        ),  # ~68
        _slot(
            SlotState.REJECTED,
            period_key="2026-M03",
            requirement_code="overdue",
            submission_id="s2",
        ),  # negative
        _slot(
            SlotState.REJECTED,
            period_key="2026-M05",
            requirement_code="mid",
            submission_id="s3",
        ),  # 7
    ]
    items = compute_attention_items([], calendar, today)
    codes = [i["requirement_code"] for i in items]
    assert codes == ["overdue", "mid", "late"]


# ─── build_attention_items_for_vendor ──────────────────────────


def test_builder_returns_empty_for_unknown_vendor(db_factory) -> None:
    db = db_factory()
    try:
        out = build_attention_items_for_vendor(db, vendor_id="nope")
    finally:
        db.close()
    assert out["items"] == []
    assert out["workspace_id"] is None
    assert out["fetched_at"]  # always present


def test_builder_resolves_workspace_for_seeded_vendor(db_factory) -> None:
    vendor_id = _seed_workspace(db_factory)
    db = db_factory()
    try:
        out = build_attention_items_for_vendor(db, vendor_id=vendor_id)
    finally:
        db.close()
    assert out["workspace_id"] is not None
    assert isinstance(out["items"], list)
    assert out["fetched_at"]


# ─── attention_list fetcher ────────────────────────────────────


def test_fetcher_empty_when_no_vendor(db_factory) -> None:
    db = db_factory()
    try:
        out = fetch_attention_list(
            {}, _scope(ReportAudience.VENDOR_FACING, vendor_id=None), db
        )
    finally:
        db.close()
    assert out["items"] == []
    assert out["workspace_id"] is None
    assert out["total_before_filter"] == 0


def test_fetcher_applies_state_filter(db_factory) -> None:
    """Filter narrows; never widens. Items in non-listed states must drop."""
    vendor_id = _seed_workspace(db_factory)

    # Patch the builder to return a known list — exercise the filter path
    # without depending on the workspace's seeded slots.
    import app.services.reports.blocks.attention_list as al_module

    sample = {
        "items": [
            {"id": "a", "state": "rejected", "institution": "sat", "title": "A",
             "due_in_days": -2, "href": "/portal/upload?a"},
            {"id": "b", "state": "missing", "institution": "imss", "title": "B",
             "due_in_days": 5, "href": "/portal/upload?b"},
            {"id": "c", "state": "rejected", "institution": "imss", "title": "C",
             "due_in_days": 0, "href": "/portal/upload?c"},
        ],
        "workspace_id": "ws-x",
        "fetched_at": "2026-05-10T00:00:00Z",
    }
    original = al_module.build_attention_items_for_vendor
    al_module.build_attention_items_for_vendor = lambda db, *, vendor_id: sample
    try:
        db = db_factory()
        try:
            out = fetch_attention_list(
                {"filter": {"states": ["rejected"]}},
                _scope(ReportAudience.VENDOR_FACING, vendor_id=vendor_id),
                db,
            )
        finally:
            db.close()
    finally:
        al_module.build_attention_items_for_vendor = original

    ids = sorted(i["id"] for i in out["items"])
    assert ids == ["a", "c"]
    assert out["filter_applied"]["states"] == ["rejected"]
    assert out["total_before_filter"] == 3


def test_fetcher_applies_institution_filter_and_max_rows(db_factory) -> None:
    vendor_id = _seed_workspace(db_factory)
    import app.services.reports.blocks.attention_list as al_module

    sample = {
        "items": [
            {"id": str(i), "state": "rejected", "institution": "sat" if i % 2 == 0 else "imss",
             "title": f"item {i}", "due_in_days": i, "href": f"/portal/upload?id={i}"}
            for i in range(10)
        ],
        "workspace_id": "ws-x",
        "fetched_at": "2026-05-10T00:00:00Z",
    }
    original = al_module.build_attention_items_for_vendor
    al_module.build_attention_items_for_vendor = lambda db, *, vendor_id: sample
    try:
        db = db_factory()
        try:
            out = fetch_attention_list(
                {"filter": {"institutions": ["sat"]}, "max_rows": 3},
                _scope(ReportAudience.VENDOR_FACING, vendor_id=vendor_id),
                db,
            )
        finally:
            db.close()
    finally:
        al_module.build_attention_items_for_vendor = original

    assert len(out["items"]) == 3
    assert all(i["institution"] == "sat" for i in out["items"])
    assert out["max_rows"] == 3


def test_fetcher_applies_only_due_within_days(db_factory) -> None:
    vendor_id = _seed_workspace(db_factory)
    import app.services.reports.blocks.attention_list as al_module

    sample = {
        "items": [
            {"id": "overdue", "state": "rejected", "institution": "sat", "title": "x",
             "due_in_days": -3, "href": "/portal/upload?a"},
            {"id": "in5", "state": "missing", "institution": "sat", "title": "x",
             "due_in_days": 5, "href": "/portal/upload?b"},
            {"id": "in20", "state": "missing", "institution": "sat", "title": "x",
             "due_in_days": 20, "href": "/portal/upload?c"},
            {"id": "noday", "state": "missing", "institution": "sat", "title": "x",
             "due_in_days": None, "href": "/portal/upload?d"},
        ],
        "workspace_id": "ws-x",
        "fetched_at": "2026-05-10T00:00:00Z",
    }
    original = al_module.build_attention_items_for_vendor
    al_module.build_attention_items_for_vendor = lambda db, *, vendor_id: sample
    try:
        db = db_factory()
        try:
            out = fetch_attention_list(
                {"filter": {"only_due_within_days": 14}},
                _scope(ReportAudience.VENDOR_FACING, vendor_id=vendor_id),
                db,
            )
        finally:
            db.close()
    finally:
        al_module.build_attention_items_for_vendor = original

    ids = sorted(i["id"] for i in out["items"])
    # Items with due_in_days <= 14 (incl. negative) survive; None drops.
    assert ids == ["in5", "overdue"]


def test_fetcher_max_rows_clamps_to_25(db_factory) -> None:
    """Configured max_rows above 25 silently clamps to 25 (catalog max)."""
    vendor_id = _seed_workspace(db_factory)
    import app.services.reports.blocks.attention_list as al_module

    sample = {
        "items": [
            {"id": str(i), "state": "rejected", "institution": "sat", "title": "x",
             "due_in_days": i, "href": "/portal/upload?id"}
            for i in range(30)
        ],
        "workspace_id": "ws-x",
        "fetched_at": "2026-05-10T00:00:00Z",
    }
    original = al_module.build_attention_items_for_vendor
    al_module.build_attention_items_for_vendor = lambda db, *, vendor_id: sample
    try:
        db = db_factory()
        try:
            out = fetch_attention_list(
                {"max_rows": 999},
                _scope(ReportAudience.VENDOR_FACING, vendor_id=vendor_id),
                db,
            )
        finally:
            db.close()
    finally:
        al_module.build_attention_items_for_vendor = original
    # canonical builder returns at most 10; max_rows clamp only matters
    # when builder returns more — but the clamp itself caps at 25.
    assert out["max_rows"] == 25
    assert len(out["items"]) <= 25


# ─── Catalog ────────────────────────────────────────────────────


def test_attention_list_registered_in_catalog() -> None:
    assert "attention_list" in KNOWN_BLOCK_TYPES
    entry = catalog_by_type()["attention_list"]
    props = entry.input_schema["properties"]
    assert "filter" in props and "max_rows" in props
    assert entry.input_schema.get("required", []) == []


def test_attention_list_in_planner_tools() -> None:
    tools = planner_tool_list()
    names = [t["name"] for t in tools]
    assert "attention_list" in names
    al = next(t for t in tools if t["name"] == "attention_list")
    assert "vendor_facing" in al["description"]


def test_attention_list_appears_after_compliance_state() -> None:
    """attention_list (P1.3) must be inserted after compliance_state
    (P1.2) — append-only ordering keeps the planner's tool list
    cache-friendly across slice boundaries. We don't pin the tail
    here because subsequent provider slices (P1.4+) append further.
    """
    catalog_types = [entry.type for entry in CATALOG]
    assert catalog_types.index("attention_list") > catalog_types.index(
        "compliance_state"
    )


# ─── Agreement with portal._compute_attention_today ────────────


@pytest.mark.parametrize(
    "onboarding_states,calendar_specs",
    [
        # Pure actionable onboarding.
        (
            [(SlotState.REJECTED, "sub-1"), (SlotState.NEEDS_CORRECTION, "sub-2")],
            [],
        ),
        # Calendar slot due within 14 days.
        ([], [(SlotState.MISSING, "2026-M05", None)]),
        # Mixed: actionable onboarding + calendar upcoming + expired.
        (
            [(SlotState.POSSIBLE_MISMATCH, "sub-3")],
            [
                (SlotState.EXPIRED, "2026-M04", "sub-x"),
                (SlotState.MISSING, "2026-M05", None),
            ],
        ),
        # All resolved — empty result both sides.
        ([(SlotState.APPROVED, None)], [(SlotState.APPROVED, "2026-M05", None)]),
    ],
)
def test_compute_attention_agrees_with_portal_compute_attention(
    onboarding_states, calendar_specs
) -> None:
    """Pin the contract: ``dashboard_compute.compute_attention_items``
    and ``portal._compute_attention_today`` produce the same (id,
    title, institution, state, due_in_days, href) tuples for every
    slot input. If this fails, one of the two has drifted.
    """
    today = date(2026, 5, 10)
    onboarding = [
        _slot(state, submission_id=sid, requirement_code=f"req-{idx}")
        for idx, (state, sid) in enumerate(onboarding_states)
    ]
    calendar = [
        _slot(
            state,
            period_key=pk,
            submission_id=sid,
            requirement_code=f"cal-{idx}",
        )
        for idx, (state, pk, sid) in enumerate(calendar_specs)
    ]
    new_items = compute_attention_items(onboarding, calendar, today)
    portal_items = portal_compute_attention_today(onboarding, calendar, today)

    def _portal_tuple(p):
        return (p.id, p.title, p.institution, p.state, p.due_in_days, p.href)

    def _new_tuple(n):
        return (n["id"], n["title"], n["institution"], n["state"], n["due_in_days"], n["href"])

    assert [_new_tuple(n) for n in new_items] == [
        _portal_tuple(p) for p in portal_items
    ]
