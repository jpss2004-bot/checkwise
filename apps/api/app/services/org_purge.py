"""Irreversible hard-purge of an expired demo tenant (Phase B4).

``purge_org`` deletes a client organization's data + storage blobs in strict
FK order (replicating the proven ``seed_demo_sandbox._wipe`` cascade, plus
Contracts), then deletes the org + Client. Member and provider-owner User rows
are ANONYMIZED + disabled rather than hard-deleted — that strips PII and burns
the login while keeping audit-log attribution resolvable and avoiding the
User-side FK cascade (password history, reset tokens). Best-effort on storage:
a flaky blob delete is counted, never aborts the purge.

Called by the ``run_demo_purge`` cron AFTER the grace window. The caller owns
the transaction (commit / rollback); this stages the deletes via ``flush``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.entities import (
    Client,
    ClientNotification,
    ComplianceSnapshot,
    Contract,
    Document,
    DocumentInspection,
    DocumentStatusHistory,
    Membership,
    Organization,
    ProviderNotification,
    ProviderWorkspace,
    RenewalReminder,
    Report,
    ReportConversation,
    ReportExport,
    ReportShare,
    ReportVersion,
    Submission,
    User,
    Validation,
    ValidationEvent,
    Vendor,
    WiseEvent,
)


class _Storage(Protocol):
    def delete(self, storage_key: str) -> None: ...


@dataclass
class PurgeResult:
    counts: dict[str, int] = field(default_factory=dict)


def purge_org(db: Session, org: Organization, *, storage: _Storage) -> PurgeResult:
    """Hard-delete ``org``'s tenant data + storage; anonymize its users.
    The caller commits. Returns per-entity counts for the audit row."""
    counts: dict[str, int] = {}

    def _del(model, cond) -> None:
        n = db.query(model).filter(cond).delete(synchronize_session=False)
        if n:
            counts[model.__name__] = counts.get(model.__name__, 0) + n

    client_id = org.client_id

    # --- id gathering --------------------------------------------------
    vendor_ids = set(
        db.scalars(select(Vendor.id).where(Vendor.client_id == client_id))
    )
    workspace_ids = set(
        db.scalars(
            select(ProviderWorkspace.id).where(
                ProviderWorkspace.client_id == client_id
            )
        )
    )
    owner_user_ids = {
        uid
        for uid in db.scalars(
            select(ProviderWorkspace.owner_user_id).where(
                ProviderWorkspace.client_id == client_id,
                ProviderWorkspace.owner_user_id.isnot(None),
            )
        )
    }
    sub_ids = set(
        db.scalars(select(Submission.id).where(Submission.client_id == client_id))
    )
    doc_ids = (
        set(db.scalars(select(Document.id).where(Document.submission_id.in_(sub_ids))))
        if sub_ids
        else set()
    )
    report_ids = set(
        db.scalars(select(Report.id).where(Report.organization_id == org.id))
    )
    member_user_ids = set(
        db.scalars(
            select(Membership.user_id).where(Membership.organization_id == org.id)
        )
    )

    # --- storage blobs (best-effort, before the rows that reference them)
    blob_keys: list[str] = []
    if doc_ids:
        blob_keys += [
            k
            for k in db.scalars(
                select(Document.storage_key).where(Document.id.in_(doc_ids))
            )
            if k
        ]
    if report_ids:
        blob_keys += [
            k
            for k in db.scalars(
                select(ReportExport.storage_key).where(
                    ReportExport.report_id.in_(report_ids)
                )
            )
            if k
        ]
    blobs = 0
    for key in blob_keys:
        try:
            storage.delete(key)
            blobs += 1
        except Exception:  # pragma: no cover — best-effort; never abort
            pass
    counts["storage_blobs"] = blobs

    # --- data rows in strict FK order ----------------------------------
    if workspace_ids:
        _del(WiseEvent, WiseEvent.workspace_id.in_(workspace_ids))
        _del(RenewalReminder, RenewalReminder.workspace_id.in_(workspace_ids))
        _del(ProviderNotification, ProviderNotification.workspace_id.in_(workspace_ids))
    _del(ClientNotification, ClientNotification.client_id == client_id)
    if sub_ids:
        _del(ValidationEvent, ValidationEvent.submission_id.in_(sub_ids))
        _del(Validation, Validation.submission_id.in_(sub_ids))
    if doc_ids:
        _del(DocumentInspection, DocumentInspection.document_id.in_(doc_ids))
        _del(DocumentStatusHistory, DocumentStatusHistory.document_id.in_(doc_ids))
    if sub_ids:
        _del(Document, Document.submission_id.in_(sub_ids))
        _del(Submission, Submission.id.in_(sub_ids))
    _del(ComplianceSnapshot, ComplianceSnapshot.client_id == client_id)
    if workspace_ids:
        _del(ProviderWorkspace, ProviderWorkspace.id.in_(workspace_ids))
    # Contracts FK vendor_id + client_id — drop before the vendors they cite.
    _del(Contract, Contract.client_id == client_id)
    if vendor_ids:
        _del(Vendor, Vendor.id.in_(vendor_ids))
    db.flush()

    if report_ids:
        _del(ReportConversation, ReportConversation.report_id.in_(report_ids))
        _del(ReportExport, ReportExport.report_id.in_(report_ids))
        _del(ReportShare, ReportShare.report_id.in_(report_ids))
        _del(ReportVersion, ReportVersion.report_id.in_(report_ids))
        _del(Report, Report.id.in_(report_ids))
    _del(ComplianceSnapshot, ComplianceSnapshot.organization_id == org.id)
    _del(Membership, Membership.organization_id == org.id)
    db.delete(org)
    # Force the org DELETE before the Client DELETE — Organization.client_id is
    # a bare FK with no ORM relationship, so the unit-of-work can't order it.
    db.flush()

    # --- anonymize + disable the tenant's users (no hard-delete) --------
    anonymized = 0
    for uid in member_user_ids | owner_user_ids:
        if uid is None:
            continue
        # Skip users still active in another org (multi-tenant safety).
        others = db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.user_id == uid)
        )
        if others and others > 0:
            continue
        user = db.get(User, uid)
        if user is None or user.deleted_at is not None:
            continue
        user.email = f"purged-{uid}@purged.invalid"
        user.full_name = "(cuenta eliminada)"
        user.password_hash = ""
        user.status = "disabled"
        user.deleted_at = utc_now()
        user.deletion_reason = "demo_purged"
        anonymized += 1
    counts["User_anonymized"] = anonymized

    client = db.get(Client, client_id) if client_id else None
    if client is not None:
        db.delete(client)
        counts["Client"] = 1
    db.flush()

    return PurgeResult(counts=counts)
