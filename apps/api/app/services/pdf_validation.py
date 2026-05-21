from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pypdf import PdfReader


@dataclass(frozen=True)
class PdfInspectionResult:
    is_pdf: bool
    is_corrupt: bool = False
    is_encrypted: bool = False
    page_count: int | None = None
    text_sample: str = ""
    text_char_count: int = 0
    has_text: bool = False
    is_probably_scanned: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def inspect_pdf(path: Path, *, max_text_pages: int = 3) -> PdfInspectionResult:
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

    if reader.is_encrypted:
        decrypted = False
        try:
            decrypted = reader.decrypt("") != 0
        except Exception:
            decrypted = False
        if not decrypted:
            return PdfInspectionResult(
                is_pdf=True,
                is_encrypted=True,
                page_count=None,
                error="El PDF está protegido con contraseña o cifrado.",
            )

    try:
        pages = reader.pages
        page_count = len(pages)
        chunks: list[str] = []
        for page in pages[:max_text_pages]:
            chunks.append(page.extract_text() or "")
    except Exception as exc:
        return PdfInspectionResult(
            is_pdf=True,
            is_corrupt=True,
            is_encrypted=reader.is_encrypted,
            error=f"No fue posible extraer páginas/texto del PDF: {exc}",
        )

    text_sample = "\n".join(chunks).strip()
    metadata = _safe_metadata(reader.metadata)
    text_char_count = len(text_sample)
    has_text = text_char_count >= 20

    return PdfInspectionResult(
        is_pdf=True,
        is_corrupt=False,
        is_encrypted=reader.is_encrypted,
        page_count=page_count,
        text_sample=text_sample[:5000],
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
