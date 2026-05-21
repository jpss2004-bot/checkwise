# Stage 2.7 — Provider upload usability · ship notes

**Status:** authored 2026-05-20. Backend + frontend + tests landed in a single phase per Jose Pablo's direction; commits split per logical surface per the standing workflow.
**Companion docs:**
- [HANDOFF_2026-05-20.md](./HANDOFF_2026-05-20.md) — the session that authored Stage 2.7.
- [PROVIDER_EXPERIENCE_IMPROVEMENT_PLAN.md](./PROVIDER_EXPERIENCE_IMPROVEMENT_PLAN.md) §20 — the staged-roadmap update.
- [../provider-feedback-transcript/PROVIDER_TRANSCRIPT_FEEDBACK_MAP.md](../provider-feedback-transcript/PROVIDER_TRANSCRIPT_FEEDBACK_MAP.md) — themes T2, T4, T5.

---

## 1. What shipped

Stage 2.7 closes three transcript themes in one phase:

| Theme | Title | Surface |
|---|---|---|
| T5 (parity) | `RecurringRequirement` first-upload guidance | Backend catalog + calendar endpoint + calendar drawer |
| T2 | Provider self-submitted correction requests | Backend endpoint + Slack notification + Tier B form on `/portal/entra-a-tu-espacio` |
| T4 | Multi-document submission (1 Submission → N Documents) | Backend endpoint (flag-gated) + intake wizard additional-files block |

Each surface is described below with the exact files touched, the contract decisions, and the locked behavior.

---

## 2. T5 parity — `RecurringRequirement` first-upload guidance

**Why:** Onboarding requirements have shipped anatomy / where_to_obtain / common_errors since Stage 2 (BL-002). The transcript T5 asks for the same shape on the recurring calendar so the calendar drawer reads identically to the onboarding expediente card.

**Backend ([apps/api/app/core/compliance_catalog.py](../../../apps/api/app/core/compliance_catalog.py)):**

- Added three fields to `RecurringRequirement`: `anatomy: str`, `where_to_obtain: str`, `common_errors: tuple[str, ...]`. All default to empty so generated catalog rows stay compatible.
- New per-institution defaults: `_RECURRING_DEFAULT_ANATOMY`, `_RECURRING_DEFAULT_WHERE`, `_RECURRING_DEFAULT_COMMON_ERRORS`. Framed around periodicity (not document identity) so the same paragraph reads cleanly across every monthly / bimestral / cuatrimestral slot.
- New per-doc-name overrides: `_RECURRING_DOC_OVERRIDES` keyed by `(institution, doc_name)`. Authored content for the highest-volume items the handoff §2.7-c called out:
  - IMSS — `Cuotas obrero patronales`, `Resumen de liquidación`
  - INFONAVIT — `Cuotas obrero patronales`, `Resumen de liquidación`
  - SAT — `Declaración ISR por retención sueldos y salarios`, `Comprobante entero pago ISR`, `Acuse declaración anual de impuestos`
  - STPS — `Acuse SISUB`, `Acuse ICSOE`
- New accessor functions: `recurring_anatomy(req)`, `recurring_where_to_obtain(req)`, `recurring_common_errors(req)`. Resolution order is instance field → per-doc override → institution default.
- Exported in `__all__` alongside the existing onboarding accessors.

**API ([apps/api/app/api/v1/portal.py](../../../apps/api/app/api/v1/portal.py)):**

The calendar endpoint (`GET /api/v1/portal/workspaces/{id}/calendar`) now emits three new fields on each item:

```jsonc
{
  "code": "REC-IMSS-2026-02-cuotas-obrero-patronales",
  // ... existing fields ...
  "anatomy": "Resumen mensual del IMSS …",
  "where_to_obtain": "Descárgalo del portal IDSE …",
  "common_errors": [
    "Subir la cédula de un mes que no es el que pide el calendario.",
    "..."
  ]
}
```

**Frontend:**

