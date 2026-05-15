# CheckWise n8n Local Metadata Workflow Specification

**Document:** `N8N_WORKFLOW_SPEC.md`  
**Workflow name:** `CheckWise Local Metadata Review Payload Dry Run`  
**Version:** `0.1.0`  
**Scope:** Local workflow specification only. No live n8n workflow JSON yet.  
**Status:** Ready to implement manually in n8n after the local JSON files exist.

---

## 1. Purpose

This document specifies, node by node, how n8n should consume the local CheckWise JSON files created by the metadata rulebook and dry-run fixture patches.

The workflow proves that n8n can:

1. Read a synthetic upload context JSON.
2. Read the CheckWise metadata template bundle JSON.
3. Select the correct document-type template.
4. Build a structured human-review metadata payload.
5. Write the review payload to a local output folder.
6. Produce a QA summary.

This workflow must **not** perform OCR, AI extraction, Google Sheets export, database writes, legal approval, or real document parsing.

---

## 2. Non-Negotiable Boundaries

This workflow is intentionally limited.

| Area | Allowed in this workflow? | Notes |
|---|---:|---|
| Read static JSON templates | Yes | Local generated files only. |
| Read synthetic upload context fixture | Yes | Fake fixture data only. |
| Build metadata review payload | Yes | Based on the static rulebook. |
| Write local JSON output | Yes | For developer inspection. |
| OCR | No | Later phase. |
| AI/model calls | No | Later phase. |
| Google Sheets | No | Later phase. |
| Database writes | No | Later phase. |
| Real uploaded documents | No | Later phase. |
| Legal approval | No | Must remain human/legal workflow. |
| Credential handling | No | No credentials should be needed. |

---

## 3. Required Local Files Before Running n8n

Before the workflow is built in n8n, the backend must already contain the outputs from the previous safe patches.

### 3.1 Static metadata rulebook

```text
backend/app/core/metadata_rules.py
backend/tests/test_metadata_rules.py
```

### 3.2 n8n template exporter

```text
backend/tools/export_n8n_metadata_templates.py
backend/tests/test_n8n_metadata_template_exporter.py
backend/docs/N8N_METADATA_TEMPLATE_EXPORT.md
```

### 3.3 Synthetic upload fixtures and review payload builder

```text
backend/tools/build_n8n_review_payload.py
backend/tests/test_n8n_review_payload_builder.py
backend/fixtures/n8n/sample_upload_context_acuse_sisub.json
backend/fixtures/n8n/sample_upload_context_contrato_prestacion_servicios.json
backend/docs/N8N_LOCAL_DRY_RUN_FIXTURES.md
```

### 3.4 Template bundle to generate before n8n consumes it

Run from `backend/`:

```bash
python tools/export_n8n_metadata_templates.py \
  --all \
  --single-file \
  --output tmp/n8n_metadata_templates/checkwise_n8n_metadata_templates.json \
  --validate-rulebook
```

Expected generated file:

```text
backend/tmp/n8n_metadata_templates/checkwise_n8n_metadata_templates.json
```

### 3.5 Input fixture selected for first run

Recommended first fixture:

```text
backend/fixtures/n8n/sample_upload_context_acuse_sisub.json
```

Second fixture for regression testing:

```text
backend/fixtures/n8n/sample_upload_context_contrato_prestacion_servicios.json
```

---

## 4. Runtime Assumptions

n8n must be able to read and write files inside the backend folder.

If n8n runs directly on the Mac, use the real absolute backend path, for example:

```text
/Users/josepablosamano/Desktop/Personal/legalshelf/checkwise/CheckWise/backend
```

If n8n runs in Docker, the backend path must be mounted into the n8n container, for example:

```text
/workspace/checkwise/backend
```

In this specification, the placeholder below means the path that n8n can actually see:

```text
{{BACKEND_ROOT}}
```

Example values:

```text
Mac direct run: /Users/josepablosamano/Desktop/Personal/legalshelf/checkwise/CheckWise/backend
Docker mount:   /workspace/checkwise/backend
```

Use absolute paths. Do not rely on relative paths inside n8n.

---

## 5. Source JSON Contracts

### 5.1 Upload context JSON

