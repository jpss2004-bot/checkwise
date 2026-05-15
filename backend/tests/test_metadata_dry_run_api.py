from __future__ import annotations

import json
from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.core.metadata_rules import RULEBOOK_VERSION
from app.main import app

client = TestClient(app)


def _pdf_bytes() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(output)
    return output.getvalue()


def test_metadata_dry_run_pdf_endpoint_uses_real_rulebook() -> None:
    response = client.post(
        "/api/v1/metadata-dry-run/pdf",
        data={
            "document_type_code": "acuse_sisub",
            "context_json": json.dumps(
                {
                    "client_legal_name": "CLIENTE DEMO, S.A. DE C.V.",
                    "provider_nomenclature": "SEGURIDAD PRI",
                    "upload_form_month": "Mayo",
                    "reported_period": "Cuatrimestre inmediato anterior",
                    "proposed_document_name": "SEGURIDAD PRI Acuse SISUB Mayo",
                }
            ),
        },
        files={"file": ("acuse_sisub.pdf", _pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["payload_type"] == "checkwise_local_pdf_metadata_dry_run"
    assert payload["metadata_rules_version"] == RULEBOOK_VERSION
    assert payload["document_type_code"] == "acuse_sisub"
    assert payload["validation_result"]["status"] == "passed"
    assert payload["deterministic_file_metadata"]["original_filename"] == "acuse_sisub.pdf"
    assert payload["deterministic_file_metadata"]["pdf_header_valid"] is True
    assert payload["deterministic_file_metadata"]["page_count"] == 1
    assert payload["safety"] == {
        "legal_approval_allowed": False,
        "ocr_used": False,
        "ai_used": False,
        "google_sheets_used": False,
        "external_services_used": False,
        "db_used": False,
        "production_upload_flow_used": False,
        "human_review_required": True,
    }

    by_key = {item["field_key"]: item for item in payload["review_items"]}
    assert by_key["document_name"]["raw_value"] == "SEGURIDAD PRI Acuse SISUB Mayo"
    assert by_key["document_category"]["raw_value"] == "Formatos"
    assert by_key["upload_form_month"]["raw_value"] == "Mayo"
    assert by_key["participants"]["status"] == "pending"


def test_metadata_dry_run_pdf_endpoint_can_include_intelligence_package() -> None:
    response = client.post(
        "/api/v1/metadata-dry-run/pdf",
        data={
            "document_type_code": "acuse_icsoe",
            "include_intelligence": "true",
            "context_json": json.dumps(
                {
                    "client_legal_name": "CLIENTE DEMO, S.A. DE C.V.",
                    "provider_nomenclature": "HUMAN MED",
                    "upload_form_month": "Septiembre",
                }
            ),
        },
        files={"file": ("acuse_icsoe.pdf", _pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_type_code"] == "acuse_icsoe"
    assert payload["safety"]["ocr_used"] is False
    assert payload["safety"]["ai_used"] is False
    assert payload["safety"]["google_sheets_used"] is False
    intelligence = payload["intelligence"]
    assert intelligence["pdf_text_extraction"]["pdf_text_extraction_used"] is True
    assert intelligence["ocr"]["status"] == "not_configured"
    assert intelligence["ai_extraction_request"]["status"] == "ready_for_n8n_ai_node"
    assert intelligence["google_sheets"]["row"]["document_type_code"] == "acuse_icsoe"


def test_metadata_dry_run_pdf_endpoint_rejects_bad_context_json() -> None:
    response = client.post(
        "/api/v1/metadata-dry-run/pdf",
        data={"document_type_code": "acuse_sisub", "context_json": "not-json"},
        files={"file": ("acuse_sisub.pdf", _pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 422
    assert "context_json must be valid JSON" in response.json()["detail"]


def test_metadata_dry_run_pdf_endpoint_rejects_unknown_document_type() -> None:
    response = client.post(
        "/api/v1/metadata-dry-run/pdf",
        data={"document_type_code": "does_not_exist"},
        files={"file": ("acuse_sisub.pdf", _pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 422
    assert "does_not_exist" in response.json()["detail"]
