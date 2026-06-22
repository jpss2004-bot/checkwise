from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pypdf import PdfReader

if TYPE_CHECKING:
    from app.services.ocr import DocumentAiOcrClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PdfInspectionResult:
    is_pdf: bool
    is_corrupt: bool = False
    is_encrypted: bool = False
    # Provenance: True when the PDF declared encryption but decrypted
    # cleanly with an empty password (owner-password-only restriction).
    # Such files are readable, so ``is_encrypted`` stays False, but the
    # flag preserves the fact for the audit trail.
    had_owner_password: bool = False
    page_count: int | None = None
    text_sample: str = ""
    text_char_count: int = 0
    has_text: bool = False
    is_probably_scanned: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    # Phase 3 OCR-fallback provenance. Only meaningful when
    # ``inspect_pdf_with_ocr_fallback`` actually invoked Document AI on a
    # scanned PDF; otherwise these stay at their defaults (``ocr_attempted``
    # False) and the intake audit trail emits no OCR event. ``inspect_pdf``
    # never touches them.
    ocr_attempted: bool = False
    ocr_text_char_count: int | None = None
    ocr_error: str | None = None
    ocr_processor_name: str | None = None


def inspect_pdf(
    path: Path,
    *,
    max_text_pages: int = 10,
    max_text_chars: int = 20_000,
) -> PdfInspectionResult:
    header = path.read_bytes()[:5]
    if header != b"%PDF-":
        return PdfInspectionResult(
            is_pdf=False,
            is_corrupt=True,
            error="El archivo no inicia con cabecera PDF válida.",
        )

    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # pypdf raises several parser-specific exceptions.
        return PdfInspectionResult(
            is_pdf=True,
            is_corrupt=True,
            error=f"No fue posible leer la estructura PDF: {exc}",
        )

    # A PDF can be "encrypted" yet open with an empty password (the
    # common case: an owner password that restricts editing but not
    # reading). Such files decrypt fine and read normally, so we must
    # NOT flag them as encrypted downstream. We only treat a file as
    # truly encrypted when the empty-password decrypt FAILS.
    had_owner_password = False
    if reader.is_encrypted:
        had_owner_password = True
        decrypted = False
        try:
            decrypted = reader.decrypt("") != 0
        except Exception:
            decrypted = False
        if not decrypted:
            return PdfInspectionResult(
                is_pdf=True,
                is_encrypted=True,
                had_owner_password=True,
                page_count=None,
                error="El PDF está protegido con contraseña o cifrado.",
            )

    try:
        pages = reader.pages
        page_count = len(pages)
        chunks: list[str] = []
        for page in pages[:max_text_pages]:
            chunks.append(page.extract_text() or "")
            if sum(len(chunk) for chunk in chunks) >= max_text_chars:
                break
    except Exception as exc:
        return PdfInspectionResult(
            is_pdf=True,
            is_corrupt=True,
            # Reached only after a successful empty-password decrypt, so
            # the file is readable: not encrypted from the caller's view.
            is_encrypted=False,
            had_owner_password=had_owner_password,
            error=f"No fue posible extraer páginas/texto del PDF: {exc}",
        )

    text_sample = "\n".join(chunks).strip()
    metadata = _safe_metadata(reader.metadata)
    text_char_count = len(text_sample)
    has_text = text_char_count >= 20

    return PdfInspectionResult(
        is_pdf=True,
        is_corrupt=False,
        # The file opened and yielded text — an empty-password decrypt
        # (owner-password-only) counts as readable, NOT encrypted.
        is_encrypted=False,
        had_owner_password=had_owner_password,
        page_count=page_count,
        text_sample=text_sample[:max_text_chars],
        text_char_count=text_char_count,
        has_text=has_text,
        is_probably_scanned=page_count > 0 and not has_text,
        metadata=metadata,
    )


def _safe_metadata(metadata: Any) -> dict[str, str]:
    if not metadata:
        return {}
    result: dict[str, str] = {}
    for key, value in dict(metadata).items():
        if value is None:
            continue
        result[str(key)] = str(value)[:500]
    return result


