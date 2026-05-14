"""Public-API catalogs exposed at /api/v1/catalogs.

The code lists are derived from the typed StrEnums in ``app.constants`` so
there is exactly one place that defines a canonical code. Labels and
extra metadata stay here because they are presentation concerns.
"""

from __future__ import annotations

from app.constants.institutions import INSTITUTION_LABELS, Institution
from app.constants.statuses import STATUS_LABELS_ES, DocumentStatus

DOCUMENT_STATUSES = [
    {"code": status.value, "label": STATUS_LABELS_ES[status]}
    for status in DocumentStatus
]

LOAD_TYPES = [
    {"code": "alta_inicial", "label": "Alta inicial"},
    {"code": "contrato", "label": "Contrato"},
    {"code": "mensual", "label": "Mensual"},
    {"code": "bimestral", "label": "Bimestral"},
    {"code": "cuatrimestral", "label": "Cuatrimestral"},
    {"code": "anual", "label": "Anual"},
    {"code": "renovacion", "label": "Renovación"},
    {"code": "evento", "label": "Evento / excepción"},
]

INSTITUTIONS = [
    {"code": institution.value, "label": INSTITUTION_LABELS[institution]}
    for institution in Institution
]

VALIDATION_RULES = [
    {"code": "file_exists", "label": "Archivo existe", "type": "tecnica"},
    {"code": "allowed_file_type", "label": "Tipo de archivo permitido", "type": "tecnica"},
    {"code": "pdf_magic_header", "label": "Estructura PDF básica", "type": "tecnica"},
    {"code": "pdf_encrypted", "label": "PDF bloqueado o protegido", "type": "tecnica"},
    {"code": "pdf_readable_text", "label": "Texto legible en PDF", "type": "tecnica"},
    {"code": "max_file_size", "label": "Tamaño máximo", "type": "tecnica"},
    {"code": "sha256_hash", "label": "Hash de archivo", "type": "tecnica"},
    {"code": "vendor_match", "label": "Proveedor coincide", "type": "fiscal"},
    {"code": "period_match", "label": "Periodo coincide", "type": "temporal"},
    {"code": "requirement_match", "label": "Requisito correcto", "type": "regulatoria"},
    {"code": "duplicate_hash", "label": "Duplicado por hash", "type": "tecnica"},
    {"code": "expired_document", "label": "Documento vencido", "type": "temporal"},
    {"code": "human_review_required", "label": "Requiere revisión humana", "type": "legal"},
    {"code": "document_intelligence", "label": "Señales documentales", "type": "inteligencia"},
]

REQUIREMENT_EXAMPLES = [
    {
        "code": "REQ-ONB-001",
        "name": "Constancia de Situación Fiscal / RFC del proveedor",
        "institution": Institution.SAT.value,
        "load_type": "alta_inicial",
        "risk_level": "alto",
        "human_review_required": True,
    },
    {
        "code": "REQ-ONB-002",
        "name": "Constancia REPSE vigente",
        "institution": Institution.STPS_REPSE.value,
        "load_type": "alta_inicial",
        "risk_level": "critico",
        "human_review_required": True,
    },
    {
        "code": "REQ-CON-001",
        "name": "Contrato firmado",
        "institution": Institution.INTERNO_CLIENTE.value,
        "load_type": "contrato",
        "risk_level": "critico",
        "human_review_required": True,
    },
    {
        "code": "REQ-MON-001",
        "name": "CFDI/XML de factura de servicio",
        "institution": Institution.SAT.value,
        "load_type": "mensual",
        "risk_level": "alto",
        "human_review_required": True,
    },
    {
        "code": "REQ-QUAD-001",
        "name": "ICSOE IMSS",
        "institution": Institution.IMSS.value,
        "load_type": "cuatrimestral",
        "risk_level": "critico",
        "human_review_required": True,
    },
    {
        "code": "REQ-REN-001",
        "name": "Renovación REPSE",
        "institution": Institution.STPS_REPSE.value,
        "load_type": "renovacion",
        "risk_level": "critico",
        "human_review_required": True,
    },
]
