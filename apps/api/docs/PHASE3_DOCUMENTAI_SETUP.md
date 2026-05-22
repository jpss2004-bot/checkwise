# Phase 3 — Google Document AI provisioning checklist

CheckWise prevalidation runs OCR via Google Document AI for any upload
where `inspect_pdf` reports `is_probably_scanned=True` (i.e. the PDF
has page count > 0 but pypdf extracted < 20 characters of text). OCR
runs **synchronously** during intake — the provider waits for the OCR
result before the verdict is returned.

This document is the one-time setup checklist. You run the manual GCP
steps; the backend reads the resulting credentials from environment
variables (Render dashboard for prod, `.env` for local).

## What this enables

- The `~1 in 40` scanned PDF in the fixture set (today:
  `masterclean-imss-comp-pago-bancario-2025-09.pdf`) gets readable
  text extracted; the detector can then run on it.
- Production scans no longer land in `pendiente_revision` with zero
  signals — the detector gets a fair shot at auto-prevalidating them.

## What this costs

Document AI **Document OCR** processor pricing (2026 list): **$1.50
per 1,000 pages** (first 1M pages/month). Most scanned PDFs are 1-3
pages, and only `~1 in 40` uploads is scanned in the current sample.
Ballpark: a tenant uploading 500 docs/month would spend $0.02/month.
We confirm via `Phase 3 metrics` (Phase 5) once it's wired up.

## Step 1 — Create or pick a Google Cloud project

You probably already have one for CheckWise. If not:

1. Visit https://console.cloud.google.com/
2. **Create Project** → name `checkwise-prod` (or whatever matches
   existing infra). Note the **Project ID** (lowercase, may differ
   from the project name).

## Step 2 — Enable Document AI

1. In the GCP console, search for **Document AI API**.
2. Click **Enable**. Wait ~30s for activation.
3. (Optional) Set up a billing alert at $10/month so you get an email
   if usage unexpectedly spikes.

## Step 3 — Create a processor

The **Document OCR** processor is the right choice for CheckWise —
generic OCR with layout preservation, no domain-specific training.
(We do *not* need Form Parser; we extract structured fields ourselves
in [document_intelligence.py](../app/services/document_intelligence.py)
after OCR.)

1. Navigate to **Document AI** → **Processors** → **+ Create Custom
   Processor**.
