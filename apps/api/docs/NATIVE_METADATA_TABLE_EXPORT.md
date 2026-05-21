# Native Metadata Table Export

This tool is the first native CheckWise replacement for the n8n spreadsheet prototype.

It takes one uploaded/local PDF, applies the real metadata rulebook, inspects the PDF, and writes structured metadata rows to CSV or XLSX.

## What It Does

- Uses `app/core/metadata_rules.py` as the source of truth.
- Writes one row per metadata field.
- Includes every field bucket from the selected rule: required, conditional, optional, and blank.
- Includes deterministic file metadata: filename, SHA-256, page count, validation status.
- Includes PDF text signals when enabled: detected institution, detected document type, RFCs, dates, period mentions, mismatch reason.
- Keeps human review required.

## What It Does Not Do

- No database writes.
- No legal approval.
- No Google Sheets write.
- No n8n dependency.
- No AI call yet.
- OCR only runs when explicitly enabled and local OCR tools are installed.

## CSV Example

```bash
cd apps/api

.venv/bin/python tools/export_pdf_metadata_table.py \
  --pdf ../../demo_assets/sample_documents/checkwise_demo_opinion_sat.pdf \
  --document-type constancia_situacion_fiscal \
  --output /tmp/checkwise_metadata_demo.csv \
  --format csv \
  --validate-rulebook
```

## XLSX Example

```bash
cd apps/api

.venv/bin/python tools/export_pdf_metadata_table.py \
  --pdf ../../demo_assets/sample_documents/checkwise_demo_opinion_sat.pdf \
  --document-type constancia_situacion_fiscal \
  --output /tmp/checkwise_metadata_demo.xlsx \
  --format xlsx \
  --validate-rulebook
```

## Context JSON

Pass upload/submission context when available:

```bash
.venv/bin/python tools/export_pdf_metadata_table.py \
  --pdf /path/to/upload.pdf \
  --document-type acuse_sisub \
  --context-json fixtures/n8n/sample_upload_context_acuse_sisub.json \
  --output /tmp/acuse_sisub_metadata.xlsx
```

Useful context keys include:

- `submission_id`
- `document_id`
- `client_legal_name`
- `provider_nomenclature`
- `expected_institution`
- `upload_form_month`
- `reported_period`
- `proposed_document_name`
- `proposed_pdf_file_name`

## Output Shape

The output is a long table: one row per document field.

Core columns:

- `submission_id`
- `document_id`
- `document_type_code`
- `document_type_name`
- `institution`
- `original_filename`
- `sha256`
- `page_count`
- `detected_institution`
- `detected_document_type`
- `mismatch_reason`
- `field_key`
- `field_label`
- `requirement_level`
- `raw_value`
- `normalized_value`
- `confidence`
- `extraction_method`
- `review_status`
- `human_review_required`

This long-table shape is intentional. It handles documents with different rulebook fields without creating unstable spreadsheet columns.

## Verification

```bash
cd apps/api

.venv/bin/ruff check tools/export_pdf_metadata_table.py tests/test_pdf_metadata_table_export.py
.venv/bin/python -m pytest tests/test_pdf_metadata_dry_run_tool.py tests/test_pdf_metadata_table_export.py
```

Note: if `.venv/bin/pytest` points to an old environment path, use `.venv/bin/python -m pytest`.
