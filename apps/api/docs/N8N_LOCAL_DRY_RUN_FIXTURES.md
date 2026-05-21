# CheckWise n8n Local Dry-Run Fixtures

This patch adds a local dry-run layer for the future n8n workflow.

It does **not** perform OCR, AI extraction, database writes, Google Sheets writes, or live document parsing. It only combines a synthetic upload context JSON with the static CheckWise metadata rulebook template and produces a review payload that n8n can use during workflow prototyping.

## Files added

```text
tools/build_n8n_review_payload.py
tests/test_n8n_review_payload_builder.py
fixtures/n8n/sample_upload_context_acuse_sisub.json
fixtures/n8n/sample_upload_context_contrato_prestacion_servicios.json
docs/N8N_LOCAL_DRY_RUN_FIXTURES.md
```

## Why this comes after the JSON template exporter

The previous exporter answers:

> For this document type, what metadata fields does CheckWise expect?

This dry-run fixture builder answers:

> Given a fake upload event and that template, what review items would n8n pass to a human reviewer?

That makes the workflow testable before adding OCR, AI, database persistence, or Google Sheets export.

## Generate one review payload

From the backend folder:

```bash
python tools/build_n8n_review_payload.py \
  --context fixtures/n8n/sample_upload_context_acuse_sisub.json \
  --output tmp/n8n_review_payloads/acuse_sisub_review_payload.json
```

Or print to stdout:

```bash
python tools/build_n8n_review_payload.py \
  --context fixtures/n8n/sample_upload_context_contrato_prestacion_servicios.json \
  --stdout
```

## What the payload contains

The generated payload contains:

- upload context from the fixture
- selected document type rule
- one review item per metadata field
- safe context/default values where possible
- blank pending items for anything requiring PDF text, OCR, AI, or human interpretation
- safety controls proving this patch does not write to DB, OCR, AI, or Sheets

## Important safety behavior

The tool may prefill fields from the upload context or the rulebook, for example:

- `client_legal_name`
- `provider_nomenclature`
- `area_interna`
- `document_category`
- `document_subtype`
- `tags`
- `upload_form_month`
- `reported_period`

It intentionally leaves document-content fields blank, for example:

- `main_date`
- `participants`
- `start_date`
- `expiration_date`
- `renewal_date`
- `notary_number`
- `public_deed_number`

Those fields require later OCR/PDF parsing, AI-assisted extraction, or human review.

## Verify

```bash
pytest tests/test_metadata_rules.py \
  tests/test_n8n_metadata_template_exporter.py \
  tests/test_n8n_review_payload_builder.py
```

Optional direct commands:

```bash
python tools/export_n8n_metadata_templates.py --list

python tools/build_n8n_review_payload.py \
  --context fixtures/n8n/sample_upload_context_acuse_sisub.json \
  --stdout
```

## Future n8n workflow shape

```text
Manual Trigger / Webhook Upload Context
        ↓
Read fake or real upload context
        ↓
Select document_type_code
        ↓
Load CheckWise metadata template
        ↓
Build review payload
        ↓
Human review queue / mock approval screen
        ↓
Later: OCR + AI extraction + reviewed export
```

## Next safe step

After this patch, the next safe step is to create an **n8n workflow specification document** that maps each future n8n node to these local JSON files. That still avoids live Google Sheets, OCR, AI, and database writes while making the automation design explicit.
