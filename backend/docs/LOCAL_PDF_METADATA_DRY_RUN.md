# Local PDF Metadata Dry Run

This document explains how to test individual PDFs separately from the CheckWise app while still using the real CheckWise metadata rulebook file.

## What this is

A local dry-run tester that accepts:

- one local PDF file
- one document type code from `app/core/metadata_rules.py`
- optional context JSON

It returns a review payload shaped like the n8n dry-run payload.

## What this is not

This does **not** use:

- the CheckWise web app
- the database
- OCR
- AI
- Google Sheets
- n8n credentials
- external services
- legal approval automation

## Why this comes before OCR/AI

The goal is to prove that an uploaded PDF can be combined with the real metadata rules and turned into a human-review payload. The system still leaves document dates, participants, contract clauses, and legal sufficiency as pending human-reviewed fields.

## List supported document types

From the backend folder:

```bash
python tools/test_pdf_metadata_dry_run.py --list-document-types
```

## Test one PDF

```bash
python tools/test_pdf_metadata_dry_run.py \
  --pdf /absolute/path/to/document.pdf \
  --document-type acuse_sisub \
  --context-json fixtures/n8n/sample_upload_context_acuse_sisub.json \
  --output tmp/pdf_metadata_dry_runs/acuse_sisub_payload.json \
  --validate-rulebook
```

Open the output JSON and inspect:

- `metadata_rules_version`
- `template`
- `review_items`
- `deterministic_file_metadata`
- `safety`
- `validation_result`

## Test without context JSON

```bash
python tools/test_pdf_metadata_dry_run.py \
  --pdf /absolute/path/to/document.pdf \
  --document-type contrato_prestacion_servicios \
  --output tmp/pdf_metadata_dry_runs/contract_payload.json \
  --validate-rulebook
```

Without context JSON, the tool can still inspect the file and load the rulebook, but many metadata fields will remain `pending`.

## What gets prefilled

The tool can prefill deterministic or context-provided values such as:

- `document_name`
- `pdf_file_name`
- `client_legal_name`
- `provider_nomenclature`
- `area_interna`
- `document_category`
- `document_subtype`
- `upload_form_month`
- `reported_period`
- local file metadata such as filename, MIME type, SHA-256, size, and page count

## What remains pending

The tool intentionally leaves these as pending unless they appear in context:

- document dates
- issue dates
- participants
- contract start/expiration/renewal details
- legal sufficiency
- final approval

## Local API for n8n Form/Webhook uploads

The same dry-run builder is also exposed through a local testing endpoint:

```text
POST /api/v1/metadata-dry-run/pdf
```

See `docs/N8N_FORM_WEBHOOK_PDF_UPLOAD.md` for the n8n Form/Webhook setup.

## n8n Cloud note

n8n Cloud cannot directly read PDFs from your local filesystem. For now, use this CLI to validate individual PDFs locally. Later, connect n8n through one of these options:

1. self-host n8n locally so it can read local files;
2. expose a local dry-run API through a temporary tunnel;
3. use an n8n Form/Webhook upload node and send the PDF as binary data.

The key principle remains the same: n8n should orchestrate the workflow, while CheckWise metadata rules remain the source of truth.

## Tests

```bash
.venv/bin/pytest tests/test_metadata_rules.py tests/test_pdf_metadata_dry_run_tool.py tests/test_metadata_dry_run_api.py
```
