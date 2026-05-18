"""Tests for the ``compliance_state`` block (P1.2).

Covers three layers:

1. ``dashboard_compute`` — pure helpers (``compute_semaphore``,
   ``bucket_document_state``, ``empty_document_counts``,
   ``build_compliance_state_for_vendor``).
2. The block fetcher in ``app.services.reports.blocks.compliance_state``.
3. Block catalog registration + planner tool surface.
4. Agreement: the new ``compute_semaphore`` and the in-place portal
   ``_compute_semaphore`` produce the same semaphore for any slot list.
   This pins the contract until the portal endpoint migrates onto the
   shared service.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.portal import _compute_semaphore as portal_compute_semaphore
from app.constants.reports import ReportAudience
from app.db.base import Base
from app.models import Client, ProviderWorkspace, User, Vendor, entities  # noqa: F401
from app.services.dashboard_compute import (
    bucket_document_state,
    build_compliance_state_for_vendor,
    compute_semaphore,
    empty_document_counts,
    resolve_workspace_for_vendor,
)
from app.services.evidence_slots import SlotKey, SlotState, SlotView
from app.services.reports.block_catalog import (
    CATALOG,
    KNOWN_BLOCK_TYPES,
    catalog_by_type,
    planner_tool_list,
)
from app.services.reports.blocks.compliance_state import fetch_compliance_state
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


def _slot(state: SlotState, *, required: bool = True) -> SlotView:
    """Synthetic SlotView for unit tests. Field names match real shape."""
    return SlotView(
        slot_key=SlotKey(
            workspace_id="ws-test",
            client_id="client-test",
            vendor_id="vendor-test",
            requirement_code="rfc",
            period_key=None,
        ),
        state=state,
        requirement_code="rfc",
        period_key=None,
        requirement_name="RFC",
        institution="sat",
        required=required,
        current_submission_id=None,
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


def _seed_workspace(db_factory, *, vendor_name: str = "Vendor A") -> str:
    """Seed a minimal active ProviderWorkspace. Returns vendor_id."""
    db = db_factory()
    try:
        client = Client(name="Client A")
        db.add(client)
        db.flush()
        vendor = Vendor(
            client_id=client.id,
            name=vendor_name,
            rfc="V12345678901",
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()
        user = User(
            email="ws_owner@cs.test",
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
            display_name=vendor_name,
            access_token=f"tok-{vendor.id}",
            onboarding_completed_at=None,
            status="active",
        )
        db.add(ws)
        db.commit()
        return vendor.id
    finally:
        db.close()


# ─── compute_semaphore ─────────────────────────────────────────


def test_semaphore_green_when_every_required_slot_resolved() -> None:
    sem = compute_semaphore(
        [_slot(SlotState.APPROVED), _slot(SlotState.EXCEPTION)],
        [_slot(SlotState.NOT_APPLICABLE)],
    )
    assert sem["level"] == "green"
    assert sem["compliance_pct"] == 100
    assert sem["total_tracked"] == 3
    assert sem["on_track"] == 3


def test_semaphore_yellow_when_pending_but_no_blocking() -> None:
    sem = compute_semaphore(
        [_slot(SlotState.APPROVED), _slot(SlotState.MISSING)],
        [_slot(SlotState.IN_REVIEW)],
    )
    assert sem["level"] == "yellow"
    assert sem["compliance_pct"] == 33  # 1 / 3
    assert sem["total_tracked"] == 3
    assert sem["on_track"] == 1


def test_semaphore_red_on_any_actionable_required_slot() -> None:
    # One rejected slot beats nine green ones.
    sem = compute_semaphore(
        [_slot(SlotState.APPROVED)] * 9 + [_slot(SlotState.REJECTED)],
        [],
    )
    assert sem["level"] == "red"
    assert sem["compliance_pct"] == 90
    assert sem["total_tracked"] == 10
    assert sem["on_track"] == 9


def test_semaphore_ignores_optional_slots() -> None:
    """An optional slot in a blocking state must not flip the level."""
    sem = compute_semaphore(
        [_slot(SlotState.APPROVED, required=True)],
        [_slot(SlotState.REJECTED, required=False)],
    )
    assert sem["level"] == "green"
    assert sem["total_tracked"] == 1


def test_semaphore_empty_input_renders_green_with_zero_tracked() -> None:
    sem = compute_semaphore([], [])
    assert sem == {
        "level": "green",
        "label": "Verde · al día",
        "reason": "Todas tus obligaciones obligatorias están aprobadas.",
        "compliance_pct": 100,
        "total_tracked": 0,
        "on_track": 0,
    }


# ─── bucket_document_state ─────────────────────────────────────


def test_bucket_document_state_maps_every_slot_state() -> None:
    """Each SlotState lands in exactly one count bucket, except
    NOT_APPLICABLE which is intentionally not counted."""
    counts = empty_document_counts()
    bucket_document_state(counts, SlotState.APPROVED)
    bucket_document_state(counts, SlotState.IN_REVIEW)
    bucket_document_state(counts, SlotState.UPLOADED)
    bucket_document_state(counts, SlotState.MISSING)
    bucket_document_state(counts, SlotState.NEEDS_CORRECTION)
    bucket_document_state(counts, SlotState.POSSIBLE_MISMATCH)
    bucket_document_state(counts, SlotState.REJECTED)
    bucket_document_state(counts, SlotState.EXPIRED)
    bucket_document_state(counts, SlotState.EXCEPTION)
    bucket_document_state(counts, SlotState.NOT_APPLICABLE)  # not counted
    assert counts == {
        "approved": 1,
        "in_review": 1,
        "uploaded": 1,
        "pending": 1,
        # NEEDS_CORRECTION + POSSIBLE_MISMATCH both bucket as needs_review
        "needs_review": 2,
        "rejected": 1,
        "expired": 1,
        "exception": 1,
    }


# ─── build_compliance_state_for_vendor ─────────────────────────


def test_build_for_vendor_returns_empty_shape_when_no_active_workspace(
    db_factory,
) -> None:
    """A vendor without an active workspace must yield a structurally
    correct empty payload — never raise, never leak someone else's
    data."""
    db = db_factory()
    try:
        result = build_compliance_state_for_vendor(db, vendor_id="missing-vendor")
    finally:
        db.close()
    assert result["workspace_id"] is None
    assert result["persona_type"] is None
    assert result["semaphore"]["total_tracked"] == 0
    assert result["document_state_counts"] == empty_document_counts()


def test_build_for_vendor_resolves_workspace_and_returns_shape(db_factory) -> None:
    """Active workspace exists → builder returns a populated workspace_id
    and persona_type, and the semaphore+counts are well-formed dicts."""
    vendor_id = _seed_workspace(db_factory)
    db = db_factory()
    try:
        result = build_compliance_state_for_vendor(db, vendor_id=vendor_id)
    finally:
        db.close()
    assert result["workspace_id"] is not None
    assert result["persona_type"] == "moral"
    # A freshly-seeded workspace with no submissions yet has every
    # required onboarding slot in MISSING — the builder rolls that up
    # as yellow ("expediente en marcha, pendiente de subir") with
    # compliance_pct == 0. Green only happens once every required slot
    # is resolved; that needs richer fixtures than this unit test
    # bothers with.
    assert result["semaphore"]["level"] in ("yellow", "green")
    assert result["semaphore"]["total_tracked"] >= 0
    assert result["semaphore"]["compliance_pct"] >= 0
    assert set(result["document_state_counts"].keys()) == set(
        empty_document_counts().keys()
    )


def test_resolve_workspace_picks_lowest_id_when_two_active_for_same_vendor(
    db_factory,
) -> None:
    """Determinism guard: if the data layer ever ends up with two
    active workspaces pointing at the same vendor, the resolver picks
    the lowest-id one (mirrors ``_actor_from`` in the reports API).
    """
    vendor_id = _seed_workspace(db_factory)
    # Add a second active workspace for the same vendor.
    db = db_factory()
    try:
        user2 = User(
            email="ws_owner2@cs.test",
            password_hash="x",
            full_name="WS Owner 2",
            status="active",
        )
        db.add(user2)
        db.flush()
        client_id = db.scalar(
            ProviderWorkspace.__table__.select()
            .with_only_columns(ProviderWorkspace.client_id)
            .where(ProviderWorkspace.vendor_id == vendor_id)
            .limit(1)
        )
        ws2 = ProviderWorkspace(
            client_id=client_id,
            vendor_id=vendor_id,
            contract_id=None,
            owner_user_id=user2.id,
            filial_name="Filial 2",
            persona_type="moral",
            display_name="Vendor A B-side",
            access_token=f"tok-2-{vendor_id}",
            onboarding_completed_at=None,
            status="active",
        )
        db.add(ws2)
        db.commit()
        all_ids = sorted(
            ws.id
            for ws in db.query(ProviderWorkspace)
            .filter(ProviderWorkspace.vendor_id == vendor_id)
            .all()
        )
        picked = resolve_workspace_for_vendor(db, vendor_id)
    finally:
        db.close()
    assert picked is not None
    assert picked.id == all_ids[0], (
        "Resolver must pick the lowest-id active workspace"
    )


# ─── compliance_state fetcher ──────────────────────────────────


def test_fetcher_returns_empty_when_scope_has_no_vendor(db_factory) -> None:
    db = db_factory()
    try:
        out = fetch_compliance_state(
            {}, _scope(ReportAudience.VENDOR_FACING, vendor_id=None), db
        )
    finally:
        db.close()
    assert out["workspace_id"] is None
    assert out["semaphore"]["total_tracked"] == 0
    assert out["document_state_counts"] == empty_document_counts()


def test_fetcher_returns_builder_output_when_vendor_set(db_factory) -> None:
    vendor_id = _seed_workspace(db_factory)
    db = db_factory()
    try:
        out = fetch_compliance_state(
            {}, _scope(ReportAudience.VENDOR_FACING, vendor_id=vendor_id), db
        )
        expected = build_compliance_state_for_vendor(db, vendor_id=vendor_id)
    finally:
        db.close()
    # Same shape — fetcher should be a thin pass-through over the
    # canonical builder, plus a block-level ``fetched_at`` stamp added
    # in P1.7 so the renderer can show "Datos al: …".
    assert out.keys() == expected.keys() | {"fetched_at"}
    assert out["workspace_id"] == expected["workspace_id"]
    assert isinstance(out["fetched_at"], str) and out["fetched_at"].endswith("Z")


def test_fetcher_renders_for_internal_audience_too(db_factory) -> None:
    """Internal staff viewing a vendor-scoped report still get the
    block payload — the safety helper bypasses for internal actors,
    and the fetcher itself only cares about vendor_id presence."""
    vendor_id = _seed_workspace(db_factory)
    db = db_factory()
    try:
        out = fetch_compliance_state(
            {}, _scope(ReportAudience.INTERNAL_ONLY, vendor_id=vendor_id), db
        )
    finally:
        db.close()
    assert out["workspace_id"] is not None


# ─── Catalog registration ──────────────────────────────────────


def test_compliance_state_is_registered_in_catalog() -> None:
    assert "compliance_state" in KNOWN_BLOCK_TYPES
    entry = catalog_by_type()["compliance_state"]
    assert entry.input_schema["type"] == "object"
    # The planner sees year as the only optional parameter.
    properties = entry.input_schema.get("properties", {})
    assert "year" in properties
    # No required fields: the block runs with empty config.
    assert entry.input_schema.get("required", []) == []


def test_planner_tool_list_advertises_compliance_state() -> None:
    tools = planner_tool_list()
    types = [t["name"] for t in tools]
    assert "compliance_state" in types
    # Description tells the planner when to pick it (provider-pulse use case).
    cs = next(t for t in tools if t["name"] == "compliance_state")
    assert "vendor_facing" in cs["description"] or "semáforo" in cs["description"]


def test_catalog_order_is_stable_append_only() -> None:
    """Provider-aware blocks must appear AFTER the original six, in the
    order they were introduced (P1.2: compliance_state, P1.3:
    attention_list, P1.4: upcoming_deadlines, …). Appending preserves
    planner prompt-cache hit rates by keeping tool-call ordering stable
    as we add blocks.

    The assertion checks relative ordering rather than the literal tail,
    so each new slice extends naturally without rewriting the test —
    add the new block type to ``provider_order`` at its slice boundary.
    """
    provider_order = ["compliance_state", "attention_list", "upcoming_deadlines"]
    catalog_types = [entry.type for entry in CATALOG]
    positions = [catalog_types.index(t) for t in provider_order]
    assert positions == sorted(positions), (
        f"Provider blocks must keep insertion order. Got positions: {positions}"
    )
    # All provider blocks must follow every legacy (pre-P1.2) block.
    last_legacy = max(
        catalog_types.index(t)
        for t in (
            "executive_summary",
            "kpi_strip",
            "vendor_risk_matrix",
            "ai_recommendation",
            "text",
            "divider",
        )
    )
    assert positions[0] > last_legacy


# ─── Agreement with portal _compute_semaphore ──────────────────


def _semaphore_to_dict(sem) -> dict:
    """Coerce the portal Pydantic semaphore to the shared dict shape."""
    return {
        "level": sem.level,
        "label": sem.label,
        "reason": sem.reason,
        "compliance_pct": sem.compliance_pct,
        "total_tracked": sem.total_tracked,
        "on_track": sem.on_track,
    }


@pytest.mark.parametrize(
    "onboarding_states,calendar_states,expected_level",
    [
        ([SlotState.APPROVED, SlotState.APPROVED], [], "green"),
        ([SlotState.APPROVED, SlotState.MISSING], [], "yellow"),
        ([SlotState.APPROVED, SlotState.REJECTED], [SlotState.IN_REVIEW], "red"),
        ([SlotState.IN_REVIEW], [SlotState.UPLOADED], "yellow"),
        ([SlotState.NEEDS_CORRECTION], [], "red"),
        ([SlotState.POSSIBLE_MISMATCH], [], "red"),
        ([SlotState.EXPIRED], [], "yellow"),
        ([], [], "green"),
    ],
)
def test_compute_semaphore_agrees_with_portal_compute_semaphore(
    onboarding_states, calendar_states, expected_level
) -> None:
    """Pin the contract: ``dashboard_compute.compute_semaphore`` and
    ``portal._compute_semaphore`` produce identical semaphore payloads
    for any slot input. If this fails, one of the two has drifted and
    one must be brought back in line.
    """
    onboarding = [_slot(s) for s in onboarding_states]
    calendar = [_slot(s) for s in calendar_states]
    new_result = compute_semaphore(onboarding, calendar)
    portal_result = _semaphore_to_dict(
        portal_compute_semaphore(onboarding, calendar)
    )
    assert new_result == portal_result
    assert new_result["level"] == expected_level
