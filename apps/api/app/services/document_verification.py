"""QR/folio extraction with official verification links (Phase B).

Official Mexican compliance documents (SAT opinión de cumplimiento,
IMSS opinión, constancias REPSE, CSF…) carry machine-verifiable
anchors: a QR code pointing at the issuing institution's verification
portal and/or a printed folio (the CFDI fiscal UUID, opinion folios).
This module extracts both from a stored PDF so the reviewer can jump
to the official verifier instead of eyeballing a screenshot:

    * **QR codes** — decoded from the embedded image XObjects of the
      first pages via ``zxing-cpp``. Each decode is classified: is it
      a URL? whose host? is the host an *official* government domain?
    * **Folios** — regex extraction over the text the inspection
      already pulled from the document (``FOLIO_PATTERNS``).

Two named risk reasons feed the Phase-A authenticity verdict (the
intake merge in ``submission_service`` re-rolls the combined reason
set through ``document_forensics.rollup_authenticity_risk``):

    * ``qr_non_official_domain`` (medium) — a QR on a document that
      claims to be institutional points somewhere that is NOT a
      government domain.
    * ``missing_expected_qr`` (info) — an institutional document with
      no decodable QR at all. INFO ONLY this phase: vector-drawn QR
      codes are invisible to image-XObject extraction (they are page
      content streams, not embedded images), so absence is a soft
      signal until the calibration harness measures real-world QR
      coverage (see ``scripts/calibrate_document_verdicts.py``).

Contract: :func:`extract_verification` swallows everything — any
internal error returns an empty result with ``error`` set in the
payload instead of raising. An extraction failure NEVER blocks an
upload.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.services.document_forensics import (
    SEVERITY_INFO,
    SEVERITY_MEDIUM,
    RiskReason,
)

logger = logging.getLogger(__name__)

# Scan budget: institutional documents put the verification QR on the
# first page (occasionally the last of 2-3); five pages × ten images
# is generous while bounding worst-case work on image-heavy uploads.
MAX_QR_PAGES = 5
MAX_IMAGES_PER_PAGE = 10

# Decoded QR content is stored verbatim up to this cap (verification
# URLs are ~100-300 chars; anything longer is payload data we only
# need a prefix of for the reviewer UI).
MAX_QR_CONTENT_CHARS = 2000

MAX_FOLIOS = 10

# Official-domain allowlist for verification links. A host counts as
# official when it EQUALS one of these domains or is a SUBDOMAIN of it
# (suffix match anchored at a dot boundary, so
# ``verificacfdi.facturaelectronica.sat.gob.mx`` is official while
# ``sat.gob.mx.evil.com`` is not). ``gob.mx`` covers the federal
# portal (e.g. ``www.gob.mx/imss``) and any ``*.gob.mx`` agency host;
# INFONAVIT is the one institution that verifies under ``.org.mx``.
OFFICIAL_VERIFICATION_DOMAINS: tuple[str, ...] = (
    "sat.gob.mx",
    "imss.gob.mx",
    "infonavit.org.mx",
    "stps.gob.mx",
    "gob.mx",
)

# Host substrings → detected-institution vocabulary (the same codes
# ``document_intelligence.INSTITUTION_KEYWORDS`` emits, minus the
# ``_repse`` suffix for STPS — the host only tells us the secretariat).
_HOST_INSTITUTION_GUESSES: tuple[tuple[str, str], ...] = (
    ("sat.gob.mx", "sat"),
    ("imss.gob.mx", "imss"),
    ("infonavit.org.mx", "infonavit"),
    ("stps.gob.mx", "stps"),
)

# detected_institution values (see INSTITUTION_KEYWORDS in
# document_intelligence) whose official documents are expected to
# carry a verification QR / official link.
_QR_EXPECTED_INSTITUTIONS = frozenset({"sat", "imss", "infonavit", "stps_repse"})

# Folio extraction over the document's text layer. Each entry is
# ``(kind, compiled regex)``; group 1 (or the whole match) is the
# folio value. The opinion-folio patterns are pragmatic: neither SAT
# nor IMSS publishes a stable folio format, so we anchor on an
# institution mention followed by the literal word "folio" and accept
# a 10-30 char ``[A-Z0-9-]`` token (with at least one digit, to skip
# ALL-CAPS words) within ~40 chars of it.
_OPINION_FOLIO_CORE = (
    r"\bfolio\b.{0,40}?"
    r"\b((?=[A-Z-]{0,29}\d)[A-Z0-9][A-Z0-9-]{8,28}[A-Z0-9])\b"
)
FOLIO_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # CFDI fiscal UUID — format-stable 8-4-4-4-12 hex, case-insensitive.
    (
        "cfdi_uuid",
        re.compile(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
            re.IGNORECASE,
        ),
    ),
    (
        "sat_opinion_folio",
        re.compile(r"\bsat\b.{0,300}?" + _OPINION_FOLIO_CORE, re.IGNORECASE | re.DOTALL),
    ),
    (
        "imss_opinion_folio",
        re.compile(r"\bimss\b.{0,300}?" + _OPINION_FOLIO_CORE, re.IGNORECASE | re.DOTALL),
    ),
)


@dataclass(frozen=True)
class VerificationResult:
    """QR + folio extraction outcome for one stored PDF."""

    qr_codes: list[dict[str, Any]] = field(default_factory=list)
    folios: list[dict[str, str]] = field(default_factory=list)
    reasons: list[RiskReason] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    analyzed: bool = False


def _empty_payload(error: str | None = None) -> dict[str, Any]:
    return {
        "qr_codes": [],
        "folios": [],
        "pages_scanned": 0,
        "images_scanned": 0,
        "error": error,
    }


def is_official_host(host: str | None) -> bool:
    """True when ``host`` equals or is a subdomain of an official domain."""
    if not host:
        return False
    normalized = host.lower().rstrip(".")
    return any(
        normalized == domain or normalized.endswith("." + domain)
        for domain in OFFICIAL_VERIFICATION_DOMAINS
    )


def _institution_guess(host: str | None) -> str | None:
    if not host:
        return None
    normalized = host.lower().rstrip(".")
    for domain, guess in _HOST_INSTITUTION_GUESSES:
        if normalized == domain or normalized.endswith("." + domain):
            return guess
    return None


def _classify_qr_content(page_number: int, content: str) -> dict[str, Any]:
    """Shape one decoded QR for the ``verification.qr_codes`` list."""
    content = content[:MAX_QR_CONTENT_CHARS]
    host: str | None = None
    is_url = False
    try:
        parsed = urlparse(content)
        if parsed.scheme in ("http", "https") and parsed.hostname:
            is_url = True
            host = parsed.hostname.lower()
    except ValueError:
        # Pathological URL (e.g. bad IPv6 brackets) — not a URL for us.
        pass
    return {
        "page": page_number,
        "content": content,
        "is_url": is_url,
        "host": host,
        "official": is_official_host(host) if is_url else False,
        "institution_guess": _institution_guess(host) if is_url else None,
    }


def _scan_qr_codes(path: Path) -> tuple[list[dict[str, Any]], int, int]:
    """Decode QR codes from embedded image XObjects.

    Returns ``(qr_codes, pages_scanned, images_scanned)``. Per-image
    failures (undecodable encodings, exotic filters) are skipped —
    only a failure to open the container bubbles up to the caller's
    fail-open wrapper. NOTE: vector-drawn QR codes live in the page
    content stream, not in image XObjects, and are invisible here —
    the reason ``missing_expected_qr`` stays a soft (info) signal.
    """
    import zxingcpp
    from PIL import Image
    from pypdf import PdfReader

    qr_codes: list[dict[str, Any]] = []
    pages_scanned = 0
    images_scanned = 0

    reader = PdfReader(str(path))
    for page_index, page in enumerate(reader.pages[:MAX_QR_PAGES], start=1):
        pages_scanned += 1
        try:
            images = list(page.images)
        except Exception:  # noqa: BLE001 — a broken resource dict is not fatal.
            continue
        for embedded in images[:MAX_IMAGES_PER_PAGE]:
            images_scanned += 1
            try:
                with Image.open(io.BytesIO(embedded.data)) as image:
                    decoded = zxingcpp.read_barcodes(image)
            except Exception:  # noqa: BLE001 — undecodable image ≠ failure.
                continue
            for result in decoded:
                if result.format.name != "QRCode" or not result.text:
                    continue
                qr_codes.append(_classify_qr_content(page_index, result.text))

    return qr_codes, pages_scanned, images_scanned


def extract_folios(text: str | None) -> list[dict[str, str]]:
    """Run ``FOLIO_PATTERNS`` over the text layer; dedupe, cap at 10."""
    if not text:
        return []
    folios: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for kind, pattern in FOLIO_PATTERNS:
        for match in pattern.finditer(text):
            value = (match.group(1) if pattern.groups else match.group(0)).upper()
            key = (kind, value)
            if key in seen:
                continue
            seen.add(key)
            folios.append({"kind": kind, "value": value})
            if len(folios) >= MAX_FOLIOS:
                return folios
    return folios


def _extract_text_from_pdf(path: Path) -> str:
    """Fallback text extraction when the caller retained none."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    chunks: list[str] = []
    for page in reader.pages[:MAX_QR_PAGES]:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 — partial text is still text.
            continue
    return "\n".join(chunks)