Input file example:

```text
{{BACKEND_ROOT}}/fixtures/n8n/sample_upload_context_acuse_sisub.json
```

Minimum required keys:

```json
{
  "submission_id": "sub_fixture_acuse_sisub_001",
  "document_id": "doc_fixture_acuse_sisub_001",
  "client_id": "client_fixture_001",
  "client_legal_name": "CLIENTE DEMO, S.A. DE C.V.",
  "vendor_id": "vendor_fixture_001",
  "vendor_legal_name": "SEGURIDAD PRIVADA DEMO, S.A. DE C.V.",
  "vendor_rfc": "SPD010101XXX",
  "provider_nomenclature": "SEGURIDAD PRI",
  "requirement_id": "req_fixture_sisub",
  "period_id": "period_2025_05",
  "document_type_code": "acuse_sisub",
  "expected_document_type_code": "acuse_sisub",
  "expected_institution": "infonavit",
  "upload_form_month": "Mayo",
  "reported_period": "Cuatrimestre inmediato anterior",
  "original_filename": "SEGURIDAD_PRI_Acuse_SISUB_Mayo.pdf",
  "proposed_document_name": "SEGURIDAD PRI Acuse SISUB Mayo",
  "proposed_pdf_file_name": "SEGURIDAD PRI Acuse SISUB Mayo.pdf",
  "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "mime_type": "application/pdf",
  "size_bytes": 245760,
  "page_count": 2,
  "uploaded_at": "2026-05-13T12:00:00Z",
  "source_form": "fixture_only_no_real_jotform",
  "storage_key": "fixtures/no-real-document/acuse-sisub.pdf",
  "file_url_for_reviewer": null,
  "fixture_notice": "Synthetic fixture. Does not contain real client, provider, fiscal, labor, payroll, or legal data."
}
```

### 5.2 Metadata template bundle JSON

Input file:

```text
{{BACKEND_ROOT}}/tmp/n8n_metadata_templates/checkwise_n8n_metadata_templates.json
```

Expected top-level structure:

```json
{
  "generated_at": "2026-05-13T00:00:00Z",
  "schema_version": "...",
  "template_kind": "checkwise_n8n_metadata_template_bundle",
  "index": {
    "document_type_count": 28,
    "document_types": []
  },
  "templates": []
}
```

Each `templates[]` item contains:

```json
{
  "document_type": {
    "code": "acuse_sisub",
    "name": "Acuse SISUB",
    "group": "cumplimiento_repse",
    "category": "Formatos",
    "subtype": "Comprobante",
    "institution": "infonavit",
    "frequency": "cuatrimestral",
    "human_review_required": true,
    "legal_approval_allowed": false,
    "required_field_keys": [],
    "conditional_field_keys": [],
    "optional_field_keys": [],
    "blank_field_keys": []
  },
  "fields": {
    "required": [],
    "conditional": [],
    "optional": [],
    "blank": []
  }
}
```

---

## 6. Workflow Topology

```text
[01 Manual Trigger]
        ↓
[02 Set Workflow Config]
        ↓
[03 Read Upload Context JSON]
        ↓
[04 Extract Upload Context JSON]
        ↓
[05 Read Template Bundle JSON]
        ↓
[06 Extract Template Bundle JSON]
        ↓
[07 Build Review Payload]
        ↓
[08 Safety Gate]
   pass ↓           fail ↓
[09 Convert Review Payload]   [12 Build Rejection Report]
        ↓                         ↓
[10 Write Review Payload]      [13 Convert Rejection Report]
        ↓                         ↓
[11 Build QA Summary]          [14 Write Rejection Report]
        ↓
[15 Convert QA Summary]
        ↓
[16 Write QA Summary]
```

---

## 7. Node-by-Node Specification

## Node 01 — Manual Trigger

| Setting | Value |
|---|---|
| Node type | `Manual Trigger` |
| Purpose | Start the local dry-run manually. |
| Automatic execution | No |

Expected output:

```json
{}
```

---

## Node 02 — Set Workflow Config

| Setting | Value |
|---|---|
| Node type | `Edit Fields` / `Set` |
| Purpose | Define file paths and selected fixture. |
| Keep Only Set | `true` if available |

