from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

RFC_ALIGNMENT_MATCH = "match"
RFC_ALIGNMENT_HOMOCLAVE_MISMATCH = "homoclave_mismatch"
RFC_ALIGNMENT_MISMATCH = "mismatch"
RFC_ALIGNMENT_ABSENT = "absent"
RFC_ALIGNMENT_NO_EXPECTED = "no_expected"

PERIOD_ALIGNMENT_MATCH = "match"
PERIOD_ALIGNMENT_MISMATCH = "mismatch"
PERIOD_ALIGNMENT_ABSENT = "absent"
PERIOD_ALIGNMENT_NO_EXPECTED = "no_expected"

IDENTITY_ALIGNMENT_MATCH = "match"
IDENTITY_ALIGNMENT_HOMOCLAVE_MISMATCH = "homoclave_mismatch"
IDENTITY_ALIGNMENT_CLIENT_MATCH = "client_match"
IDENTITY_ALIGNMENT_MISMATCH = "mismatch"
IDENTITY_ALIGNMENT_ABSENT = "absent"
IDENTITY_ALIGNMENT_NO_EXPECTED = "no_expected"


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
    period_alignment: str | None = None
    identity_alignment: str | None = None


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
RFC_LABEL_RE = re.compile(
    r"(?:r\s*\.?\s*f\s*\.?\s*c\s*\.?|registro\s+federal\s+de\s+contribuyentes)"
    r"[^A-ZÑ&0-9]{0,12}([A-ZÑ&0-9\s.\-/]{12,48})",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b")
PERIOD_RE = re.compile(
    r"\b(?:20\d{2}[-/ ]?(?:0?[1-9]|1[0-2])|"
    r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|"
    r"noviembre|diciembre|bimestre|cuatrimestre)\b",
    re.IGNORECASE,
)
MONTH_NAMES = {
    "enero": "01",
    "febrero": "02",
    "marzo": "03",
    "abril": "04",
    "mayo": "05",
    "junio": "06",
    "julio": "07",
    "agosto": "08",
    "septiembre": "09",
    "setiembre": "09",
    "octubre": "10",
    "noviembre": "11",
    "diciembre": "12",
}
MONTH_NAME_PATTERN = "|".join(MONTH_NAMES)
YEAR_MONTH_RE = re.compile(r"\b(20\d{2})[-/\s]?(?:m)?(0?[1-9]|1[0-2])\b", re.IGNORECASE)
DATE_PERIOD_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2}|\d{2})\b")
MONTH_YEAR_RE = re.compile(
    rf"\b({MONTH_NAME_PATTERN})\s+(?:de\s+)?(20\d{{2}})\b",
    re.IGNORECASE,
)
YEAR_MONTH_NAME_RE = re.compile(
    rf"\b(20\d{{2}})\s+(?:de\s+)?({MONTH_NAME_PATTERN})\b",
    re.IGNORECASE,
)


def analyze_document_text(
    text: str,
    *,
    expected_requirement: str,
    expected_institution: str,
    expected_period: str,
    expected_rfc: str | None = None,
    expected_vendor_name: str | None = None,
    expected_client_name: str | None = None,
    expected_client_rfc: str | None = None,
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
            period_alignment=compute_period_alignment(expected_period, text),
            identity_alignment=compute_identity_alignment(
                [],
                text,
                expected_provider_rfc=expected_rfc,
                expected_provider_name=expected_vendor_name,
                expected_client_rfc=expected_client_rfc,
                expected_client_name=expected_client_name,
            ),
        )

    detected_type = _best_keyword_match(normalized_text, DOCUMENT_TYPE_KEYWORDS)
    detected_institution = _best_keyword_match(normalized_text, INSTITUTION_KEYWORDS)
    rfcs = extract_rfcs(text)
    rfc_alignment = compute_rfc_alignment(rfcs, expected_rfc)
    identity_alignment = compute_identity_alignment(
        rfcs,
        text,
        expected_provider_rfc=expected_rfc,
        expected_provider_name=expected_vendor_name,
        expected_client_rfc=expected_client_rfc,
        expected_client_name=expected_client_name,
    )
    dates = sorted(set(DATE_RE.findall(text)))[:20]
    period_mentions = sorted(set(PERIOD_RE.findall(text)))[:20]
    period_alignment = compute_period_alignment(expected_period, text)

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
    elif period_alignment != PERIOD_ALIGNMENT_MATCH:
        anomalies.append("period_not_confirmed")

    if identity_alignment == IDENTITY_ALIGNMENT_MISMATCH:
        anomalies.append("rfc_mismatch")
        confidence = min(confidence, 0.49)
    elif identity_alignment == IDENTITY_ALIGNMENT_CLIENT_MATCH:
        anomalies.append("identity_matches_client_not_provider")
        confidence = min(confidence, 0.49)
    elif identity_alignment == IDENTITY_ALIGNMENT_HOMOCLAVE_MISMATCH:
        anomalies.append("rfc_homoclave_mismatch")
        confidence = min(confidence, 0.65)
    elif identity_alignment == IDENTITY_ALIGNMENT_ABSENT:
        anomalies.append("rfc_not_detected")
        confidence = min(confidence, 0.69)

    if period_alignment == PERIOD_ALIGNMENT_MISMATCH:
        if "period_not_confirmed" not in anomalies:
            anomalies.append("period_not_confirmed")
        confidence = min(confidence, 0.49)
    elif period_alignment == PERIOD_ALIGNMENT_ABSENT:
        if "period_not_confirmed" not in anomalies:
            anomalies.append("period_not_confirmed")
        confidence = min(confidence, 0.69)

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
        rfc_alignment=rfc_alignment,
        period_alignment=period_alignment,
        identity_alignment=identity_alignment,
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
    raw = text or ""
    candidates = {normalize_rfc(match) for match in RFC_RE.findall(raw)}
    candidates.update(normalize_rfc(match) for match in RFC_SPACED_RE.findall(raw))
    for labeled in RFC_LABEL_RE.findall(raw):
        compact = normalize_rfc(labeled) or ""
        candidates.update(RFC_RE.findall(compact))
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