# ---------------------------------------------------------------------------
# Phase 3 — OCR fallback for scanned uploads
# ---------------------------------------------------------------------------
#
# ``inspect_pdf`` extracts embedded text via pypdf. When the PDF is a
# scan (born-image, no text layer) pypdf returns nothing, the detector
# sees an empty string, and the submission lands in
# ``pendiente_revision`` with zero signals — even when the file is
# obviously correct.
#
# ``inspect_pdf_with_ocr_fallback`` is the intake-time entrypoint:
# it runs the pure inspection first and, when ``is_probably_scanned``
# is True, asks the OCR client for text. On success it replaces
# ``text_sample`` / ``text_char_count`` / ``has_text`` so the detector
# can run; ``is_probably_scanned`` is intentionally left True so the
# reviewer surface knows the text came from OCR rather than pypdf
# (the audit trail matters for evidence quality).
#
# Any OCR failure path (no client configured, no creds, API error,
# timeout) returns the original ``PdfInspectionResult`` unchanged —
# OCR never aborts an upload.


_PDF_TEXT_MIN_CHARS = 20


@lru_cache(maxsize=1)
def _cached_ocr_client() -> DocumentAiOcrClient | None:
    """Lazy singleton — build the OCR client on first use, cache thereafter.

    Cached at module level so each worker only pays the SDK / auth
    setup cost once. ``lru_cache(maxsize=1)`` makes the build idempotent
    without a manual lock. Returns ``None`` when OCR is disabled or
    misconfigured; the caller treats that as "no OCR available".
    """
    # Local import — avoids importing the Google SDK at module-load
    # time, which lets the rest of the codebase run in environments
    # that haven't installed ``google-cloud-documentai``.
    from app.services.ocr import build_ocr_client_from_settings

    return build_ocr_client_from_settings()


def inspect_pdf_with_ocr_fallback(
    path: Path,
    *,
    max_text_pages: int = 10,
    max_text_chars: int = 20_000,
    ocr_client: DocumentAiOcrClient | None | object = ...,
) -> PdfInspectionResult:
    """Run ``inspect_pdf`` and OCR the file if it looks like a scan.

    ``ocr_client`` is an injection seam for tests: pass ``None`` to
    force the no-OCR path, pass a stub client to assert against the
    OCR-success path, or leave at the sentinel to use the cached
    production client.
    """
    result = inspect_pdf(
        path,
        max_text_pages=max_text_pages,
        max_text_chars=max_text_chars,
    )
    if not result.is_probably_scanned:
        return result

    client = _cached_ocr_client() if ocr_client is ... else ocr_client
    if client is None:
        # No OCR configured — OCR was NOT attempted, so the row stays as
        # "scanned, no text" with ocr_attempted False (no OCR audit event).
        return result

    # From here OCR is genuinely invoked. Record the provenance fields so
    # the intake audit trail can emit a truthful ``ocr_performed`` event
    # (pass / warning / fail) regardless of the outcome. ``extract_text``
    # is contracted to never raise — it folds read/API/timeout failures
    # into ``OcrResult.error`` — so OCR never aborts an upload.
    ocr_result = client.extract_text(path)
    text = (ocr_result.text or "").strip()
    ocr_fields: dict[str, Any] = {
        "ocr_attempted": True,
        "ocr_text_char_count": len(text),
        "ocr_error": ocr_result.error,
        "ocr_processor_name": getattr(client, "processor_name", None),
    }

    if not text:
        # OCR ran but produced nothing usable (error or genuinely empty) —
        # keep the original text so the row still records "scanned, no
        # text" and lands in pendiente_revision, but stamp the OCR
        # provenance so the audit event reflects what happened.
        return replace(result, **ocr_fields)

    return replace(
        result,
        text_sample=text[:max_text_chars],
        text_char_count=len(text),
        has_text=len(text) >= _PDF_TEXT_MIN_CHARS,
        # is_probably_scanned stays True — the audit trail records
        # that text came from OCR, not from the original PDF.
        **ocr_fields,
    )