def extract_verification(
    path: Path,
    *,
    detected_institution: str | None,
    extracted_text: str | None,
) -> VerificationResult:
    """Extract QR codes + folios from one stored PDF; never raises.

    ``detected_institution`` is the heuristic institution code from
    ``analyze_document_text`` (sat / imss / infonavit / stps_repse / …)
    and gates the two risk reasons. ``extracted_text`` is the text the
    inspection already pulled at intake; pass ``None`` to re-extract
    from the file (the calibration harness does — text is not stored).

    On any internal error returns an empty result with ``error`` set
    in the payload and ``analyzed=False`` — intake fails open.
    """
    try:
        return _extract(
            Path(path),
            detected_institution=detected_institution,
            extracted_text=extracted_text,
        )
    except Exception as exc:  # noqa: BLE001 — fail-open contract.
        logger.warning("Verification extraction failed for %s: %s", path, exc)
        return VerificationResult(payload=_empty_payload(str(exc)[:500]))


def _extract(
    path: Path,
    *,
    detected_institution: str | None,
    extracted_text: str | None,
) -> VerificationResult:
    qr_codes, pages_scanned, images_scanned = _scan_qr_codes(path)

    if extracted_text is None:
        try:
            extracted_text = _extract_text_from_pdf(path)
        except Exception:  # noqa: BLE001 — no text, no folios; QRs still count.
            extracted_text = None
    folios = extract_folios(extracted_text)

    reasons: list[RiskReason] = []
    institutional = detected_institution in _QR_EXPECTED_INSTITUTIONS

    if institutional:
        non_official_hosts = sorted(
            {
                qr["host"]
                for qr in qr_codes
                if qr["is_url"] and qr["host"] and not qr["official"]
            }
        )
        for host in non_official_hosts:
            reasons.append(
                RiskReason(
                    code="qr_non_official_domain",
                    severity=SEVERITY_MEDIUM,
                    detail_es=(
                        f"El código QR del documento apunta a un dominio no "
                        f"oficial ({host}) — los enlaces de verificación de "
                        "documentos oficiales usan dominios de gobierno."
                    ),
                )
            )

        if not qr_codes:
            # INFO ONLY this phase: image-XObject extraction cannot see
            # vector-drawn QR codes, so "no QR" is a soft signal. It
            # gets promoted only after the calibration harness measures
            # real-world QR coverage on prod data (qr_found_rate).
            reasons.append(
                RiskReason(
                    code="missing_expected_qr",
                    severity=SEVERITY_INFO,
                    detail_es=(
                        "No se encontró un código QR de verificación; los "
                        "documentos oficiales suelen incluirlo. (El documento "
                        "puede usar un QR vectorial que el análisis no "
                        "rasteriza.)"
                    ),
                )
            )

    payload = {
        "qr_codes": qr_codes,
        "folios": folios,
        "pages_scanned": pages_scanned,
        "images_scanned": images_scanned,
        "error": None,
    }
    return VerificationResult(
        qr_codes=qr_codes,
        folios=folios,
        reasons=reasons,
        payload=payload,
        analyzed=True,
    )
