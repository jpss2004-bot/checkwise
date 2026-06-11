"""Pure-local PDF authenticity forensics (document-revalidation Phase A).

Official Mexican compliance documents (SAT, IMSS, INFONAVIT) are
produced by institutional systems — never by consumer design tools —
and are not edited after generation. This module inspects a stored
PDF's *container* (metadata, incremental-update markers, active
content) for signs of tampering and rolls them up into a single
reviewer-facing verdict:

    * ``"clean"``       — no medium/high finding.
    * ``"suspicious"``  — at least one medium finding.
    * ``"high_risk"``   — at least one high finding.
    * ``None``          — analysis failed (the file could not be
      parsed at all). Intake fails open: a forensics error NEVER
      blocks an upload, it just leaves the verdict empty.

Each finding is a *named* reason ``{"code", "severity", "detail_es"}``
with a Spanish ``detail_es`` ready for the reviewer UI. The raw
findings (producer, dates, ``%%EOF`` count, JavaScript flags, …) ride
along in the ``forensics`` dict as evidence.

The verdict is intentionally separate from
``requirement_match_confidence`` (content heuristics): a document can
match its requirement perfectly *and* have been forged in Canva.

Contract: :func:`analyze_pdf_forensics` swallows everything — any
internal error returns a result with ``risk=None`` and a
``forensics_error`` note instead of raising.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pypdf import PdfReader

logger = logging.getLogger(__name__)

RISK_CLEAN = "clean"
RISK_SUSPICIOUS = "suspicious"
RISK_HIGH = "high_risk"

SEVERITY_INFO = "info"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

_SEVERITY_ORDER = {SEVERITY_HIGH: 0, SEVERITY_MEDIUM: 1, SEVERITY_INFO: 2}

# Producer/Creator substrings (lower-cased match) of consumer design and
# editing tools that official SAT / IMSS / INFONAVIT documents are never
# generated with. A match means a human re-built or re-touched the file:
# design suites, office suites, and online "edit your PDF" services.
# Institutional generators (e.g. "SAT", "Acrobat Distiller", server-side
# report libraries) are intentionally NOT listed — absence from this
# list never penalizes.
SUSPICIOUS_GENERATORS: tuple[str, ...] = (
    "canva",
    "photoshop",
    "illustrator",
    "gimp",
    "microsoft word",
    "microsoft® word",
    "libreoffice",
    "openoffice",
    "writer",  # LibreOffice/OpenOffice Writer producer strings
    "ilovepdf",
    "smallpdf",
    "sejda",
    "pdfescape",
    "foxit pdf editor",
    "foxit editor",
    "foxitpdfeditor",
)

# ModDate − CreationDate gaps below this are normal generator jitter
# (some libraries stamp the two fields milliseconds-to-minutes apart).
_EDIT_GAP_THRESHOLD = timedelta(minutes=5)

# Beyond this gap the file was reopened and saved much later — that is
# not jitter, that is an editing session.
_EDIT_GAP_HIGH_THRESHOLD = timedelta(days=30)

# A document for period 2026-M04 created a couple of days before April 1
# can be legitimate clock skew / early issuance; created weeks before the
# period starts is impossible.
_PERIOD_GRACE = timedelta(days=5)

# Canonical monthly period keys look like "2026-M04" (see
# ``app/core/period_validation.py``). Only monthly keys carry "the
# document cannot predate the period" semantics we can check cheaply;
# bimonthly/quarterly/annual/onboarding keys are skipped.
_MONTHLY_PERIOD_RE = re.compile(r"^(20\d{2})-M(0?[1-9]|1[0-2])$")

# PDF date strings: D:YYYYMMDDHHmmSS plus optional timezone suffix.
# Every component after the year is optional in the wild, so parse
# defensively and treat the value as a naive timestamp.
_PDF_DATE_RE = re.compile(
    r"D?:?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?"
)

_PDF_TEXT_MIN_CHARS = 20


@dataclass(frozen=True)
class RiskReason:
    code: str
    severity: str  # "info" | "medium" | "high"
    detail_es: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "detail_es": self.detail_es,
        }


@dataclass(frozen=True)
class ForensicsResult:
    """Verdict + named reasons + raw evidence for one PDF."""

    risk: str | None  # clean | suspicious | high_risk; None = not analyzed
    reasons: list[RiskReason] = field(default_factory=list)
    forensics: dict[str, Any] = field(default_factory=dict)

    @property
    def analyzed(self) -> bool:
        return self.risk is not None

    def reasons_payload(self) -> list[dict[str, str]]:
        """JSON-ready shape for the ``risk_reasons`` column."""
        return [reason.as_dict() for reason in self.reasons]


def parse_pdf_date(raw: str | None) -> datetime | None:
    """Parse the PDF ``D:YYYYMMDDHHmmSS`` date format defensively.

    Returns a naive ``datetime`` (timezone suffixes are ignored — the
    checks below only compare PDF dates against each other or against
    whole months, where sub-hour precision is irrelevant) or ``None``
    when the string is missing or unparseable.
    """
    if not raw:
        return None
    match = _PDF_DATE_RE.search(str(raw))
    if not match:
        return None
    try:
        year = int(match.group(1))
        month = int(match.group(2) or 1)
        day = int(match.group(3) or 1)
        hour = int(match.group(4) or 0)
        minute = int(match.group(5) or 0)
        second = int(match.group(6) or 0)
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        # Garbage like month 00 / day 32 — treat as unparseable.
        return None


def _matched_generator(*values: str | None) -> str | None:
    """First raw Producer/Creator value matching the suspicious list."""
    for value in values:
        if not value:
            continue
        lowered = value.lower()
        if any(marker in lowered for marker in SUSPICIOUS_GENERATORS):
            return value
    return None


def _period_month_start(period_key: str | None) -> datetime | None:
    """First day of a canonical monthly period key, else ``None``."""
    if not period_key:
        return None
    match = _MONTHLY_PERIOD_RE.match(period_key.strip())
    if not match:
        return None
    return datetime(int(match.group(1)), int(match.group(2)), 1)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y %H:%M")


def analyze_pdf_forensics(
    path: Path,
    *,
    period_key: str | None,
    pdf_metadata: dict | None,
) -> ForensicsResult:
    """Run all container-level authenticity checks on one stored PDF.

    ``pdf_metadata`` is the dict ``inspect_pdf`` already extracted at
    intake (keys like ``/Producer``); pass it to avoid re-reading the
    Info dictionary. ``period_key`` is the submission's canonical
    period key — only monthly keys (``2026-M04``) activate the
    created-before-period check.

    Never raises: any internal failure returns ``risk=None`` with a
    ``forensics_error`` note in the forensics dict.
    """
    try:
        return _analyze(Path(path), period_key=period_key, pdf_metadata=pdf_metadata)
    except Exception as exc:  # noqa: BLE001 — fail-open contract.
        logger.warning("Forensics analysis failed for %s: %s", path, exc)
        return ForensicsResult(
            risk=None,
            reasons=[],
            forensics={"forensics_error": str(exc)[:500]},
        )


def _analyze(
    path: Path,
    *,
    period_key: str | None,
    pdf_metadata: dict | None,
) -> ForensicsResult:
    raw_bytes = path.read_bytes()
    # Opening the reader is the analyzability gate: if pypdf cannot
    # parse the container at all there is nothing trustworthy to say
    # about authenticity, so let the exception bubble to the fail-open
    # wrapper (risk=None == "sin analizar").
    reader = PdfReader(str(path))

    metadata: dict[str, Any]
    if pdf_metadata:
        metadata = pdf_metadata
    else:
        try:
            info = reader.metadata
            metadata = {str(k): str(v) for k, v in dict(info or {}).items() if v is not None}
        except Exception:  # noqa: BLE001 — metadata is optional evidence.
            metadata = {}

    producer = metadata.get("/Producer")
    creator = metadata.get("/Creator")
    creation_raw = metadata.get("/CreationDate")
    mod_raw = metadata.get("/ModDate")
    creation_date = parse_pdf_date(creation_raw)
    mod_date = parse_pdf_date(mod_raw)

    eof_count = raw_bytes.count(b"%%EOF")
    incremental_updates = max(0, eof_count - 1)

    has_javascript = False
    has_open_action = False
    try:
        root = reader.trailer["/Root"].get_object()
        names = root.get("/Names")
        if names is not None:
            names = names.get_object()
            has_javascript = names.get("/JavaScript") is not None
        has_open_action = root.get("/OpenAction") is not None
    except Exception:  # noqa: BLE001 — a broken catalog is not active content.
        pass

    # "Digitally generated" inference for the stripped-metadata check:
    # a file with an embedded text layer came out of a generator (scans
    # have no text), so missing Producer + CreationDate means the
    # metadata was deliberately removed.
    has_text_layer = False
    try:
        if reader.pages:
            sample = reader.pages[0].extract_text() or ""
            has_text_layer = len(sample.strip()) >= _PDF_TEXT_MIN_CHARS
    except Exception:  # noqa: BLE001 — extraction failure ≠ no text; stay False.
        pass

    forensics: dict[str, Any] = {
        "producer": producer,
        "creator": creator,
        "creation_date": creation_raw,
        "creation_date_parsed": creation_date.isoformat() if creation_date else None,
        "mod_date": mod_raw,
        "mod_date_parsed": mod_date.isoformat() if mod_date else None,
        "eof_count": eof_count,
        "incremental_updates": incremental_updates,
        "has_javascript": has_javascript,
        "has_open_action": has_open_action,
        "has_text_layer": has_text_layer,
        "period_key": period_key,
    }

    reasons: list[RiskReason] = []

    # --- Suspicious generator (medium) -------------------------------
    matched_generator = _matched_generator(producer, creator)
    if matched_generator:
        reasons.append(
            RiskReason(
                code="suspicious_generator",
                severity=SEVERITY_MEDIUM,
                detail_es=(
                    f"Generado con {matched_generator} — los documentos "
                    "oficiales no se producen con editores de diseño."
                ),
            )
        )

    # --- Edited after creation (medium / high) -----------------------
    # Two signals fold into ONE reason so a single editing session is
    # not double-penalized: the ModDate gap and the incremental-update
    # (%%EOF) count both mean "modified after first write". Raw counts
    # stay in ``forensics`` for the evidence panel.
    edit_severity: str | None = None
    edit_detail: str | None = None
    if creation_date and mod_date and (mod_date - creation_date) > _EDIT_GAP_THRESHOLD:
        gap = mod_date - creation_date
        edit_severity = (
            SEVERITY_HIGH if gap > _EDIT_GAP_HIGH_THRESHOLD else SEVERITY_MEDIUM
        )
        edit_detail = (
            "Documento editado después de su creación — creado el "
            f"{_fmt(creation_date)}, modificado el {_fmt(mod_date)}."
        )
    if incremental_updates > 0:
        if edit_severity is None:
            edit_severity = SEVERITY_MEDIUM
            edit_detail = (
                "Documento editado después de su creación — el archivo "
                f"registra {incremental_updates + 1} escrituras "
                "incrementales."
            )
        # else: keep the date-based detail (richer) at its severity;
        # the raw eof_count is already in forensics.
    if edit_severity is not None and edit_detail is not None:
        reasons.append(
            RiskReason(
                code="edited_after_creation",
                severity=edit_severity,
                detail_es=edit_detail,
            )
        )

    # --- Created before the claimed period (high) --------------------
    period_start = _period_month_start(period_key)
    if period_start is not None and creation_date is not None:
        if creation_date < period_start - _PERIOD_GRACE:
            reasons.append(
                RiskReason(
                    code="created_before_period",
                    severity=SEVERITY_HIGH,
                    detail_es=(
                        f"El documento fue creado el {_fmt(creation_date)}, "
                        f"antes de que iniciara el periodo declarado "
                        f"({period_key}) — un documento del periodo no "
                        "puede existir antes del periodo."
                    ),
                )
            )

    # --- Active content (high) ----------------------------------------
    if has_javascript or has_open_action:
        reasons.append(
            RiskReason(
                code="embedded_javascript",
                severity=SEVERITY_HIGH,
                detail_es=(
                    "El PDF contiene código activo (JavaScript) — "
                    "inusual en documentos oficiales."
                ),
            )
        )

    # --- Stripped metadata (info — never elevates alone) -------------
    if has_text_layer and not producer and not creation_date:
        reasons.append(
            RiskReason(
                code="stripped_metadata",
                severity=SEVERITY_INFO,
                detail_es=(
                    "El PDF fue generado digitalmente pero no conserva "
                    "metadatos de origen (productor ni fecha de creación) "
                    "— posible limpieza de metadatos."
                ),
            )
        )

    reasons.sort(key=lambda reason: _SEVERITY_ORDER.get(reason.severity, 9))

    if any(reason.severity == SEVERITY_HIGH for reason in reasons):
        risk = RISK_HIGH
    elif any(reason.severity == SEVERITY_MEDIUM for reason in reasons):
        risk = RISK_SUSPICIOUS
    else:
        risk = RISK_CLEAN

    return ForensicsResult(risk=risk, reasons=reasons, forensics=forensics)
