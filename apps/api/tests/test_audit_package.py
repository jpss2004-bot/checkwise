"""Audit-package composer tests — the cross-tenant audit ZIP.

``app.services.audit_package`` builds the single ZIP a ``client_admin``
hands an inspector: every provider under the client, scoped by filters.
Because it composes bytes from across an entire client portfolio it is
security-sensitive on three axes this module pins:

* **Zip-Slip** — a crafted vendor name / period / filename must never
  produce an arcname that escapes the extraction directory.
* **Size caps** — the composer must refuse (before yielding a byte) any
  package over the file-count / total-byte caps.
* **Index/contents consistency** — a row the INDICE references but whose
  bytes are missing from storage must be recorded in
  ``DOCUMENTOS_FALTANTES.txt`` rather than silently dropped.

Plus the approved-only default (don't leak in-review/rejected evidence
unless explicitly opted in) and the audit-log metadata shape (don't dump
every submission id into the trail).

No test here touches the database: ``stream_audit_package`` accepts a
pre-resolved ``entries`` list, so the streaming + cap paths run against
injected entries and a fake storage backend. The DB-backed
``build_entries`` resolution is out of scope for this pure-unit file.
"""

from __future__ import annotations

import contextlib
import io
import zipfile
from types import SimpleNamespace

import pytest

from app.constants.statuses import DocumentStatus
from app.services.audit_package import (
    DEFAULT_STATUSES,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    AuditPackageEntry,
    AuditPackageFilters,
    AuditPackageTooLargeError,
    _render_missing_note,
    _safe_arcname,
    _safe_filename,
    _safe_path_segment,
    _suffix_arcname,
    _vendor_folder,
    _ZipStreamSink,
    stream_audit_package,
)

# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _entry(**over) -> AuditPackageEntry:
    """One resolved entry with sane defaults; override per test."""
    base = dict(
        arcname="vendor-a-RFC010101AAA/sat/2026-M01/doc.pdf",
        storage_key="key-1",
        size_bytes=10,
        vendor_id="v1",
        vendor_name="Vendor A",
        vendor_rfc="RFC010101AAA",
        institution_code="sat",
        institution_name="SAT",
        period_key="2026-M01",
        requirement_code="sat:csf:mensual",
        requirement_name="Constancia de Situación Fiscal",
        status="aprobado",
        filename="doc.pdf",
        submitted_at_iso="2026-05-01T00:00:00",
    )
    base.update(over)
    return AuditPackageEntry(**base)


class _FakeStorage:
    """Minimal storage stub exposing the ``open_stream`` context manager
    ``stream_audit_package`` relies on. A key absent from ``blobs`` raises,
    mirroring a missing object in real storage."""

    def __init__(self, blobs: dict[str, bytes]):
        self._blobs = blobs

    @contextlib.contextmanager
    def open_stream(self, storage_key: str):
        if storage_key not in self._blobs:
            raise FileNotFoundError(storage_key)
        yield io.BytesIO(self._blobs[storage_key])


def _drain(gen) -> bytes:
    return b"".join(gen)


# ─────────────────────────────────────────────────────────────────────
# Zip-Slip / arcname sanitization
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "hostile",
    [
        "../../etc/passwd",
        "..\\..\\windows\\system32\\cmd.exe",
        "/abs/escape.pdf",
        "a/./b/../c.pdf",
        "....//....//x.pdf",
        "C:\\Users\\victim\\secret.pdf",
        "vendor/../../../root.pdf",
    ],
)
def test_safe_arcname_neutralizes_traversal(hostile: str) -> None:
    safe = _safe_arcname(hostile)
    parts = safe.split("/")
    # No segment may be a traversal primitive, and the path may never be
    # absolute — either would let an extractor write outside the target dir.
    assert ".." not in parts
    assert not safe.startswith("/")
    assert not safe.startswith("\\")
    assert "\\" not in safe  # backslashes normalized to forward slashes
    assert safe  # never empty


def test_safe_arcname_empty_falls_back() -> None:
    assert _safe_arcname("") == "documento"
    assert _safe_arcname("///") == "documento"


def test_safe_arcname_idempotent_on_clean_path() -> None:
    clean = "vendor-a/sat/2026-M01/constancia.pdf"
    assert _safe_arcname(clean) == clean


