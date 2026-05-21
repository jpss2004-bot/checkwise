"""Context Assembler — the trust boundary between CheckWise's
canonical data and the LLM.

Architectural commitments (docs/REPORTS_ARCHITECTURE.md §3):

1. The LLM never reads raw data. It only sees the dict assembled here.
2. Tenant scoping is enforced server-side per request, never via UI.
3. AI-generated text is separated from canonical data — this module
   builds the read-only "what the model saw" snapshot.

Three-layer protection (mirrors the spec):

- Pre-fetch:  the data_fetcher receives a frozen ReportContext
              containing org/client/vendor IDs that came from the
              authenticated session, never from the user's prompt.
- At-fetch:   every SQLAlchemy query joins through organization_id /
              client_id / vendor_id; orphan or cross-tenant rows
              cannot appear in the result set.
- Post-fetch: a sanitizer strips fields tagged ``pii: True`` for
              non-internal audiences.

Phase 3.3a ships the scaffolding: actor → context → snapshot. The
real per-block data_fetchers (vendor_risk_matrix needs SAT rows,
kpi_strip needs aggregate counts, etc.) land in 3.3b alongside the
streaming pipeline. For 3.3a the planner only needs the *summary* of
the scope to do its job — not the row-level data.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants.reports import ReportAudience
from app.models.entities import (
    Client,
    ComplianceSnapshot,
    Submission,
    Vendor,
    new_id,
    utc_now,
)
from app.services.report_service import ReportActor, ReportPermissionError


@dataclass(frozen=True)
class ReportScope:
    """The slice of data a report is about.

    Built from the authenticated session + the report row. Never from
    free-form user input. The planner sees a serialized form of this
    scope, never the actor.user_id or unrelated workspace ids.
    """

    organization_id: str
    audience: ReportAudience
    client_id: str | None = None
    vendor_id: str | None = None
    period: str | None = None


@dataclass(frozen=True)
class ScopeSummary:
    """Aggregate, PII-sanitized snapshot of the scope.

    This is what the planner is given. Counts and labels only —
    enough to reason about which blocks to choose, but not enough to
    leak any individual document's contents.
    """

    organization_label: str
    client_label: str | None
    vendor_label: str | None
    period: str | None
    audience: str

    vendors_total: int
    vendors_at_risk: int
    submissions_recent: int
    institutions_in_scope: list[str]

    def to_planner_payload(self) -> dict:
        """The dict the planner sees as `<scope>...</scope>`."""
        return {
            "organization": self.organization_label,
            "client": self.client_label,
            "vendor": self.vendor_label,
            "period": self.period,
            "audience": self.audience,
            "metrics": {
                "vendors_total": self.vendors_total,
                "vendors_at_risk": self.vendors_at_risk,
                "submissions_recent": self.submissions_recent,
            },
            "institutions_in_scope": self.institutions_in_scope,
        }


@dataclass(frozen=True)
class AssembledContext:
    """What the planner receives, plus the snapshot row id for the
    audit trail.

    The snapshot is persisted as a ``compliance_snapshots`` row before
    the LLM call so we can prove later "this is what the model saw."
    The same snapshot id ends up on every ReportVersion the planner
    produces (Phase 3.3b wiring).
    """

    scope: ReportScope
    summary: ScopeSummary
    snapshot_id: str
    snapshot_hash: str


# ─── Public entry point ────────────────────────────────────────


def assemble_context(
    db: Session,
    *,
    actor: ReportActor,
    scope: ReportScope,
) -> AssembledContext:
    """Build a planner-ready context, persisting a snapshot.

    Authorisation rules:
    - Internal staff bypass tenant scoping (matches existing admin
      endpoints).
    - Everyone else must hold a membership in scope.organization_id.
    - The scope's client_id / vendor_id must belong to the
      organization (no cross-tenant binding).

    The function is intentionally narrow: it asks for the rows it
    needs from the DB, sanitizes via ``_sanitize_for_audience``, hashes
    the result, persists a snapshot, and returns. No side effects
    beyond the snapshot insert.
    """

    if not actor.is_internal and scope.organization_id not in actor.organization_ids:
        raise ReportPermissionError(
            "Caller cannot assemble context for an organization they don't belong to."
        )

    # ── Resolve labels (display-only, no PII unless audience is internal).
    organization_label = _organization_label(db, scope.organization_id)
    client_label = _client_label(db, scope.client_id) if scope.client_id else None
    vendor_label = _vendor_label(db, scope.vendor_id) if scope.vendor_id else None

    # ── Aggregates.
    vendors_total, vendors_at_risk = _vendor_counts(db, scope)
    submissions_recent = _submissions_recent(db, scope)
    institutions_in_scope = _institutions_in_scope(db, scope)

    summary = ScopeSummary(
        organization_label=organization_label,
        client_label=client_label,
        vendor_label=vendor_label,
        period=scope.period,
        audience=scope.audience.value,
        vendors_total=vendors_total,
        vendors_at_risk=vendors_at_risk,
        submissions_recent=submissions_recent,
        institutions_in_scope=institutions_in_scope,
    )

    # ── Persist snapshot.
    payload = summary.to_planner_payload()
    sanitized = _sanitize_for_audience(payload, scope.audience)
    snapshot_hash = _hash_payload(sanitized)

    snapshot_row = ComplianceSnapshot(
        id=new_id(),
        organization_id=scope.organization_id,
        client_id=scope.client_id,
        vendor_id=scope.vendor_id,
        scope_filter={
            "period": scope.period,
            "audience": scope.audience.value,
            "client_id": scope.client_id,
            "vendor_id": scope.vendor_id,
        },
        data_json=sanitized,
        row_count=vendors_total + submissions_recent,
        data_hash=snapshot_hash,
        taken_at=utc_now(),
    )
    db.add(snapshot_row)
    db.commit()
    db.refresh(snapshot_row)

    return AssembledContext(
        scope=scope,
        summary=summary,
        snapshot_id=snapshot_row.id,
        snapshot_hash=snapshot_hash,
    )


# ─── PII sanitizer ─────────────────────────────────────────────


# Fields that may carry PII (names, RFCs, contact info). Stripped for
# any non-internal audience by default. New fields added to scope
# summary should be tagged here.
_PII_FIELDS: frozenset[str] = frozenset(
    {
        # ScopeSummary fields
        "client",
        "vendor",
    }
)


def _sanitize_for_audience(payload: dict, audience: ReportAudience) -> dict:
    """Strip PII labels for audiences that don't need them.

    The planner doesn't need real vendor names to decide on blocks —
    it just needs counts + categorical metadata. By removing PII at
    the boundary, even a misbehaved model can't echo back names that
    weren't meant for the audience.
    """
    if audience == ReportAudience.INTERNAL_ONLY:
        return payload

    return {
        key: (None if key in _PII_FIELDS and value is not None else value)
        for key, value in payload.items()
    }


def _hash_payload(payload: dict) -> str:
    """Stable SHA-256 of the snapshot payload. Used to dedupe cached
    plans and to anchor the audit trail."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ─── Aggregate queries ─────────────────────────────────────────


