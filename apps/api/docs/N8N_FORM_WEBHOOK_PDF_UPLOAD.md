# n8n Form/Webhook PDF Upload Dry Run

This is the next local prototype after the synthetic fixture runner. It lets n8n receive an individual PDF and ask the CheckWise backend to build a metadata review payload using the real rulebook in `app/core/metadata_rules.py`.

## Endpoint

Run the backend locally from `backend`:

```bash
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Then post a multipart form request:

```http
POST http://127.0.0.1:8000/api/v1/metadata-dry-run/pdf
```

Fields:

- `file`: uploaded PDF binary
- `document_type_code`: rulebook code, for example `acuse_sisub`
- `context_json`: optional JSON object as a string
- `include_intelligence`: optional boolean; use `true` for PDF text/OCR/AI/Sheets packages
- `enable_ocr`: optional boolean; use `true` only after local OCR is installed

Example:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/metadata-dry-run/pdf" \
  -F "file=@/absolute/path/to/document.pdf" \
  -F "document_type_code=acuse_sisub" \
  -F 'context_json={"client_legal_name":"CLIENTE DEMO, S.A. DE C.V.","provider_nomenclature":"SEGURIDAD PRI","upload_form_month":"Mayo"}' \
  -F "include_intelligence=true" \
  -F "enable_ocr=true"
```

## n8n Nodes

For an immediate visual smoke test in the n8n browser canvas, import:

```text
backend/fixtures/n8n/checkwise_pdf_metadata_dry_run_local_smoke_test.json
```

That workflow uses the clean SISUB sample PDF and the already-tested backend endpoint. It is intentionally a local smoke test: n8n reads a local PDF from disk, sends it to the backend with the HTTP Request node, and validates the safety gates.

After the smoke test passes, import the interactive upload workflow:

```text
backend/fixtures/n8n/checkwise_pdf_metadata_form_upload.json
```

That workflow opens an n8n-hosted form where you upload an individual PDF, choose the expected document type, and pass context fields to the backend. The current version is visually split into five segments:

- Upload intake
- CheckWise backend rulebook plus local OCR
- Safety gate
- AI suggestions
- Google Sheets audit row

Recommended workflow:

```text
Form Trigger or Webhook Trigger
  ->
Normalize upload context
  ->
HTTP Request to CheckWise metadata dry-run endpoint
  ->
Validate safety gates
  ->
Show or return review payload
```

The HTTP Request node should use:

- Method: `POST`
- Body Content Type: `multipart-form-data`
- File field name: `file`
- Text fields: `document_type_code`, `context_json`

## Safety Boundary

The endpoint does not use the database, AI, Google Sheets, external services, or production storage. It only writes the uploaded PDF to a temporary local file long enough to inspect deterministic file metadata, run optional local OCR, and build the review payload.

Every response must keep:

```json
{
  "legal_approval_allowed": false,
  "ai_used": false,
  "google_sheets_used": false,
  "external_services_used": false,
  "human_review_required": true
}
```

`ocr_used` is `false` by default. It may become `true` only when `enable_ocr=true`
and local Tesseract/Poppler OCR completes. AI and Sheets are n8n-side steps, not
backend-side steps.

## Local OCR Setup

Install the OCR toolchain once:

```bash
brew install tesseract tesseract-lang poppler
```

Confirm the commands are available:

```bash
which tesseract
which pdftoppm
tesseract --list-langs | rg '^(eng|spa)$'
```

The backend uses `pdftoppm` to rasterize the first pages and `tesseract` with
`spa+eng` when both languages are available.

## Credential Wiring

The importable workflow already contains the OpenAI and Google Sheets nodes, but
n8n cannot store your private credentials inside a repository JSON file. After
importing the workflow, wire these two credentials in n8n:

- OpenAI node: create/select an OpenAI credential named `OpenAI CheckWise Metadata`.
- Google Sheets node: create/select a Google Sheets OAuth2 credential named `Google Sheets CheckWise Metadata`.

For Sheets, also set the Spreadsheet ID in `Google Sheets - append google_sheets_row`.
The node currently uses this expression as a placeholder:

```text
{{ $env.CHECKWISE_GOOGLE_SHEET_ID || 'PASTE_SPREADSHEET_ID_HERE' }}
```

Either replace `PASTE_SPREADSHEET_ID_HERE` in n8n or launch n8n with:

```bash
CHECKWISE_GOOGLE_SHEET_ID="your-spreadsheet-id" npx n8n
```

## n8n Cloud / Browser Warning

n8n Cloud cannot call `localhost:8000` on your Mac. For n8n Cloud, use one of:

- a temporary tunnel such as cloudflared;
- a deployed dev backend URL;
- self-hosted n8n running locally.

For a temporary cloudflared tunnel:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

Use the printed `https://*.trycloudflare.com` URL in the workflow HTTP node:

```text
https://YOUR-TUNNEL.trycloudflare.com/api/v1/metadata-dry-run/pdf
```

For local/self-hosted n8n on the same machine, use:

```text
http://127.0.0.1:8000/api/v1/metadata-dry-run/pdf
```

If local self-hosted n8n blocks loopback requests with an SSRF warning, restart
n8n with loopback explicitly allowed:

```bash
N8N_SSRF_ALLOWED_IP_RANGES=127.0.0.0/8 npx n8n
```

## Verification

```bash
.venv/bin/pytest tests/test_metadata_rules.py
.venv/bin/pytest tests/test_pdf_metadata_dry_run_tool.py
.venv/bin/pytest tests/test_metadata_dry_run_api.py
```

## Local n8n Smoke Test

Use three terminals:

Terminal 1, backend:

```bash
cd /Users/josepablosamano/Desktop/Personal/legalshelf/checkwise/CheckWise/backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Terminal 2, n8n:

```bash
npx n8n
```

Browser:

```text
http://127.0.0.1:5678
```

Copy the local test PDFs into n8n's allowed file-read folder:

```bash
mkdir -p /Users/josepablosamano/.n8n-files/checkwise-test-pdfs
cp /Users/josepablosamano/Desktop/Personal/legalshelf/checkwise/test-pdfs/clean/*.pdf \
  /Users/josepablosamano/.n8n-files/checkwise-test-pdfs/
```

Then import:

```text
/Users/josepablosamano/Desktop/Personal/legalshelf/checkwise/CheckWise/backend/fixtures/n8n/checkwise_pdf_metadata_dry_run_local_smoke_test.json
```

Click `Execute workflow`. The final node should return `status: passed`.

If an older imported copy shows `Unrecognized node type: n8n-nodes-base.executeCommand`, delete that workflow from n8n and import the file again. The current workflow uses `Read Binary Files`, `HTTP Request`, and `Code`.

If `Read sample PDF` says file access is not allowed, the workflow is still pointing outside `/Users/josepablosamano/.n8n-files`. Re-import the current workflow file after copying the PDFs above.

If `Validate safety gates` says `Unsupported language: javascript`, delete the imported workflow and re-import the current workflow file. The current file uses n8n's expected `javaScript` value.

## Interactive Form Upload Test

After the smoke test passes, import:

```text
/Users/josepablosamano/Desktop/Personal/legalshelf/checkwise/CheckWise/backend/fixtures/n8n/checkwise_pdf_metadata_form_upload.json
```

In n8n:

1. Open the imported workflow.
2. Select the `Upload PDF form` node.
3. Click `Execute step` or `Execute workflow`.
4. Open the test form URL n8n provides.
5. Upload one PDF.
6. Select `acuse_sisub` or `acuse_icsoe`.
7. Submit the form.
8. Inspect `Validate safety gates`.

Expected final output:

```json
{
  "status": "passed"
}
```

The validation/summary nodes expose:

- `pdf_text_extraction`: local embedded-text extraction using `pypdf`
- `ocr_status`: local OCR status, engine, language, text length, and text sample
- `ai_extraction_request`: prompt/payload sent to the n8n OpenAI node
- `google_sheets_row`: flattened row sent to the n8n Google Sheets append node

The backend still does not approve documents or write to Sheets directly.