- [apps/web/lib/api/portal.ts](../../../apps/web/lib/api/portal.ts) — added the three fields on `CalendarItem`.
- [apps/web/components/checkwise/portal/expediente-card.tsx](../../../apps/web/components/checkwise/portal/expediente-card.tsx) — extracted `DocumentGuidanceDisclosure` to a public exported surface that takes `{anatomy, where_to_obtain, common_errors, summary_label?}`. Backward-compatible: the existing in-page call site uses the new prop signature.
- [apps/web/app/portal/calendar/page.tsx](../../../apps/web/app/portal/calendar/page.tsx) — `CalendarEntry` carries the three new fields; the drawer renders the shared disclosure with a periodicity-aware label "Acerca de este comprobante".

**Tests ([apps/api/tests/test_portal_canonical_enrichment.py](../../../apps/api/tests/test_portal_canonical_enrichment.py)):**

- `test_calendar_items_carry_anatomy_where_to_obtain_common_errors` — every calendar item ships non-empty guidance with at least an institution fallback.
- `test_calendar_priority_items_carry_authored_per_doc_overrides` — IMSS / INFONAVIT / ISR mensual / SAT acuse anual / SISUB / ICSOE all carry the per-doc copy (≥ 5 common-error bullets, override-specific anatomy markers).
- `test_calendar_guidance_no_engineer_dialect_leaks` — banned strings (`SHA-256`, `hash`, `OCR`, `anomaly`, `pipeline`, `parser`) never appear in calendar guidance.
- `test_recurring_catalog_helpers_resolve_in_priority_order` — accessor resolution rules pinned (instance → override → institution default).

---

## 3. T2 — Correction request endpoint + form mount

**Locked decision (Tier B):** providers can self-submit corrections only for `contact_email`, `contact_phone`, `contact_name`. RFC, razón social and contract reference stay support-only; the endpoint returns 422 with a "contact support" Spanish message for anything outside that whitelist.

**Backend ([apps/api/app/services/correction_request_service.py](../../../apps/api/app/services/correction_request_service.py)) — new service module:**

- `TIER_B_FIELDS: frozenset[str]` — the locked whitelist.
- `TIER_B_FIELD_LABEL_ES: dict[str, str]` — Spanish labels used in the response and Slack payloads.
- `record_and_check_rate(user_id)` — in-memory sliding-window rate limit (5 requests / hour / user). Reset hook for tests.
- `create_correction_request(...)` — persists the request as a single `audit_log` row with `action="correction_request.submitted"`, `actor_type="provider"`, before/after carrying the current/proposed values, metadata carrying the reason + message + ip_hash + user_agent + status.
- `deliver_to_slack(correction_id, snapshot)` — best-effort POST to `SLACK_CORRECTION_WEBHOOK_URL`. Mirrors the `contact_service.py` shape: stdlib `urllib`, Block Kit body, never raises. Failures log at WARNING.
- `slack_payload_snapshot(...)` — builds the small dict the BackgroundTask closes over.

**Config ([apps/api/app/core/config.py](../../../apps/api/app/core/config.py)):**

- New `SLACK_CORRECTION_WEBHOOK_URL: str = ""` setting. Empty (default) → audit-log persistence only, no error.

**Endpoint ([apps/api/app/api/v1/portal.py](../../../apps/api/app/api/v1/portal.py)):**

```
POST /api/v1/portal/workspaces/{workspace_id}/correction-requests
```

Request body (JSON):

```jsonc
{
  "field": "contact_email" | "contact_phone" | "contact_name",
  "current_value": "viejo@correo.mx",
  "proposed_value": "nuevo@correo.mx",
  "reason": "…",
  "message": "…"   // optional
}
```

Response (202 Accepted):

```jsonc
{
  "id": "<audit_log.id>",
  "field": "contact_email",
  "status": "pending",
  "created_at_iso": "2026-05-20T…"
}
```

Error contract:
- `422` — field outside Tier B (with a "contact support" Spanish detail), proposed equals current, missing reason, or empty proposed.
- `429` — rate limit (5/hour/user).
- `401` — legacy `X-Workspace-Token` path (no user identity) is rejected explicitly; correction requests need an actor.