Fields to set:

```json
{
  "workflow_version": "0.1.0",
  "backend_root": "{{BACKEND_ROOT}}",
  "upload_context_filename": "sample_upload_context_acuse_sisub.json",
  "template_bundle_relative_path": "tmp/n8n_metadata_templates/checkwise_n8n_metadata_templates.json",
  "review_payload_output_relative_dir": "tmp/n8n_review_payloads",
  "qa_output_relative_dir": "tmp/n8n_review_payloads",
  "error_output_relative_dir": "tmp/n8n_errors",
  "allow_ai": false,
  "allow_ocr": false,
  "allow_google_sheets": false,
  "allow_database_writes": false,
  "allow_legal_approval": false
}
```

For the second test run, change only:

```json
{
  "upload_context_filename": "sample_upload_context_contrato_prestacion_servicios.json"
}
```

---

## Node 03 — Read Upload Context JSON

| Setting | Value |
|---|---|
| Node type | `Read/Write Files from Disk` |
| Operation | `Read File(s) From Disk` |
| Purpose | Read the selected synthetic upload context fixture. |
| File(s) Selector | `={{$json.backend_root + "/fixtures/n8n/" + $json.upload_context_filename}}` |
| Put Output File in Field | `uploadContextFile` |
| MIME Type option | `application/json` |

Expected output:

- Original JSON fields from Node 02 may be retained depending on n8n behavior.
- Binary field `uploadContextFile` must exist.

---

## Node 04 — Extract Upload Context JSON

| Setting | Value |
|---|---|
| Node type | `Extract From File` |
| Operation | `Extract From JSON` |
| Purpose | Convert the upload context binary file into normal n8n JSON. |
| Input Binary Field | `uploadContextFile` |

Expected output:

One JSON item with keys such as:

```json
{
  "submission_id": "sub_fixture_acuse_sisub_001",
  "document_id": "doc_fixture_acuse_sisub_001",
  "document_type_code": "acuse_sisub",
  "expected_document_type_code": "acuse_sisub",
  "provider_nomenclature": "SEGURIDAD PRI",
  "proposed_document_name": "SEGURIDAD PRI Acuse SISUB Mayo"
}
```

---

## Node 05 — Read Template Bundle JSON

| Setting | Value |
|---|---|
| Node type | `Read/Write Files from Disk` |
| Operation | `Read File(s) From Disk` |
| Purpose | Read the generated metadata template bundle. |
| File(s) Selector | `={{$('Set Workflow Config').first().json.backend_root + "/" + $('Set Workflow Config').first().json.template_bundle_relative_path}}` |
| Put Output File in Field | `templateBundleFile` |
| MIME Type option | `application/json` |

Expected output:

- Binary field `templateBundleFile` must exist.

---

## Node 06 — Extract Template Bundle JSON

| Setting | Value |
|---|---|
| Node type | `Extract From File` |
| Operation | `Extract From JSON` |
| Purpose | Convert the template bundle binary file into normal n8n JSON. |
| Input Binary Field | `templateBundleFile` |

Expected output:

One JSON item containing:

```json
{
  "template_kind": "checkwise_n8n_metadata_template_bundle",
  "index": {
    "document_type_count": 28
  },
  "templates": []
}
```

---

## Node 07 — Build Review Payload

| Setting | Value |
|---|---|
| Node type | `Code` |
| Language | `JavaScript` |
| Mode | `Run Once for All Items` |
| Purpose | Combine upload context + selected metadata rule into a review payload. |

Code:

