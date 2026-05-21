# Native Metadata Table Export

This is the first native CheckWise replacement for the n8n spreadsheet prototype.

When a provider uploads a PDF through the portal, CheckWise now generates an XLSX metadata table automatically. The CLI remains available for local QA and backfills.

## Automatic Upload Export

Provider upload endpoint:

```text
POST /api/v1/portal/workspaces/{workspace_id}/submissions
```

After the upload is accepted, the backend writes an XLSX file under:

```text
metadata_exports/{client}/{provider}/{period}/{document_type}/
```

The automatic files are:

```text
{submission_id}_{document_id}_metadata.xlsx
latest_metadata.xlsx
```

CheckWise also rebuilds one current master workbook per client:

```text
metadata_exports/{client}/client_master_metadata.xlsx
```

Example:

```text
metadata_exports/cliente-piloto-checkwise/servicios-demo-sa-de-cv/2026-b1/comprobante-pago-bancario-infonavit/
  3f6..._9ac..._metadata.xlsx
  latest_metadata.xlsx
```

Every automatic export writes a `validation_events` row:

```text
event_type = metadata_table_exported
rule_code  = metadata_table_export
result     = completed | skipped | failed
```

The event payload includes:

- `document_type_code`
- `output_path`
- `latest_path`
- `reason`

## What It Does

- Uses `app/core/metadata_rules.py` as the source of truth.
- Writes a guided XLSX workbook for admin/client review.
- Keeps the raw one-row-per-field data available in the final workbook tab.
- Includes every field bucket from the selected rule: required, conditional, optional, and blank.
- Includes deterministic file metadata: filename, SHA-256, page count, validation status.
- Includes PDF text signals when enabled: detected institution, detected document type, RFCs, dates, period mentions, mismatch reason.
- Keeps human review required.

## What It Does Not Do

- No extracted metadata table persistence yet; the automatic upload flow only writes the audit/validation event that points to the XLSX.
- No legal approval.
- No Google Sheets write.
- No n8n dependency.
- No AI call yet.
- OCR only runs when explicitly enabled and local OCR tools are installed.

## Configuration

Automatic export is controlled by:

```text
AUTO_METADATA_EXPORT_ENABLED=true
METADATA_EXPORT_PATH=./metadata_exports
```

In local development, both defaults are already set.

## Document Type Resolution

The upload flow resolves the metadata document type automatically from:

1. The selected canonical requirement, when it maps directly.
2. The expected requirement name plus institution.
3. The PDF signal classifier, for known high-confidence aliases.
4. The uploaded filename, as a fallback.

If the type cannot be resolved, the provider upload still succeeds. CheckWise records `metadata_table_exported` with `result=skipped` and a reason so LegalShelf can fix the mapping.

## Manual CSV Example

```bash
cd apps/api

.venv/bin/python tools/export_pdf_metadata_table.py \
  --pdf ../../demo_assets/sample_documents/checkwise_demo_opinion_sat.pdf \
  --document-type constancia_situacion_fiscal \
  --output /tmp/checkwise_metadata_demo.csv \
  --format csv \
  --validate-rulebook
```

## Manual XLSX Example

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

The automatic XLSX is organized as a LegalShelf review workbook:

- `00 Guia`: plain-language summary for the admin, including client, provider, expected document, expected institution, period/file context, overall status, and mismatch warning.
- `01 Revision`: the practical review tab. Each row is a metadata field with the LegalShelf rule, extracted/proposed value, confidence, current status, source/method, and suggested action.
- `02 Senales`: document-level comparison signals: expected vs detected document, expected vs detected institution, RFCs, dates, periods, match confidence, anomaly codes, and OCR status.
- `03 Datos`: the complete raw export table for auditing, filtering, integrations, or future database import.

The workbook uses visual status colors so LegalShelf can immediately separate fields that are ready, prefilled but needing review, pending, or possible mismatch/more urgent review.

The client master workbook is intentionally cleaner and shareable:

- `00 Guia`: client-level summary.
- `01 Metadata Cliente`: the LegalShelf parameters per provider/document/field.
- `02 Documentos`: document-level expected-vs-detected signals.

It does not include backend paths, hashes, database ids, or raw technical dump tabs.

The CSV output remains a long table: one row per document field.

Core columns:

- `submission_id`
- `document_id`
- `document_type_code`
- `document_type_name`
- `institution`
- `period_key`
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

## Where Admins Find It

For an upload in May, the admin does not need to click anything extra. When the provider upload completes, CheckWise writes:

```text
metadata_exports/{client}/{provider}/{period}/{document_type}/latest_metadata.xlsx
```

Use `latest_metadata.xlsx` for the newest upload in that client/provider/period/document folder. Use the `{submission_id}_{document_id}_metadata.xlsx` file when you need the exact historical export for a specific upload.

Use `metadata_exports/{client}/client_master_metadata.xlsx` when LegalShelf needs the current client-level file to review or share.

Admins can access the same files inside the MVP at `/admin/metadata`. The page supports document-level preview/download and client master preview/download.

## Verification

```bash
cd apps/api

.venv/bin/ruff check tools/export_pdf_metadata_table.py tests/test_pdf_metadata_table_export.py
.venv/bin/python -m pytest tests/test_pdf_metadata_dry_run_tool.py tests/test_pdf_metadata_table_export.py
```

Note: if `.venv/bin/pytest` points to an old environment path, use `.venv/bin/python -m pytest`.
