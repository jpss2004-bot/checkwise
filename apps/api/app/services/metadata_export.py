from __future__ import annotations

import logging
import re
import shutil
import unicodedata
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.metadata_rules import all_metadata_rules, metadata_rule_by_code
from app.db.session import SessionLocal
from app.models import (
    Client,
    Contract,
    Document,
    DocumentInspection,
    Requirement,
    Submission,
    Vendor,
)
from app.models import Institution as InstitutionModel
from app.services.document_intelligence import DocumentSignals
from app.services.metadata_store import persist_export, sync_client_latest_exports
from app.services.pdf_validation import PdfInspectionResult
from app.services.requirement_service import ResolvedPeriod, ResolvedRequirement
from app.services.storage import StoredFile, get_storage_service
from tools.export_pdf_metadata_table import (
    export_pdf_metadata_table,
    read_metadata_field_rows_from_xlsx,
    write_client_master_xlsx,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MetadataExportResult:
    status: str
    document_type_code: str | None = None
    output_path: str | None = None
    latest_path: str | None = None
    master_path: str | None = None
    reason: str | None = None


_CLASSIFIER_TO_METADATA_CODE = {
    "contrato": "contrato_prestacion_servicios",
    "repse_constancia": "registro_repse",
    # Pre-validation classifier code -> metadata rulebook code. Only the
    # unambiguous 1:1 mappings live here; the upload's requirement_code is
    # resolved first (see resolve_metadata_document_type_code) and stays
    # authoritative. Ambiguous classifier codes (imss_pago / infonavit_pago
    # → several SUA/CFDI/bank rules, factura_cfdi / opinion_cumplimiento_sat
    # → no rulebook entry) are intentionally left out so the requirement
    # slot decides instead of a coin-flip.
    "imss_liquidacion": "resumen_liquidacion_imss",
    "infonavit_liquidacion": "resumen_liquidacion_infonavit",
}


def _text_extraction_from_prevalidation(
    pdf_inspection: PdfInspectionResult,
    document_signals: DocumentSignals,
) -> dict[str, Any]:
    """Repackage the intake inspection into the metadata "intelligence" shape.

    Mirrors ``tools.test_pdf_metadata_dry_run._build_pdf_text_extraction`` so
    the metadata pipeline can reuse the text + signals the live path already
    produced (with full tenant context and OCR fallback) instead of re-opening
    the PDF and re-running the regex classifier. ``ocr_used`` reports False
    because the metadata pipeline itself did not run OCR — any OCR text came
    from intake — which keeps the dry-run safety check (``ocr_used`` requires
    ``enable_ocr``) satisfied.
    """
    return {
        "pdf_text_extraction_used": True,
        "method": "reused_prevalidation_inspection",
        "ocr_used": False,
        "text_char_count": pdf_inspection.text_char_count,
        "has_text": pdf_inspection.has_text,
        "is_probably_scanned": pdf_inspection.is_probably_scanned,
        "text_sample": pdf_inspection.text_sample,
        "signals": {
            "detected_institution": document_signals.detected_institution,
            "detected_document_type": document_signals.detected_document_type,
            "detected_rfcs": document_signals.detected_rfcs,
            "detected_dates": document_signals.detected_dates,
            "period_mentions": document_signals.period_mentions,
            "requirement_match_confidence": document_signals.requirement_match_confidence,
            "mismatch_reason": document_signals.mismatch_reason,
            "anomaly_codes": document_signals.anomaly_codes,
        },
    }


def export_metadata_table_after_upload(
    *,
    stored_file: StoredFile,
    client: Client,
    vendor: Vendor,
    contract: Contract | None,
    institution: InstitutionModel,
    resolved_requirement: ResolvedRequirement,
    resolved_period: ResolvedPeriod,
    document: Document,
    detected_document_type: str | None,
    pdf_inspection: PdfInspectionResult | None = None,
    document_signals: DocumentSignals | None = None,
    field_suggestions: dict[str, dict[str, Any]] | None = None,
) -> MetadataExportResult:
    """Create the automatic XLSX metadata table for a submitted PDF.

    This function is deliberately best-effort: metadata export should be
    visible to LegalShelf but must never block the provider's upload.
    Callers record the returned status as a ValidationEvent.

    When ``pdf_inspection`` and ``document_signals`` are supplied (the live
    intake path always has them in hand), the PDF text + classifier signals
    are reused instead of re-opening the file and re-running
    ``analyze_document_text`` — the single biggest piece of duplicated work
    between pre-validation and metadata export.
    """
    if not settings.AUTO_METADATA_EXPORT_ENABLED:
        return MetadataExportResult(status="skipped", reason="automatic export disabled")

    document_type_code = resolve_metadata_document_type_code(
        requirement_code=resolved_requirement.canonical_code,
        requirement_name=resolved_requirement.canonical_name,
        institution_code=institution.code,
        filename=stored_file.original_filename,
        detected_document_type=detected_document_type,
    )
    if document_type_code is None:
        return MetadataExportResult(
            status="skipped",
            reason="metadata document type could not be resolved",
        )

    context = _metadata_context(
        client=client,
        vendor=vendor,
        contract=contract,
        institution=institution,
        requirement_id=resolved_requirement.requirement.id,
        requirement_code=resolved_requirement.canonical_code,
        requirement_name=resolved_requirement.canonical_name,
        period_id=resolved_period.period.id,
        period_key=resolved_period.canonical_period_key,
        document=document,
        stored_file=stored_file,
        document_type_code=document_type_code,
    )

    precomputed_text_extraction = None
    if pdf_inspection is not None and document_signals is not None:
        precomputed_text_extraction = _text_extraction_from_prevalidation(
            pdf_inspection, document_signals
        )

    return _write_metadata_workbooks(
        stored_file=stored_file,
        client_name=client.name,
        client_id=client.id,
        vendor_name=vendor.name,
        period_key=resolved_period.canonical_period_key,
        document_type_code=document_type_code,
        context=context,
        precomputed_text_extraction=precomputed_text_extraction,
        field_suggestions=field_suggestions,
    )


def _write_metadata_workbooks(
    *,
    stored_file: StoredFile,
    client_name: str,
    client_id: str,
    vendor_name: str,
    period_key: str | None,
    document_type_code: str,
    context: dict[str, Any],
    precomputed_text_extraction: dict[str, Any] | None = None,
    field_suggestions: dict[str, dict[str, Any]] | None = None,
    rebuild_master: bool = True,
) -> MetadataExportResult:
    """Write the per-document + latest workbooks, mirror, rebuild the master.

    The shared core behind both the synchronous intake export and the async
    comprehension re-export. ``field_suggestions`` (field_key -> {value,
    confidence, evidence}) prefills the ``ai_assisted`` cells.
    """
    output_dir = _export_directory(
        client_name=client_name,
        client_id=client_id,
        vendor_name=vendor_name,
        period_key=period_key,
        document_type_code=document_type_code,
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = (
        output_dir / f"{context['submission_id']}_{context['document_id']}_metadata.xlsx"
    )
    latest_path = output_dir / "latest_metadata.xlsx"

    try:
        export_pdf_metadata_table(
            pdf_path=stored_file.path,
            document_type_code=document_type_code,
            context=context,
            output_path=output_path,
            output_format="xlsx",
            include_intelligence=True,
            enable_ocr=False,
            precomputed_text_extraction=precomputed_text_extraction,
            field_suggestions=field_suggestions,
        )
        shutil.copyfile(output_path, latest_path)
        # Mirror both workbooks to durable storage BEFORE the master
        # rebuild — Render's disk is ephemeral, and the rebuild must be
        # able to recover the full slot set after a deploy.
        persist_export(output_path)
        persist_export(latest_path)
        # Bulk backfill rebuilds the master once per client at the end rather
        # than once per document (avoids O(n²) reads of the slot set).
        master_path = (
            rebuild_client_master_metadata_export(
                client_name=client_name, client_id=client_id
            )
            if rebuild_master
            else None
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as telemetry, not a provider error
        return MetadataExportResult(
            status="failed",
            document_type_code=document_type_code,
            reason=f"{exc.__class__.__name__}: {exc}",
        )

    return MetadataExportResult(
        status="completed",
        document_type_code=document_type_code,
        output_path=str(output_path),
        latest_path=str(latest_path),
        master_path=str(master_path) if master_path else None,
    )


def reexport_metadata_with_field_suggestions(
    *,
    document_id: str,
    pdf_path: str,
    field_suggestions: list[dict[str, Any]],
) -> MetadataExportResult:
    """Re-export one document's metadata workbook with AI field suggestions.

    Called from the shadow runner AFTER the deep comprehension tier produced
    ``field_suggestions`` (Phase 3). Reconstructs the export context from the
    persisted submission so it does not depend on request-scoped objects,
    reuses the intake classifier signals from ``DocumentInspection`` (no
    re-parse), and overwrites the intake skeleton workbook with the
    prefilled one. Best-effort: never raises into the caller.
    """
    if not settings.AUTO_METADATA_EXPORT_ENABLED:
        return MetadataExportResult(status="skipped", reason="automatic export disabled")
    if not field_suggestions:
        return MetadataExportResult(status="skipped", reason="no field suggestions")

    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            return MetadataExportResult(status="failed", reason="document not found")
        submission = db.get(Submission, document.submission_id)
        if submission is None:
            return MetadataExportResult(status="failed", reason="submission not found")
        client = db.get(Client, submission.client_id)
        vendor = db.get(Vendor, submission.vendor_id)
        institution = db.get(InstitutionModel, submission.institution_id)
        requirement = db.get(Requirement, submission.requirement_id)
        contract = db.get(Contract, submission.contract_id) if submission.contract_id else None
        if client is None or vendor is None or institution is None or requirement is None:
            return MetadataExportResult(status="failed", reason="submission relations missing")
        inspection = db.scalar(
            select(DocumentInspection).where(DocumentInspection.document_id == document_id)
        )

        document_type_code = resolve_metadata_document_type_code(
            requirement_code=submission.requirement_code,
            requirement_name=requirement.name,
            institution_code=institution.code,
            filename=document.original_filename,
            detected_document_type=(
                inspection.detected_document_type if inspection is not None else None
            ),
        )
        if document_type_code is None:
            return MetadataExportResult(
                status="skipped",
                reason="metadata document type could not be resolved",
            )

        stored_file = StoredFile(
            storage_key=document.storage_key,
            path=Path(pdf_path),
            original_filename=document.original_filename,
            mime_type=document.mime_type,
            size_bytes=document.size_bytes or 0,
            sha256=document.sha256,
            extension=Path(document.original_filename or "").suffix.lstrip("."),
        )
        context = _metadata_context(
            client=client,
            vendor=vendor,
            contract=contract,
            institution=institution,
            requirement_id=submission.requirement_id,
            requirement_code=submission.requirement_code,
            requirement_name=requirement.name,
            period_id=submission.period_id,
            period_key=submission.period_key,
            document=document,
            stored_file=stored_file,
            document_type_code=document_type_code,
        )
        precomputed = (
            _text_extraction_from_inspection(inspection) if inspection is not None else None
        )
        return _write_metadata_workbooks(
            stored_file=stored_file,
            client_name=client.name,
            vendor_name=vendor.name,
            period_key=submission.period_key,
            document_type_code=document_type_code,
            context=context,
            precomputed_text_extraction=precomputed,
            field_suggestions=_suggestions_by_key(field_suggestions),
        )
    finally:
        db.close()


def _suggestions_by_key(
    field_suggestions: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Index a field_suggestions list by field_key (last write wins)."""
    indexed: dict[str, dict[str, Any]] = {}
    for suggestion in field_suggestions or []:
        key = str(suggestion.get("field_key") or "").strip()
        if key:
            indexed[key] = suggestion
    return indexed


def _text_extraction_from_inspection(
    inspection: DocumentInspection,
) -> dict[str, Any]:
    """Build the metadata "intelligence" shape from a persisted inspection.

    The async re-export runs after intake, where the in-memory
    ``PdfInspectionResult`` is long gone and the extracted text was never
    persisted. The classifier *detections* were, so rebuild the signals from
    the ``DocumentInspection`` columns and avoid re-opening the PDF. The
    text sample is unavailable (not stored) — fine, since the n8n text
    hand-off is superseded by the in-house suggestions.
    """
    return {
        "pdf_text_extraction_used": True,
        "method": "reused_inspection_row",
        "ocr_used": False,
        "text_char_count": inspection.text_char_count or 0,
        "has_text": bool(inspection.has_text),
        "is_probably_scanned": bool(inspection.is_probably_scanned),
        "text_sample": "",
        "signals": {
            "detected_institution": inspection.detected_institution,
            "detected_document_type": inspection.detected_document_type,
            "detected_rfcs": list(inspection.detected_rfcs or []),
            "detected_dates": list(inspection.detected_dates or []),
            "period_mentions": list(inspection.period_mentions or []),
            "requirement_match_confidence": inspection.requirement_match_confidence,
            "mismatch_reason": inspection.mismatch_reason,
            "anomaly_codes": [],
        },
    }


# Process-local cache of parsed slot rows, keyed by the workbook's identity
# (path + mtime_ns + size). The master rebuild reads every slot's
# ``latest_metadata.xlsx`` on EACH provider upload; without a cache that is
# O(N) unzip+XML-parse per upload, quadratic over a reporting cycle. A slot's
# rows only change when its workbook is rewritten (new mtime/size), so a
# re-upload busts exactly that one slot's entry and every other slot is served
# from the cache. The master stays byte-identical to a cold full rebuild: the
# same row dicts are concatenated in the same ``sorted(rglob(...))`` order and
# handed to the same ``write_client_master_xlsx`` writer — the cache only
# changes WHERE the rows come from, never WHAT they are or their order.
_SLOT_ROWS_CACHE_MAX_ENTRIES = 2048
_slot_rows_cache: OrderedDict[tuple[str, int, int], list[dict[str, str]]] = (
    OrderedDict()
)


def _read_slot_rows_cached(workbook_path: Path) -> list[dict[str, str]]:
    """Read a slot workbook's metadata rows, memoized on file identity.

    Returns the SAME rows ``read_metadata_field_rows_from_xlsx`` would; the
    cache is a pure read-through keyed by ``(path, mtime_ns, size)`` so a
    rewrite of the slot file (intake/re-export overwrites it) invalidates the
    entry automatically. Process-local and bounded by an LRU, so a long-lived
    worker building masters for many clients can't grow it without bound.
    """
    try:
        stat = workbook_path.stat()
    except OSError:
        # File vanished between rglob and stat — fall back to a direct read so
        # the caller surfaces the same error it would have without the cache.
        return read_metadata_field_rows_from_xlsx(workbook_path)
    cache_key = (str(workbook_path), stat.st_mtime_ns, stat.st_size)
    cached = _slot_rows_cache.get(cache_key)
    if cached is not None:
        _slot_rows_cache.move_to_end(cache_key)  # LRU bump
        # Defensive copy: callers ``extend`` into a shared list and the cached
        # value must stay an immutable snapshot of the parse.
        return [dict(row) for row in cached]
    rows = read_metadata_field_rows_from_xlsx(workbook_path)
    _slot_rows_cache[cache_key] = [dict(row) for row in rows]
    _slot_rows_cache.move_to_end(cache_key)
    while len(_slot_rows_cache) > _SLOT_ROWS_CACHE_MAX_ENTRIES:
        _slot_rows_cache.popitem(last=False)
    return rows


def rebuild_client_master_metadata_export(
    *, client_name: str, client_id: str
) -> Path | None:
    """Rebuild the current shareable master workbook for one client.

    The master intentionally reads only each slot's ``latest_metadata.xlsx``
    so it represents the current state rather than every historical upload.

    Per-slot parses are memoized on file identity (see
    ``_read_slot_rows_cached``), so the hot per-upload rebuild only re-parses
    the single slot that just changed instead of unzip+XML-parsing every slot.
    The aggregated rows — and therefore the written master — are byte-identical
    to a cold full rebuild.
    """
    # Keyed on the immutable, unique ``client.id`` (suffixed onto the name
    # slug) so two clients whose names slugify identically never share a tree
    # and the rebuild can never aggregate one tenant's slots into another's
    # master (cross-tenant metadata leak).
    client_segment = f"{_slug(client_name)}-{client_id}"
    client_root = Path(settings.METADATA_EXPORT_PATH) / client_segment
    # Pull any per-slot workbooks the local disk lost (deploy/restart on
    # ephemeral storage) back from the mirror, otherwise this rebuild
    # would aggregate only the post-deploy uploads and overwrite the
    # previous, complete master with the impoverished result.
    sync_client_latest_exports(client_segment)
    if not client_root.exists():
        return None

    rows: list[dict[str, str]] = []
    for workbook_path in sorted(client_root.rglob("latest_metadata.xlsx")):
        rows.extend(_read_slot_rows_cached(workbook_path))
    if not rows:
        return None

    master_path = client_root / "client_master_metadata.xlsx"
    write_client_master_xlsx(rows, master_path, client_name=client_name)
    persist_export(master_path)
    return master_path


def _bulk_by_id(db: Session, model: Any, ids: set[str]) -> dict[str, Any]:
    """Fetch ``model`` rows for ``ids`` in one IN query, keyed by ``id``.

    Used by the backfill to prefetch per-submission relations in bulk instead
    of issuing a ``db.get`` per scanned row. Empty ``ids`` short-circuits with
    no query.
    """
    if not ids:
        return {}
    return {obj.id: obj for obj in db.scalars(select(model).where(model.id.in_(ids)))}


@dataclass
class MetadataBackfillResult:
    """Counters for one backfill run (CW-14)."""

    scanned: int = 0
    generated: int = 0
    skipped_existing: int = 0
    skipped_unresolved: int = 0
    failed: int = 0
    clients_rebuilt: int = 0


def backfill_metadata_exports(
    db: Session,
    *,
    client_id: str | None = None,
    vendor_id: str | None = None,
    period_key: str | None = None,
    statuses: tuple[str, ...] | None = None,
    force: bool = False,
    dry_run: bool = True,
    limit: int | None = None,
    log: Callable[[str], None] | None = None,
) -> MetadataBackfillResult:
    """Generate metadata workbooks for already-stored documents missing one (CW-14).

    Metadata XLSX tables are produced at intake. Documents uploaded before
    automatic export existed — or whose export failed — have no
    ``latest_metadata.xlsx`` and never reach the client master. This rebuilds
    them from the persisted ``DocumentInspection`` signals (no OCR / LLM /
    re-parse), pulling each PDF from storage on demand.

    Idempotent: a slot that already has a ``latest_metadata.xlsx`` is skipped
    unless ``force``. Within a run the newest submission owns each slot (rows
    are processed newest-first), so a backfilled master reflects current state.
    The per-client master is rebuilt once at the end, not per document.
    ``dry_run`` (default) reports what would be written without touching
    storage. Scope with ``client_id`` / ``vendor_id`` / ``period_key`` /
    ``statuses``; cap with ``limit``.
    """
    result = MetadataBackfillResult()
    emit = log or (lambda _message: None)

    if not settings.AUTO_METADATA_EXPORT_ENABLED and not force:
        emit(
            "AUTO_METADATA_EXPORT_ENABLED is off — pass force=True to backfill anyway."
        )
        return result

    stmt = (
        select(Submission, Document)
        .join(Document, Document.submission_id == Submission.id)
        .order_by(Submission.created_at.desc())
    )
    if client_id:
        stmt = stmt.where(Submission.client_id == client_id)
    if vendor_id:
        stmt = stmt.where(Submission.vendor_id == vendor_id)
    if period_key:
        stmt = stmt.where(Submission.period_key == period_key)
    if statuses:
        stmt = stmt.where(Submission.status.in_(statuses))
    if limit:
        stmt = stmt.limit(limit)

    storage = get_storage_service()
    processed_slots: set[Path] = set()
    clients_touched: dict[str, str] = {}

    # Prefetch every per-submission relation in bulk (one IN query per entity
    # type) instead of 5-6 ``db.get``/scalar lookups per scanned row. ``db.get``
    # already de-dups via the identity map, but the first touch of each distinct
    # client/vendor/institution/requirement/contract was still a round-trip and
    # the ``DocumentInspection`` scalar (keyed by a never-repeating document_id)
    # was a true per-row query. Output is unchanged: the loop reads the same
    # objects, just from in-memory maps.
    scanned_rows = db.execute(stmt).all()
    submissions = [submission for submission, _document in scanned_rows]
    client_ids = {s.client_id for s in submissions if s.client_id}
    vendor_ids = {s.vendor_id for s in submissions if s.vendor_id}
    institution_ids = {s.institution_id for s in submissions if s.institution_id}
    requirement_ids = {s.requirement_id for s in submissions if s.requirement_id}
    contract_ids = {s.contract_id for s in submissions if s.contract_id}
    document_ids = {document.id for _submission, document in scanned_rows if document.id}

    clients_by_id = _bulk_by_id(db, Client, client_ids)
    vendors_by_id = _bulk_by_id(db, Vendor, vendor_ids)
    institutions_by_id = _bulk_by_id(db, InstitutionModel, institution_ids)
    requirements_by_id = _bulk_by_id(db, Requirement, requirement_ids)
    contracts_by_id = _bulk_by_id(db, Contract, contract_ids)
    inspections_by_document_id: dict[str, DocumentInspection] = {}
    if document_ids:
        inspections_by_document_id = {
            inspection.document_id: inspection
            for inspection in db.scalars(
                select(DocumentInspection).where(
                    DocumentInspection.document_id.in_(document_ids)
                )
            )
        }

    for submission, document in scanned_rows:
        result.scanned += 1
        client = clients_by_id.get(submission.client_id)
        vendor = vendors_by_id.get(submission.vendor_id)
        institution = institutions_by_id.get(submission.institution_id)
        requirement = requirements_by_id.get(submission.requirement_id)
        if (
            client is None
            or vendor is None
            or institution is None
            or requirement is None
        ):
            result.failed += 1
            continue
        contract = (
            contracts_by_id.get(submission.contract_id)
            if submission.contract_id
            else None
        )
        inspection = inspections_by_document_id.get(document.id)

        document_type_code = resolve_metadata_document_type_code(
            requirement_code=submission.requirement_code,
            requirement_name=requirement.name,
            institution_code=institution.code,
            filename=document.original_filename,
            detected_document_type=(
                inspection.detected_document_type if inspection is not None else None
            ),
        )
        if document_type_code is None:
            result.skipped_unresolved += 1
            continue

        slot_dir = _export_directory(
            client_name=client.name,
            client_id=client.id,
            vendor_name=vendor.name,
            period_key=submission.period_key,
            document_type_code=document_type_code,
        )
        if slot_dir in processed_slots:
            # A newer submission already owns this slot's current workbook.
            result.skipped_existing += 1
            continue
        processed_slots.add(slot_dir)
        if (slot_dir / "latest_metadata.xlsx").exists() and not force:
            result.skipped_existing += 1
            continue

        label = (
            f"{client.name} / {vendor.name} / "
            f"{submission.period_key or 'alta-inicial'} / {document_type_code}"
        )
        if dry_run:
            emit(f"would generate: {label}")
            result.generated += 1
            clients_touched[client.id] = client.name
            continue

        try:
            pdf_path = storage.open_for_read(document.storage_key)
        except Exception as exc:  # noqa: BLE001 - best-effort per document
            emit(f"FAILED fetch {document.id}: {exc.__class__.__name__}: {exc}")
            result.failed += 1
            continue

        stored_file = StoredFile(
            storage_key=document.storage_key,
            path=Path(pdf_path),
            original_filename=document.original_filename,
            mime_type=document.mime_type,
            size_bytes=document.size_bytes or 0,
            sha256=document.sha256,
            extension=Path(document.original_filename or "").suffix.lstrip("."),
        )
        context = _metadata_context(
            client=client,
            vendor=vendor,
            contract=contract,
            institution=institution,
            requirement_id=submission.requirement_id,
            requirement_code=submission.requirement_code,
            requirement_name=requirement.name,
            period_id=submission.period_id,
            period_key=submission.period_key,
            document=document,
            stored_file=stored_file,
            document_type_code=document_type_code,
        )
        precomputed = (
            _text_extraction_from_inspection(inspection)
            if inspection is not None
            else None
        )
        write_result = _write_metadata_workbooks(
            stored_file=stored_file,
            client_name=client.name,
            client_id=client.id,
            vendor_name=vendor.name,
            period_key=submission.period_key,
            document_type_code=document_type_code,
            context=context,
            precomputed_text_extraction=precomputed,
            rebuild_master=False,
        )
        if write_result.status == "completed":
            result.generated += 1
            clients_touched[client.id] = client.name
            emit(f"generated: {label}")
        else:
            result.failed += 1
            emit(f"FAILED write {document.id}: {write_result.reason}")

    if not dry_run:
        for client_id, client_name in sorted(
            clients_touched.items(), key=lambda item: item[1]
        ):
            rebuild_client_master_metadata_export(
                client_name=client_name, client_id=client_id
            )
            result.clients_rebuilt += 1

    return result


def resolve_metadata_document_type_code(
    *,
    requirement_code: str | None,
    requirement_name: str,
    institution_code: str,
    filename: str,
    detected_document_type: str | None = None,
) -> str | None:
    """Map the upload requirement to a metadata-rule document type."""
    if requirement_code:
        maybe_metadata_code = requirement_code.strip().lower()
        try:
            metadata_rule_by_code(maybe_metadata_code)
            return maybe_metadata_code
        except KeyError:
            pass

    if detected_document_type in _CLASSIFIER_TO_METADATA_CODE:
        return _CLASSIFIER_TO_METADATA_CODE[detected_document_type]

    normalized_name = _normalize(requirement_name)
    normalized_filename = _normalize(Path(filename).stem.replace("_", " "))
    institution = institution_code.strip().lower()

    candidates = [
        rule
        for rule in all_metadata_rules(include_annexes=True)
        if rule.institution == institution or rule.applies_to_all_institutions
    ]
    scored: list[tuple[int, str]] = []
    for rule in candidates:
        rule_name = _normalize(rule.name)
        rule_code = _normalize(rule.code.replace("_", " "))
        score = 0
        if normalized_name == rule_name:
            score += 100
        if normalized_name and (normalized_name in rule_name or rule_name in normalized_name):
            score += 70
        if normalized_name and _token_overlap(normalized_name, rule_name) >= 0.6:
            score += 45
        if rule_code and rule_code in normalized_filename:
            score += 35
        if rule_name and _token_overlap(normalized_filename, rule_name) >= 0.6:
            score += 25
        if score:
            scored.append((score, rule.code))

    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][1]


def _metadata_context(
    *,
    client: Client,
    vendor: Vendor,
    contract: Contract | None,
    institution: InstitutionModel,
    requirement_id: str,
    requirement_code: str | None,
    requirement_name: str,
    period_id: str,
    period_key: str | None,
    document: Document,
    stored_file: StoredFile,
    document_type_code: str,
) -> dict[str, Any]:
    # Takes primitives (not the resolver objects) so the async re-export
    # path can rebuild the same context straight from a persisted Submission.
    return {
        "submission_id": document.submission_id,
        "document_id": document.id,
        "client_id": client.id,
        "client_legal_name": client.name,
        "vendor_id": vendor.id,
        "vendor_legal_name": vendor.name,
        "vendor_rfc": vendor.rfc,
        "provider_nomenclature": vendor.name,
        "contract_id": contract.id if contract else None,
        "contract_reference": contract.external_reference if contract else None,
        "requirement_id": requirement_id,
        "requirement_code": requirement_code,
        "requirement_name": requirement_name,
        "period_id": period_id,
        "period_key": period_key,
        "document_type_code": document_type_code,
        "expected_document_type_code": document_type_code,
        "expected_institution": institution.code,
        "upload_form_month": _period_month_label(period_key),
        "reported_period": period_key,
        "original_filename": stored_file.original_filename,
        "sha256": stored_file.sha256,
        "mime_type": stored_file.mime_type,
        "size_bytes": stored_file.size_bytes,
        "storage_key": stored_file.storage_key,
        "proposed_pdf_file_name": stored_file.original_filename,
    }


def _client_dir_segment(client: Client) -> str:
    """Canonical per-client path/key segment for the export tree.

    Client.name has NO DB uniqueness (only ``rfc`` is unique), so keying the
    export tree on the slug alone let two clients whose names slugify the same
    share ``metadata_exports/<slug>/...`` — the master rebuild then aggregated
    both tenants into one workbook the download served cross-tenant. Suffixing
    the immutable, unique ``client.id`` isolates them. This is the ONE place
    the segment is defined; ``_export_directory``,
    ``rebuild_client_master_metadata_export``, ``client_master_file_path`` and
    the S3 mirror all reuse it so the local path and the durable key never
    drift.
    """
    return f"{_slug(client.name)}-{client.id}"


def _export_directory(
    *,
    client_name: str,
    client_id: str,
    vendor_name: str,
    period_key: str | None,
    document_type_code: str,
) -> Path:
    return (
        Path(settings.METADATA_EXPORT_PATH)
        / f"{_slug(client_name)}-{client_id}"
        / _slug(vendor_name)
        / _slug(period_key or "alta-inicial")
        / _slug(document_type_code)
    )


def _period_month_label(period_key: str | None) -> str | None:
    if not period_key or "-M" not in period_key:
        return None
    try:
        month = int(period_key.split("-M", 1)[1])
    except ValueError:
        return None
    months = (
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre",
    )
    if 1 <= month <= 12:
        return months[month - 1]
    return None


def _token_overlap(left: str, right: str) -> float:
    left_tokens = {token for token in left.split() if len(token) > 2}
    right_tokens = {token for token in right.split() if len(token) > 2}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens), 1)


def _normalize(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9]+", " ", ascii_text).lower()).strip()


def _slug(value: str) -> str:
    normalized = _normalize(value)
    return re.sub(r"[^a-z0-9-]+", "-", normalized.replace(" ", "-")).strip("-") or "unknown"