```javascript
const config = $('Set Workflow Config').first().json;
const uploadContext = $('Extract Upload Context JSON').first().json;
const bundle = $('Extract Template Bundle JSON').first().json;

if (!bundle || !Array.isArray(bundle.templates)) {
  throw new Error('Invalid metadata template bundle: templates[] not found.');
}

const documentTypeCode =
  uploadContext.expected_document_type_code ||
  uploadContext.document_type_code;

if (!documentTypeCode) {
  throw new Error('Upload context is missing expected_document_type_code/document_type_code.');
}

const template = bundle.templates.find((item) => {
  return item.document_type && item.document_type.code === documentTypeCode;
});

if (!template) {
  throw new Error(`No metadata template found for document_type_code=${documentTypeCode}`);
}

const documentType = template.document_type;

const fieldGroups = [
  ['required', template.fields?.required || []],
  ['conditional', template.fields?.conditional || []],
  ['optional', template.fields?.optional || []],
  ['blank', template.fields?.blank || []],
];

const contextValueMap = {
  client_legal_name: uploadContext.client_legal_name,
  provider_nomenclature: uploadContext.provider_nomenclature,
  document_name: uploadContext.proposed_document_name,
  pdf_file_name: uploadContext.proposed_pdf_file_name,
  document_category: documentType.category,
  document_subtype: documentType.subtype,
  area_interna: 'Compliance',
  tags: documentType.fixed_tags,
  upload_form_month: uploadContext.upload_form_month,
  reported_period: uploadContext.reported_period,
  document_institution_name: uploadContext.expected_institution || documentType.institution,
};

function normalizeValue(value) {
  if (Array.isArray(value)) return value.join(' | ');
  if (value === undefined) return null;
  return value;
}

const reviewItems = [];

for (const [requirementLevel, fields] of fieldGroups) {
  for (const field of fields) {
    const rawValue = contextValueMap[field.key] ?? null;
    const hasContextValue = rawValue !== null && rawValue !== undefined && rawValue !== '';

    reviewItems.push({
      submission_id: uploadContext.submission_id,
      document_id: uploadContext.document_id,
      client_id: uploadContext.client_id,
      vendor_id: uploadContext.vendor_id,
      requirement_id: uploadContext.requirement_id,
      period_id: uploadContext.period_id,
      document_type_code: documentType.code,
      field_key: field.key,
      field_label: field.label,
      field_description: field.description,
      requirement_level: requirementLevel,
      allowed_extraction_methods: field.extraction_methods || [],
      raw_value: hasContextValue ? rawValue : null,
      normalized_value: hasContextValue ? normalizeValue(rawValue) : null,
      confidence: hasContextValue ? 1.0 : null,
      extraction_method: hasContextValue ? 'context' : null,
      source_page: null,
      source_text_snippet: null,
      human_review_required: true,
      review_status: 'pending',
      reviewed_value: null,
      reviewer_decision: null,
      review_notes: hasContextValue
        ? 'Prefilled from upload context or static metadata rulebook.'
        : 'Pending future OCR/AI/human extraction. Not extracted in local n8n dry run.',
    });
  }
}

const missingRequiredFieldKeys = reviewItems
  .filter((item) => item.requirement_level === 'required')
  .filter((item) => item.raw_value === null || item.raw_value === undefined || item.raw_value === '')
  .map((item) => item.field_key);

const payload = {
  payload_kind: 'checkwise_n8n_review_payload_dry_run',
  schema_version: bundle.schema_version || 'unknown',
  workflow_version: config.workflow_version,
  generated_at: new Date().toISOString(),
  workflow_stage: 'local_n8n_dry_run_before_ocr_ai_sheets_db',
  source: {
    upload_context_filename: config.upload_context_filename,
    template_bundle_relative_path: config.template_bundle_relative_path,
  },
  upload_context: uploadContext,
  document_type: documentType,
  review_items: reviewItems,
  summary: {
    document_type_code: documentType.code,
    document_type_name: documentType.name,
    review_item_count: reviewItems.length,
    required_item_count: reviewItems.filter((item) => item.requirement_level === 'required').length,
    missing_required_field_count: missingRequiredFieldKeys.length,
    missing_required_field_keys: missingRequiredFieldKeys,
    has_missing_required_fields: missingRequiredFieldKeys.length > 0,
    human_review_required: true,
    legal_approval_allowed: false,
  },
  safety_controls: {
    no_ocr: config.allow_ocr === false,
    no_ai: config.allow_ai === false,
    no_google_sheets: config.allow_google_sheets === false,
    no_database_writes: config.allow_database_writes === false,
    no_legal_approval: config.allow_legal_approval === false,
  },
  routing: {
    next_queue: 'human_metadata_review_fixture_only',
    export_allowed: false,
    sheets_export_allowed: false,
    legal_approval_allowed: false,
  },
  warnings: [
    'Synthetic dry-run payload only.',
    'No OCR, AI, Google Sheets, database writes, or legal approval performed.',
    'Missing required fields are expected until OCR/AI/human extraction is added in a later phase.',
  ],
};

return [{ json: payload }];
```

