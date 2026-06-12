from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

RFC_ALIGNMENT_MATCH = "match"
RFC_ALIGNMENT_HOMOCLAVE_MISMATCH = "homoclave_mismatch"
RFC_ALIGNMENT_MISMATCH = "mismatch"
RFC_ALIGNMENT_ABSENT = "absent"
RFC_ALIGNMENT_NO_EXPECTED = "no_expected"


@dataclass(frozen=True)
class DocumentSignals:
    detected_institution: str | None = None
    detected_document_type: str | None = None
    detected_rfcs: list[str] = field(default_factory=list)
    detected_dates: list[str] = field(default_factory=list)
    period_mentions: list[str] = field(default_factory=list)
    requirement_match_confidence: float | None = None
    mismatch_reason: str | None = None
    anomaly_codes: list[str] = field(default_factory=list)
    expected_rfc: str | None = None
    rfc_alignment: str | None = None


DOCUMENT_TYPE_KEYWORDS = {
    "opinion_cumplimiento_sat": ["opinion de cumplimiento", "32-d", "sat"],
    "factura_cfdi": ["cfdi", "factura", "uuid", "comprobante fiscal"],
    "nomina_cfdi": ["nomina", "recibo de nomina", "percepciones", "deducciones"],
    "imss_pago": ["imss", "cuotas obrero", "registro patronal"],
    "infonavit_pago": ["infonavit", "aportaciones", "amortizaciones"],
    "repse_constancia": ["repse", "registro de prestadoras", "stps"],
    "contrato": ["contrato", "prestacion de servicios", "vigencia"],
}

INSTITUTION_KEYWORDS = {
    "sat": ["sat", "servicio de administracion tributaria", "cfdi", "32-d"],
    "imss": ["imss", "instituto mexicano del seguro social"],
    "infonavit": ["infonavit"],
    "stps_repse": ["stps", "repse", "secretaria del trabajo"],
}

