"""Static CheckWise metadata rulebook derived from the Legal Shelf PDF.

This module is intentionally pure Python: no database tables, no OCR, no AI,
no Google Sheets client, and no side effects. It gives the backend a typed,
testable catalog of the document/file types and metadata fields described in
``CW & LS- PROPUESTA MD SIMPLIFICADA.docx.pdf``.

The purpose of this first step is to make the PDF operational knowledge stable
before n8n, OCR, AI, Google Sheets export, or reviewer screens consume it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

RULEBOOK_SOURCE = "CW & LS- PROPUESTA MD SIMPLIFICADA.docx.pdf"
RULEBOOK_VERSION = "2026.05.static-v1"
RULEBOOK_TITLE = "Parametrización de Documentos de Cumplimiento REPSE - CheckWise"

DocumentGroup = Literal[
    "expediente_corporativo",
    "documentos_contractuales",
    "registros",
    "cumplimiento_repse",
    "reporte_monitoreo_regulatorio",
]
DocumentCategory = Literal["Corporativo", "Contrato", "Formatos", "Registros", "Otros"]
InstitutionCode = Literal["interno_cliente", "sat", "imss", "infonavit", "stps_repse"]
Frequency = Literal[
    "unica_vez",
    "mensual",
    "bimestral",
    "cuatrimestral",
    "anual",
    "cada_3_anios",
    "reporte_interno",
    "evento",
]
Hierarchy = Literal["principal", "anexo"]
ExtractionMethod = Literal[
    "context",
    "deterministic",
    "pdf_text",
    "ocr",
    "ai_assisted",
    "human_review",
]
RequirementLevel = Literal["required", "optional", "conditional", "blank"]


@dataclass(frozen=True)
class MetadataFieldDefinition:
    """Definition of one metadata field supported by the rulebook."""

    key: str
    label: str
    requirement_level: RequirementLevel
    description: str
    extraction_methods: tuple[ExtractionMethod, ...]
    human_review_required: bool = True


@dataclass(frozen=True)
class DocumentMetadataRule:
    """Metadata rule for one document or explicit annex file type."""

    code: str
    name: str
    group: DocumentGroup
    category: DocumentCategory
    subtype: str
    institution: InstitutionCode
    frequency: Frequency
    hierarchy: Hierarchy
    source_section: str
    naming_pattern: str
    required_field_keys: tuple[str, ...]
    optional_field_keys: tuple[str, ...] = ()
    conditional_field_keys: tuple[str, ...] = ()
    blank_field_keys: tuple[str, ...] = ("related_documents",)
    fixed_tags: tuple[str, ...] = ()
    annex_document_type_codes: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    human_review_required: bool = True
    legal_approval_allowed: bool = False

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation for tests or future APIs."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Field catalog
# ---------------------------------------------------------------------------

FIELD_DEFINITIONS: dict[str, MetadataFieldDefinition] = {
    "client_legal_name": MetadataFieldDefinition(
        key="client_legal_name",
        label="Denominación o Razón Social Completa del Cliente de CheckWise",
        requirement_level="required",
        description="Cliente al que se vincula el proveedor/documento.",
        extraction_methods=("context", "human_review"),
    ),
    "provider_nomenclature": MetadataFieldDefinition(
        key="provider_nomenclature",
        label="Nomenclatura de Proveedor",
        requirement_level="required",
        description="Nombre corto del proveedor según reglas de persona moral/física del PDF.",
        extraction_methods=("context", "deterministic", "human_review"),
    ),
    "document_name": MetadataFieldDefinition(
        key="document_name",
        label="Nombre del Documento",
        requirement_level="required",
        description="Nombre final del documento conforme a la nomenclatura Legal Shelf/CheckWise.",
        extraction_methods=("deterministic", "ai_assisted", "human_review"),
    ),
    "area_interna": MetadataFieldDefinition(
        key="area_interna",
        label="Área Interna",
        requirement_level="required",
        description="Área interna indicada por el PDF; para estos documentos es Compliance.",
        extraction_methods=("deterministic",),
        human_review_required=False,
    ),
    "document_category": MetadataFieldDefinition(
        key="document_category",
        label="Tipo de Documento",
        requirement_level="required",
        description="Categoría documental: Corporativo, Contrato, Formatos, Registros u Otros.",
        extraction_methods=("deterministic", "ai_assisted", "human_review"),
    ),
    "document_subtype": MetadataFieldDefinition(
        key="document_subtype",
        label="Sub-tipo de documento",
        requirement_level="required",
        description="Subtipo documental específico definido por el PDF.",
        extraction_methods=("deterministic", "ai_assisted", "human_review"),
    ),
    "main_date": MetadataFieldDefinition(
        key="main_date",
        label="Fecha principal del documento",
        requirement_level="required",
        description="Fecha que el PDF exige capturar; su significado cambia por tipo documental.",
        extraction_methods=("pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "full_date_label": MetadataFieldDefinition(
        key="full_date_label",
        label="Fecha Completa",
        requirement_level="required",
        description="Fecha en formato DD de mes de AAAA, por ejemplo 07 de marzo de 2024.",
        extraction_methods=("deterministic", "human_review"),
    ),
    "date_8_digits": MetadataFieldDefinition(
        key="date_8_digits",
        label="Fecha a 8 dígitos",
        requirement_level="required",
        description="Fecha en formato DDMMAAAA para nomenclatura o anexos.",
        extraction_methods=("deterministic", "human_review"),
    ),
    "participants": MetadataFieldDefinition(
        key="participants",
        label="Participantes",
        requirement_level="required",
        description="Participantes que deben registrarse según reglas del tipo documental.",
        extraction_methods=("pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "tags": MetadataFieldDefinition(
        key="tags",
        label="Etiquetas",
        requirement_level="required",
        description="Etiquetas obligatorias y etiquetas de expediente/cumplimiento/institución.",
        extraction_methods=("deterministic", "human_review"),
    ),
    "pdf_file_name": MetadataFieldDefinition(
        key="pdf_file_name",
        label="Archivo PDF - nombre",
        requirement_level="required",
        description="El PDF debe nombrarse igual que el documento final.",
        extraction_methods=("deterministic", "human_review"),
    ),
    "pdf_quality_ocr": MetadataFieldDefinition(
        key="pdf_quality_ocr",
        label="Archivo PDF - calidad y OCR",
        requirement_level="required",
        description="El PDF debe tener buena calidad de escaneo y proceso OCR según el PDF.",
        extraction_methods=("deterministic", "pdf_text", "ocr", "human_review"),
    ),
    "description": MetadataFieldDefinition(
        key="description",
        label="Descripción",
        requirement_level="conditional",
        description="Texto fijo, listado de anexos o vacío, dependiendo del tipo documental.",
        extraction_methods=("deterministic", "ai_assisted", "human_review"),
    ),
    "annexes": MetadataFieldDefinition(
        key="annexes",
        label="Anexos",
        requirement_level="conditional",
        description=(
            "Archivos anexos que acompañan a un documento principal cuando el PDF lo indica."
        ),
        extraction_methods=("context", "human_review"),
    ),
    "related_documents": MetadataFieldDefinition(
        key="related_documents",
        label="Documentos relacionados",
        requirement_level="blank",
        description="El PDF normalmente indica N/A; se deja vacío salvo decisión posterior.",
        extraction_methods=("deterministic",),
        human_review_required=False,
    ),
    "public_deed_number": MetadataFieldDefinition(
        key="public_deed_number",
        label="Número de Escritura Pública",
        requirement_level="required",
        description="Número de escritura pública para constitutivas/protocolizaciones.",
        extraction_methods=("pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "deed_date": MetadataFieldDefinition(
        key="deed_date",
        label="Fecha de Escritura",
        requirement_level="required",
        description="Fecha indicada en el proemio de la escritura.",
        extraction_methods=("pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "notary_number": MetadataFieldDefinition(
        key="notary_number",
        label="Número de Notario",
        requirement_level="required",
        description="Número de la Notaría Pública.",
        extraction_methods=("pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "society_participant": MetadataFieldDefinition(
        key="society_participant",
        label="Sociedad del Acta Constitutiva",
        requirement_level="required",
        description="Sociedad que debe registrarse como participante en escrituras públicas.",
        extraction_methods=("pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "start_date": MetadataFieldDefinition(
        key="start_date",
        label="Fecha de Inicio",
        requirement_level="required",
        description="Fecha de firma o inicio para documentos contractuales.",
        extraction_methods=("pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "expiration_date": MetadataFieldDefinition(
        key="expiration_date",
        label="Fecha de Vencimiento",
        requirement_level="conditional",
        description="Fecha de vencimiento cuando exista.",
        extraction_methods=("pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "indefinite_validity": MetadataFieldDefinition(
        key="indefinite_validity",
        label="Vigencia Indefinida",
        requirement_level="conditional",
        description="Casilla cuando el documento no tiene vencimiento.",
        extraction_methods=("pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "renewal_date": MetadataFieldDefinition(
        key="renewal_date",
        label="Fecha de Renovación",
        requirement_level="optional",
        description="Fecha de renovación si el documento la expone.",
        extraction_methods=("pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "automatic_renewal": MetadataFieldDefinition(
        key="automatic_renewal",
        label="Renovación Automática",
        requirement_level="conditional",
        description="Casilla cuando el documento indique renovación automática.",
        extraction_methods=("pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "provider_participant": MetadataFieldDefinition(
        key="provider_participant",
        label="Proveedor participante",
        requirement_level="required",
        description="Denominación, razón social o nombre completo del proveedor y rol.",
        extraction_methods=("pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "client_participant": MetadataFieldDefinition(
        key="client_participant",
        label="Cliente participante",
        requirement_level="required",
        description="Denominación, razón social o nombre completo del cliente y rol.",
        extraction_methods=("context", "pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "birth_date": MetadataFieldDefinition(
        key="birth_date",
        label="Fecha de Nacimiento",
        requirement_level="required",
        description="Fecha de nacimiento en identificación oficial.",
        extraction_methods=("pdf_text", "ocr", "human_review"),
    ),
    "official_id_type": MetadataFieldDefinition(
        key="official_id_type",
        label="Tipo de Identificación Oficial",
        requirement_level="required",
        description="Tipo de identificación para incluirlo como etiqueta.",
        extraction_methods=("pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "id_owner_name": MetadataFieldDefinition(
        key="id_owner_name",
        label="Propietario de Identificación Oficial",
        requirement_level="required",
        description="Nombre completo del propietario de la identificación.",
        extraction_methods=("pdf_text", "ocr", "human_review"),
    ),
    "issue_date": MetadataFieldDefinition(
        key="issue_date",
        label="Fecha de Emisión",
        requirement_level="required",
        description="Fecha de emisión del documento.",
        extraction_methods=("pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "expedition_date": MetadataFieldDefinition(
        key="expedition_date",
        label="Fecha de Expedición",
        requirement_level="required",
        description="Fecha de expedición, especialmente para Registro Patronal/TIP.",
        extraction_methods=("pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "taxpayer_name": MetadataFieldDefinition(
        key="taxpayer_name",
        label="Nombre del contribuyente",
        requirement_level="required",
        description="Contribuyente de la Constancia de Situación Fiscal u otro documento fiscal.",
        extraction_methods=("pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "registration_state": MetadataFieldDefinition(
        key="registration_state",
        label="Estado del Registro",
        requirement_level="required",
        description="Original, Renovación o Actualización cuando aplique.",
        extraction_methods=("pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "is_current_for_report_year": MetadataFieldDefinition(
        key="is_current_for_report_year",
        label="Vigente respecto al año de reporte",
        requirement_level="conditional",
        description="Determina si el registro es principal o anexo del vigente.",
        extraction_methods=("context", "pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "prior_registration_annexes": MetadataFieldDefinition(
        key="prior_registration_annexes",
        label="Registros anteriores como anexos",
        requirement_level="conditional",
        description="Registros REPSE o patronales cronológicamente anteriores al principal.",
        extraction_methods=("context", "human_review"),
    ),
    "upload_form_month": MetadataFieldDefinition(
        key="upload_form_month",
        label="Mes de carga en Formulario CheckWise",
        requirement_level="required",
        description="Mes agregado al nombre de documentos de cumplimiento REPSE.",
        extraction_methods=("context", "deterministic"),
        human_review_required=False,
    ),
    "reported_period": MetadataFieldDefinition(
        key="reported_period",
        label="Periodo que reporta",
        requirement_level="required",
        description="Mes, bimestre, cuatrimestre o año al que corresponde el documento.",
        extraction_methods=("context", "pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "document_institution_name": MetadataFieldDefinition(
        key="document_institution_name",
        label="Institución mencionada en el documento",
        requirement_level="required",
        description="SAT, IMSS, INFONAVIT u otra institución identificada en el documento.",
        extraction_methods=("pdf_text", "ocr", "ai_assisted", "human_review"),
    ),
    "report_period": MetadataFieldDefinition(
        key="report_period",
        label="Periodo del Reporte",
        requirement_level="required",
        description="Periodo acumulado del Reporte de Monitoreo Regulatorio.",
        extraction_methods=("context", "pdf_text", "ocr", "human_review"),
    ),
    "report_upload_date": MetadataFieldDefinition(
        key="report_upload_date",
        label="Fecha de carga del Reporte",
        requirement_level="required",
        description="Fecha en que se subió el Reporte de Monitoreo Regulatorio.",
        extraction_methods=("context", "deterministic", "human_review"),
    ),
}

BASE_REQUIRED_FIELDS: tuple[str, ...] = (
    "client_legal_name",
    "provider_nomenclature",
    "document_name",
    "area_interna",
    "document_category",
    "document_subtype",
    "main_date",
    "full_date_label",
    "date_8_digits",
    "participants",
    "tags",
    "pdf_file_name",
    "pdf_quality_ocr",
)

CONTRACT_REQUIRED_FIELDS: tuple[str, ...] = BASE_REQUIRED_FIELDS + (
    "start_date",
    "provider_participant",
    "client_participant",
)
CONTRACT_CONDITIONAL_FIELDS: tuple[str, ...] = (
    "expiration_date",
    "indefinite_validity",
    "automatic_renewal",
    "annexes",
    "description",
)
CONTRACT_OPTIONAL_FIELDS: tuple[str, ...] = ("renewal_date",)

COMPLIANCE_REQUIRED_FIELDS: tuple[str, ...] = BASE_REQUIRED_FIELDS + (
    "issue_date",
    "upload_form_month",
    "reported_period",
    "document_institution_name",
)

EXPEDIENTE_TAG = "Expediente Corporativo REPSE"
CUMPLIMIENTO_TAG = "Cumplimiento REPSE"
SAT_TAG = "Servicio de Administración Tributaria SAT"
IMSS_TAG = "Instituto Mexicano del Seguro Social IMSS"
INFONAVIT_TAG = "Instituto del Fondo Nacional de la Vivienda para los Trabajadores INFONAVIT"
REPSE_TAG = "Registro de Prestadoras de Servicios Especializados u Obras Especializadas"
SUA_TAG = "SUA"
REPORTE_TAG = "Reporte de Documentos de Proveedor REPSE"


def _rule(
    *,
    code: str,
    name: str,
    group: DocumentGroup,
    category: DocumentCategory,
    subtype: str,
    institution: InstitutionCode,
    frequency: Frequency,
    hierarchy: Hierarchy = "principal",
    source_section: str,
    naming_pattern: str,
    required_field_keys: tuple[str, ...] = BASE_REQUIRED_FIELDS,
    optional_field_keys: tuple[str, ...] = (),
    conditional_field_keys: tuple[str, ...] = (),
    blank_field_keys: tuple[str, ...] = ("related_documents",),
    fixed_tags: tuple[str, ...] = (),
    annex_document_type_codes: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
) -> DocumentMetadataRule:
    return DocumentMetadataRule(
        code=code,
        name=name,
        group=group,
        category=category,
        subtype=subtype,
        institution=institution,
        frequency=frequency,
        hierarchy=hierarchy,
        source_section=source_section,
        naming_pattern=naming_pattern,
        required_field_keys=required_field_keys,
        optional_field_keys=optional_field_keys,
        conditional_field_keys=conditional_field_keys,
        blank_field_keys=blank_field_keys,
        fixed_tags=fixed_tags,
        annex_document_type_codes=annex_document_type_codes,
        notes=notes,
    )


_DOCUMENT_RULES: tuple[DocumentMetadataRule, ...] = (
    _rule(
        code="escritura_constitutiva",
        name="Constitutiva",
        group="expediente_corporativo",
        category="Corporativo",
        subtype="Escritura Pública y Constitutiva",
        institution="interno_cliente",
        frequency="unica_vez",
        source_section="I.I. Constitutiva",
        naming_pattern="{provider_nomenclature} {public_deed_number}",
        required_field_keys=BASE_REQUIRED_FIELDS
        + ("public_deed_number", "deed_date", "notary_number", "society_participant"),
        fixed_tags=(EXPEDIENTE_TAG,),
        notes=("No registrar notarios, delegados, asistentes, escrutadores ni comparecientes.",),
    ),
    _rule(
        code="protocolizacion_acta_reforma_estatutos",
        name="Protocolización de Acta / Reforma de Estatutos u Objeto Social",
        group="expediente_corporativo",
        category="Corporativo",
        subtype="Escritura Pública",
        institution="interno_cliente",
        frequency="unica_vez",
        source_section="I.II. Protocolización de Acta",
        naming_pattern="{provider_nomenclature} {public_deed_number}",
        required_field_keys=BASE_REQUIRED_FIELDS
        + ("public_deed_number", "deed_date", "notary_number", "society_participant"),
        fixed_tags=(EXPEDIENTE_TAG,),
        notes=("No registrar notarios, delegados, asistentes, escrutadores ni comparecientes.",),
    ),
    _rule(
        code="contrato_prestacion_servicios",
        name="Contrato de Prestación de Servicios",
        group="documentos_contractuales",
        category="Contrato",
        subtype="Prestación de Servicios",
        institution="interno_cliente",
        frequency="unica_vez",
        source_section="II.I. Contrato de Prestación de Servicios",
        naming_pattern="{provider_nomenclature} Contrato Prestación Servicios",
        required_field_keys=CONTRACT_REQUIRED_FIELDS,
        optional_field_keys=CONTRACT_OPTIONAL_FIELDS,
        conditional_field_keys=CONTRACT_CONDITIONAL_FIELDS,
        fixed_tags=(EXPEDIENTE_TAG,),
        annex_document_type_codes=("anexo_contrato",),
    ),
    _rule(
        code="prorroga_extension_contrato",
        name="Prórroga / Extensión del Contrato",
        group="documentos_contractuales",
        category="Contrato",
        subtype="Otros",
        institution="interno_cliente",
        frequency="evento",
        source_section="II.II. Prórroga / Extensión del Contrato",
        naming_pattern="{provider_nomenclature} Prórroga / Extensión",
        required_field_keys=CONTRACT_REQUIRED_FIELDS,
        optional_field_keys=CONTRACT_OPTIONAL_FIELDS,
        conditional_field_keys=CONTRACT_CONDITIONAL_FIELDS,
        fixed_tags=(EXPEDIENTE_TAG,),
    ),
    _rule(
        code="addendum",
        name="Addendum",
        group="documentos_contractuales",
        category="Contrato",
        subtype="Otros",
        institution="interno_cliente",
        frequency="evento",
        source_section="II.III. Addendum",
        naming_pattern="{provider_nomenclature} Addendum",
        required_field_keys=CONTRACT_REQUIRED_FIELDS,
        optional_field_keys=CONTRACT_OPTIONAL_FIELDS,
        conditional_field_keys=CONTRACT_CONDITIONAL_FIELDS,
        fixed_tags=(EXPEDIENTE_TAG,),
    ),
    _rule(
        code="convenio_modificatorio",
        name="Convenio Modificatorio",
        group="documentos_contractuales",
        category="Contrato",
        subtype="Modificatorio",
        institution="interno_cliente",
        frequency="evento",
        source_section="II.IV. Convenio Modificatorio",
        naming_pattern="{provider_nomenclature} Convenio Modificatorio",
        required_field_keys=CONTRACT_REQUIRED_FIELDS,
        optional_field_keys=CONTRACT_OPTIONAL_FIELDS,
        conditional_field_keys=CONTRACT_CONDITIONAL_FIELDS,
        fixed_tags=(EXPEDIENTE_TAG,),
        notes=("Si se incluye referencia de secuencia, preservarla en el nombre.",),
    ),
    _rule(
        code="orden_servicio",
        name="Órden de Servicio",
        group="documentos_contractuales",
        category="Contrato",
        subtype="Órden de Servicios",
        institution="interno_cliente",
        frequency="evento",
        source_section="II.V. Órdenes de Servicios",
        naming_pattern="{provider_nomenclature} Órden Servicio",
        required_field_keys=CONTRACT_REQUIRED_FIELDS,
        optional_field_keys=CONTRACT_OPTIONAL_FIELDS,
        conditional_field_keys=CONTRACT_CONDITIONAL_FIELDS,
        fixed_tags=(EXPEDIENTE_TAG,),
    ),
    _rule(
        code="anexo_contrato",
        name="Anexo de Contrato / Convenio",
        group="documentos_contractuales",
        category="Contrato",
        subtype="Anexo",
        institution="interno_cliente",
        frequency="evento",
        hierarchy="anexo",
        source_section="II.I. Anexos / 2.2 Nomenclatura por Tipo de Documento",
        naming_pattern="Anexo {annex_label} del {principal_document_name} {date_8_digits}",
        required_field_keys=BASE_REQUIRED_FIELDS + ("annexes",),
        fixed_tags=(EXPEDIENTE_TAG,),
        notes=("Se carga como archivo anexo del documento contractual principal.",),
    ),
    _rule(
        code="identificacion_oficial",
        name="Identificación Oficial",
        group="expediente_corporativo",
        category="Corporativo",
        subtype="Otros",
        institution="interno_cliente",
        frequency="unica_vez",
        source_section="III.I. Identificación Oficial",
        naming_pattern="{provider_nomenclature} Identificación Oficial",
        required_field_keys=BASE_REQUIRED_FIELDS
        + ("birth_date", "official_id_type", "id_owner_name"),
        fixed_tags=(EXPEDIENTE_TAG,),
    ),
    _rule(
        code="constancia_situacion_fiscal",
        name="Constancia de Situación Fiscal",
        group="expediente_corporativo",
        category="Formatos",
        subtype="Otros",
        institution="sat",
        frequency="unica_vez",
        source_section="III.II. Constancia de Situación Fiscal",
        naming_pattern="{provider_nomenclature} CSF",
        required_field_keys=BASE_REQUIRED_FIELDS + ("issue_date", "taxpayer_name"),
        fixed_tags=(EXPEDIENTE_TAG, SAT_TAG),
        notes=("Descripción fija: Constancia de Situación Fiscal.",),
    ),
    _rule(
        code="registro_repse",
        name="Registro REPSE",
        group="registros",
        category="Registros",
        subtype="Registro REPSE",
        institution="stps_repse",
        frequency="cada_3_anios",
        source_section="IV.I. Registro REPSE",
        naming_pattern="{provider_nomenclature} {registration_state} REPSE",
        required_field_keys=BASE_REQUIRED_FIELDS + ("issue_date", "registration_state"),
        conditional_field_keys=(
            "is_current_for_report_year",
            "prior_registration_annexes",
            "annexes",
        ),
        fixed_tags=(EXPEDIENTE_TAG, REPSE_TAG),
    ),
    _rule(
        code="registro_patronal",
        name="Registro Patronal",
        group="registros",
        category="Registros",
        subtype="Otros",
        institution="imss",
        frequency="unica_vez",
        source_section="IV.II. Registro Patronal",
        naming_pattern="{provider_nomenclature} Registro Patronal {registration_state}",
        required_field_keys=BASE_REQUIRED_FIELDS + ("expedition_date", "registration_state"),
        conditional_field_keys=(
            "is_current_for_report_year",
            "prior_registration_annexes",
            "annexes",
        ),
        fixed_tags=(EXPEDIENTE_TAG, IMSS_TAG),
        notes=("Descripción fija: Tarjeta de Identificación Patronal (TIP).",),
    ),
    _rule(
        code="acuse_sisub",
        name="Acuse SISUB",
        group="cumplimiento_repse",
        category="Formatos",
        subtype="Comprobante",
        institution="infonavit",
        frequency="cuatrimestral",
        source_section="V.I. Acuse SISUB",
        naming_pattern="{provider_nomenclature} Acuse SISUB {upload_form_month}",
        required_field_keys=COMPLIANCE_REQUIRED_FIELDS,
        conditional_field_keys=("annexes", "description"),
        fixed_tags=(CUMPLIMIENTO_TAG, INFONAVIT_TAG),
        annex_document_type_codes=("complementaria_sisub",),
        notes=(
            "El PDF llama la periodicidad trimestral, "
            "pero el periodo descrito es cuatrimestral."
        ),
    ),
    _rule(
        code="complementaria_sisub",
        name="Complementaria SISUB",
        group="cumplimiento_repse",
        category="Formatos",
        subtype="Comprobante",
        institution="infonavit",
        frequency="cuatrimestral",
        hierarchy="anexo",
        source_section="V.I. Acuse SISUB / Complementaria",
        naming_pattern="{provider_nomenclature} Complementaria SISUB {date_8_digits}",
        required_field_keys=COMPLIANCE_REQUIRED_FIELDS,
        fixed_tags=(CUMPLIMIENTO_TAG, INFONAVIT_TAG),
    ),
    _rule(
        code="acuse_icsoe",
        name="Acuse ICSOE",
        group="cumplimiento_repse",
        category="Formatos",
        subtype="Comprobante",
        institution="imss",
        frequency="cuatrimestral",
        source_section="V.II. Acuse ICSOE",
        naming_pattern="{provider_nomenclature} Acuse ICSOE {upload_form_month}",
        required_field_keys=COMPLIANCE_REQUIRED_FIELDS,
        conditional_field_keys=("annexes", "description"),
        fixed_tags=(CUMPLIMIENTO_TAG, IMSS_TAG),
        annex_document_type_codes=("complementaria_icsoe",),
        notes=(
            "El PDF llama la periodicidad trimestral, "
            "pero el periodo descrito es cuatrimestral."
        ),
    ),
    _rule(
        code="complementaria_icsoe",
        name="Complementaria ICSOE",
        group="cumplimiento_repse",
        category="Formatos",
        subtype="Comprobante",
        institution="imss",
        frequency="cuatrimestral",
        hierarchy="anexo",
        source_section="V.II. Acuse ICSOE / Complementaria",
        naming_pattern="{provider_nomenclature} Complementaria ICSOE {date_8_digits}",
        required_field_keys=COMPLIANCE_REQUIRED_FIELDS,
        fixed_tags=(CUMPLIMIENTO_TAG, IMSS_TAG),
    ),
)


def _compliance_rule(
    *,
    code: str,
    name: str,
    institution: InstitutionCode,
    frequency: Frequency,
    source_section: str,
    naming_label: str,
    fixed_tags: tuple[str, ...],
    notes: tuple[str, ...] = (),
) -> DocumentMetadataRule:
    return _rule(
        code=code,
        name=name,
        group="cumplimiento_repse",
        category="Formatos",
        subtype="Comprobante",
        institution=institution,
        frequency=frequency,
        source_section=source_section,
        naming_pattern=f"{{provider_nomenclature}} {naming_label} {{upload_form_month}}",
        required_field_keys=COMPLIANCE_REQUIRED_FIELDS,
        fixed_tags=(CUMPLIMIENTO_TAG,) + fixed_tags,
        notes=notes,
    )


_COMPLIANCE_RULES: tuple[DocumentMetadataRule, ...] = (
    _compliance_rule(
        code="comprobante_pago_bancario_infonavit",
        name="Comprobante de Pago Bancario - INFONAVIT",
        institution="infonavit",
        frequency="bimestral",
        source_section="V.III. Comprobante de Pago Bancario - INFONAVIT",
        naming_label="Comp. de Pago Bancario",
        fixed_tags=(INFONAVIT_TAG,),
    ),
    _compliance_rule(
        code="cfdi_pago_cuotas_infonavit",
        name="CFDI de Pago de Cuotas - INFONAVIT",
        institution="infonavit",
        frequency="bimestral",
        source_section="V.IV. CFDI de Pago de Cuotas - INFONAVIT",
        naming_label="CFDI de Pago de Cuotas",
        fixed_tags=(INFONAVIT_TAG,),
        notes=("El PDF contiene la frase ambigua 'Fecha de Procel documento'.",),
    ),
    _compliance_rule(
        code="cuotas_obrero_patronales_sua_infonavit",
        name="Cuotas Obrero Patronales (SUA) - INFONAVIT",
        institution="infonavit",
        frequency="bimestral",
        source_section="V.V. Cuotas Obrero Patronales (SUA) - INFONAVIT",
        naming_label="Cuotas Obrero Patronales",
        fixed_tags=(SUA_TAG, INFONAVIT_TAG),
    ),
    _compliance_rule(
        code="resumen_liquidacion_infonavit",
        name="Resumen de Liquidación - INFONAVIT",
        institution="infonavit",
        frequency="bimestral",
        source_section="V.VI. Resumen de Liquidación - INFONAVIT",
        naming_label="Resumen Liquidación",
        fixed_tags=(INFONAVIT_TAG,),
        notes=("El ejemplo del PDF parece reutilizar 'Cuotas Obrero Patronales'; validar naming.",),
    ),
    _compliance_rule(
        code="comprobante_pago_bancario_imss",
        name="Comprobante de Pago Bancario - IMSS",
        institution="imss",
        frequency="mensual",
        source_section="V.VII. Comprobante de Pago Bancario - IMSS",
        naming_label="Comp. de Pago Bancario",
        fixed_tags=(IMSS_TAG,),
        notes=(
            "La tabla de periodicidad menciona reporte de bimestre inmediato anterior; "
            "confirmar."
        ),
    ),
    _compliance_rule(
        code="cfdi_pago_cuotas_imss",
        name="CFDI de Pago de Cuotas - IMSS",
        institution="imss",
        frequency="mensual",
        source_section="V.VIII. CFDI de Pago de Cuotas - IMSS",
        naming_label="CFDI de Pago de Cuotas",
        fixed_tags=(IMSS_TAG,),
        notes=("El PDF contiene la frase ambigua 'Fecha de Procel documento'.",),
    ),
    _compliance_rule(
        code="cuotas_obrero_patronales_sua_imss",
        name="Cuotas Obrero Patronales (SUA) - IMSS",
        institution="imss",
        frequency="mensual",
        source_section="V.IX. Cuotas Obrero Patronales (SUA) - IMSS",
        naming_label="Cuotas Obrero Patronales",
        fixed_tags=(SUA_TAG, IMSS_TAG),
    ),
    _compliance_rule(
        code="resumen_liquidacion_imss",
        name="Resumen de Liquidación - IMSS",
        institution="imss",
        frequency="mensual",
        source_section="V.X. Resumen de Liquidación - IMSS",
        naming_label="Resumen Liquidación",
        fixed_tags=(IMSS_TAG,),
        notes=("El ejemplo del PDF parece reutilizar 'Cuotas Obrero Patronales'; validar naming.",),
    ),
    _compliance_rule(
        code="declaracion_isr_retencion_sueldos_salarios_sat",
        name="Declaración ISR Por Retención de Sueldos y Salarios - SAT",
        institution="sat",
        frequency="mensual",
        source_section="V.XI. Declaración ISR Por Retención de Sueldos y Salarios - SAT",
        naming_label="Declaración ISR por Retención de Sueldos y Salarios",
        fixed_tags=(SAT_TAG,),
    ),
    _compliance_rule(
        code="declaracion_iva_sat",
        name="Declaración IVA - SAT",
        institution="sat",
        frequency="mensual",
        source_section="V.XII. Declaración IVA - SAT",
        naming_label="Declaración IVA",
        fixed_tags=(SAT_TAG,),
    ),
    _compliance_rule(
        code="comprobante_entero_pago_isr_sat",
        name="Comprobante Entero de Pago ISR - SAT",
        institution="sat",
        frequency="mensual",
        source_section="V.XIII. Comprobante Entero de Pago ISR - SAT",
        naming_label="Comp. Entero de Pago ISR",
        fixed_tags=(SAT_TAG,),
    ),
    _compliance_rule(
        code="comprobante_entero_pago_iva_sat",
        name="Comprobante Entero de Pago IVA - SAT",
        institution="sat",
        frequency="mensual",
        source_section="V.XIV. Comprobante Entero de Pago IVA - SAT",
        naming_label="Comp. Entero Pago IVA",
        fixed_tags=(SAT_TAG,),
    ),
    _compliance_rule(
        code="comprobantes_nomina_trabajadores_sat",
        name="Comprobantes de Nómina de Trabajadores - SAT",
        institution="sat",
        frequency="mensual",
        source_section="V.XV. Comprobantes de Nómina de Trabajadores - SAT",
        naming_label="Comps. Nómina Trabajadores",
        fixed_tags=(SAT_TAG,),
    ),
    _compliance_rule(
        code="acuse_declaracion_anual_impuestos_sat",
        name="Acuse Declaración Anual de Impuestos - SAT",
        institution="sat",
        frequency="anual",
        source_section="V.XVI. Acuse Declaración Anual de Impuestos - SAT",
        naming_label="Acuse Declaración Anual de Impuestos",
        fixed_tags=(SAT_TAG,),
    ),
    _rule(
        code="reporte_monitoreo_regulatorio",
        name="Reporte de Monitoreo Regulatorio",
        group="reporte_monitoreo_regulatorio",
        category="Otros",
        subtype="Reporte",
        institution="interno_cliente",
        frequency="reporte_interno",
        source_section="VI. Reportes de Monitoreo Regulatorio",
        naming_pattern="{provider_nomenclature} Reporte de Monitoreo Regulatorio {report_period}",
        required_field_keys=BASE_REQUIRED_FIELDS + ("report_period", "report_upload_date"),
        fixed_tags=(REPORTE_TAG, CUMPLIMIENTO_TAG),
        notes=(
            "Se genera internamente por proveedor al finalizar la parametrización.",
            "Debe parametrizarse dentro de los 3 días hábiles posteriores.",
        ),
    ),
)

ALL_METADATA_RULES: tuple[DocumentMetadataRule, ...] = _DOCUMENT_RULES + _COMPLIANCE_RULES

PRINCIPAL_DOCUMENT_TYPE_COUNT = sum(
    1 for rule in ALL_METADATA_RULES if rule.hierarchy == "principal"
)
ANNEX_DOCUMENT_TYPE_COUNT = sum(1 for rule in ALL_METADATA_RULES if rule.hierarchy == "anexo")

EXPECTED_PRINCIPAL_DOCUMENT_TYPE_CODES: tuple[str, ...] = tuple(
    rule.code for rule in ALL_METADATA_RULES if rule.hierarchy == "principal"
)
EXPECTED_ANNEX_DOCUMENT_TYPE_CODES: tuple[str, ...] = tuple(
    rule.code for rule in ALL_METADATA_RULES if rule.hierarchy == "anexo"
)


class UnknownDocumentTypeError(KeyError):
    """Raised when a requested metadata rule code does not exist."""


def all_metadata_rules(*, include_annexes: bool = True) -> tuple[DocumentMetadataRule, ...]:
    """Return all metadata rules.

    Args:
        include_annexes: When false, returns only principal document types.
    """
    if include_annexes:
        return ALL_METADATA_RULES
    return tuple(rule for rule in ALL_METADATA_RULES if rule.hierarchy == "principal")


def metadata_rule_by_code(code: str) -> DocumentMetadataRule:
    """Return one metadata rule by stable rulebook code."""
    normalized = code.strip().lower()
    for rule in ALL_METADATA_RULES:
        if rule.code == normalized:
            return rule
    raise UnknownDocumentTypeError(f"Unknown metadata document type: {code}")


def field_definition(field_key: str) -> MetadataFieldDefinition:
    """Return one field definition by key."""
    try:
        return FIELD_DEFINITIONS[field_key]
    except KeyError as exc:
        raise KeyError(f"Unknown metadata field: {field_key}") from exc


def metadata_rules_as_dicts(*, include_annexes: bool = True) -> list[dict]:
    """Return metadata rules as JSON-serializable dictionaries."""
    return [rule.to_dict() for rule in all_metadata_rules(include_annexes=include_annexes)]


def n8n_template_for_document_type(code: str) -> dict:
    """Return a deterministic JSON template suitable for a future n8n node.

    This does not perform extraction. It only says what fields are expected for
    a document type and which review controls apply.
    """
    rule = metadata_rule_by_code(code)
    required = [field_definition(key) for key in rule.required_field_keys]
    optional = [field_definition(key) for key in rule.optional_field_keys]
    conditional = [field_definition(key) for key in rule.conditional_field_keys]
    blank = [field_definition(key) for key in rule.blank_field_keys]
    return {
        "rulebook": {
            "source": RULEBOOK_SOURCE,
            "version": RULEBOOK_VERSION,
            "title": RULEBOOK_TITLE,
        },
        "document_type": rule.to_dict(),
        "fields": {
            "required": [asdict(item) for item in required],
            "optional": [asdict(item) for item in optional],
            "conditional": [asdict(item) for item in conditional],
            "blank": [asdict(item) for item in blank],
        },
        "controls": {
            "human_review_required": rule.human_review_required,
            "legal_approval_allowed": rule.legal_approval_allowed,
            "no_ocr_in_this_patch": True,
            "no_ai_in_this_patch": True,
            "no_google_sheets_in_this_patch": True,
            "no_db_migration_in_this_patch": True,
        },
    }


def validate_metadata_rulebook() -> list[str]:
    """Return catalog problems. Empty list means structurally valid."""
    problems: list[str] = []
    codes = [rule.code for rule in ALL_METADATA_RULES]
    if len(codes) != len(set(codes)):
        problems.append("Duplicate metadata rule codes detected.")
    for rule in ALL_METADATA_RULES:
        all_field_keys = (
            rule.required_field_keys
            + rule.optional_field_keys
            + rule.conditional_field_keys
            + rule.blank_field_keys
        )
        for key in all_field_keys:
            if key not in FIELD_DEFINITIONS:
                problems.append(f"Rule {rule.code} references unknown field {key}.")
        if rule.legal_approval_allowed:
            problems.append(f"Rule {rule.code} incorrectly allows legal approval.")
    return problems


__all__ = [
    "ALL_METADATA_RULES",
    "ANNEX_DOCUMENT_TYPE_COUNT",
    "BASE_REQUIRED_FIELDS",
    "EXPECTED_ANNEX_DOCUMENT_TYPE_CODES",
    "EXPECTED_PRINCIPAL_DOCUMENT_TYPE_CODES",
    "FIELD_DEFINITIONS",
    "PRINCIPAL_DOCUMENT_TYPE_COUNT",
    "RULEBOOK_SOURCE",
    "RULEBOOK_TITLE",
    "RULEBOOK_VERSION",
    "DocumentMetadataRule",
    "MetadataFieldDefinition",
    "UnknownDocumentTypeError",
    "all_metadata_rules",
    "field_definition",
    "metadata_rule_by_code",
    "metadata_rules_as_dicts",
    "n8n_template_for_document_type",
    "validate_metadata_rulebook",
]