Expected output:

```json
{
  "payload_kind": "checkwise_n8n_review_payload_dry_run",
  "document_type": {
    "code": "acuse_sisub"
  },
  "review_items": [],
  "summary": {
    "review_item_count": 20,
    "legal_approval_allowed": false
  },
  "safety_controls": {
    "no_ocr": true,
    "no_ai": true,
    "no_google_sheets": true,
    "no_database_writes": true,
    "no_legal_approval": true
  }
}
```

The exact `review_item_count` depends on the document type rule.

---

## Node 08 — Safety Gate

| Setting | Value |
|---|---|
| Node type | `IF` |
| Purpose | Prevent accidental continuation if safety controls are false. |

Conditions:

```text
{{$json.safety_controls.no_ocr}} equals true
{{$json.safety_controls.no_ai}} equals true
{{$json.safety_controls.no_google_sheets}} equals true
{{$json.safety_controls.no_database_writes}} equals true
{{$json.safety_controls.no_legal_approval}} equals true
{{$json.summary.legal_approval_allowed}} equals false
{{$json.routing.sheets_export_allowed}} equals false
```

True branch:

```text
Continue to Node 09.
```

False branch:

```text
Continue to Node 12 Build Rejection Report.
```

---

## Node 09 — Convert Review Payload to JSON File

| Setting | Value |
|---|---|
| Node type | `Convert to File` |
| Operation | `Convert to JSON` |
| Purpose | Turn the review payload JSON into a binary JSON file. |
| Put Output File in Field | `reviewPayloadFile` |
| File Name | `={{$json.document_type.code + "_review_payload_n8n.json"}}` |

Expected binary field:

```text
reviewPayloadFile
```

---

## Node 10 — Write Review Payload to Disk

| Setting | Value |
|---|---|
| Node type | `Read/Write Files from Disk` |
| Operation | `Write File to Disk` |
| Purpose | Save the generated review payload locally. |
| Input Binary Field | `reviewPayloadFile` |
| File Path and Name | `={{$('Set Workflow Config').first().json.backend_root + "/" + $('Set Workflow Config').first().json.review_payload_output_relative_dir + "/" + $json.document_type.code + "_review_payload_n8n.json"}}` |
| Append | `false` |

Expected output file:

```text
{{BACKEND_ROOT}}/tmp/n8n_review_payloads/acuse_sisub_review_payload_n8n.json
```

For contract fixture:

```text
{{BACKEND_ROOT}}/tmp/n8n_review_payloads/contrato_prestacion_servicios_review_payload_n8n.json
```

---

## Node 11 — Build QA Summary

| Setting | Value |
|---|---|
| Node type | `Code` |
| Language | `JavaScript` |
| Mode | `Run Once for All Items` |
| Purpose | Generate a small inspection summary for the developer. |

Code:

```javascript
const payload = $('Build Review Payload').first().json;

const qaSummary = {
  payload_kind: 'checkwise_n8n_review_payload_qa_summary',
  generated_at: new Date().toISOString(),
  status: 'ready_for_manual_inspection',
  document_type_code: payload.document_type.code,
  document_type_name: payload.document_type.name,
  upload_context_submission_id: payload.upload_context.submission_id,
  review_item_count: payload.summary.review_item_count,
  required_item_count: payload.summary.required_item_count,
  missing_required_field_count: payload.summary.missing_required_field_count,
  missing_required_field_keys: payload.summary.missing_required_field_keys,
  safety_controls: payload.safety_controls,
  output_file_expected: `${payload.document_type.code}_review_payload_n8n.json`,
  next_step: 'Inspect payload manually. Do not connect OCR, AI, Google Sheets, or DB yet.',
};

return [{ json: qaSummary }];
```

---

## Node 12 — Build Rejection Report

| Setting | Value |
|---|---|
| Node type | `Code` |
| Language | `JavaScript` |
| Mode | `Run Once for All Items` |
| Purpose | Build a local error file if safety controls fail. |