**Frontend:**

- [apps/web/lib/api/corrections.ts](../../../apps/web/lib/api/corrections.ts) — new real API client. Exports `TIER_B_FIELDS`, `TIER_B_FIELD_LABEL_ES`, `submitCorrectionRequest`. Mirrors the existing portal API auth resolution (`Authorization: Bearer` + `credentials: "include"`). The legacy `apps/web/lib/mock/corrections.ts` stays in the tree — it still backs the inline editable profile on the same page — but the correction-request flow no longer touches it.
- [apps/web/components/checkwise/workspace/correction-request-form.tsx](../../../apps/web/components/checkwise/workspace/correction-request-form.tsx) — rewritten. Field selector is restricted to the three Tier B fields. Submission calls the real API client. Always-on info alert pointing providers to `soporte@checkwise.mx` for non-Tier-B changes.
- [apps/web/app/portal/entra-a-tu-espacio/page.tsx](../../../apps/web/app/portal/entra-a-tu-espacio/page.tsx) — mounted the form as a new "Solicitar corrección de un dato de contacto" section below the existing inline-editable profile form.

**Tests ([apps/api/tests/test_portal_correction_requests.py](../../../apps/api/tests/test_portal_correction_requests.py)):**

17 tests covering: Tier B happy paths (each of the three fields), audit-log row shape, non-Tier-B rejection (every field outside the whitelist), no-change rejection, missing-reason rejection, empty-proposed rejection, rate-limit transition (5 OK → 6th 429), cross-workspace tenant guard, Slack-disabled fallback.

---

## 4. T4 — Multi-document submission (1 Submission → N Documents)

**Locked caps (Jose Pablo, 2026-05-20):**
- N ≤ 5 files per submission (1 primary + up to 4 annexes).
- ≤ 30 MB aggregate per submission. Per-file cap stays at the existing 15 MB.
- Atomic semantics: all-or-nothing per submission. Any failure rolls back the entire submission and best-effort cleans up storage writes.
- Feature flag: `MULTI_FILE_UPLOAD_ENABLED` (backend) + `NEXT_PUBLIC_MULTI_FILE_UPLOAD_ENABLED` (frontend). Both default `false` — single-file path stays canonical until ops flips the flag.

**Backend ([apps/api/app/services/submission_service.py](../../../apps/api/app/services/submission_service.py)):**

- New `finalize_multi_document_submission(db, *, stored_files: list[StoredFile], …)` helper. Creates 1 `Submission` with N `Document` children, runs the full per-document pipeline (PDF inspection → classifier signals → `Validation` rows → `DocumentStatusHistory` → native-intake `ValidationEvent` timeline → audit log) inside one DB transaction.
- Submission overall status = worst-case across documents (`REQUIERE_ACLARACION` > `POSIBLE_MISMATCH` > `PENDIENTE_REVISION`), preserving the existing single-file derivation rule.
- Audit metadata carries `multi_file_upload=True`, `document_count`, `total_size_bytes`, `storage_keys`, `sha256_list`.
- The single-file `finalize_intake_submission` is untouched — every existing test path stays green.

**Schemas ([apps/api/app/schemas/submissions.py](../../../apps/api/app/schemas/submissions.py)):**

- New `DocumentBatchEntry` — per-document detail (document_id, filename, sha256, storage_key, status, inspection, signals, validations, events).
- New `MultiSubmissionResponse` — `{submission_id, status, documents[], support, message}`.

**Endpoint ([apps/api/app/api/v1/portal.py](../../../apps/api/app/api/v1/portal.py)):**

```
POST /api/v1/portal/workspaces/{workspace_id}/submissions/batch
```

Multipart form fields mirror the single-file `/submissions` endpoint (`period_code`, `period_key`, `load_type`, `institution_code`, `requirement_name`, `requirement_code`, `comments`, `initial_status`, `supersedes_submission_id`). The file field changes from `file: UploadFile` to `files: list[UploadFile]`. Behavior:

