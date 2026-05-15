from __future__ import annotations

import json

import pytest

from app.core.metadata_rules import (
    ANNEX_DOCUMENT_TYPE_COUNT,
    EXPECTED_ANNEX_DOCUMENT_TYPE_CODES,
    EXPECTED_PRINCIPAL_DOCUMENT_TYPE_CODES,
    PRINCIPAL_DOCUMENT_TYPE_COUNT,
    UnknownDocumentTypeError,
    all_metadata_rules,
    metadata_rule_by_code,
    n8n_template_for_document_type,
    validate_metadata_rulebook,
)

EXPECTED_PRINCIPAL_COUNT = 28
EXPECTED_ANNEX_COUNT = 3


@pytest.mark.parametrize(
    "code",
    [
        "escritura_constitutiva",
        "protocolizacion_acta_reforma_estatutos",
        "contrato_prestacion_servicios",
        "prorroga_extension_contrato",
        "addendum",
        "convenio_modificatorio",
        "orden_servicio",
        "identificacion_oficial",
        "constancia_situacion_fiscal",
        "registro_repse",
        "registro_patronal",
        "acuse_sisub",
        "acuse_icsoe",
        "comprobante_pago_bancario_infonavit",
        "cfdi_pago_cuotas_infonavit",
        "cuotas_obrero_patronales_sua_infonavit",
        "resumen_liquidacion_infonavit",
        "comprobante_pago_bancario_imss",
        "cfdi_pago_cuotas_imss",
        "cuotas_obrero_patronales_sua_imss",
        "resumen_liquidacion_imss",
        "declaracion_isr_retencion_sueldos_salarios_sat",
        "declaracion_iva_sat",
        "comprobante_entero_pago_isr_sat",
        "comprobante_entero_pago_iva_sat",
        "comprobantes_nomina_trabajadores_sat",
        "acuse_declaracion_anual_impuestos_sat",
        "reporte_monitoreo_regulatorio",
    ],
)
def test_all_pdf_principal_document_types_are_represented(code: str) -> None:
    assert metadata_rule_by_code(code).hierarchy == "principal"


@pytest.mark.parametrize(
    "code",
    ["anexo_contrato", "complementaria_sisub", "complementaria_icsoe"],
)
def test_explicit_pdf_annex_file_types_are_represented(code: str) -> None:
    assert metadata_rule_by_code(code).hierarchy == "anexo"


def test_rulebook_counts_are_intentional() -> None:
    assert PRINCIPAL_DOCUMENT_TYPE_COUNT == EXPECTED_PRINCIPAL_COUNT
    assert ANNEX_DOCUMENT_TYPE_COUNT == EXPECTED_ANNEX_COUNT
    assert len(EXPECTED_PRINCIPAL_DOCUMENT_TYPE_CODES) == EXPECTED_PRINCIPAL_COUNT
    assert len(EXPECTED_ANNEX_DOCUMENT_TYPE_CODES) == EXPECTED_ANNEX_COUNT
    assert len(all_metadata_rules()) == EXPECTED_PRINCIPAL_COUNT + EXPECTED_ANNEX_COUNT
    assert len(all_metadata_rules(include_annexes=False)) == EXPECTED_PRINCIPAL_COUNT


def test_rule_codes_are_unique_and_catalog_validates() -> None:
    codes = [rule.code for rule in all_metadata_rules()]
    assert len(codes) == len(set(codes))
    assert validate_metadata_rulebook() == []


def test_every_rule_has_core_metadata_controls() -> None:
    for rule in all_metadata_rules():
        assert "client_legal_name" in rule.required_field_keys
        assert "provider_nomenclature" in rule.required_field_keys
        assert "document_name" in rule.required_field_keys
        assert "area_interna" in rule.required_field_keys
        assert "document_category" in rule.required_field_keys
        assert "document_subtype" in rule.required_field_keys
        assert "participants" in rule.required_field_keys
        assert "tags" in rule.required_field_keys
        assert "pdf_file_name" in rule.required_field_keys
        assert "pdf_quality_ocr" in rule.required_field_keys
        assert rule.human_review_required is True
        assert rule.legal_approval_allowed is False