Code:

```javascript
const payload = $input.first().json;

return [{
  json: {
    payload_kind: 'checkwise_n8n_rejection_report',
    generated_at: new Date().toISOString(),
    status: 'blocked_by_safety_gate',
    reason: 'One or more forbidden capabilities were enabled or legal approval was allowed.',
    safety_controls: payload.safety_controls || null,
    summary: payload.summary || null,
    routing: payload.routing || null,
  }
}];
```

---

## Node 13 — Convert Rejection Report to JSON File

| Setting | Value |
|---|---|
| Node type | `Convert to File` |
| Operation | `Convert to JSON` |
| Purpose | Turn the rejection report into a local JSON file. |
| Put Output File in Field | `rejectionReportFile` |
| File Name | `rejection_report_n8n.json` |

---

## Node 14 — Write Rejection Report to Disk

| Setting | Value |
|---|---|
| Node type | `Read/Write Files from Disk` |
| Operation | `Write File to Disk` |
| Purpose | Save safety failure details. |
| Input Binary Field | `rejectionReportFile` |
| File Path and Name | `={{$('Set Workflow Config').first().json.backend_root + "/" + $('Set Workflow Config').first().json.error_output_relative_dir + "/rejection_report_n8n.json"}}` |
| Append | `false` |

Expected output file if safety gate fails:

```text
{{BACKEND_ROOT}}/tmp/n8n_errors/rejection_report_n8n.json
```

---

## Node 15 — Convert QA Summary to JSON File

| Setting | Value |
|---|---|
| Node type | `Convert to File` |
| Operation | `Convert to JSON` |
| Purpose | Turn QA summary into a local JSON file. |
| Put Output File in Field | `qaSummaryFile` |
| File Name | `={{$json.document_type_code + "_qa_summary_n8n.json"}}` |

---

## Node 16 — Write QA Summary to Disk

| Setting | Value |
|---|---|
| Node type | `Read/Write Files from Disk` |
| Operation | `Write File to Disk` |
| Purpose | Save QA summary locally. |
| Input Binary Field | `qaSummaryFile` |
| File Path and Name | `={{$('Set Workflow Config').first().json.backend_root + "/" + $('Set Workflow Config').first().json.qa_output_relative_dir + "/" + $json.document_type_code + "_qa_summary_n8n.json"}}` |
| Append | `false` |

Expected output file:

```text
{{BACKEND_ROOT}}/tmp/n8n_review_payloads/acuse_sisub_qa_summary_n8n.json
```

---

## 8. Expected Output Payload Shape

The main output file must look like this:

```json
{
  "payload_kind": "checkwise_n8n_review_payload_dry_run",
  "schema_version": "...",
  "workflow_version": "0.1.0",
  "generated_at": "2026-05-13T00:00:00.000Z",
  "workflow_stage": "local_n8n_dry_run_before_ocr_ai_sheets_db",
  "source": {
    "upload_context_filename": "sample_upload_context_acuse_sisub.json",
    "template_bundle_relative_path": "tmp/n8n_metadata_templates/checkwise_n8n_metadata_templates.json"
  },
  "upload_context": {},
  "document_type": {},
  "review_items": [],
  "summary": {},
  "safety_controls": {},
  "routing": {},
  "warnings": []
}
```

Each review item must contain:

```json
{
  "submission_id": "...",
  "document_id": "...",
  "client_id": "...",
  "vendor_id": "...",
  "requirement_id": "...",
  "period_id": "...",
  "document_type_code": "acuse_sisub",
  "field_key": "document_name",
  "field_label": "Nombre del Documento",
  "field_description": "...",
  "requirement_level": "required",
  "allowed_extraction_methods": [],
  "raw_value": "...",
  "normalized_value": "...",
  "confidence": 1.0,
  "extraction_method": "context",
  "source_page": null,
  "source_text_snippet": null,
  "human_review_required": true,
  "review_status": "pending",
  "reviewed_value": null,
  "reviewer_decision": null,
  "review_notes": "..."
}
```

---

## 9. Manual Test Procedure

### 9.1 Prepare backend-generated template bundle

