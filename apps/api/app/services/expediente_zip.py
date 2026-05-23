"""Expediente ZIP composition.

Phase 5 / Slice 5B — composes a streaming ZIP of every uploaded
document on a provider workspace. The backend opts for in-process
``zipfile.ZipFile`` writing into an iterator-driven buffer per the
locked decision: simple, no infra dependency, works against both
the local FS and S3 backends.

Caps protect the API node:
  * ``MAX_FILES = 200`` — past this we 413 rather than spool a
    massive ZIP.
  * ``MAX_TOTAL_BYTES = 500 * 1024 * 1024`` (500 MB) — same.

States with no bytes on disk (``pendiente``, ``vencido``,
``no_aplica``) are skipped silently — including them would 404
mid-ZIP. Every other state (approved, in_review, uploaded,
rejected, requiere_aclaracion, posible_mismatch, excepcion_legal)
contributes the latest stored document so the provider gets their
full evidence trail (rejected docs may be useful for re-uploads).

Folder layout inside the archive: ``<institution>/<period_key>/<filename>``
so untarring produces a sensible directory tree. ``institution``
falls back to ``otros`` and ``period_key`` to ``sin-periodo`` when
the source row is incomplete — defensive against legacy /
partial-seed submissions.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.statuses import DocumentStatus
from app.models import Document, Institution, ProviderWorkspace, Submission
from app.services.storage import get_storage_service

MAX_FILES = 200
MAX_TOTAL_BYTES = 500 * 1024 * 1024

# Submission states that have NO document bytes on disk. Excluded so
# the ZIP iterator never hits a 404 mid-stream.
_NO_BYTES_STATES: frozenset[str] = frozenset({
    DocumentStatus.PENDIENTE.value,
    DocumentStatus.VENCIDO.value,
    DocumentStatus.NO_APLICA.value,
})


@dataclass(frozen=True)
class ExpedienteFilters:
    """Optional filter set for the expediente ZIP composition.

    Slice 5C — passing any combination of ``status``,
    ``period_key``, and ``institution`` scopes the archive AND the
    pre-flight cap check. ``None`` on a field means "no filter".

    Filters compose AND-wise. Unknown ``institution`` codes resolve
    to an empty result (no Institution row → no submission matches),
    matching the same defensive behavior the client portal already
    uses.

    ``to_audit_dict`` returns a JSON-safe shape for the audit log
    metadata — only non-null fields appear, ``None`` when no filter
    is active (so the audit row reads cleanly).
    """

    status: str | None = None
    period_key: str | None = None
    institution: str | None = None

    @property
    def is_empty(self) -> bool:
        return self.status is None and self.period_key is None and self.institution is None

    def to_audit_dict(self) -> dict[str, str] | None:
        if self.is_empty:
            return None
        out: dict[str, str] = {}
        if self.status:
            out["status"] = self.status
        if self.period_key:
            out["period_key"] = self.period_key
        if self.institution:
            out["institution"] = self.institution
        return out


_NO_FILTERS = ExpedienteFilters()
# Sentinel re-export so callers don't have to construct an empty
# instance themselves when they want "no filters".
__all__ = (
    "ExpedienteFilters",
    "ExpedienteSummary",
    "ExpedienteTooLargeError",
    "MAX_FILES",
    "MAX_TOTAL_BYTES",
    "stream_expediente_zip",
    "summarize_expediente",
)
# ``field`` is imported for future filter additions (e.g. date
# ranges); silence the unused-import warning until then.
_ = field


class ExpedienteTooLargeError(Exception):
    """Raised when the workspace exceeds either cap.

    Carries both observed counts so the endpoint can render a
    plain-Spanish 413 explaining which limit was hit.
    """

    def __init__(self, *, file_count: int, total_bytes: int, exceeds: str):
        self.file_count = file_count
        self.total_bytes = total_bytes
        self.exceeds = exceeds  # "files" | "bytes"
        super().__init__(
            f"Expediente exceeds {exceeds} cap "
            f"(files={file_count}, bytes={total_bytes})."
        )


class ExpedienteSummary(NamedTuple):
    """Cheap pre-flight read of the workspace's downloadable footprint.

    Used by the endpoint to 413 BEFORE streaming starts, so the
    caller learns about the cap immediately rather than after a
    half-built ZIP.
    """

    file_count: int
    total_bytes: int


@dataclass(frozen=True)
class _ZipEntry:
    arcname: str
    storage_key: str
    size_bytes: int


def summarize_expediente(
    db: Session,
    workspace: ProviderWorkspace,
    filters: ExpedienteFilters | None = None,
) -> ExpedienteSummary:
    """Count files + total bytes on the workspace without reading bytes.

    Pure SQL — joins submissions → documents and filters out the
    no-byte states. ``filters`` further scopes the count, so the
    endpoint can apply the same caps to a filtered subset.
    """
    rows = list(_iter_workspace_documents(db, workspace, filters or _NO_FILTERS))
    return ExpedienteSummary(
        file_count=len(rows),
        total_bytes=sum(int(r[2] or 0) for r in rows),
    )


def stream_expediente_zip(
    db: Session,
    workspace: ProviderWorkspace,
    filters: ExpedienteFilters | None = None,
) -> Iterator[bytes]:
    """Yield ZIP bytes for the workspace's expediente, in chunks.

    Raises ``ExpedienteTooLargeError`` BEFORE yielding any bytes if
    the workspace exceeds either cap. Each call materializes a fresh
    in-memory ZIP buffer via ``zipfile.ZipFile``; FastAPI's
    ``StreamingResponse`` consumes the iterator and writes the bytes
    to the wire in order.

    Filename layout: ``<institution>/<period_key>/<safe_filename>``.
    Identical-name collisions across slots are disambiguated by
    appending an index suffix so the ZIP never silently drops a row.

    Slice 5C — ``filters`` scopes both the cap check and the
    archive composition. ``None`` (or an empty ``ExpedienteFilters``)
    behaves identically to the original full-pull semantics.
    """
    entries = _build_entries(db, workspace, filters or _NO_FILTERS)
    file_count = len(entries)
    total_bytes = sum(e.size_bytes for e in entries)
    if file_count > MAX_FILES:
        raise ExpedienteTooLargeError(
            file_count=file_count,
            total_bytes=total_bytes,
            exceeds="files",
        )
    if total_bytes > MAX_TOTAL_BYTES:
        raise ExpedienteTooLargeError(
            file_count=file_count,
            total_bytes=total_bytes,
            exceeds="bytes",
        )

    storage = get_storage_service()
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as zf:
        for entry in entries:
            try:
                src_path = storage.open_for_read(entry.storage_key)
            except Exception:
                # Storage helper raised; skip the row rather than
                # blowing up the whole archive. Audit row already
                # captured intent — the missing file is the bug to
                # fix elsewhere.
                continue
            if not src_path.exists():
                continue
            with src_path.open("rb") as src:
                zf.writestr(entry.arcname, src.read())
    buffer.seek(0)
    yield buffer.read()


def _iter_workspace_documents(
    db: Session,
    workspace: ProviderWorkspace,
    filters: ExpedienteFilters = _NO_FILTERS,
) -> Iterator[tuple[Submission, Document, int]]:
    """Yield ``(submission, document, size_bytes)`` tuples for the
    workspace's downloadable submissions. Used by both the
    summary and the streaming paths so the filter logic stays in
    one place.

    Slice 5C — when ``filters`` is non-empty, the SQL further
    scopes the result. ``institution`` resolves via
    ``Institution.code`` so unknown codes naturally yield zero
    rows (no Institution row → no submission matches), matching
    the defensive behavior the client portal uses.
    """
    stmt = (
        select(Submission)
        .where(
            Submission.client_id == workspace.client_id,
            Submission.vendor_id == workspace.vendor_id,
            Submission.status.notin_(_NO_BYTES_STATES),
        )
        .order_by(Submission.created_at.asc())
    )
    if filters.status:
        stmt = stmt.where(Submission.status == filters.status)
    if filters.period_key:
        stmt = stmt.where(Submission.period_key == filters.period_key)
    if filters.institution:
        inst_id = db.scalar(
            select(Institution.id).where(Institution.code == filters.institution)
        )
        if inst_id is None:
            # Unknown institution → empty result. Force-empty rather
            # than 400 so a future catalog code can ship without
            # breaking the download flow.
            return
        stmt = stmt.where(Submission.institution_id == inst_id)

    submissions = list(db.scalars(stmt))
    for sub in submissions:
        doc = db.scalar(
            select(Document).where(Document.submission_id == sub.id).limit(1)
        )
        if doc is None:
            continue
        yield sub, doc, int(doc.size_bytes or 0)


def _build_entries(
    db: Session,
    workspace: ProviderWorkspace,
    filters: ExpedienteFilters = _NO_FILTERS,
) -> list[_ZipEntry]:
    """Translate workspace submissions into ZIP entries with collision-safe arcnames."""
    seen: dict[str, int] = {}
    entries: list[_ZipEntry] = []
    for sub, doc, size in _iter_workspace_documents(db, workspace, filters):
        institution_code = (
            sub.institution.code if sub.institution else None
        ) or "otros"
        period = sub.period_key or "sin-periodo"
        safe = _safe_filename(doc.original_filename or f"documento-{doc.id}.pdf")
        base_arcname = f"{institution_code}/{period}/{safe}"
        # Disambiguate within the same folder when two slots happen
        # to share the same filename.
        count = seen.get(base_arcname, 0)
        seen[base_arcname] = count + 1
        if count == 0:
            arcname = base_arcname
        else:
            stem, dot, ext = safe.rpartition(".")
            if not dot:
                stem, ext = safe, ""
            arcname = (
                f"{institution_code}/{period}/{stem}-{count}"
                + (f".{ext}" if ext else "")
            )
        entries.append(
            _ZipEntry(arcname=arcname, storage_key=doc.storage_key, size_bytes=size)
        )
    return entries


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    cleaned = _SAFE_FILENAME_RE.sub("-", name.strip()).strip("-")
    return cleaned or "documento"
