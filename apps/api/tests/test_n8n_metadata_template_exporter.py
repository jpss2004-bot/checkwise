from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "tools" / "export_n8n_metadata_templates.py"

spec = importlib.util.spec_from_file_location("export_n8n_metadata_templates", SCRIPT_PATH)
exporter = importlib.util.module_from_spec(spec)
assert spec is not None
assert spec.loader is not None
spec.loader.exec_module(exporter)


def test_build_single_n8n_template_for_acuse_sisub() -> None:
    payload = exporter.build_n8n_export_template(
        "acuse_sisub",
        generated_at="2026-05-13T00:00:00Z",
    )

    assert payload["template_kind"] == "checkwise_n8n_metadata_template"
    assert payload["schema_version"] == exporter.TEMPLATE_SCHEMA_VERSION
    assert payload["document_type"]["code"] == "acuse_sisub"
    assert payload["document_type"]["institution"] == "infonavit"
    assert payload["n8n"]["review_controls"]["final_approval_must_be_human"] is True
    assert payload["n8n"]["review_controls"]["legal_approval_allowed"] is False
    assert payload["safety_controls"]["no_ocr_in_this_patch"] is True
    assert payload["safety_controls"]["no_ai_in_this_patch"] is True
    assert payload["safety_controls"]["no_google_sheets_in_this_patch"] is True
    assert payload["safety_controls"]["no_db_migration_in_this_patch"] is True

    required_keys = payload["field_order"]["required"]
    assert "document_name" in required_keys
    assert "upload_form_month" in required_keys
    assert "reported_period" in required_keys


def test_catalog_index_is_compact_and_excludes_annexes_by_default() -> None:
    index = exporter.build_catalog_index(
        include_annexes=False,
        generated_at="2026-05-13T00:00:00Z",
    )

    assert index["template_kind"] == "checkwise_n8n_metadata_template_index"
    assert index["include_annexes"] is False
    assert index["document_type_count"] == 28

    first_item = index["document_types"][0]
    assert set(first_item) == {
        "code",
        "name",
        "group",
        "category",
        "subtype",
        "institution",
        "frequency",
        "hierarchy",
        "human_review_required",
        "legal_approval_allowed",
    }
    assert all(item["hierarchy"] == "principal" for item in index["document_types"])


def test_export_single_document_type_to_file(tmp_path: Path) -> None:
    output_path = tmp_path / "acuse_sisub.json"

    exit_code = exporter.main(
        [
            "--document-type",
            "acuse_sisub",
            "--output",
            str(output_path),
            "--validate-rulebook",
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["document_type"]["code"] == "acuse_sisub"
    assert payload["n8n"]["recommended_workflow_stage"] == "after_upload_before_ocr_ai_or_sheets"


def test_export_all_as_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "templates"

    exit_code = exporter.main(["--all", "--output", str(output_dir), "--validate-rulebook"])

    assert exit_code == 0
    index_path = output_dir / "catalog_index.json"
    acuse_path = output_dir / "document_types" / "acuse_sisub.json"
    assert index_path.exists()
    assert acuse_path.exists()

    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["document_type_count"] == 28

    acuse = json.loads(acuse_path.read_text(encoding="utf-8"))
    assert acuse["document_type"]["code"] == "acuse_sisub"


def test_export_all_as_single_file_bundle(tmp_path: Path) -> None:
    output_path = tmp_path / "bundle.json"

    exit_code = exporter.main(
        ["--all", "--single-file", "--output", str(output_path), "--validate-rulebook"]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["template_kind"] == "checkwise_n8n_metadata_template_bundle"
    assert payload["index"]["document_type_count"] == 28
    assert len(payload["templates"]) == 28
    assert {item["document_type"]["code"] for item in payload["templates"]} >= {
        "acuse_sisub",
        "registro_repse",
        "contrato_prestacion_servicios",
    }


def test_unknown_document_type_returns_non_zero() -> None:
    exit_code = exporter.main(["--document-type", "not_a_real_type", "--stdout"])

    assert exit_code == 1
