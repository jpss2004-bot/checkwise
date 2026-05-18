"""Tests for the ``prioritized_actions`` block (P1.5).

Layers:

1. ``dashboard_compute`` — pure helpers (``action_title_for_state``,
   ``action_body_for_state``, ``compute_suggested_actions``,
   ``build_suggested_actions_for_vendor``).
2. ``app.services.reports.blocks.prioritized_actions.fetch_prioritized_actions``
   — filter (priorities / types) + max_actions clamp + empty shapes.
3. Catalog registration.
4. Agreement: the new dict-output ``compute_suggested_actions`` and
   the portal Pydantic ``_compute_suggested_actions`` produce the
   same id / type / title / body / priority / href / requirement_code /
   period_key tuples for any slot input.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.portal import (
    _compute_suggested_actions as portal_compute_suggested_actions,
)
from app.constants.reports import ReportAudience
from app.db.base import Base
from app.models import Client, ProviderWorkspace, User, Vendor, entities  # noqa: F401
from app.services.dashboard_compute import (
    action_body_for_state,
    action_title_for_state,
    build_suggested_actions_for_vendor,
    compute_suggested_actions,
)
from app.services.evidence_slots import SlotKey, SlotState, SlotView
from app.services.reports.block_catalog import (
    CATALOG,
    KNOWN_BLOCK_TYPES,
    catalog_by_type,
    planner_tool_list,
)
from app.services.reports.blocks.prioritized_actions import (
    fetch_prioritized_actions,
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


def _slot(
    state: SlotState,
    *,
    period_key: str | None = None,
    requirement_code: str = "rfc",
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
        requirement_name=f"Documento {requirement_code}",
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
            email="ws_owner@pa.test",
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


# ─── title / body helpers ──────────────────────────────────────


def test_title_body_branch_per_state() -> None:
    rejected = _slot(SlotState.REJECTED, submission_id="s1")
    needs = _slot(SlotState.NEEDS_CORRECTION, submission_id="s2")
    mismatch = _slot(SlotState.POSSIBLE_MISMATCH, submission_id="s3")
    other = _slot(SlotState.MISSING)
    assert "rechazado" in action_title_for_state(rejected).lower()
    assert "aclara" in action_title_for_state(needs).lower()
    assert "verifica" in action_title_for_state(mismatch).lower()
    # Non-blocking state falls back to requirement name.
    assert action_title_for_state(other) == "Documento rfc"

    assert "rechaz" in action_body_for_state(rejected).lower()
    assert "aclaración" in action_body_for_state(needs).lower()
    assert "inconsistencia" in action_body_for_state(mismatch).lower()
    # Non-blocking state returns empty body — the caller fills in.
    assert action_body_for_state(other) == ""


# ─── compute_suggested_actions ─────────────────────────────────


def test_actions_blocking_states_get_high_priority() -> None:
    today = date(2026, 5, 10)
    onboarding = [
        _slot(SlotState.REJECTED, requirement_code="rfc", submission_id="s1"),
        _slot(
            SlotState.NEEDS_CORRECTION,
            requirement_code="cif",
            submission_id="s2",
        ),
    ]
    calendar = [
        _slot(
            SlotState.POSSIBLE_MISMATCH,
            period_key="2026-M05",
            requirement_code="iva",
            submission_id="s3",
        ),
    ]
    actions = compute_suggested_actions(onboarding, calendar, today)
    assert [a["priority"] for a in actions] == ["high"] * 3
    types = [a["type"] for a in actions]
    assert types == ["reupload", "clarify", "verify_mismatch"]
    # Every action carries an upload href.
    for a in actions:
        assert a["href"].startswith("/portal/upload?")


def test_actions_missing_onboarding_is_medium() -> None:
    today = date(2026, 5, 10)
    onboarding = [_slot(SlotState.MISSING, requirement_code="rfc")]
    actions = compute_suggested_actions(onboarding, [], today)
    assert len(actions) == 1
    assert actions[0]["priority"] == "medium"
    assert actions[0]["type"] == "complete_onboarding"
    assert actions[0]["period_key"] is None


def test_actions_calendar_upcoming_priority_depends_on_days() -> None:
    # M05 deadline conventionally day 17. Two anchor points exercise
    # both priority branches:
    # - today = 2026-05-13 → due_in = 4 → priority "medium" (≤ 5).
    # - today = 2026-05-08 → due_in = 9 → priority "low" (> 5, ≤ 14).
    cal = [_slot(SlotState.MISSING, period_key="2026-M05", requirement_code="iva-05")]
    medium = compute_suggested_actions([], cal, date(2026, 5, 13))
    low = compute_suggested_actions([], cal, date(2026, 5, 8))
    assert medium[0]["priority"] == "medium"
    assert medium[0]["type"] == "upcoming"
    assert low[0]["priority"] == "low"
    assert low[0]["type"] == "upcoming"

    # An M06 deadline from 2026-05-10 is ~38 days away → outside the
    # 14-day window → skipped entirely.
    cal_far = [_slot(SlotState.MISSING, period_key="2026-M06", requirement_code="iva-06")]
    assert compute_suggested_actions([], cal_far, date(2026, 5, 10)) == []


def test_actions_capped_at_5() -> None:
    today = date(2026, 5, 10)
    onboarding = [
        _slot(SlotState.REJECTED, requirement_code=f"r-{i}", submission_id=f"s{i}")
        for i in range(8)
    ]
    actions = compute_suggested_actions(onboarding, [], today)
    assert len(actions) == 5


# ─── build_suggested_actions_for_vendor ────────────────────────


def test_builder_empty_for_unknown_vendor(db_factory) -> None:
    db = db_factory()
    try:
        out = build_suggested_actions_for_vendor(db, vendor_id="nope")
    finally:
        db.close()
    assert out["items"] == []
    assert out["workspace_id"] is None
    assert out["fetched_at"]
    assert out["as_of"]


def test_builder_returns_shape_for_seeded_workspace(db_factory) -> None:
    vendor_id = _seed_workspace(db_factory)
    db = db_factory()
    try:
        out = build_suggested_actions_for_vendor(db, vendor_id=vendor_id)
    finally:
        db.close()
    assert out["workspace_id"] is not None
    assert isinstance(out["items"], list)


# ─── fetcher ────────────────────────────────────────────────────


def test_fetcher_empty_when_no_vendor(db_factory) -> None:
    db = db_factory()
    try:
        out = fetch_prioritized_actions({}, _scope(vendor_id=None), db)
    finally:
        db.close()
    assert out["items"] == []
    assert out["workspace_id"] is None
    assert out["total_before_filter"] == 0


def test_fetcher_filters_by_priority(db_factory) -> None:
    vendor_id = _seed_workspace(db_factory)
    import app.services.reports.blocks.prioritized_actions as pa_module

    sample = {
        "items": [
            {"id": "h1", "priority": "high", "type": "reupload",
             "title": "T", "body": "B", "href": "/x?h1",
             "requirement_code": "a", "period_key": None},
            {"id": "m1", "priority": "medium", "type": "complete_onboarding",
             "title": "T", "body": "B", "href": "/x?m1",
             "requirement_code": "b", "period_key": None},
            {"id": "h2", "priority": "high", "type": "clarify",
             "title": "T", "body": "B", "href": "/x?h2",
             "requirement_code": "c", "period_key": None},
        ],
        "workspace_id": "ws-x",
        "fetched_at": "2026-05-10T00:00:00Z",
        "as_of": "2026-05-10",
    }
    original = pa_module.build_suggested_actions_for_vendor
    pa_module.build_suggested_actions_for_vendor = lambda db, *, vendor_id: sample
    try:
        db = db_factory()
        try:
            out = fetch_prioritized_actions(
                {"filter": {"priorities": ["high"]}},
                _scope(vendor_id=vendor_id),
                db,
            )
        finally:
            db.close()
    finally:
        pa_module.build_suggested_actions_for_vendor = original
    ids = sorted(a["id"] for a in out["items"])
    assert ids == ["h1", "h2"]
    assert out["filter_applied"]["priorities"] == ["high"]
    assert out["total_before_filter"] == 3


def test_fetcher_filters_by_type_and_caps_at_5(db_factory) -> None:
    vendor_id = _seed_workspace(db_factory)
    import app.services.reports.blocks.prioritized_actions as pa_module

    sample = {
        "items": [
            {"id": str(i), "priority": "high",
             "type": "reupload" if i % 2 == 0 else "upcoming",
             "title": "T", "body": "B", "href": "/x", "requirement_code": "r",
             "period_key": None}
            for i in range(10)
        ],
        "workspace_id": "ws-x",
        "fetched_at": "2026-05-10T00:00:00Z",
        "as_of": "2026-05-10",
    }
    original = pa_module.build_suggested_actions_for_vendor
    pa_module.build_suggested_actions_for_vendor = lambda db, *, vendor_id: sample
    try:
        db = db_factory()
        try:
            out = fetch_prioritized_actions(
                {"filter": {"types": ["reupload"]}, "max_actions": 99},
                _scope(vendor_id=vendor_id),
                db,
            )
        finally:
            db.close()
    finally:
        pa_module.build_suggested_actions_for_vendor = original
    assert all(a["type"] == "reupload" for a in out["items"])
    # max_actions clamps to MAX_CAP (=5).
    assert out["max_actions"] == 5
    assert len(out["items"]) <= 5


def test_fetcher_default_max_actions_is_three(db_factory) -> None:
    vendor_id = _seed_workspace(db_factory)
    import app.services.reports.blocks.prioritized_actions as pa_module

    sample = {
        "items": [
            {"id": str(i), "priority": "high", "type": "reupload",
             "title": "T", "body": "B", "href": "/x", "requirement_code": "r",
             "period_key": None}
            for i in range(5)
        ],
        "workspace_id": "ws-x",
        "fetched_at": "2026-05-10T00:00:00Z",
        "as_of": "2026-05-10",
    }
    original = pa_module.build_suggested_actions_for_vendor
    pa_module.build_suggested_actions_for_vendor = lambda db, *, vendor_id: sample
    try:
        db = db_factory()
        try:
            out = fetch_prioritized_actions(
                {},  # no max_actions → default 3
                _scope(vendor_id=vendor_id),
                db,
            )
        finally:
            db.close()
    finally:
        pa_module.build_suggested_actions_for_vendor = original
    assert out["max_actions"] == 3
    assert len(out["items"]) == 3


# ─── Catalog ────────────────────────────────────────────────────


def test_prioritized_actions_registered_in_catalog() -> None:
    assert "prioritized_actions" in KNOWN_BLOCK_TYPES
    entry = catalog_by_type()["prioritized_actions"]
    props = entry.input_schema["properties"]
    assert "filter" in props and "max_actions" in props


def test_prioritized_actions_in_planner_tools() -> None:
    tools = planner_tool_list()
    names = [t["name"] for t in tools]
    assert "prioritized_actions" in names
    pa = next(t for t in tools if t["name"] == "prioritized_actions")
    # Description must steer the planner to use this instead of
    # ai_recommendation for vendor reports.
    assert "ai_recommendation" in pa["description"]
    assert "vendor_facing" in pa["description"]


def test_catalog_tail_order_after_p15() -> None:
    """Append-only: compliance_state (P1.2) → attention_list (P1.3) →
    upcoming_deadlines (P1.4) → prioritized_actions (P1.5)."""
    tail = [entry.type for entry in CATALOG[-4:]]
    assert tail == [
        "compliance_state",
        "attention_list",
        "upcoming_deadlines",
        "prioritized_actions",
    ]


# ─── Agreement with portal._compute_suggested_actions ──────────


@pytest.mark.parametrize(
    "onboarding_states,calendar_specs",
    [
        # Pure blocking onboarding.
        (
            [(SlotState.REJECTED, "s-r"), (SlotState.NEEDS_CORRECTION, "s-n")],
            [],
        ),
        # Missing onboarding (medium).
        ([(SlotState.MISSING, None)], []),
        # Upcoming calendar within 14 days.
        ([], [(SlotState.MISSING, "2026-M05", None)]),
        # Mixed.
        (
            [(SlotState.POSSIBLE_MISMATCH, "s-m")],
            [
                (SlotState.MISSING, "2026-M05", None),
                (SlotState.MISSING, "2026-M07", None),
            ],
        ),
        # All resolved → both producers empty.
        ([(SlotState.APPROVED, None)], [(SlotState.APPROVED, "2026-M05", None)]),
    ],
)
def test_compute_actions_agrees_with_portal_compute_actions(
    onboarding_states, calendar_specs
) -> None:
    """Pin the contract — drift here means the report block is no
    longer truthful relative to the dashboard hero."""
    today = date(2026, 5, 10)
    onboarding = [
        _slot(state, submission_id=sid, requirement_code=f"o-{idx}")
        for idx, (state, sid) in enumerate(onboarding_states)
    ]
    calendar = [
        _slot(
            state,
            period_key=pk,
            submission_id=sid,
            requirement_code=f"c-{idx}",
        )
        for idx, (state, pk, sid) in enumerate(calendar_specs)
    ]
    new_items = compute_suggested_actions(onboarding, calendar, today)
    portal_items = portal_compute_suggested_actions(onboarding, calendar, today)

    def _t(p):
        if isinstance(p, dict):
            return (p["id"], p["type"], p["title"], p["body"], p["priority"],
                    p["href"], p["requirement_code"], p["period_key"])
        return (p.id, p.type, p.title, p.body, p.priority, p.href,
                p.requirement_code, p.period_key)

    assert [_t(n) for n in new_items] == [_t(p) for p in portal_items]