- Flag off → 404 with a plain-Spanish "no está disponible aún" detail.
- Empty `files` → 422.
- Count > 5 → 422.
- Aggregate > 30 MB → 413 with the cap surfaced in MB.
- Non-PDF in batch → 400, whole batch rejected, no submission written.
- Storage write fails mid-batch → DB rollback + best-effort storage cleanup via `storage.delete(...)` when the backend exposes it.

**Frontend ([apps/web/components/checkwise/intake-wizard.tsx](../../../apps/web/components/checkwise/intake-wizard.tsx)):**

- New `additionalFiles: File[]` state + `additionalFilesError` state, both empty by default.
- Helpers `validateMultiFileAggregate`, `addAdditionalFiles`, `removeAdditionalFile`.
- New "¿Necesitas adjuntar más archivos a esta misma entrega?" section under the primary dropzone in `UploadStep`. Flag-gated. Multi-file input, per-file list with size + remove button.
- Submit fork: when the flag is on AND `additionalFiles.length > 0`, the form posts to `/submissions/batch` and the success view consumes the `MultiSubmissionResponse` by synthesizing a `SubmissionResponse` from the first document (so step 4 doesn't need a parallel branch). Single-file path is byte-for-byte identical to before the change.

**Tests ([apps/api/tests/test_portal_multi_file_upload.py](../../../apps/api/tests/test_portal_multi_file_upload.py)):**

8 tests covering: feature-flag-off 404, happy-path 3-file submission (1 Submission → 3 Documents, per-doc validations + status history + audit-log markers), worst-case status aggregation, file-count cap, aggregate-size cap, non-PDF rejection (whole batch), empty-files rejection, replacement-lineage with a multi-doc batch.

---

## 5. Verification

- Backend: `pytest tests/ -q` → 546 passed (was 521 before Stage 2.7; +25 new tests).
- Backend: `ruff check` on every touched file → clean.
- Frontend: `npx tsc --noEmit` → clean (ignoring pre-existing stale `.cw-next-*` duplicate-identifier noise from cached generated types).
- Frontend: `npx next lint --file <each touched file>` → clean.
- Frontend: dev server compiled `/portal/entra-a-tu-espacio`, `/portal/upload`, `/portal/calendar` → all 200, no console errors. Portal routes redirect anonymous visitors to `/login` so the form + wizard cannot be visually walked without a seeded portal session (handoff §7).

---

## 6. Feature flags + rollout

| Flag | Default | When to flip |
|---|---|---|
| `MULTI_FILE_UPLOAD_ENABLED` (backend) | `false` | Together with the frontend flag, once ops confirms storage + DB capacity for 30 MB aggregate uploads. |
| `NEXT_PUBLIC_MULTI_FILE_UPLOAD_ENABLED` (frontend) | `false` | Same. |
| `SLACK_CORRECTION_WEBHOOK_URL` (backend) | empty | Whenever ops wants Slack notifications. Endpoint persists the audit_log row regardless of webhook state. |

Rollback plan for multi-file: flip both flags back to `false`. The endpoint returns 404, the wizard hides the annex section, the legacy single-file path continues to work — no redeploy required.

---

## 7. Out of scope (deferred)

- Visual screenshot proof. Portal routes require an authenticated session that this environment cannot mint; static verification + per-route 200 compilation was the available signal.
- The legacy `apps/web/lib/mock/corrections.ts` still backs the inline-editable profile on `/portal/entra-a-tu-espacio`. Migrating that surface to a real backend endpoint is its own track (not Tier B — those are first_name / last_name / phone / job_title / contact_preference).
- Admin triage UI for correction requests. The audit_log row is queryable via existing admin tooling; a dedicated tray can land as a follow-up if ops needs one.
- Privacy notice + the full correction-request backend writeback workflow remain on Stage 2.8 (gated on legal copy from Paco / Beko).

---

*End of Stage 2.7 ship notes.*