def test_safe_path_segment_and_filename_reject_dot_only() -> None:
    assert _safe_path_segment("..") == "sin-nombre"
    assert _safe_path_segment(".") == "sin-nombre"
    assert _safe_filename("..") == "documento"
    # Spaces / unsafe chars collapse to single dashes, dots preserved.
    assert _safe_path_segment("Razón Social, S.A. de C.V.") == "Raz-n-Social-S.A.-de-C.V."
    assert _safe_filename("mi archivo final.pdf") == "mi-archivo-final.pdf"


def test_vendor_folder_combines_name_and_rfc() -> None:
    vendor = SimpleNamespace(name="Vendor A", rfc="rfc010101aaa")
    folder = _vendor_folder(vendor)
    assert folder == "Vendor-A-RFC010101AAA"  # rfc upper-cased, joined


def test_vendor_folder_traversal_name_is_neutralized() -> None:
    vendor = SimpleNamespace(name="..", rfc="")
    assert _vendor_folder(vendor) == "sin-nombre"


# ─────────────────────────────────────────────────────────────────────
# Collision suffixing — never silently drop a same-named row
# ─────────────────────────────────────────────────────────────────────


def test_suffix_arcname_inserts_before_extension() -> None:
    base = "vendor-a/sat/2026-M01/doc.pdf"
    assert _suffix_arcname(base, 1) == "vendor-a/sat/2026-M01/doc-1.pdf"


def test_suffix_arcname_handles_no_extension() -> None:
    assert _suffix_arcname("vendor-a/contratos/contrato", 2) == "vendor-a/contratos/contrato-2"


# ─────────────────────────────────────────────────────────────────────
# Size caps — refuse before yielding any bytes
# ─────────────────────────────────────────────────────────────────────


def test_stream_raises_on_file_count_cap_before_yielding() -> None:
    entries = [_entry(storage_key=f"k{i}", arcname=f"v/sat/2026-M01/d{i}.pdf") for i in range(MAX_FILES + 1)]
    gen = stream_audit_package(None, None, AuditPackageFilters(), entries=entries)
    # The cap check sits before the first ``yield``; the very first
    # iteration must raise, proving no bytes were emitted first.
    with pytest.raises(AuditPackageTooLargeError) as ei:
        next(gen)
    assert ei.value.exceeds == "files"
    assert ei.value.file_count == MAX_FILES + 1


def test_stream_raises_on_total_bytes_cap() -> None:
    entries = [_entry(size_bytes=MAX_TOTAL_BYTES + 1)]
    gen = stream_audit_package(None, None, AuditPackageFilters(), entries=entries)
    with pytest.raises(AuditPackageTooLargeError) as ei:
        next(gen)
    assert ei.value.exceeds == "bytes"
    assert ei.value.total_bytes == MAX_TOTAL_BYTES + 1


# ─────────────────────────────────────────────────────────────────────
# Streaming — valid archive, manifest cover, missing-file note, Zip-Slip
# ─────────────────────────────────────────────────────────────────────


def test_stream_produces_valid_zip_with_manifest_and_contents(monkeypatch) -> None:
    e1 = _entry(storage_key="k1", arcname="vendor-a/sat/2026-M01/a.pdf")
    e2 = _entry(storage_key="k2", arcname="vendor-b/imss/2026-M01/b.pdf")
    storage = _FakeStorage({"k1": b"AAAA", "k2": b"BBBBBB"})
    monkeypatch.setattr("app.services.audit_package.get_storage_service", lambda: storage)

    data = _drain(
        stream_audit_package(
            None,
            None,
            AuditPackageFilters(),
            manifest_pdf=b"%PDF-1.4 fake-index",
            entries=[e1, e2],
        )
    )
    zf = zipfile.ZipFile(io.BytesIO(data))
    assert zf.testzip() is None  # archive integrity
    names = set(zf.namelist())
    assert "INDICE.pdf" in names
    assert e1.arcname in names
    assert e2.arcname in names
    assert "DOCUMENTOS_FALTANTES.txt" not in names
    assert zf.read("INDICE.pdf") == b"%PDF-1.4 fake-index"
    assert zf.read(e1.arcname) == b"AAAA"
    assert zf.read(e2.arcname) == b"BBBBBB"