2. Pick **Document OCR**.
3. **Region**: `us` (lower latency from Render's Oregon region) unless
   you have a data-residency requirement that demands `eu`.
4. **Processor name**: `checkwise-ocr-prod` (and `checkwise-ocr-dev`
   if you want a separate dev processor — recommended; share would
   confuse cost telemetry).
5. Click **Create**. Wait ~10s for provisioning.
6. **Copy the Processor ID** from the processor detail page. It looks
   like `abc123def456789` (15 chars, all lowercase hex).
7. Note the **Location** (`us` or `eu`) — you'll need it for env vars.

## Step 4 — Create a service account

The backend authenticates as a service account, not as your user.

1. **IAM & Admin** → **Service Accounts** → **+ Create Service
   Account**.
2. Name: `checkwise-ocr`. Click **Create and Continue**.
3. **Grant role**: `Document AI API User`
   (`roles/documentai.apiUser`). This is the *minimum* role —
   it can run inference but cannot create / delete processors. Click
   **Continue** → **Done**.
4. On the service-account list, click the new account → **Keys** tab
   → **Add Key** → **Create New Key** → **JSON** → **Create**. The
   browser downloads `checkwise-ocr-<random>.json`.
5. **Treat this file like a password.** Never commit it. Render and
   any other deploy target read it via env var, not from disk in the
   repo.

## Step 5 — Set environment variables

The backend reads four values. Set them in **all** environments that
should run OCR (Render → Environment tab → Add):

| Variable | Value | Notes |
|---|---|---|
| `OCR_ENABLED` | `true` | Master switch. Leave unset/`false` to disable OCR (the pipeline falls back to today's behavior — scans go to `pendiente_revision`). |
| `GOOGLE_DOC_AI_PROJECT_ID` | (from Step 1) | The lowercase Project ID, e.g. `checkwise-prod`. |
| `GOOGLE_DOC_AI_LOCATION` | `us` or `eu` | Matches Step 3.7. |
| `GOOGLE_DOC_AI_PROCESSOR_ID` | (from Step 3.6) | The processor's 15-char hex ID. |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | (paste full JSON content from Step 4.4) | Render allows multi-line env values; paste the entire JSON. Locally, you can use `GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json` instead — the backend prefers `_JSON` if set, else falls back to the standard SDK path. |

### Render specifics

1. Render dashboard → CheckWise API service → **Environment** tab.
2. **+ Add Environment Variable** for each row above.
3. For `GOOGLE_APPLICATION_CREDENTIALS_JSON`, click the value field
   and paste the entire JSON (including curly braces). Render
   preserves newlines.
4. Click **Save Changes**. Render redeploys automatically.

### Local development

In `apps/api/.env` (do NOT commit):

```
OCR_ENABLED=true
GOOGLE_DOC_AI_PROJECT_ID=checkwise-dev
GOOGLE_DOC_AI_LOCATION=us
GOOGLE_DOC_AI_PROCESSOR_ID=abc123def456789
GOOGLE_APPLICATION_CREDENTIALS=/Users/yourname/.gcp/checkwise-ocr-dev.json
```

## Step 6 — Verify

After Render redeploys (or after a local `uvicorn` restart):

1. Upload the scanned fixture
   `apps/api/tests/fixtures/prevalidation/masterclean-imss-comp-pago-bancario-2025-09.pdf`
   via the provider portal against any IMSS recurring slot.
2. Open the resulting submission in the reviewer console.
3. Confirm `DocumentInspection.has_text=true` and
   `DocumentInspection.is_probably_scanned=true` (both — `is_probably_scanned`
   is preserved as a reviewer audit flag even after OCR succeeds).
4. Confirm `text_char_count` > 0 (was 0 before Phase 3).
5. The submission's status should now be either `prevalidado` (if
   confidence ≥ 0.7) or `pendiente_revision` (if lower); never
   `requiere_aclaracion`.

## Rollback

Set `OCR_ENABLED=false` (or unset) and redeploy. The backend skips
OCR entirely and reverts to today's behavior — scanned uploads land
in `pendiente_revision` with empty text. No data is lost; existing
`DocumentInspection` rows retain their OCR'd text from prior runs.

## Cost monitoring

Phase 5 will expose a `/admin/prevalidation/stats` endpoint with
"OCR calls (7-day)" and "OCR pages billed (7-day)" tiles. Until then,
GCP Console → **Billing** → **Reports** → filter to **Document AI**
shows running spend.

## Troubleshooting

| Symptom | Diagnosis |
|---|---|
| OCR is skipped silently in prod | `OCR_ENABLED` is unset or non-truthy. Check the env tab. |
| `403 PermissionDenied` in API logs | Service account is missing the `Document AI API User` role, or you're hitting the wrong location. |
| `404 Processor not found` | `GOOGLE_DOC_AI_PROCESSOR_ID` or `GOOGLE_DOC_AI_LOCATION` doesn't match the processor you created. |
| OCR call takes > 10s | Document AI is occasionally slow on a cold processor. The backend uses a 30s timeout; uploads should still succeed. If consistent, raise a Phase 3 follow-up. |
| `Invalid credentials` on boot | `GOOGLE_APPLICATION_CREDENTIALS_JSON` has been mangled by the Render UI (extra escaping). Re-paste from the original `.json` file. |

## Open follow-ups (deferred to Phase 5)

- Cost telemetry tile on the admin dashboard.
- Per-tenant OCR rate limit (in case a misconfigured workspace
  uploads thousands of scans in a burst).
- Async OCR fallback: if the synchronous OCR call exceeds N seconds,
  persist intake with `status=pendiente_revision` and queue a job to
  finish OCR in the background. Today's implementation is fully
  synchronous; we'll revisit when we have real latency data.
