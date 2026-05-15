from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from tools.build_n8n_review_payload import (  # noqa: E402
    REVIEW_PAYLOAD_SCHEMA_VERSION,
    build_n8n_review_payload,
    read_json,
    validate_upload_context,
)
from tools.export_n8n_metadata_templates import build_n8n_export_template  # noqa: E402

SISUB_CONTEXT_PATH = BACKEND_ROOT / "fixtures/n8n/sample_upload_context_acuse_sisub.json"
CONTRACT_CONTEXT_PATH = (
    BACKEND_ROOT / "fixtures/n8n/sample_upload_context_contrato_prestacion_servicios.json"
)


def test_fixture_files_are_valid_json_objects() -> None:
    for path in [SISUB_CONTEXT_PATH, CONTRACT_CONTEXT_PATH]:
        payload = read_json(path)
        assert isinstance(payload, dict)
        assert payload["fixture_notice"].startswith("Synthetic fixture")
        assert "document_type_code" in payload


def test_build_review_payload_for_acuse_sisub() -> None:
    context = read_json(SISUB_CONTEXT_PATH)
    payload = build_n8n_review_payload(
        context=context,
        document_type_code="acuse_sisub",
        generated_at="2026-05-13T00:00:00Z",
    )

    assert payload["payload_kind"] == "checkwise_n8n_review_payload_fixture"
    assert payload["schema_version"] == REVIEW_PAYLOAD_SCHEMA_VERSION
    assert payload["document_type"]["code"] == "acuse_sisub"
    assert payload["routing"]["institution"] == "infonavit"
    assert payload["routing"]["legal_approval_allowed"] is False
    assert payload["safety_controls"]["no_ocr_in_this_patch"] is True
    assert payload["safety_controls"]["no_ai_in_this_patch"] is True
    assert payload["safety_controls"]["no_google_sheets_in_this_patch"] is True

    template = build_n8n_export_template("acuse_sisub", generated_at="2026-05-13T00:00:00Z")
    buckets = ["required", "optional", "conditional", "blank"]
    expected_count = sum(len(template["fields"][b]) for b in buckets)
    assert payload["summary"]["review_item_count"] == expected_count
    assert len(payload["review_items"]) == expected_count


def test_context_and_rulebook_defaults_are_prefilled_but_pdf_fields_remain_pending() -> None:
    context = read_json(SISUB_CONTEXT_PATH)
    payload = build_n8n_review_payload(
        context=context,
        document_type_code="acuse_sisub",
        generated_at="2026-05-13T00:00:00Z",
    )
    by_key = {item["field_key"]: item for item in payload["review_items"]}

    assert by_key["client_legal_name"]["raw_value"] == "CLIENTE DEMO, S.A. DE C.V."
    assert by_key["client_legal_name"]["extraction_method"] == "context"
    assert by_key["provider_nomenclature"]["raw_value"] == "SEGURIDAD PRI"
    assert by_key["area_interna"]["raw_value"] == "Compliance"
    assert by_key["document_category"]["raw_value"] == "Formatos"
    assert by_key["document_subtype"]["raw_value"] == "Comprobante"
    assert "Cumplimiento REPSE" in by_key["tags"]["raw_value"]

    assert by_key["main_date"]["raw_value"] is None
    assert by_key["main_date"]["extraction_method"] == "template_only"
    assert by_key["main_date"]["review_status"] == "pending"
    assert by_key["participants"]["raw_value"] is None
    assert by_key["participants"]["review_status"] == "pending"


def test_contract_payload_keeps_contract_lifecycle_fields_pending() -> None:
    context = read_json(CONTRACT_CONTEXT_PATH)
    payload = build_n8n_review_payload(
        context=context,
        document_type_code="contrato_prestacion_servicios",
        generated_at="2026-05-13T00:00:00Z",
    )
    by_key = {item["field_key"]: item for item in payload["review_items"]}

    for key in ["start_date", "expiration_date", "renewal_date", "automatic_renewal"]:
        assert key in by_key
        assert by_key[key]["raw_value"] is None
        assert by_key[key]["review_status"] == "pending"
        assert by_key[key]["extraction_method"] == "template_only"

    assert by_key["document_name"]["raw_value"] == (
        "ARTURO VILLAGRÁN JIMÉNEZ Contrato Prestación Servicios"
    )
    assert by_key["document_name"]["extraction_method"] == "context_proposed_value"


def test_missing_required_context_is_rejected() -> None:
    context = read_json(SISUB_CONTEXT_PATH)
    context.pop("submission_id")
    errors = validate_upload_context(context, ["submission_id", "document_id"])
    assert errors == ["Missing required context key: submission_id"]

    with pytest.raises(ValueError, match="Missing required context key: submission_id"):
        build_n8n_review_payload(context=context, document_type_code="acuse_sisub")


def test_review_payload_is_json_serializable() -> None:
    context = read_json(SISUB_CONTEXT_PATH)
    payload = build_n8n_review_payload(context=context, document_type_code="acuse_sisub")
    encoded = json.dumps(payload, ensure_ascii=False)
    assert "checkwise_n8n_review_payload_fixture" in encoded
    assert "legal_approval_allowed" in encoded


def test_cli_writes_review_payload_file(tmp_path: Path) -> None:
    output = tmp_path / "acuse_sisub_review_payload.json"
    result = subprocess.run(
        [
            sys.executable,
            "tools/build_n8n_review_payload.py",
            "--context",
            str(SISUB_CONTEXT_PATH),
            "--output",
            str(output),
        ],
        cwd=BACKEND_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )

    assert "Wrote" in result.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["document_type"]["code"] == "acuse_sisub"
    assert payload["routing"]["legal_approval_allowed"] is False


def test_cli_stdout_outputs_json() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "tools/build_n8n_review_payload.py",
            "--context",
            str(CONTRACT_CONTEXT_PATH),
            "--stdout",
        ],
        cwd=BACKEND_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(result.stdout)
    assert payload["document_type"]["code"] == "contrato_prestacion_servicios"
    assert payload["safety_controls"]["no_file_content_extraction_in_this_patch"] is True
