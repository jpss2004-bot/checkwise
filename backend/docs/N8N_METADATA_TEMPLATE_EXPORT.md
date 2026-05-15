# CheckWise n8n Metadata Template Exporter

This patch adds a local JSON exporter for n8n workflow prototypes.

It does **not** add OCR, AI extraction, Google Sheets integration, database migrations, or changes to the existing upload flow.

## Why this exists

The metadata rulebook catalog is the source of truth for what each CheckWise document type requires. n8n should orchestrate workflow steps, but it should not become the place where REPSE/Legal Shelf metadata rules are hardcoded.

This exporter converts the static backend rulebook into JSON templates that n8n can consume.

## Files added

```text
backend/tools/export_n8n_metadata_templates.py
backend/tests/test_n8n_metadata_template_exporter.py
backend/docs/N8N_METADATA_TEMPLATE_EXPORT.md
```

## Basic commands

From the `backend/` folder:

```bash
python tools/export_n8n_metadata_templates.py --list
```

Export one template to stdout:

```bash
python tools/export_n8n_metadata_templates.py \
  --document-type acuse_sisub \
  --stdout \
  --validate-rulebook
```

Export one template to a file:

```bash
python tools/export_n8n_metadata_templates.py \
  --document-type acuse_sisub \
  --output tmp/n8n_metadata_templates/document_types/acuse_sisub.json \
  --validate-rulebook
```

Export all principal document templates as a folder:

```bash
python tools/export_n8n_metadata_templates.py \
  --all \
  --output tmp/n8n_metadata_templates \
  --validate-rulebook
```

Export all principal document templates as one bundle file:

```bash
python tools/export_n8n_metadata_templates.py \
  --all \
  --single-file \
  --output tmp/n8n_metadata_templates/checkwise_n8n_metadata_templates.json \
  --validate-rulebook
```

Include explicit annex templates if needed:

```bash
python tools/export_n8n_metadata_templates.py \
  --all \
  --include-annexes \
  --output tmp/n8n_metadata_templates_with_annexes \
  --validate-rulebook
```

## JSON shape

Each exported document template includes:

- `template_kind`
- `schema_version`
- `generated_at`
- `rulebook`
- `document_type`
- `fields.required`
- `fields.optional`
- `fields.conditional`
- `fields.blank`
- `field_order`
- `n8n.input_context_contract`
- `n8n.output_item_contract`
- `n8n.review_controls`
- `safety_controls`
- `warnings`

The exported values are templates only. They do not contain extracted provider metadata.

## Intended n8n prototype flow

```text
Manual Trigger / Webhook
  ↓
Receive upload context or test fixture
  ↓
Choose expected document_type_code
  ↓
Read JSON template from CheckWise export
  ↓
Build empty metadata review items
  ↓
Send items to a human review surface or mock inspection table
```

## Safety rules

The exporter keeps these controls explicit in each template:

```json
{
  "no_ocr_in_this_patch": true,
  "no_ai_in_this_patch": true,
  "no_google_sheets_in_this_patch": true,
  "no_db_migration_in_this_patch": true
}
```

The template also states that final approval must be human and that `legal_approval_allowed` is false.

## Verification

```bash
cd backend
.venv/bin/ruff check tools/export_n8n_metadata_templates.py tests/test_n8n_metadata_template_exporter.py
.venv/bin/pytest tests/test_metadata_rules.py tests/test_n8n_metadata_template_exporter.py
```

If you are not using the virtual environment:

```bash
python -m pytest tests/test_metadata_rules.py tests/test_n8n_metadata_template_exporter.py
```

## Next step after this patch

The next safe step is to create a small sample `n8n-fixtures/` folder with one fake upload context JSON and one generated output bundle. That allows n8n to be tested without touching real provider documents, Google credentials, OCR, or AI services.