def compute_identity_alignment(
    detected_rfcs: list[str] | tuple[str, ...] | set[str],
    text: str,
    *,
    expected_provider_rfc: str | None,
    expected_provider_name: str | None = None,
    expected_client_rfc: str | None = None,
    expected_client_name: str | None = None,
) -> str:
    """Decide whether the document appears to belong to the expected provider.

    Provider evidence wins over client evidence: a provider document may mention
    the client, but a document that only matches the client or another RFC is not
    strong enough to prevalidate.
    """
    provider_rfc = normalize_rfc(expected_provider_rfc)
    client_rfc = normalize_rfc(expected_client_rfc)
    normalized_text = _normalize(text)
    provider_name_present = _name_present(normalized_text, expected_provider_name)
    client_name_present = _name_present(normalized_text, expected_client_name)

    detected = [rfc for rfc in (normalize_rfc(value) for value in detected_rfcs) if rfc]
    if not provider_rfc and not expected_provider_name:
        return IDENTITY_ALIGNMENT_NO_EXPECTED
    if provider_rfc and provider_rfc in detected:
        return IDENTITY_ALIGNMENT_MATCH
    if provider_name_present:
        return IDENTITY_ALIGNMENT_MATCH

    if provider_rfc and detected:
        provider_core = provider_rfc[:-3]
        for rfc in detected:
            if len(rfc) == len(provider_rfc) and rfc[:-3] == provider_core:
                return IDENTITY_ALIGNMENT_HOMOCLAVE_MISMATCH

    if client_rfc and client_rfc in detected:
        return IDENTITY_ALIGNMENT_CLIENT_MATCH
    if client_name_present and not provider_name_present:
        return IDENTITY_ALIGNMENT_CLIENT_MATCH

    if detected:
        return IDENTITY_ALIGNMENT_MISMATCH
    if provider_rfc or expected_provider_name:
        return IDENTITY_ALIGNMENT_ABSENT
    return IDENTITY_ALIGNMENT_NO_EXPECTED


def normalize_period_key(value: str | None) -> str | None:
    """Normalize period-like values to ``YYYY-MM`` when possible."""
    if not value:
        return None
    normalized = _normalize(value)
    match = re.search(r"\b(20\d{2})[-/\s]?(?:m)?(0?[1-9]|1[0-2])\b", normalized)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}"
    month_match = re.search(rf"\b({MONTH_NAME_PATTERN})\s+(?:de\s+)?(20\d{{2}})\b", normalized)
    if month_match:
        return f"{month_match.group(2)}-{MONTH_NAMES[month_match.group(1)]}"
    year_month_match = re.search(rf"\b(20\d{{2}})\s+(?:de\s+)?({MONTH_NAME_PATTERN})\b", normalized)
    if year_month_match:
        return f"{year_month_match.group(1)}-{MONTH_NAMES[year_month_match.group(2)]}"
    return None


def extract_period_keys(text: str) -> list[str]:
    """Extract month-level period candidates from OCR/text samples."""
    normalized = _normalize(text)
    candidates: set[str] = set()
    for year, month in YEAR_MONTH_RE.findall(normalized):
        candidates.add(f"{year}-{int(month):02d}")
    for _day, month, year in DATE_PERIOD_RE.findall(normalized):
        full_year = f"20{year}" if len(year) == 2 else year
        candidates.add(f"{full_year}-{int(month):02d}")
    for month_name, year in MONTH_YEAR_RE.findall(normalized):
        candidates.add(f"{year}-{MONTH_NAMES[_normalize(month_name)]}")
    for year, month_name in YEAR_MONTH_NAME_RE.findall(normalized):
        candidates.add(f"{year}-{MONTH_NAMES[_normalize(month_name)]}")
    return sorted(candidates)


def compute_period_alignment(expected_period: str | None, text: str) -> str:
    """Compare detected period candidates against the expected submission period."""
    expected = normalize_period_key(expected_period)
    if not expected:
        return PERIOD_ALIGNMENT_NO_EXPECTED
    detected = extract_period_keys(text)
    if not detected:
        return PERIOD_ALIGNMENT_ABSENT
    if expected in detected:
        return PERIOD_ALIGNMENT_MATCH
    return PERIOD_ALIGNMENT_MISMATCH


def _keyword_hit_count(text: str, keywords: list[str]) -> int:
    """Number of distinct keywords from ``keywords`` that occur in ``text``."""
    return sum(1 for keyword in keywords if _normalize(keyword) in text)


def _name_present(normalized_text: str, expected_name: str | None) -> bool:
    normalized_name = _normalize(expected_name or "")
    if not normalized_text or not normalized_name:
        return False
    if normalized_name in normalized_text:
        return True
    tokens = [
        token
        for token in normalized_name.split()
        if len(token) > 3
        and token
        not in {
            "sade",
            "sapi",
            "cvl",
            "sa",
            "cv",
            "de",
            "del",
            "la",
            "las",
            "los",
            "servicios",
            "comercializadora",
        }
    ]
    if not tokens:
        return False
    hits = sum(1 for token in tokens if token in normalized_text)
    required = 1 if len(tokens) == 1 else max(2, (len(tokens) + 1) // 2)
    return hits >= required


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
