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
from app.services.reports.blocks.data_fetchers import fetch_ai_recommendation
from app.services.reports.blocks.prioritized_actions import (
    fetch_prioritized_actions,
)
from app.services.reports.context import ReportScope
from app.services.reports.insights import compute_vendor_insight

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


def test_vendor_insight_findings_include_action_links(db_factory) -> None:
    vendor_id = _seed_workspace(db_factory)
    db = db_factory()
    try:
        insight = compute_vendor_insight(
            db,
            _scope(vendor_id=vendor_id),
            today=date(2026, 1, 5),
        )
    finally:
        db.close()
    assert insight is not None
    linked = [
        finding
        for finding in insight["findings"]
        if finding.get("links")
    ]
    assert linked
    assert all(
        link["href"].startswith("/portal/upload")
        for finding in linked
        for link in finding["links"]
    )


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


def test_ai_recommendation_carries_prioritized_action_links(db_factory) -> None:
    vendor_id = _seed_workspace(db_factory)
    db = db_factory()
    try:
        out = fetch_ai_recommendation(
            {"priority_count": 2, "audience_tone": "client"},
            _scope(vendor_id=vendor_id),
            db,
        )
    finally:
        db.close()
    assert out["action_links"]
    assert len(out["action_links"]) <= 2
    assert all(link["href"].startswith("/portal/upload") for link in out["action_links"])


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
    """Append-only catalog. P1.2→P1.5 (compliance_state, attention_list,
    upcoming_deadlines, prioritized_actions) landed as a contiguous run in
    order. The M4 reports redesign (2026-06) then appended ``compliance_radar``
    at the very tail without reordering anything before it — so we assert the
    P1 run stayed intact and the radar is the newest entry, rather than pinning
    the absolute last-4 (which the radar legitimately shifted)."""
    order = [entry.type for entry in CATALOG]
    p1_run = [
        "compliance_state",
        "attention_list",
        "upcoming_deadlines",
        "prioritized_actions",
    ]
    start = order.index("compliance_state")
    assert order[start : start + 4] == p1_run
    # Append-only tail: M4 added compliance_radar, then the 2026-06
    # cliente-report pass added compliance_overview and
    # compliance_by_institution — each at the end, without reordering
    # anything before it.
    assert order[-3:] == [
        "compliance_radar",
        "compliance_overview",
        "compliance_by_institution",
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


# ─── Phase 6D — renewal actions slotting ────────────────────────


def _renewal_action(priority: str, code: str = "ONB-CORP-M-002") -> dict:
    """Hand-crafted renewal action dict mirroring
    ``compute_renewal_actions``' output shape. Tests for the slotting
    behavior in ``compute_suggested_actions`` don't need the real
    helper — they just need a dict that walks the same priority gate.
    """
    return {
        "id": f"act-{code}-renewal-{priority}",
        "type": "renewal",
        "title": f"Renueva {code} — fixture",
        "body": "fixture body",
        "priority": priority,
        "href": f"/portal/upload?requirement_code={code}&from=renewal",
        "requirement_code": code,
        "period_key": None,
    }


def test_compute_actions_back_compat_when_renewal_actions_omitted() -> None:
    """Callers that don't pass renewal_actions see identical output to
    pre-6D behavior. This is the back-compat pin.
    """
    today = date(2026, 5, 10)
    onboarding = [_slot(SlotState.MISSING, requirement_code="rfc")]
    without = compute_suggested_actions(onboarding, [], today)
    explicit_none = compute_suggested_actions(
        onboarding, [], today, renewal_actions=None
    )
    explicit_empty = compute_suggested_actions(
        onboarding, [], today, renewal_actions=[]
    )
    assert without == explicit_none == explicit_empty


def test_compute_actions_includes_high_priority_renewals_alongside_blocking() -> None:
    """An overdue renewal lands in the same priority tier as expired
    calendar items (slotted between blocking states and the missing-
    onboarding pass).
    """
    today = date(2026, 5, 10)
    onboarding = [_slot(SlotState.REJECTED, requirement_code="rfc", submission_id="s1")]
    renewal = [_renewal_action("high", code="ONB-REPSE-001")]
    actions = compute_suggested_actions(
        onboarding, [], today, renewal_actions=renewal
    )
    types = [a["type"] for a in actions]
    priorities = [a["priority"] for a in actions]
    # Both items high-priority; the renewal lands after the blocking
    # reupload because the pipeline appends in pass order.
    assert types == ["reupload", "renewal"]
    assert priorities == ["high", "high"]


def test_compute_actions_includes_medium_renewals_after_upcoming() -> None:
    """Due-soon renewals share the medium tier with missing-onboarding
    and the 5-day upcoming window. Both surface in the same list
    capped at 5.
    """
    today = date(2026, 5, 10)
    renewal = [
        _renewal_action("medium", code="ONB-CORP-M-002"),
        _renewal_action("medium", code="ONB-PATR-001"),
    ]
    actions = compute_suggested_actions([], [], today, renewal_actions=renewal)
    assert [a["type"] for a in actions] == ["renewal", "renewal"]
    assert {a["priority"] for a in actions} == {"medium"}
    assert {a["requirement_code"] for a in actions} == {
        "ONB-CORP-M-002",
        "ONB-PATR-001",
    }


def test_compute_actions_high_priority_renewals_dont_displace_blocking() -> None:
    """When the cap is reached, blocking-state items come first because
    they're added first in the pipeline. A high-priority renewal
    appears only if room remains.
    """
    today = date(2026, 5, 10)
    onboarding = [
        _slot(SlotState.REJECTED, requirement_code=f"rej-{i}", submission_id=f"s{i}")
        for i in range(5)
    ]
    renewal = [_renewal_action("high")]
    actions = compute_suggested_actions(
        onboarding, [], today, renewal_actions=renewal
    )
    assert len(actions) == 5
    assert all(a["type"] == "reupload" for a in actions)


def test_compute_actions_separates_renewal_priorities_correctly() -> None:
    """Mixed-priority renewal_actions: high goes in the 2.6 pass, medium
    goes in the 3.5 pass. The pipeline order interleaves them with
    existing actions.
    """
    today = date(2026, 5, 10)
    renewal = [
        _renewal_action("high", code="ONB-REPSE-001"),
        _renewal_action("medium", code="ONB-CORP-M-002"),
    ]
    actions = compute_suggested_actions([], [], today, renewal_actions=renewal)
    # Empty slots — only the two renewals fire. High before medium
    # because pass 2.6 runs before pass 3.5.
    assert [a["requirement_code"] for a in actions] == [
        "ONB-REPSE-001",
        "ONB-CORP-M-002",
    ]
    assert [a["priority"] for a in actions] == ["high", "medium"]


def test_portal_pydantic_compute_actions_accepts_renewals() -> None:
    """The Pydantic mirror in app.api.v1.portal must accept and emit
    the same renewal payloads with type='renewal' on the
    DashboardSuggestedAction model.
    """
    today = date(2026, 5, 10)
    renewal = [
        _renewal_action("high", code="ONB-REPSE-001"),
        _renewal_action("medium", code="ONB-CORP-M-002"),
    ]
    out = portal_compute_suggested_actions(
        [], [], today, renewal_actions=renewal
    )
    assert [r.type for r in out] == ["renewal", "renewal"]
    assert [r.priority for r in out] == ["high", "medium"]
    assert [r.requirement_code for r in out] == ["ONB-REPSE-001", "ONB-CORP-M-002"]
    # The Literal["renewal", ...] on DashboardSuggestedAction
    # accepts the type — no Pydantic ValidationError.


# ─── Phase 6D — compute_renewal_actions (DB-backed) ────────────


def _seed_approved_csf(db, workspace, *, updated_at):
    """Insert an approved CSF (ONB-CORP-M-002) for the workspace.

    Mirrors the shape ``test_renewal_dispatch.py`` uses to control
    the renewal anchor — we set ``updated_at`` directly because the
    workflow service does so via transition; here we want a
    deterministic anchor without involving the workflow.
    """
    from sqlalchemy import select

    from app.constants.statuses import DocumentStatus
    from app.models import (
        Institution,
        Period,
        Requirement,
        RequirementVersion,
        Submission,
    )

    inst = db.scalar(select(Institution).where(Institution.code == "sat"))
    if inst is None:
        inst = Institution(code="sat", name="SAT")
        db.add(inst)
        db.flush()
    req = Requirement(
        code="req-ONB-CORP-M-002",
        name="CSF",
        institution_id=inst.id,
        load_type="onboarding",
        frequency="alta_inicial",
        risk_level="medium",
        current_version=1,
    )
    db.add(req)
    db.flush()
    version = RequirementVersion(requirement_id=req.id, version=1)
    db.add(version)
    db.flush()
    period = db.scalar(select(Period).where(Period.code == "onb-test-pa"))
    if period is None:
        period = Period(code="onb-test-pa", period_type="onboarding", period_key="onb-test-pa")
        db.add(period)
        db.flush()
    sub = Submission(
        client_id=workspace.client_id,
        vendor_id=workspace.vendor_id,
        institution_id=inst.id,
        requirement_id=req.id,
        requirement_version_id=version.id,
        period_id=period.id,
        load_type="onboarding",
        status=DocumentStatus.APROBADO.value,
        requirement_code="ONB-CORP-M-002",
        period_key=None,
        created_at=updated_at,
        updated_at=updated_at,
    )
    db.add(sub)
    db.commit()


def test_compute_renewal_actions_emits_due_soon_for_csf_approaching(db_factory) -> None:
    """CSF approved 60 days ago → due in 30 → medium priority renewal."""
    from datetime import datetime, timedelta

    from sqlalchemy import select

    from app.models import ProviderWorkspace
    from app.services.dashboard_compute import compute_renewal_actions

    vendor_id = _seed_workspace(db_factory)  # noqa: F841 — ws by side effect
    today = date(2026, 6, 1)
    anchor_dt = datetime(2026, 6, 1) - timedelta(days=60)

    db = db_factory()
    try:
        ws = db.scalar(select(ProviderWorkspace))
        assert ws is not None
        _seed_approved_csf(db, ws, updated_at=anchor_dt)
    finally:
        db.close()

    db = db_factory()
    try:
        ws = db.scalar(select(ProviderWorkspace))
        assert ws is not None
        out = compute_renewal_actions(db, ws, today)
    finally:
        db.close()

    assert len(out) == 1
    item = out[0]
    assert item["type"] == "renewal"
    assert item["priority"] == "medium"
    assert item["requirement_code"] == "ONB-CORP-M-002"
    assert item["period_key"] is None
    assert "?requirement_code=ONB-CORP-M-002" in item["href"]
    assert "from=renewal" in item["href"]


def test_compute_renewal_actions_empty_without_approved_submission(db_factory) -> None:
    """No approved CSF → renewal cycle hasn't started → no actions."""
    from sqlalchemy import select

    from app.models import ProviderWorkspace
    from app.services.dashboard_compute import compute_renewal_actions

    _seed_workspace(db_factory)
    today = date(2026, 6, 1)

    db = db_factory()
    try:
        ws = db.scalar(select(ProviderWorkspace))
        assert ws is not None
        out = compute_renewal_actions(db, ws, today)
    finally:
        db.close()
    assert out == []


def test_compute_renewal_actions_high_priority_when_overdue(db_factory) -> None:
    """CSF approved 100 days ago → due 10 days ago → high priority."""
    from datetime import datetime, timedelta

    from sqlalchemy import select

    from app.models import ProviderWorkspace
    from app.services.dashboard_compute import compute_renewal_actions

    _seed_workspace(db_factory)
    today = date(2026, 6, 1)
    anchor_dt = datetime(2026, 6, 1) - timedelta(days=100)

    db = db_factory()
    try:
        ws = db.scalar(select(ProviderWorkspace))
        assert ws is not None
        _seed_approved_csf(db, ws, updated_at=anchor_dt)
    finally:
        db.close()

    db = db_factory()
    try:
        ws = db.scalar(select(ProviderWorkspace))
        assert ws is not None
        out = compute_renewal_actions(db, ws, today)
    finally:
        db.close()

    assert len(out) == 1
    assert out[0]["priority"] == "high"
    assert "vencido" in out[0]["title"].lower()