From `backend/`:

```bash
python tools/export_n8n_metadata_templates.py \
  --all \
  --single-file \
  --output tmp/n8n_metadata_templates/checkwise_n8n_metadata_templates.json \
  --validate-rulebook
```

### 9.2 Optional: compare with backend CLI output

From `backend/`:

```bash
python tools/build_n8n_review_payload.py \
  --context fixtures/n8n/sample_upload_context_acuse_sisub.json \
  --output tmp/n8n_review_payloads/acuse_sisub_review_payload_cli_reference.json
```

This is not required by n8n, but useful as a reference.

### 9.3 Run n8n workflow manually

Execute the workflow from Node 01.

Expected files:

```text
tmp/n8n_review_payloads/acuse_sisub_review_payload_n8n.json
tmp/n8n_review_payloads/acuse_sisub_qa_summary_n8n.json
```

### 9.4 Change fixture and run again

In Node 02, change:

```text
sample_upload_context_acuse_sisub.json
```

to:

```text
sample_upload_context_contrato_prestacion_servicios.json
```

Expected files:

```text
tmp/n8n_review_payloads/contrato_prestacion_servicios_review_payload_n8n.json
tmp/n8n_review_payloads/contrato_prestacion_servicios_qa_summary_n8n.json
```

---

## 10. Acceptance Criteria

The workflow is successful only if all criteria pass.

| Criteria | Expected result |
|---|---|
| Reads upload context fixture | Pass |
| Reads generated template bundle | Pass |
| Finds matching template by `document_type_code` | Pass |
| Produces one review item per rulebook field | Pass |
| Prefills context-safe values only | Pass |
| Leaves OCR/AI/human-only fields pending | Pass |
| Writes review payload JSON locally | Pass |
| Writes QA summary JSON locally | Pass |
| Does not call external APIs | Pass |
| Does not use credentials | Pass |
| Does not write to DB | Pass |
| Does not connect Google Sheets | Pass |
| Does not perform legal approval | Pass |
| Safety gate blocks forbidden capabilities | Pass |

---

## 11. Failure Conditions

The workflow should fail or write a rejection report if any of the following happens:

1. Template bundle file is missing.
2. Upload context file is missing.
3. `templates[]` is missing from the bundle.
4. `expected_document_type_code` and `document_type_code` are both missing.
5. No matching document type template exists.
6. Any safety flag becomes false.
7. Any branch attempts AI, OCR, Google Sheets, database writes, or legal approval.

---

## 12. What This Workflow Proves

This workflow proves that the CheckWise backend rulebook can act as the source of truth for n8n.

n8n does not own the legal/compliance logic. n8n only orchestrates:

```text
Upload context JSON
        +
Metadata template bundle JSON
        ↓
Human-review payload JSON
```

This is the correct architectural boundary.

---

## 13. What Comes After This Specification

After this specification is reviewed, the next safe steps are:

1. Build the actual local n8n workflow manually from this document.
2. Export the n8n workflow JSON from n8n.
3. Store the exported workflow in the repo as a fixture/template, with credentials removed.
4. Add a backend document explaining how to import/run the workflow.
5. Only then consider a webhook/API version.

Do not jump directly to Google Sheets, OCR, or AI.

---

## 14. Future Workflow Versions

### Version 0.2 — Webhook/API version

Replace file reads with a local CheckWise API endpoint:

```text
POST /api/v1/internal/n8n/review-payload-preview
```

This should return the review payload directly.

### Version 0.3 — Real upload event version

Trigger from a real upload event, but still no OCR/AI.

### Version 0.4 — CSV/Sheets draft export

Export only reviewed or fixture-safe data.

### Version 0.5 — OCR prototype

Add OCR only after field-level review model is stable.

### Version 0.6 — AI extraction prototype

Add AI only after strict schemas, confidence scoring, and human-review controls are implemented.

---

## 15. Final Architecture Rule

CheckWise owns:

```text
metadata rules
schema
review states
legal/compliance boundaries
audit expectations
```

n8n owns:

```text
workflow orchestration
file movement during prototype
manual test automation
later integration routing
```

Google Sheets, OCR, and AI remain future integration layers, not foundations.