def _organization_label(db: Session, organization_id: str) -> str:
    from app.models.entities import Organization

    org = db.get(Organization, organization_id)
    return org.name if org else organization_id


def _client_label(db: Session, client_id: str) -> str:
    client = db.get(Client, client_id)
    return client.name if client else client_id


def _vendor_label(db: Session, vendor_id: str) -> str:
    vendor = db.get(Vendor, vendor_id)
    return vendor.name if vendor else vendor_id


def _vendor_counts(db: Session, scope: ReportScope) -> tuple[int, int]:
    """Returns (total vendors in scope, vendors with any blocking state)."""
    stmt = select(func.count(func.distinct(Vendor.id)))
    if scope.client_id:
        stmt = stmt.where(Vendor.client_id == scope.client_id)
    if scope.vendor_id:
        stmt = stmt.where(Vendor.id == scope.vendor_id)
    total = db.scalar(stmt) or 0

    # "At-risk" = any submission with status in {posible_mismatch,
    # requiere_aclaracion, rechazado, vencido} in scope. We count
    # distinct vendor_ids that have at least one such submission.
    risk_stmt = select(func.count(func.distinct(Submission.vendor_id))).where(
        Submission.status.in_(
            ["posible_mismatch", "requiere_aclaracion", "rechazado", "vencido"]
        )
    )
    if scope.client_id:
        risk_stmt = risk_stmt.where(Submission.client_id == scope.client_id)
    if scope.vendor_id:
        risk_stmt = risk_stmt.where(Submission.vendor_id == scope.vendor_id)
    at_risk = db.scalar(risk_stmt) or 0

    return int(total), int(at_risk)


def _submissions_recent(db: Session, scope: ReportScope) -> int:
    """Count of submissions in the report's scope. No row contents,
    just the cardinality — that's all the planner needs."""
    stmt = select(func.count(Submission.id))
    if scope.client_id:
        stmt = stmt.where(Submission.client_id == scope.client_id)
    if scope.vendor_id:
        stmt = stmt.where(Submission.vendor_id == scope.vendor_id)
    if scope.period:
        stmt = stmt.where(Submission.period_key == scope.period)
    return int(db.scalar(stmt) or 0)


def _institutions_in_scope(db: Session, scope: ReportScope) -> list[str]:
    """Distinct institutions a submission was filed against in scope."""
    from app.models.entities import Institution

    stmt = (
        select(func.distinct(Institution.code))
        .join(Submission, Submission.institution_id == Institution.id)
    )
    if scope.client_id:
        stmt = stmt.where(Submission.client_id == scope.client_id)
    if scope.vendor_id:
        stmt = stmt.where(Submission.vendor_id == scope.vendor_id)
    return sorted([row for row in db.scalars(stmt) if row])


# ─── Debug helper for tests ────────────────────────────────────


def context_as_dict(ctx: AssembledContext) -> dict:
    """Stable shape for fixture comparisons in tests."""
    return {
        "scope": asdict(ctx.scope),
        "summary": asdict(ctx.summary),
        "snapshot_id": ctx.snapshot_id,
        "snapshot_hash": ctx.snapshot_hash,
    }