def test_contract_rules_include_lifecycle_fields() -> None:
    for code in [
        "contrato_prestacion_servicios",
        "prorroga_extension_contrato",
        "addendum",
        "convenio_modificatorio",
        "orden_servicio",
    ]:
        rule = metadata_rule_by_code(code)
        assert rule.category == "Contrato"
        assert "start_date" in rule.required_field_keys
        assert "provider_participant" in rule.required_field_keys
        assert "client_participant" in rule.required_field_keys
        assert "expiration_date" in rule.conditional_field_keys
        assert "indefinite_validity" in rule.conditional_field_keys
        assert "automatic_renewal" in rule.conditional_field_keys
        assert "renewal_date" in rule.optional_field_keys


def test_public_deed_rules_include_notary_and_deed_fields() -> None:
    for code in ["escritura_constitutiva", "protocolizacion_acta_reforma_estatutos"]:
        rule = metadata_rule_by_code(code)
        assert rule.category == "Corporativo"
        assert "public_deed_number" in rule.required_field_keys
        assert "deed_date" in rule.required_field_keys
        assert "notary_number" in rule.required_field_keys
        assert "society_participant" in rule.required_field_keys


def test_recurring_compliance_rules_include_period_and_upload_month() -> None:
    recurring_codes = [
        code
        for code in EXPECTED_PRINCIPAL_DOCUMENT_TYPE_CODES
        if metadata_rule_by_code(code).group == "cumplimiento_repse"
    ]
    assert recurring_codes
    for code in recurring_codes:
        rule = metadata_rule_by_code(code)
        assert "upload_form_month" in rule.required_field_keys
        assert "reported_period" in rule.required_field_keys
        assert "document_institution_name" in rule.required_field_keys
        assert rule.category == "Formatos"
        assert rule.subtype == "Comprobante"


def test_specific_institution_mapping_matches_pdf_rulebook() -> None:
    assert metadata_rule_by_code("acuse_sisub").institution == "infonavit"
    assert metadata_rule_by_code("acuse_icsoe").institution == "imss"
    assert metadata_rule_by_code("registro_repse").institution == "stps_repse"
    assert metadata_rule_by_code("constancia_situacion_fiscal").institution == "sat"


def test_annex_relationships_are_explicit() -> None:
    assert metadata_rule_by_code("contrato_prestacion_servicios").annex_document_type_codes == (
        "anexo_contrato",
    )
    assert metadata_rule_by_code("acuse_sisub").annex_document_type_codes == (
        "complementaria_sisub",
    )
    assert metadata_rule_by_code("acuse_icsoe").annex_document_type_codes == (
        "complementaria_icsoe",
    )


def test_n8n_template_is_serializable_and_does_not_enable_external_workflows() -> None:
    template = n8n_template_for_document_type("acuse_sisub")
    json.dumps(template)

    assert template["document_type"]["code"] == "acuse_sisub"
    assert template["controls"]["human_review_required"] is True
    assert template["controls"]["legal_approval_allowed"] is False
    assert template["controls"]["no_ocr_in_this_patch"] is True
    assert template["controls"]["no_ai_in_this_patch"] is True
    assert template["controls"]["no_google_sheets_in_this_patch"] is True
    assert template["controls"]["no_db_migration_in_this_patch"] is True

    required_field_keys = {field["key"] for field in template["fields"]["required"]}
    assert "upload_form_month" in required_field_keys
    assert "reported_period" in required_field_keys


def test_unknown_document_type_fails_loudly() -> None:
    with pytest.raises(UnknownDocumentTypeError):
        metadata_rule_by_code("not_in_pdf")
