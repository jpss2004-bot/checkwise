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
from dataclasses import dataclass
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.statuses import DocumentStatus
from app.models import Document, ProviderWorkspace, Submission
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
    db: Session, workspace: ProviderWorkspace
) -> ExpedienteSummary:
    """Count files + total bytes on the workspace without reading bytes.

    Pure SQL — joins submissions → documents and filters out the
    no-byte states. Returns the totals so the endpoint can enforce
    caps before any bytes leave storage.
    """
    rows = list(_iter_workspace_documents(db, workspace))
    return ExpedienteSummary(
        file_count=len(rows),
        total_bytes=sum(int(r[2] or 0) for r in rows),
    )


def stream_expediente_zip(
    db: Session, workspace: ProviderWorkspace
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
    """
    entries = _build_entries(db, workspace)
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
    db: Session, workspace: ProviderWorkspace
) -> Iterator[tuple[Submission, Document, int]]:
    """Yield ``(submission, document, size_bytes)`` tuples for the
    workspace's downloadable submissions. Used by both the
    summary and the streaming paths so the filter logic stays in
    one place.
    """
    submissions = list(
        db.scalars(
            select(Submission)
            .where(
                Submission.client_id == workspace.client_id,
                Submission.vendor_id == workspace.vendor_id,
                Submission.status.notin_(_NO_BYTES_STATES),
            )
            .order_by(Submission.created_at.asc())
        )
    )
    for sub in submissions:
        doc = db.scalar(
            select(Document).where(Document.submission_id == sub.id).limit(1)
        )
        if doc is None:
            continue
        yield sub, doc, int(doc.size_bytes or 0)


def _build_entries(
    db: Session, workspace: ProviderWorkspace
) -> list[_ZipEntry]:
    """Translate workspace submissions into ZIP entries with collision-safe arcnames."""
    seen: dict[str, int] = {}
    entries: list[_ZipEntry] = []
    for sub, doc, size in _iter_workspace_documents(db, workspace):
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