def test_stream_records_missing_objects_instead_of_dropping_them(monkeypatch) -> None:
    present = _entry(storage_key="here", arcname="vendor-a/sat/2026-M01/here.pdf")
    gone = _entry(
        storage_key="vanished",
        arcname="vendor-b/imss/2026-M02/gone.pdf",
        vendor_name="Vendor B",
        filename="gone.pdf",
        period_key="2026-M02",
        institution_name="IMSS",
    )
    storage = _FakeStorage({"here": b"present-bytes"})  # "vanished" absent
    monkeypatch.setattr("app.services.audit_package.get_storage_service", lambda: storage)

    data = _drain(
        stream_audit_package(None, None, AuditPackageFilters(), entries=[present, gone])
    )
    zf = zipfile.ZipFile(io.BytesIO(data))
    names = set(zf.namelist())
    assert present.arcname in names
    assert gone.arcname not in names  # missing bytes => not in the body
    assert "DOCUMENTOS_FALTANTES.txt" in names
    note = zf.read("DOCUMENTOS_FALTANTES.txt").decode("utf-8")
    # The note ties the gap back to the exact row the INDICE listed.
    assert "Vendor B" in note
    assert "gone.pdf" in note
    assert "vanished" in note


def test_stream_sanitizes_hostile_arcname_in_the_real_archive(monkeypatch) -> None:
    evil = _entry(storage_key="k", arcname="../../../../etc/passwd")
    storage = _FakeStorage({"k": b"x"})
    monkeypatch.setattr("app.services.audit_package.get_storage_service", lambda: storage)

    data = _drain(stream_audit_package(None, None, AuditPackageFilters(), entries=[evil]))
    zf = zipfile.ZipFile(io.BytesIO(data))
    for name in zf.namelist():
        assert ".." not in name.split("/")
        assert not name.startswith("/")


# ─────────────────────────────────────────────────────────────────────
# Filters — approved-only default + audit-log metadata shape
# ─────────────────────────────────────────────────────────────────────


def test_effective_statuses_defaults_to_approved_only() -> None:
    assert AuditPackageFilters().effective_statuses == (DocumentStatus.APROBADO.value,)
    assert DEFAULT_STATUSES == frozenset({DocumentStatus.APROBADO.value})


def test_effective_statuses_preserves_explicit_selection() -> None:
    explicit = AuditPackageFilters(statuses=("aprobado", "en_revision"))
    assert explicit.effective_statuses == ("aprobado", "en_revision")


def test_to_audit_dict_emits_default_statuses_and_omits_unset_fields() -> None:
    audit = AuditPackageFilters().to_audit_dict()
    assert audit == {"statuses": [DocumentStatus.APROBADO.value]}


def test_to_audit_dict_records_submission_count_not_the_ids() -> None:
    filters = AuditPackageFilters(
        institutions=("sat", "imss"),
        requirement_codes=("sat:csf:mensual",),
        vendor_ids=("v1",),
        submission_ids=("s1", "s2", "s3"),
    )
    audit = filters.to_audit_dict()
    # The raw whitelist is never dumped into the trail — only its size.
    assert "submission_ids" not in audit
    assert audit["submission_ids_count"] == 3
    assert audit["institutions"] == ["sat", "imss"]
    assert audit["requirement_codes"] == ["sat:csf:mensual"]
    assert audit["vendor_ids"] == ["v1"]


# ─────────────────────────────────────────────────────────────────────
# Streaming sink — drain protocol that keeps memory bounded
# ─────────────────────────────────────────────────────────────────────


def test_zip_stream_sink_is_non_seekable_and_drains() -> None:
    sink = _ZipStreamSink()
    assert sink.writable() is True
    # Non-seekable is load-bearing: it forces ZipFile to emit data
    # descriptors so the buffer can be truncated mid-stream.
    assert sink.seekable() is False

    sink.write(b"hello")
    sink.write(b"world")
    assert sink.tell() == 10  # absolute offset, cumulative
    assert sink.pending == 10

    out = b"".join(sink.drain())
    assert out == b"helloworld"
    assert sink.pending == 0  # buffer cleared
    assert sink.tell() == 10  # offset keeps growing, never resets
    assert b"".join(sink.drain()) == b""  # nothing left to drain


def test_render_missing_note_lists_every_row() -> None:
    a = _entry(vendor_name="Alpha", filename="a.pdf", storage_key="ka")
    b = _entry(vendor_name="Beta", filename="b.pdf", storage_key="kb")
    note = _render_missing_note([a, b])
    assert "Alpha" in note and "a.pdf" in note and "ka" in note
    assert "Beta" in note and "b.pdf" in note and "kb" in note