RFC_RE = re.compile(r"\b[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}\b", re.IGNORECASE)
RFC_SPACED_RE = re.compile(
    r"\b(?:[A-ZÑ&][\s.\-/]*){3,4}"
    r"(?:\d[\s.\-/]*){6}"
    r"(?:[A-Z0-9][\s.\-/]*){3}\b",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b")
PERIOD_RE = re.compile(
    r"\b(?:20\d{2}[-/ ]?(?:0?[1-9]|1[0-2])|"
    r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|"
    r"noviembre|diciembre|bimestre|cuatrimestre)\b",
    re.IGNORECASE,
)


def analyze_document_text(
    text: str,
    *,
    expected_requirement: str,
    expected_institution: str,
    expected_period: str,
    expected_rfc: str | None = None,
) -> DocumentSignals:
    normalized_text = _normalize(text)
    normalized_requirement = _normalize(expected_requirement)
    anomalies: list[str] = []

    if not normalized_text:
        return DocumentSignals(
            requirement_match_confidence=0.0,
            mismatch_reason=None,
            anomaly_codes=["pdf_without_readable_text"],
            expected_rfc=normalize_rfc(expected_rfc),
            rfc_alignment=compute_rfc_alignment([], expected_rfc),
        )

    detected_type = _best_keyword_match(normalized_text, DOCUMENT_TYPE_KEYWORDS)
    detected_institution = _best_keyword_match(normalized_text, INSTITUTION_KEYWORDS)
    rfcs = extract_rfcs(text)
    dates = sorted(set(DATE_RE.findall(text)))[:20]
    period_mentions = sorted(set(PERIOD_RE.findall(text)))[:20]

    expected_tokens = [token for token in normalized_requirement.split() if len(token) > 4]
    token_hits = sum(1 for token in expected_tokens if token in normalized_text)
    token_score = token_hits / max(len(expected_tokens), 1)

    # Phase 1 — boilerplate-tolerant institution scoring. Pre-Phase-1
    # the score required ``detected_institution == expected``, which is
    # the *best-match* — a SAT opinión de cumplimiento that also names
    # IMSS in boilerplate often scored 0 on this axis because the IMSS
    # keyword count beat SAT's. We now credit the expected institution
    # for being mentioned at all; the best-match output remains
    # available on ``detected_institution`` for reviewer context.
    expected_institution_present = (
        expected_institution
        and _keyword_hit_count(normalized_text, INSTITUTION_KEYWORDS.get(expected_institution, []))
        > 0
    )
    institution_score = 1.0 if expected_institution_present else 0.0
    confidence = round((token_score * 0.7) + (institution_score * 0.3), 2)

    mismatch_reason = None
    expected_doc_type = _expected_document_type(normalized_requirement)
    if detected_type and expected_doc_type and detected_type != expected_doc_type:
        anomalies.append("possible_document_type_mismatch")
        mismatch_reason = (
            f"El documento parece '{detected_type}', pero el requisito esperado sugiere "
            f"'{expected_doc_type}'."
        )
        confidence = min(confidence, 0.35)
    elif (
        detected_institution
        and detected_institution != expected_institution
        and not expected_institution_present
    ):
        # Phase 1 — only fire if the expected institution is fully
        # absent. If it's mentioned anywhere, treat the other detection
        # as a legitimate cross-reference (SAT opinión naming IMSS,
        # IMSS pago naming INFONAVIT in summary tables, etc.) rather
        # than alarming the provider.
        anomalies.append("possible_institution_mismatch")
        mismatch_reason = (
            f"La institución detectada '{detected_institution}' no coincide con "
            f"'{expected_institution}'."
        )
        confidence = min(confidence, 0.45)
    elif expected_period and _normalize(expected_period) not in normalized_text:
        anomalies.append("period_not_confirmed")

    return DocumentSignals(
        detected_institution=detected_institution,
        detected_document_type=detected_type,
        detected_rfcs=rfcs,
        detected_dates=dates,
        period_mentions=period_mentions,
        requirement_match_confidence=confidence,
        mismatch_reason=mismatch_reason,
        anomaly_codes=anomalies,
        expected_rfc=normalize_rfc(expected_rfc),
        rfc_alignment=compute_rfc_alignment(rfcs, expected_rfc),
    )


def normalize_rfc(value: str | None) -> str | None:
    """Normalize RFCs for matching while preserving RFC-specific letters."""
    if not value:
        return None
    normalized = unicodedata.normalize("NFKC", value).upper()
    compact = re.sub(r"[^A-Z0-9Ñ&]", "", normalized)
    return compact or None


def extract_rfcs(text: str) -> list[str]:
    """Extract RFC candidates from raw and OCR-spaced text."""
    candidates = {normalize_rfc(match) for match in RFC_RE.findall(text or "")}
    candidates.update(normalize_rfc(match) for match in RFC_SPACED_RE.findall(text or ""))
    return sorted(rfc for rfc in candidates if rfc and len(rfc) in (12, 13))


def compute_rfc_alignment(
    detected_rfcs: list[str] | tuple[str, ...] | set[str],
    expected_rfc: str | None,
) -> str:
    """Compare detected RFC candidates against the provider RFC.

    The return value is advisory only; status derivation still depends
    exclusively on document/institution match signals.
    """
    expected = normalize_rfc(expected_rfc)
    if not expected:
        return RFC_ALIGNMENT_NO_EXPECTED

    detected = [rfc for rfc in (normalize_rfc(value) for value in detected_rfcs) if rfc]
    if not detected:
        return RFC_ALIGNMENT_ABSENT

    if expected in detected:
        return RFC_ALIGNMENT_MATCH

    expected_core = expected[:-3]
    for rfc in detected:
        if len(rfc) == len(expected) and rfc[:-3] == expected_core:
            return RFC_ALIGNMENT_HOMOCLAVE_MISMATCH

    return RFC_ALIGNMENT_MISMATCH


def _keyword_hit_count(text: str, keywords: list[str]) -> int:
    """Number of distinct keywords from ``keywords`` that occur in ``text``."""
    return sum(1 for keyword in keywords if _normalize(keyword) in text)


def _best_keyword_match(text: str, keyword_map: dict[str, list[str]]) -> str | None:
    """Return the unique top-scoring key, or None if there is no clear winner.

    Phase 1 — pre-Phase-1 a tie on a positive score silently returned
    the first dict-inserted key, which produced a structural bias toward
    ``opinion_cumplimiento_sat`` / ``sat`` (the first entries in each
    catalog). Ties are now treated as ambiguous and return None so the
    downstream mismatch logic does not act on a coin-flip.
    """
    scores = {code: _keyword_hit_count(text, keywords) for code, keywords in keyword_map.items()}
    if not scores:
        return None
    best_score = max(scores.values())
    if best_score == 0:
        return None
    top = [code for code, score in scores.items() if score == best_score]
    if len(top) > 1:
        return None
    return top[0]


def _expected_document_type(requirement: str) -> str | None:
    if "opinion" in requirement and "sat" in requirement:
        return "opinion_cumplimiento_sat"
    if "factura" in requirement or "cfdi" in requirement:
        return "factura_cfdi"
    if "nomina" in requirement:
        return "nomina_cfdi"
    if "imss" in requirement:
        return "imss_pago"
    if "infonavit" in requirement:
        return "infonavit_pago"
    if "repse" in requirement:
        return "repse_constancia"
    if "contrato" in requirement:
        return "contrato"
    return None


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()
