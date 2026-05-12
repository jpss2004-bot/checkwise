from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


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
) -> DocumentSignals:
    normalized_text = _normalize(text)
    normalized_requirement = _normalize(expected_requirement)
    anomalies: list[str] = []

    if not normalized_text:
        return DocumentSignals(
            requirement_match_confidence=0.0,
            mismatch_reason=None,
            anomaly_codes=["pdf_without_readable_text"],
        )

    detected_type = _best_keyword_match(normalized_text, DOCUMENT_TYPE_KEYWORDS)
    detected_institution = _best_keyword_match(normalized_text, INSTITUTION_KEYWORDS)
    rfcs = sorted(set(match.upper() for match in RFC_RE.findall(text)))
    dates = sorted(set(DATE_RE.findall(text)))[:20]
    period_mentions = sorted(set(PERIOD_RE.findall(text)))[:20]

    expected_tokens = [token for token in normalized_requirement.split() if len(token) > 4]
    token_hits = sum(1 for token in expected_tokens if token in normalized_text)
    token_score = token_hits / max(len(expected_tokens), 1)

    institution_score = 1.0 if detected_institution == expected_institution else 0.0
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
    elif detected_institution and detected_institution != expected_institution:
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
    )


def _best_keyword_match(text: str, keyword_map: dict[str, list[str]]) -> str | None:
    scores = {
        code: sum(1 for keyword in keywords if _normalize(keyword) in text)
        for code, keywords in keyword_map.items()
    }
    best_code, best_score = max(scores.items(), key=lambda item: item[1])
    return best_code if best_score > 0 else None


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
