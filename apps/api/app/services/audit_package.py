"""Audit-ready cross-vendor ZIP composition.

Junta 2026-05-23 — when an auditor arrives at a client's office, the
client_admin needs to deliver a single ZIP scoped to exactly what the
inspector asked for: specific institutions, a date range, and
typically only approved evidence. This module is the composer.

Differences from :mod:`app.services.expediente_zip` (which exists for
a single provider workspace):

* **Scope is the entire client portfolio** — every
  ``ProviderWorkspace`` under ``client_id`` contributes documents.
* **Layout is** ``<vendor>/<institucion>/<periodo>/<archivo>``.
  Vendor-first matches the most common audit framing
  ("muéstrame todo lo de proveedor X").
* **Period is a range** (``period_from`` / ``period_to``) instead of
  a single ``period_key``.
* **Status defaults to approved-only** — including in-review or
  rejected docs by default would invite uncomfortable auditor
  questions; the API surfaces a toggle so the user can opt in.
* **An INDICE.pdf cover** lives at the archive root listing every
  file. It is composed in :mod:`app.services.audit_package_manifest`
  and inserted by the streaming routine here.

Caps mirror ``expediente_zip`` (200 files / 500 MB). Cross-vendor
packages can blow past these fast, so the endpoint returns a
clear 413 guiding the user to narrow the filters.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.statuses import DocumentStatus
from app.core.period_range import (
    filter_period_from_to_range,
    period_overlaps_range,
)
from app.models import (
    Client,
    Document,
    Institution,
    ProviderWorkspace,
    Requirement,
    Submission,
    Vendor,
)
from app.services.storage import get_storage_service

MAX_FILES = 200
MAX_TOTAL_BYTES = 500 * 1024 * 1024

# Default status set when the caller does not specify one. Approved
# evidence is what an auditor wants to see; everything else is
# internal-work-in-progress and only ships when the client_admin
# explicitly opts in.
DEFAULT_STATUSES: frozenset[str] = frozenset({DocumentStatus.APROBADO.value})

# Onboarding contract requirement codes. Sourced from
# ``app.core.compliance_catalog._ONBOARDING_MORAL`` (section
# "Contrato"). Submissions whose ``requirement_code`` lands in this
# set are rewritten at entry-time to live under a dedicated
# ``contratos`` folder (and a synthetic ``contrato`` institution
# code) so an auditor unzipping the package finds the contract
# package as its own first-class group rather than buried inside
# ``interno_cliente/sin-periodo/``. The folder shape and the synthetic
# code thread through the ZIP layout, the INDICE.pdf manifest and the
# tree picker's grouping automatically.
CONTRACT_REQUIREMENT_CODES: frozenset[str] = frozenset(
    {"ONB-CONT-001", "ONB-CONT-002", "ONB-CONT-003"}
)
CONTRACT_INSTITUTION_CODE: str = "contrato"
CONTRACT_INSTITUTION_NAME: str = "Contrato"
CONTRACT_FOLDER: str = "contratos"

# Onboarding corporate-documentation requirement codes. Sourced from
# ``app.core.compliance_catalog._ONBOARDING_MORAL`` / ``_ONBOARDING_FISICA``
# (section "Documentación Corporativa"), restricted to the codes whose
# issuing source is ``interno_cliente`` — the CSF codes (ONB-CORP-M-002 /
# ONB-CORP-F-002) are real SAT documents and stay under ``sat``. Mirrors the
# contract carve-out above: these submissions are lifted into a dedicated
# ``corporativo`` folder and synthetic institution code so the acta
# constitutiva and official ID surface as their own first-class group rather
# than being buried inside ``interno_cliente/sin-periodo/``. With both
# carve-outs in place, the onboarding ``interno_cliente`` bucket holds only a
# genuine miscellaneous remainder.
CORPORATE_REQUIREMENT_CODES: frozenset[str] = frozenset(
    {"ONB-CORP-M-001", "ONB-CORP-F-001"}
)
CORPORATE_INSTITUTION_CODE: str = "corporativo"
CORPORATE_INSTITUTION_NAME: str = "Documentación Corporativa"
CORPORATE_FOLDER: str = "corporativo"

# Statuses that have no bytes on disk. Excluded from every audit
# package regardless of explicit selection so the ZIP never hits a
# 404 mid-stream.
_NO_BYTES_STATES: frozenset[str] = frozenset({
    DocumentStatus.PENDIENTE.value,
    DocumentStatus.VENCIDO.value,
    DocumentStatus.NO_APLICA.value,
})


@dataclass(frozen=True)
class AuditPackageFilters:
    """Filter set for an audit package.

    All fields are optional. ``period_from`` / ``period_to`` are
    canonical period keys (``YYYY-Mxx`` / ``YYYY-Bx`` / ``YYYY-Qx`` /
    ``YYYY-A``) used as string range bounds — comparison is
    lexicographic, which works because the canonical format sorts
    chronologically within a year and the year prefix sorts
    correctly across years.

    ``institutions`` and ``requirement_codes`` are institution
    codes (e.g. ``sat``) and full requirement codes
    (e.g. ``sat:declaracion_iva:mensual``) respectively. ``statuses``
    defaults to ``{aprobado}`` when omitted.
    """

    period_from: str | None = None
    period_to: str | None = None
    institutions: tuple[str, ...] = ()
    requirement_codes: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    vendor_ids: tuple[str, ...] = ()
    # Item 2 — when non-empty, the resolved entry set is further
    # narrowed to exactly these submission ids. The other filters
    # still apply first (they shape the candidate set the tree picker
    # showed to the user); ``submission_ids`` is the explicit
    # whitelist the user ticked. An empty tuple keeps the legacy
    # filter-only behaviour intact, so the GET endpoint stays
    # backward-compatible.
    submission_ids: tuple[str, ...] = ()

    @property
    def effective_statuses(self) -> tuple[str, ...]:
        """Return the statuses to actually filter by.

        Empty input falls back to ``DEFAULT_STATUSES`` so the
        composition path always has a non-empty set; the rest of the
        service can assume the iterable has at least one value.
        """
        if self.statuses:
            return self.statuses
        return tuple(sorted(DEFAULT_STATUSES))

    def to_audit_dict(self) -> dict[str, list[str] | str | int]:
        """JSON-safe shape for the audit log metadata."""
        out: dict[str, list[str] | str | int] = {}
        if self.period_from:
            out["period_from"] = self.period_from
        if self.period_to:
            out["period_to"] = self.period_to
        if self.institutions:
            out["institutions"] = list(self.institutions)
        if self.requirement_codes:
            out["requirement_codes"] = list(self.requirement_codes)
        out["statuses"] = list(self.effective_statuses)
        if self.vendor_ids:
            out["vendor_ids"] = list(self.vendor_ids)
        if self.submission_ids:
            # Record the count + a stable hash rather than dumping
            # every id into the audit log; the actual whitelist can be
            # reconstructed from the per-submission rows the same
            # audit event references.
            out["submission_ids_count"] = len(self.submission_ids)
        return out


# ``field`` reserved for future filter additions; silence unused
# warning until then.
_ = field


class AuditPackageTooLargeError(Exception):
    """Raised when the composed package exceeds either cap.

    Carries the observed counts plus the offending dimension so the
    endpoint can render a plain-Spanish 413 explaining which limit
    was hit and how to narrow the filters.
    """

    def __init__(self, *, file_count: int, total_bytes: int, exceeds: str):
        self.file_count = file_count
        self.total_bytes = total_bytes
        self.exceeds = exceeds  # "files" | "bytes"
        super().__init__(
            f"Audit package exceeds {exceeds} cap "
            f"(files={file_count}, bytes={total_bytes})."
        )


@dataclass(frozen=True)
class AuditPackageEntry:
    """One ZIP entry resolved from a Submission/Document pair.

    Exposed (not private) because the manifest generator consumes the
    same shape to build the INDICE table — keeping the resolution in
    one place avoids drift between the file the auditor opens and the
    index that describes it.
    """

    arcname: str
    storage_key: str
    size_bytes: int
    vendor_id: str
    vendor_name: str
    vendor_rfc: str | None
    institution_code: str
    institution_name: str
    period_key: str
    requirement_code: str | None
    requirement_name: str
    status: str
    filename: str
    submitted_at_iso: str | None
    # Item 2 — the underlying Submission id so the tree picker can
    # build a (vendor → institution → period → submission) hierarchy
    # and round-trip the user's selection back into
    # ``AuditPackageFilters.submission_ids``.
    submission_id: str = ""


class AuditPackageSummary(NamedTuple):
    """Cheap pre-flight read used by the /preview endpoint.

    Provides enough breakdowns for the UI to render a live counter
    ("27 documentos de 3 proveedores · cubre SAT · IMSS") without
    re-running the SQL each filter tweak.
    """

    file_count: int
    total_bytes: int
    vendor_counts: dict[str, int]  # vendor_id → file count
    institution_counts: dict[str, int]  # institution code → file count
    requirement_counts: dict[str, int]  # requirement code → file count


__all__ = (
    "AuditPackageFilters",
    "AuditPackageEntry",
    "AuditPackageSummary",
    "AuditPackageTooLargeError",
    "MAX_FILES",
    "MAX_TOTAL_BYTES",
    "DEFAULT_STATUSES",
    "build_entries",
    "summarize_audit_package",
    "stream_audit_package",
)


def summarize_audit_package(
    db: Session,
    client: Client,
    filters: AuditPackageFilters,
) -> AuditPackageSummary:
    """Cheap pre-flight count + breakdowns.

    Walks the same selection logic ``build_entries`` uses but returns
    only aggregates so the /preview endpoint can answer in O(rows)
    without doing any file IO.
    """
    entries = build_entries(db, client, filters)
    vendor_counts: dict[str, int] = {}
    institution_counts: dict[str, int] = {}
    requirement_counts: dict[str, int] = {}
    total_bytes = 0
    for e in entries:
        vendor_counts[e.vendor_id] = vendor_counts.get(e.vendor_id, 0) + 1
        institution_counts[e.institution_code] = (
            institution_counts.get(e.institution_code, 0) + 1
        )
        if e.requirement_code:
            requirement_counts[e.requirement_code] = (
                requirement_counts.get(e.requirement_code, 0) + 1
            )
        total_bytes += e.size_bytes
    return AuditPackageSummary(
        file_count=len(entries),
        total_bytes=total_bytes,
        vendor_counts=vendor_counts,
        institution_counts=institution_counts,
        requirement_counts=requirement_counts,
    )


def stream_audit_package(
    db: Session,
    client: Client,
    filters: AuditPackageFilters,
    manifest_pdf: bytes | None = None,
) -> Iterator[bytes]:
    """Yield ZIP bytes for the audit package.

    Raises ``AuditPackageTooLargeError`` BEFORE yielding any bytes if
    the resolved file count or total byte size exceeds either cap.

    ``manifest_pdf`` is written verbatim as ``INDICE.pdf`` at the
    archive root when provided. Callers should generate it via
    :func:`app.services.audit_package_manifest.render_audit_manifest`
    and pass it through so the cover stays in sync with the entry
    set the streaming pass actually wrote.

    Identical-name collisions inside the same vendor/inst/period
    folder are disambiguated with a numeric suffix so the archive
    never silently drops a row.
    """
    entries = build_entries(db, client, filters)
    file_count = len(entries)
    total_bytes = sum(e.size_bytes for e in entries)
    if file_count > MAX_FILES:
        raise AuditPackageTooLargeError(
            file_count=file_count,
            total_bytes=total_bytes,
            exceeds="files",
        )
    if total_bytes > MAX_TOTAL_BYTES:
        raise AuditPackageTooLargeError(
            file_count=file_count,
            total_bytes=total_bytes,
            exceeds="bytes",
        )

    storage = get_storage_service()
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as zf:
        if manifest_pdf is not None:
            zf.writestr("INDICE.pdf", manifest_pdf)
        for entry in entries:
            try:
                src_path = storage.open_for_read(entry.storage_key)
            except Exception:
                # Storage helper raised; skip the row rather than blow
                # up the whole archive. The manifest still lists the
                # row so the auditor sees the gap; the audit log
                # already records intent.
                continue
            if not src_path.exists():
                continue
            with src_path.open("rb") as src:
                zf.writestr(entry.arcname, src.read())
    buffer.seek(0)
    yield buffer.read()


def build_entries(
    db: Session,
    client: Client,
    filters: AuditPackageFilters,
) -> list[AuditPackageEntry]:
    """Resolve every Submission/Document under ``client`` that matches
    the filter set, return them as ``AuditPackageEntry`` rows.

    Layout: ``<vendor_slug>/<institution_code>/<period_key>/<safe_filename>``.
    Vendor folder uses ``name + " (" + rfc + ")"`` so two providers
    sharing a similar name stay distinguishable. ``period_key``
    falls back to ``sin-periodo`` for legacy rows without a canonical
    key.

    Selection logic:

    * Walk every ``ProviderWorkspace`` under the client (the
      tenancy unit for documents).
    * Optionally narrow to ``filters.vendor_ids``.
    * Submission scoped to the client + vendor pair, status in the
      effective set, institution + requirement code matching when
      those are set.
    * Period range applied semantically via
      :func:`app.core.period_range.period_overlaps_range` — a
      bimestral (``YYYY-Bx``), cuatrimestral (``YYYY-Qx``) or
      annual (``YYYY-A``) row is INCLUDED whenever its calendar
      window overlaps the user's monthly range. Lexicographic
      ``period_key`` comparison is intentionally NOT used because
      mixed formats sort wrong (``2026-Q1`` lexically > ``2026-M12``
      even though Q1 starts in January).
    * ``_NO_BYTES_STATES`` excluded unconditionally — including them
      would yield a 404 mid-stream.
    """
    effective_statuses = filters.effective_statuses
    # Drop any no-byte statuses the caller asked for; they yield no
    # archive contents anyway. Keep the rest verbatim so the audit
    # row reflects what the user requested.
    streamable_statuses = tuple(
        s for s in effective_statuses if s not in _NO_BYTES_STATES
    )
    if not streamable_statuses:
        return []

    workspace_stmt = (
        select(ProviderWorkspace)
        .where(ProviderWorkspace.client_id == client.id)
        .order_by(ProviderWorkspace.created_at.asc())
    )
    if filters.vendor_ids:
        workspace_stmt = workspace_stmt.where(
            ProviderWorkspace.vendor_id.in_(filters.vendor_ids)
        )
    workspaces = list(db.scalars(workspace_stmt))
    if not workspaces:
        return []

    # Resolve institution codes → ids once. Unknown codes resolve to
    # empty (skip) rather than 400 so a future catalog code can ship
    # without breaking the download flow.
    institution_id_for: dict[str, str] = {}
    institution_name_for: dict[str, str] = {}
    institution_code_for_id: dict[str, str] = {}
    institution_filter_ids: list[str] = []
    institution_rows = list(db.scalars(select(Institution)))
    for inst in institution_rows:
        institution_id_for[inst.code] = inst.id
        institution_name_for[inst.code] = inst.name
        institution_code_for_id[inst.id] = inst.code
    if filters.institutions:
        institution_filter_ids = [
            institution_id_for[code]
            for code in filters.institutions
            if code in institution_id_for
        ]
        if not institution_filter_ids:
            return []

    # Resolve vendor metadata once for arcname composition.
    vendor_ids_seen = [w.vendor_id for w in workspaces]
    vendor_rows = list(
        db.scalars(select(Vendor).where(Vendor.id.in_(vendor_ids_seen)))
    )
    vendor_for: dict[str, Vendor] = {v.id: v for v in vendor_rows}

    # Resolve requirement_code → name once for manifest rendering.
    requirement_rows = list(db.scalars(select(Requirement)))
    requirement_name_for: dict[str, str] = {r.code: r.name for r in requirement_rows}

    entries: list[AuditPackageEntry] = []
    seen_arc: dict[str, int] = {}
    for ws in workspaces:
        vendor = vendor_for.get(ws.vendor_id)
        if vendor is None:
            continue
        sub_stmt = (
            select(Submission)
            .where(
                Submission.client_id == ws.client_id,
                Submission.vendor_id == ws.vendor_id,
                Submission.status.in_(streamable_statuses),
                Submission.status.notin_(_NO_BYTES_STATES),
            )
            .order_by(Submission.created_at.asc())
        )
        if institution_filter_ids:
            sub_stmt = sub_stmt.where(
                Submission.institution_id.in_(institution_filter_ids)
            )
        if filters.requirement_codes:
            sub_stmt = sub_stmt.where(
                Submission.requirement_code.in_(filters.requirement_codes)
            )
        # Period range is applied in Python (not SQL) so the test
        # is a date-range overlap rather than a string comparison
        # on ``period_key``. See ``app.core.period_range`` for the
        # full rationale; the short version is that lexicographic
        # ``period_key`` ordering breaks when bimestral / cuatrimestral
        # / annual keys mix with monthly keys.
        range_start, range_end = filter_period_from_to_range(
            filters.period_from, filters.period_to
        )
        submissions = list(db.scalars(sub_stmt))
        # Batch-load the first document per submission in ONE query (was an
        # N+1: a SELECT per submission). A submission normally carries
        # exactly one document; when several exist we keep the lowest id,
        # matching the previous ``LIMIT 1`` (which had no explicit order)
        # deterministically.
        docs_by_submission: dict[str, Document] = {}
        if submissions:
            for d in db.scalars(
                select(Document)
                .where(Document.submission_id.in_([s.id for s in submissions]))
                .order_by(Document.submission_id, Document.id)
            ):
                docs_by_submission.setdefault(d.submission_id, d)
        # Materialise the whitelist once per workspace pass; a missing
        # filter is a no-op (every submission passes the membership
        # check below). Using ``frozenset`` keeps the lookup O(1) even
        # when the user ticks hundreds of rows.
        submission_id_whitelist: frozenset[str] | None = (
            frozenset(filters.submission_ids) if filters.submission_ids else None
        )
        for sub in submissions:
            if (
                submission_id_whitelist is not None
                and sub.id not in submission_id_whitelist
            ):
                continue
            if not period_overlaps_range(
                sub.period_key, range_start, range_end
            ):
                continue
            doc = docs_by_submission.get(sub.id)
            if doc is None:
                continue
            # Resolve institution from the id→code/name maps built once
            # above, instead of the lazy ``sub.institution`` relationship
            # (which fired a query per submission).
            institution_code = (
                institution_code_for_id.get(sub.institution_id) or "otros"
            )
            institution_name = (
                institution_name_for.get(institution_code) or institution_code
            )
            period = sub.period_key or "sin-periodo"
            safe_name = _safe_filename(
                doc.original_filename or f"documento-{doc.id}.pdf"
            )
            vendor_slug = _vendor_folder(vendor)
            # Item 1 follow-up — contracts get their own first-class
            # folder so an auditor unzipping the package finds the
            # contract artefacts immediately instead of digging into
            # ``interno_cliente/sin-periodo/``. The synthetic
            # ``contrato`` institution code threads through the
            # manifest label (``_INSTITUTION_LABELS`` in
            # audit_package_manifest.py) and the tree picker grouping
            # — three surfaces shifted by one constant.
            is_contract = (
                sub.requirement_code is not None
                and sub.requirement_code in CONTRACT_REQUIREMENT_CODES
            )
            # Corporate docs (acta constitutiva, official ID) get the same
            # first-class treatment as contracts — see CORPORATE_* above. The
            # synthetic ``corporativo`` code threads through the manifest label
            # and the tree-picker pin exactly like ``contrato`` does.
            is_corporate = (
                sub.requirement_code is not None
                and sub.requirement_code in CORPORATE_REQUIREMENT_CODES
            )
            if is_contract:
                institution_code = CONTRACT_INSTITUTION_CODE
                institution_name = CONTRACT_INSTITUTION_NAME
                base_arc = f"{vendor_slug}/{CONTRACT_FOLDER}/{safe_name}"
            elif is_corporate:
                institution_code = CORPORATE_INSTITUTION_CODE
                institution_name = CORPORATE_INSTITUTION_NAME
                base_arc = f"{vendor_slug}/{CORPORATE_FOLDER}/{safe_name}"
            else:
                base_arc = f"{vendor_slug}/{institution_code}/{period}/{safe_name}"
            count = seen_arc.get(base_arc, 0)
            seen_arc[base_arc] = count + 1
            arcname = base_arc if count == 0 else _suffix_arcname(base_arc, count)

            entries.append(
                AuditPackageEntry(
                    arcname=arcname,
                    storage_key=doc.storage_key,
                    size_bytes=int(doc.size_bytes or 0),
                    vendor_id=vendor.id,
                    vendor_name=vendor.name,
                    vendor_rfc=vendor.rfc,
                    institution_code=institution_code,
                    institution_name=institution_name,
                    period_key=period,
                    requirement_code=sub.requirement_code,
                    requirement_name=(
                        (sub.requirement_code and requirement_name_for.get(sub.requirement_code))
                        or (sub.requirement.name if sub.requirement else sub.requirement_code or "")
                    ),
                    status=sub.status,
                    filename=doc.original_filename or safe_name,
                    submitted_at_iso=(
                        sub.created_at.isoformat() if sub.created_at else None
                    ),
                    submission_id=sub.id,
                )
            )
    return entries


def _vendor_folder(vendor: Vendor) -> str:
    base = _safe_path_segment(vendor.name or "proveedor")
    rfc = (vendor.rfc or "").strip().upper()
    if rfc:
        return f"{base}-{_safe_path_segment(rfc)}"
    return base


_SAFE_PATH_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_path_segment(value: str) -> str:
    cleaned = _SAFE_PATH_SEGMENT_RE.sub("-", value.strip()).strip("-")
    return cleaned or "sin-nombre"


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    cleaned = _SAFE_FILENAME_RE.sub("-", name.strip()).strip("-")
    return cleaned or "documento"


def _suffix_arcname(base: str, idx: int) -> str:
    """Append ``-N`` before the extension on a collision."""
    head, sep, tail = base.rpartition("/")
    if not sep:
        head, tail = "", base
    stem, dot, ext = tail.rpartition(".")
    if not dot:
        return f"{head}/{tail}-{idx}" if head else f"{tail}-{idx}"
    new_tail = f"{stem}-{idx}.{ext}"
    return f"{head}/{new_tail}" if head else new_tail


# Convenience for callers that want to iterate entries without
# materializing the list (e.g. the manifest generator). Currently
# ``build_entries`` is the canonical builder; this helper just
# wraps it so a generator-style call site stays valid.
def iter_entries(
    db: Session,
    client: Client,
    filters: AuditPackageFilters,
) -> Iterable[AuditPackageEntry]:
    return build_entries(db, client, filters)
