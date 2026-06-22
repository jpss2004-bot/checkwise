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

import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.statuses import DocumentStatus
from app.models import Document, Institution, ProviderWorkspace, Submission
from app.services.audit_package import (
    _DRAIN_THRESHOLD_BYTES,
    _STREAM_CHUNK_BYTES,
    _safe_arcname,
    _safe_path_segment,
    _ZipStreamSink,
)
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
    *,
    entries: list[_ZipEntry] | None = None,
) -> Iterator[bytes]:
    """Yield ZIP bytes for the workspace's expediente as a TRUE streaming
    generator (bounded memory).

    Raises ``ExpedienteTooLargeError`` BEFORE yielding any bytes if the
    workspace exceeds either cap. The ZIP is composed against a
    non-seekable rolling buffer drained and yielded after every entry —
    and mid-entry past ~1 MB — so neither the whole archive nor any
    single source file is held in RAM. Source bytes stream in fixed-size
    chunks via ``storage.open_stream`` (no per-entry /tmp temp copy).
    FastAPI's ``StreamingResponse`` consumes the iterator and writes the
    bytes to the wire in order.

    Filename layout: ``<institution>/<period_key>/<safe_filename>``.
    Identical-name collisions across slots are disambiguated by
    appending an index suffix so the ZIP never silently drops a row.
    Arcnames are sanitized (no ``..``/leading-slash/drive segments) so a
    crafted filename cannot escape the extraction directory (Zip-Slip).

    Missing storage objects are skipped from the body AND recorded in a
    ``DOCUMENTOS_FALTANTES.txt`` note at the archive root so the listing
    and the contents stay consistent.

    Slice 5C — ``filters`` scopes both the cap check and the archive
    composition. ``None`` (or an empty ``ExpedienteFilters``) behaves
    identically to the original full-pull semantics. ``entries`` lets a
    caller that already resolved the list pass it through so the
    generator skips the duplicate ``_build_entries`` DB scan.
    """
    if entries is None:
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
    sink = _ZipStreamSink()
    missing: list[_ZipEntry] = []
    with zipfile.ZipFile(
        sink, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as zf:
        for entry in entries:
            wrote = False
            try:
                with storage.open_stream(entry.storage_key) as src:
                    with zf.open(_safe_arcname(entry.arcname), mode="w") as dst:
                        while chunk := src.read(_STREAM_CHUNK_BYTES):
                            dst.write(chunk)
                            if sink.pending >= _DRAIN_THRESHOLD_BYTES:
                                yield from sink.drain()
                    wrote = True
            except Exception:
                # Storage helper raised or the object is missing; skip the
                # row rather than blowing up the whole archive. Recorded in
                # the missing-files note below so the listing and the
                # contents do not silently diverge.
                wrote = False
            if not wrote:
                missing.append(entry)
                continue
            yield from sink.drain()
        if missing:
            zf.writestr(
                _safe_arcname("DOCUMENTOS_FALTANTES.txt"),
                _render_missing_note(missing).encode("utf-8"),
            )
            yield from sink.drain()
    yield from sink.drain()


def _render_missing_note(entries: list[_ZipEntry]) -> str:
    """Body for the ``DOCUMENTOS_FALTANTES.txt`` note listing entries
    whose bytes could not be packaged."""
    lines = [
        "Documentos que no pudieron incluirse en el expediente",
        "(archivo no encontrado en almacenamiento al momento de la descarga):",
        "",
    ]
    lines.extend(
        f"- {e.arcname} (storage_key={e.storage_key})" for e in entries
    )
    lines.append("")
    lines.append(
        "Si esperabas estos documentos, contacta a soporte para verificar "
        "el almacenamiento."
    )
    return "\n".join(lines)


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
        institution_code = _safe_path_segment(
            (sub.institution.code if sub.institution else None) or "otros"
        )
        # Sanitize the period segment too — a crafted ``period_key`` ('..')
        # would otherwise land verbatim in the arcname. ``_safe_arcname``
        # at write time is the backstop; cleaning here keeps the picker
        # labels consistent with the bytes on disk.
        period = _safe_path_segment(sub.period_key or "sin-periodo")
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
    # A filename of exactly '..'/'.' is a traversal primitive on naive
    # extractors — collapse dot-only names to a safe placeholder.
    if cleaned in ("", ".", "..") or set(cleaned) <= {"."}:
        return "documento"
    return cleaned
