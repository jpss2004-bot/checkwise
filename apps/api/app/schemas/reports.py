"""Pydantic schemas for the Reports API.

Phase 3.1 ships the entity-level shapes only. Block-level schemas (the
content_json contents) are deliberately left open — the block registry
in Phase 3.2+ will validate those shape-by-shape against zod / Pydantic
schemas registered per block type. For now ``content_json`` is typed as
``dict`` and accepted as-is.

See docs/REPORTS_ARCHITECTURE.md §4 and §13.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.constants.reports import (
    ConversationRole,
    ExportFormat,
    ExportStatus,
    ReportAudience,
    ReportStatus,
    ReportVersionOrigin,
)

# ─── Reports ─────────────────────────────────────────────────────


class ReportCreate(BaseModel):
    """Create-a-report payload.

    Audience is required. If audience != internal_only the caller must
    supply at least one of client_id / vendor_id — enforced by both the
    DB CHECK constraint and the service layer for nicer error copy.
    """

    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    audience: ReportAudience
    client_id: str | None = None
    vendor_id: str | None = None
    # The initial empty canvas. The service layer creates a v1 version
    # for any new report so the editor has something to load.
    initial_content_json: dict | None = None


class ReportPatch(BaseModel):
    """Partial update for report metadata.

    Audience changes are allowed but trigger a service-layer
    re-validation of scope (the same CHECK rule).
    """

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    audience: ReportAudience | None = None
    status: ReportStatus | None = None
    client_id: str | None = None
    vendor_id: str | None = None


class ReportSummary(BaseModel):
    """List-view row for a report."""

    id: str
    title: str
    description: str | None
    audience: ReportAudience
    status: ReportStatus
    organization_id: str
    client_id: str | None
    vendor_id: str | None
    current_version_id: str | None
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime


class ReportRead(ReportSummary):
    """Full read response. Includes the latest version inline so the
    editor can mount without a second round-trip.
    """

    current_version: ReportVersionRead | None = None


# ─── Versions ────────────────────────────────────────────────────


class ReportVersionCreate(BaseModel):
    """Manual save payload.

    The caller writes the full content_json. The service layer assigns
    version_number = max(existing) + 1 atomically.
    """

    content_json: dict
    label: str | None = Field(default=None, max_length=120)
    plan_json: dict | None = None
    generated_by: ReportVersionOrigin = ReportVersionOrigin.USER
    parent_version_id: str | None = None
    source_snapshot_id: str | None = None
    llm_metadata: dict | None = None


class ReportVersionSummary(BaseModel):
    """List-view row for a version (no content)."""

    id: str
    report_id: str
    version_number: int
    label: str | None
    parent_version_id: str | None
    generated_by: ReportVersionOrigin
    created_by_user_id: str
    created_at: datetime


class ReportVersionRead(ReportVersionSummary):
    """Full version including content_json + plan_json + llm_metadata."""

    content_json: dict
    plan_json: dict | None
    source_snapshot_id: str | None
    llm_metadata: dict | None


# ─── List wrappers ───────────────────────────────────────────────


class ReportList(BaseModel):
    items: list[ReportSummary]
    total: int


class ReportVersionList(BaseModel):
    items: list[ReportVersionSummary]
    total: int


# ─── Conversations / shares / exports (placeholder schemas) ──────
#
# Tables + models exist for these in Phase 3.1, but the endpoints
# don't. The schemas are scaffolded here so the later sub-phases
# don't have to think about wire shapes — they just fill in the
# endpoint code.


class ConversationTurnRead(BaseModel):
    id: str
    report_id: str
    turn_number: int
    role: ConversationRole
    content_json: dict
    attached_version_id: str | None
    created_at: datetime


class ReportShareRead(BaseModel):
    id: str
    report_id: str
    version_id: str
    audience: ReportAudience
    watermark: str | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    last_accessed_at: datetime | None
    access_count: int


class ReportExportRead(BaseModel):
    id: str
    report_id: str
    version_id: str
    format: ExportFormat
    status: ExportStatus
    bytes: int | None
    requested_at: datetime
    ready_at: datetime | None
    error_text: str | None


# ─── Presets (R1.0) ──────────────────────────────────────────────


class ReportPresetSummary(BaseModel):
    """One preset entry returned by GET /api/v1/reports/_presets.

    The frontend renders these as cards in the role-scoped report
    list page. ``recommended_prompt`` is the string the editor
    pre-fills into the AI prompt textarea on first open.
    """

    id: str
    title: str
    description: str
    audience: ReportAudience
    recommended_prompt: str


class ReportPresetList(BaseModel):
    items: list[ReportPresetSummary]


class CreateFromPresetRequest(BaseModel):
    """Body for POST /api/v1/reports/from-preset.

    ``organization_id`` is required for callers with more than one
    membership; otherwise we use the single org just like ReportCreate.

    ``client_id`` / ``vendor_id`` are forwarded to the underlying
    create_report call. The service layer rejects audiences other than
    ``internal_only`` unless at least one is supplied. For preset
    callers the endpoint auto-resolves ``client_id`` from the
    caller's client_admin membership when not supplied — see
    ``post_from_preset``.
    """

    preset_id: str = Field(min_length=1, max_length=80)
    client_id: str | None = None
    vendor_id: str | None = None
    # When true, the endpoint generates the report's first populated version
    # inline (hybrid: AI with deterministic fallback) before returning, so the
    # frontend can route straight to a finished read-only report. When false
    # (legacy), it returns an empty report for the editor flow.
    auto_generate: bool = False


# ─── Planner (Phase 3.3a) ────────────────────────────────────────


class PlanReportRequest(BaseModel):
    """Body for ``POST /api/v1/reports/{id}/plan``.

    The user supplies a natural-language description of what they
    want. The server assembles tenant-scoped context and asks the
    LLM to plan the structured block sequence.
    """

    prompt: str = Field(min_length=1, max_length=4000)
    period: str | None = Field(default=None, max_length=20)


class PlannedBlockResponse(BaseModel):
    """One block in a plan response."""

    id: str
    type: str
    config: dict


class PlanReportResponse(BaseModel):
    """``POST /api/v1/reports/{id}/plan`` returns this.

    The plan is not yet executed and no new ``report_versions`` row
    is created — that's Phase 3.3b. The endpoint persists a
    ``compliance_snapshots`` row so the plan can be audited; the
    snapshot_id is included here.
    """

    blocks: list[PlannedBlockResponse]
    rationale: str
    audience: ReportAudience
    scope_hint: dict
    model: str
    stop_reason: str
    usage: dict
    snapshot_id: str
    llm_backend: str
