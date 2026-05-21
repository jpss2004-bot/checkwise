# CheckWise — Admin QA Audit

## Objective

Audit and QA the entire admin-facing surface of CheckWise end-to-end and
confirm whether the improvements landed for the provider portal in
Stages 1 and 2 (and the wider BL-T1 → BL-T9 transcript feedback) are
correctly reflected on the internal/legal/admin side. This is a
QA + parity + implementation-readiness audit, not a redesign.

## Scope

- All routes under `app/admin/*` plus admin-only shared components.
- Backend admin API (`apps/api/app/api/v1/admin.py`), reviewer API
  (`apps/api/app/api/v1/reviewer.py`), and the cross-role surfaces those
  pages mount (reports list, report editor, submission timeline,
  reviewer decision panel).
- Provider-side improvements only insofar as they have an admin
  counterpart (presets, error states, Spanish labels, period limits,
  REPSE-date hardcoding, XML acceptance, mismatch surfacing, rejection
  causes, correction requests, automatic document identification,
  timeline/process language).

Out of scope: redesign work, schema migrations, AI classifier retraining,
new auth flows, legal copy authorship.

## Date / commit

- Date: 2026-05-20
- Branch: `main`
- Commit at audit start: `ba3d7c7e00fe3cc4df752c9e22e1adaf977348d7`
- Repo: `jpss2004-bot/checkwise`

## Routes discovered

| Route | Purpose | Role gate | Data source | Key components | Tested |
|---|---|---|---|---|---|
| `/admin` (page.tsx) | Internal landing — surfaces, operations launcher, session card. | `internal_admin` and/or `reviewer` (via session in localStorage) | `readAdminSession()` (no API call) | `BrandLogo`, `Card`, `Badge` | ✅ |
| `/admin/login/page.tsx` | Marker route for redirects; relies on `/login` | none (redirect) | n/a | n/a | ✅ |
| `/admin/_shell.tsx` | Header + horizontal nav + drawer, role guard, feedback launcher. | `internal_admin` or `reviewer` | session only | `BrandLogo`, `MetadataStrip`, `FeedbackLauncher` | ✅ |
| `/admin/dashboard` | Operative summary, semaphore, signal list, ops launcher. | shell guard | `getAdminOverview()` | `RadialGauge`, `MetadataStrip`, `ErrorState`, `Skeleton` | ✅ |
| `/admin/clients` | Catalogue + create/edit clients. | shell guard | `listClients`, `createClient`, `updateClient` | `DataTable`, `Surface` | ✅ |
| `/admin/vendors` | Catalogue + create/edit providers, RFC-locked on edit. | shell guard | `listVendors`, `listClients`, `createVendor`, `updateVendor` | `DataTable`, `Surface` | ✅ |
| `/admin/requirements` | Regulatory requirement catalogue. | shell guard | `listRequirements`, `createRequirement`, `updateRequirement` | `DataTable`, `Surface` | ✅ |
| `/admin/calendar` | Yearly REPSE catalogue + period rows. | shell guard | `getAdminCalendar`, `listPeriods` | `MiniBars`, `Surface`, `MetadataStrip` | ✅ |
| `/admin/reviewer` | FIFO review queue, status filter tabs. | `reviewer` or `internal_admin` | `getReviewerQueue` | `Tabs`, `Table`, `EmptyState`, `ErrorState`, `RequirementStatusBadge` | ✅ |
| `/admin/reviewer/[submission_id]` | Submission detail — signals, lineage, timeline, decision. | `reviewer` or `internal_admin` | `getReviewerSubmission`, `submitDecision` | `ReviewDecisionPanel`, `SubmissionTimeline`, `RequirementStatusBadge`, `SubmissionDetailSkeleton` | ✅ |
| `/admin/reports` | Internal reports list — shares `ReportsListView`. | shell guard + reports RBAC | `listPresets`, `listReports` | `ReportsListView` (R2) | ✅ |
| `/admin/reports/[id]` | Editor — shares `ReportEditor`. | shell guard + reports RBAC | report endpoints | `ReportEditor` | ✅ |
| `/admin/contact-requests` | Landing-form lead triage (`new → reviewed → contacted → closed`). | shell guard | `listContactRequests`, `updateContactRequestStatus` | `DataTable`, `Select` | ✅ |
| `/admin/feedback-reports` | Bug/improvement triage from in-app launcher. | shell guard | `listFeedbackReports`, `updateFeedbackReportStatus`, `getFeedbackReport` | `DataTable`, `Dialog`, `Select`, `Field`, `Textarea` | ✅ |
| `/admin/audit-log` | Generic audit-event explorer with 4 filters. | shell guard | `listAuditLog` | `DataTable`, `Input`, `Label` | ✅ |
| `/client/*` (linked from admin home) | Client preview — same gating as admin via session | shell guard (separate `client/_shell.tsx`) | `lib/api/admin.ts` overlap | `ReportsListView`, `DataTable` | partial — out of strict admin scope |

### Backend admin / reviewer / cross-role endpoints

- `GET /admin/overview` — dashboard counters.
- `GET /admin/clients`, `POST /admin/clients`, `PATCH /admin/clients/{id}` — clients CRUD.
- `GET /admin/vendors`, `POST /admin/vendors`, `PATCH /admin/vendors/{id}` — vendors CRUD.
- `GET /admin/requirements`, `POST /admin/requirements`, `PATCH /admin/requirements/{id}` — catalogue CRUD.
- `GET /admin/periods?year=&period_type=` — clamped to `[MIN_YEAR=2021, MAX_YEAR=2099]`.
- `GET /admin/calendar?year=&persona_type=` — same clamps, default year hardcoded to `2026`.
- `GET /admin/contact-requests` + `PATCH /admin/contact-requests/{id}`.
- `GET /admin/feedback-reports` (+`/{id}` detail) + `PATCH /admin/feedback-reports/{id}`.
- `GET /admin/audit-log` — filterable.
- `GET /reviewer/queue`, `GET /reviewer/submissions/{id}`, `POST /reviewer/submissions/{id}/decision`.
- Reports: `GET /reports/_presets`, `GET /reports`, `GET /reports/{id}`, `POST /reports`, `PATCH /reports/{id}`, plus executor endpoints — all shared across roles, tenant-locked at the actor builder.
- Provider correction requests: `POST /portal/workspaces/{id}/correction-requests` — writes an `audit_log` row + Slack-best-effort delivery. **No paired admin GET/triage endpoint.**

## Workflows tested

Static QA only (live admin session not provisioned in this environment — see Screenshots section). The audit relies on reading every page component end-to-end against the backend it calls.

For each route I checked: route guard, data-load path, retry path, skeleton vs empty vs error states, presence of period clamps, technical-vs-friendly copy, mismatch surfacing, rejection action flow, audit-trail visibility, accessibility hints (aria-labels), and shared-component reuse.

## Admin reports audit

- `/admin/reports` correctly mounts the shared `ReportsListView` with `role="admin"` and `showAudienceFilter`. The preset-load failure path is now visible (BL-008): a separate `<Alert variant="warning">` with a Reintentar button shows when `listPresets()` returns non-401/403 errors. Empty vs failed presets are distinct. ✅
- `/admin/reports/[id]` mounts the shared `ReportEditor`. Print route is intentionally `/portal/reports/{id}/print` (chrome-less, shared). ✅
- Filter set: status + audience + title-search + sort. Sort change is client-side over the server-paginated set. ✅
- Soft issue: the AI-prompt placeholder inside `report-editor.tsx:566` says `"ej. Genera un resumen REPSE de mayo 2026 para los proveedores con SAT pendiente."` — still hardcoded year. Low risk because it's example copy and the prompt itself isn't materialised, but it will read stale in 2027. Flagged as **P2** (`A-016` in backlog), not auto-fixed.

## Admin document review audit

- Queue (`/admin/reviewer`) uses FIFO ordering by age, four-tab filters (`Todos / Por revisar / Posible mismatch / Aclaración`). Mismatch tab includes both `has_mismatch=true` rows and rows whose status is `posible_mismatch`. ✅
- Mismatch is visually surfaced — small "Mismatch" pill under the status badge in the row. ✅
- Detail (`/admin/reviewer/[submission_id]`) reuses `<SubmissionTimeline>` so the reviewer sees the same triple-trail (status / events / replacement lineage) the provider sees. Lineage strip uses linked submission ids. ✅
- **P0 finding:** the `ReasonsCard` (line 329-358) renders `r.rule_code` as the primary signal title (`title={r.rule_code}`). On the provider portal the equivalent card uses a `REASON_TITLES` Spanish map and `lib/constants/validation.ts::validationLabel()` already exists for this. Reviewers currently see raw `file_exists`, `pdf_readable_text`, `duplicate_hash` etc. as primary labels. → Fix applied (see "Small fixes applied" below).
- `TraceabilityCard` exposes `SHA-256` and the document filename. This is a labeled diagnostic card, so it conforms to the user's instruction: "admin-facing views may expose more detail in controlled diagnostic areas." No change.
- Decision panel exposes four actions: Aprobar / Rechazar / Pedir aclaración / Excepción legal — each gated by a confirm dialog and (where applicable) a required reason field. The reason is free text. No structured taxonomy of legally meaningful rejection causes. **P1 gap** (`A-005`).

## Admin validation / timeline audit

- `<SubmissionTimeline>` already translates the major event types via `EVENT_LABEL` (`pdf_validation`, `document_intelligence`, `duplicate_check`, `intake_received`, `reviewer_decision`, etc.) and actor types via `ACTOR_TYPE_LABEL`. Plain Spanish on both surfaces. ✅
- The shared `RequirementStatusBadge` has 11 distinct STATUS_LABELS + STATUS_DESCRIPTIONS in plain Spanish — admin queue, admin detail, and provider portal all consume it. ✅
- Edge: not every emitted rule_code has a Spanish entry in `VALIDATION_RULE_LABELS_ES`. Missing in the central map: `native_intake`, `canonical_requirement_code`, `canonical_period_key`, `submission_replacement`. These are normally `info` severity and filtered out of `reasons`, but worth tracking. **P2** (`A-014`).

## Provider / admin parity findings

### Provider improvements already reflected on admin
- BL-001 / R2 — reports preset gallery + load-failure alert. Admin reuses the same `ReportsListView` so admins benefit immediately.
- BL-003 / Stage 1 — Spanish labels are present in shared `RequirementStatusBadge`, `SubmissionTimeline` event labels, `VALIDATION_RULE_LABELS_ES` map.
- BL-T6 — XML acceptance is documented and the admin intake surfaces enforce `.pdf` only (`assert_pdf_upload`).
- BL-T7 / BL-T8 — backend `validate_year` / `validate_period_key` is wired on `/admin/periods`, `/admin/calendar`, `/portal/...` and clamps to `[2021, 2099]`. The reviewer queue does not take a year param so it is unaffected.
- BL-T8b — `_compute_semaphore` and `dashboard_compute.compute_semaphore` both already implement the "0/N → red" honesty branch so admins viewing the client preview see the same honest level.
- BL-T9 — prevalidation `message` strings are now plain Spanish without byte/hash/OCR leaks; reasons rendered from `detail.reasons[].message` therefore read clean.

### Provider improvements **missing** from admin
- Spanish rule labels in the reviewer **reasons** card — Stage 1 fixed the provider surface; admin still rendered `rule_code` as primary. (P0, fixed by this audit.)
- Period floor on the admin/client calendar year input — `<Input type="number" min={2024}>` is stricter than the backend (2021) and excludes legitimate REPSE periods 2021-2023. (P0, fixed by this audit.)
- Dynamic year on the backend `/admin/calendar` default — still hardcoded `year: int = 2026`. (P1, fixed by this audit.)
- Provider correction-request triage — backend writes `audit_log` rows with action `correction_request.submitted` but there is no `/admin/correction-requests` (or equivalent) UI to surface them. Admins must hand-query the generic audit-log filter to see them. (**P1**, `A-001`.)
- Structured rejection-cause taxonomy — provider sees a single free-text "razón"; legally meaningful causes are not curated. (**P1**, `A-005`.)
- Stage 2 onboarding-card "Acerca de este documento" disclosure — admins reviewing a submission see the requirement name but not the same anatomy / where-to-obtain / common-errors guidance to inform a decision. Soft P2 (`A-008`).
- Client RFC editability — vendor edit form correctly locks RFC; client edit form does not. (P1, `A-002`.)

## Bugs found

| ID | Title | Severity | Route / File |
|---|---|---|---|
| A-003 | Raw `rule_code` rendered as primary signal title on `/admin/reviewer/[submission_id]` (Spanish labels missing). | P0 | `apps/web/app/admin/reviewer/[submission_id]/page.tsx:351` |
| A-004 | Admin/Client calendar year input floors at 2024, excluding 2021-2023 REPSE periods that the backend accepts. | P0 | `apps/web/app/admin/calendar/page.tsx:93`, `apps/web/app/client/calendar/page.tsx:108` |
| A-010 | Backend `/admin/calendar` default `year=2026` is hardcoded and will silently age. | P1 | `apps/api/app/api/v1/admin.py:841` |

## UX issues found

| ID | Title | Severity |
|---|---|---|
| A-005 | No structured taxonomy of legally meaningful rejection causes; reviewer types free text every time. | P1 |
| A-006 | "Empty" copy on `/admin/reports` preset gallery says "Aún no hay reportes disponibles para tu cuenta" — fine for unauthorised roles but reads identical to a genuine empty seed; distinct copy + a tester-visible hint of which seed is missing would help. | P2 |
| A-007 | The reviewer "razón obligatoria" textarea (`ReviewDecisionPanel`) gives a free-form prompt without any examples in copy beyond a single placeholder line. Reviewers benefit from suggested cause chips. | P2 |
| A-008 | Reviewer detail does not surface the requirement-level "anatomía / cómo obtenerlo / errores comunes" guidance from `compliance_catalog.py` that the provider sees on the expediente cards. | P2 |
| A-015 | Admin dashboard uses "workspaces" in the visible caption + signal label. Internal vocabulary is acceptable per visual-direction tier lock, but a tooltip explaining the term would help legal/ops staff who don't read code. | P3 |

## Security / privacy issues found

| ID | Title | Severity |
|---|---|---|
| A-002 | `/admin/clients` edit form lets an admin edit the RFC (legal identifier) with no warning, confirmation, or rationale capture beyond the generic audit log. The matching vendor form correctly hides RFC on edit; this is an inconsistency, not a deliberate decision. | P1 |
| A-009 | Reviewer `TraceabilityCard` shows SHA-256 + filename — by spec acceptable in a labeled diagnostic area, but the label could be more explicit (e.g. "Datos técnicos · sólo para diagnóstico") to keep the operator separation crisp. | P3 |
| A-013 | XML acceptance is correctly blocked at the upload boundary, but the user-facing copy on the admin/reviewer error path is not exercised because admins do not upload. No action required; documented in `docs/audits/slack-feedback-triage/...` and acceptable. | — |

## Data / modeling issues found

| ID | Title | Severity |
|---|---|---|
| A-011 | Hardcoded fallback string `"Pendiente de semilla completa desde matriz regulatoria REPSE 2026."` in `apps/api/app/services/requirement_service.py:153`. Surfaces as `legal_basis` when the catalog is incomplete, and quietly ages. | P2 |
| A-012 | Missing entries in `apps/web/lib/constants/validation.ts::VALIDATION_RULE_LABELS_ES`: `native_intake`, `canonical_requirement_code`, `canonical_period_key`, `submission_replacement`. Falls back gracefully but a forgotten entry stands out in QA as raw snake_case. | P2 |

## Report / export issues found

- Reports list, editor, and execution share one shell across roles. The R1.0 + R2 hardening that landed for BL-001 / BL-008 applies to admin without further work. No new issues found here.
- Print route at `/portal/reports/{id}/print` is chrome-less and identical across roles — confirmed by the admin route handing it through directly.

## Period / date issues found

- Backend validators (`validate_year`, `validate_period_key`) enforce `[2021, 2099]` consistently — `/admin/periods`, `/admin/calendar`, `/portal/...` all import them.
- **Frontend floor on the calendar year input is 2024**, both admin and client preview surfaces. → Fixed (see "Small fixes applied").
- **Backend default `year=2026` on `/admin/calendar`** is hardcoded. → Fixed (see "Small fixes applied").
- Report-editor placeholder string "mayo 2026" — not fixed, deferred to **P2** (`A-016`).
- `requirement_service.py` `legal_basis` fallback "REPSE 2026" — not fixed, deferred to **P2** (`A-011`).

## XML / file-validation findings

- `apps/api/app/services/submission_service.py:54-67` rejects anything that does not end in `.pdf` and a non-PDF MIME type. Error copy is plain Spanish: "En esta fase solo se aceptan archivos PDF."
- `apps/api/app/api/v1/metadata_dry_run.py` is a local-only n8n endpoint with no production admin UI consumer. No admin auth bypass observed.
- Frontend intake (`components/checkwise/intake-wizard.tsx`, `components/checkwise/document-submission-form.tsx`) sets `accept=".pdf,application/pdf"` and shows a plain-Spanish error on non-PDF.
- Decision: XML stays blocked. Documented at `docs/audits/.../HANDOFF_2026-05-20.md` (BL-T6).

## Rejection-cause findings

- `ReviewDecisionPanel` collects a single free-text reason for `reject`, `request_clarification`, and `mark_exception`. The user-facing dialog body says: "El documento se devolverá al proveedor con tu razón."
- No selectable list of common legal-grade causes (RFC mismatch, periodo incorrecto, sello inválido, opinión incumplida, firmas faltantes, etc.).
- Provider visibility: the reason is shown to the provider in the submission detail. So free text + reviewer discretion is the de-facto truth, and there is no admin reporting that says "how many rejections last month cited RFC mismatch?"
- **Recommendation:** add a curated chip list of common causes that prepopulates the textarea. Keep the textarea editable so a reviewer can still type a custom reason. Optional: persist the chosen cause code separately so audit/reporting can aggregate. **P1**, `A-005`.

## Automatic document identification findings

- Detection lives in `apps/api/app/services/document_intelligence.py`. Surfaces:
  - `inspection.mismatch_reason` (string) → shown as "Posible mismatch" on the reviewer detail and provider detail (`ReasonsCard`).
  - `Submission.status = posible_mismatch` → reviewer queue mismatch tab and `RequirementStatusBadge`.
  - `Validation` rows with `severity=warning|error` reach `detail.reasons`.
- Whether the detection is "rule-based, heuristic, OCR-based, or AI-assisted" is not surfaced to the reviewer beyond the `event_type` in the timeline (e.g. `pdf_validation`, `document_intelligence`). For a reviewer audit trail this is acceptable; for confidence calibration we could expose `confidence` on each event row more prominently. **P2** (`A-008` covers reviewer-side guidance, `A-018` for confidence presentation).
- The honesty fix BL-T8b ensures a "100% verified compliance" headline cannot appear while obligations remain unscored. The reviewer queue surfacing of `posible_mismatch` ensures an obviously wrong document does NOT silently approve to clean status; a human must call it.

## Timeline / process language

- `<SubmissionTimeline>` is shared. Provider and admin both get plain-Spanish event labels via `EVENT_LABEL`. Actor labels are plain-Spanish via `ACTOR_TYPE_LABEL`. Severity tones are mapped to design tokens.
- Technical leakage in admin-only diagnostic cards (SHA-256, filename, sizes) is intentional and bounded. Reviewer detail labels them "Trazabilidad," which is a known diagnostic area.
- Reviewer detail page eyebrow "Reviewer workbench" is the only English string in the visible reviewer chrome. Acceptable for internal vocabulary; flagged as **P3** (`A-017`).

## Screenshots

This audit was conducted statically from the repository state at commit
`ba3d7c7`. Live admin authentication was not exercised because: this run
ships in a sandbox without persisted reviewer/internal_admin credentials,
and the local server was not started (the user instructions cap the
scope at small parity fixes, not a full live demo).

To capture proof under `docs/audits/admin-qa/screenshots/`, an operator
with `internal_admin` and `reviewer` roles must:

1. `./dev.sh` and seed via `apps/api/scripts/seed_demo.py` (the existing
   demo provisioner).
2. Authenticate at `http://localhost:3000/login` with a reviewer-capable
   admin.
3. Capture the following pages:
   - `admin-dashboard-overview.png` — `/admin/dashboard`
   - `admin-reports-list.png` — `/admin/reports`
   - `admin-review-queue.png` — `/admin/reviewer`
   - `admin-submission-detail-validation.png` — `/admin/reviewer/<id>`
     (any submission with at least one `Validation` row whose severity is
     warning/error — to prove the Spanish labels fix)
   - `admin-period-filter.png` — `/admin/calendar` with year set to 2021
     (to prove the new floor)
   - `admin-report-export-state.png` — `/admin/reports/<id>` after
     "Exportar" is clicked

Naming and location to live under `docs/audits/admin-qa/screenshots/`.

## Provider-side improvements checked for admin parity (summary)

| Improvement | Admin parity |
|---|---|
| Stage 1 — provider presets / report errors / Spanish labels / upload guidance / workspace terminology | ✅ shared components; **❌ reviewer reasons still raw rule_code → fixed** |
| Stage 2 — Acerca de este documento (anatomy / where to obtain / common errors) | ❌ not surfaced on reviewer detail (P2 `A-008`) |
| BL-T1 privacy / legal clarity | n/a admin-side direct UI |
| BL-T2 provider correction requests | ⚠️ backend exists; **❌ no admin triage UI** (P1 `A-001`) |
| BL-T3 REPSE 2026 hardcoded | ⚠️ residual in 2 files; backend admin default **fixed**; copy-only leaks deferred |
| BL-T4 multi-document uploads | n/a admin-side direct UI |
| BL-T5 full rejection causes | ❌ free text only (P1 `A-005`) |
| BL-T6 XML security stance | ✅ |
| BL-T7 / BL-T8 period limits 2021+ | backend ✅; frontend floor **fixed** to 2021 |
| BL-T8b honesty around posible_mismatch / 100% compliance | ✅ |
| BL-T9 plain-Spanish wizard helper | ✅ |

## Small fixes applied in this audit

All changes are narrowly tied to today's Stage 1 / Stage 2 / BL-Tx work,
under the "small safe parity fixes" allowance.

1. **`apps/web/app/admin/reviewer/[submission_id]/page.tsx`** — translate
   the validation `rule_code` into the existing Spanish label via
   `lib/constants/validation.ts::validationLabel`. The raw code stays in
   the row's `title=` attribute and aria-label so QA / engineers can
   still map a row to a backend assertion. Mirrors the provider-side
   `REASON_TITLES` pattern.
2. **`apps/web/app/admin/calendar/page.tsx`** + **`apps/web/app/client/calendar/page.tsx`**
   — lower the `<Input type="number" min={2024}>` to `min={2021}` to match
   `apps/api/app/core/period_validation.py::MIN_YEAR`. Admins can now
   inspect any legitimate REPSE period since the 2021 outsourcing reform
   without bypassing the form.
3. **`apps/api/app/api/v1/admin.py`** — replace the hardcoded
   `year: int = 2026` default on `GET /admin/calendar` with a dynamic
   `date.today().year` resolved at request time. The clamp `ge=MIN_YEAR,
   le=MAX_YEAR` already enforces the validator window. Mirrors the BL-T3
   spirit (no hardcoded forward-year assumptions).

No backend tests or pydantic models change. No public API contract
changes (response shape and request parameters identical; only the
default value of an optional query parameter shifts to "current year").

## Risks and open questions

- **Free-text rejection causes** is a P1 UX/legal risk: the reviewer
  reason is the source of truth for the provider and for audit logs. A
  curated taxonomy is a follow-up worth scheduling, but it must be
  signed off by Paco / Beko / legal so the copy stands up to
  compliance audit. Do not implement without sign-off.
- **Correction-request admin inbox** depends on a backend `GET` paired
  with the existing `POST`. Both surfaces should land together to avoid
  leaving the Slack channel as the only triage path.
- **Client RFC edit warning** is small but legally sensitive — a 1-2
  line confirmation copy needs Paco's voice. Tracked as P1 but not auto
  fixed.
- **`requirement_service.py` legal_basis fallback** — touches what
  surfaces as legal copy. Defer to legal for the replacement string;
  removing it without a substitute leaves an empty value where the
  catalog is incomplete.
- **Live admin screenshots** still pending; this audit was run
  statically. The fixes above are testable in the standing pytest /
  vitest / build commands but the visual evidence has to come from a
  live run.

## Recommended first admin-side implementation batch (after small fixes land)

1. **A-001** — provider correction-request admin inbox: `GET /admin/correction-requests`, `PATCH /admin/correction-requests/{id}/status`, `/admin/correction-requests` page. Mirrors `contact-requests` shape so the chrome reuse is trivial.
2. **A-005** — structured rejection-cause taxonomy in `ReviewDecisionPanel`: a curated chip list (RFC mismatch / periodo incorrecto / sello inválido / opinión incumplida / firma faltante / otros) that prepopulates the textarea; persist `reason_code` separately for aggregation.
3. **A-002** — client edit form RFC guard: lock the RFC field by default with a "Editar identificador legal" toggle that demands a one-line justification and writes both old/new to `audit_log`.
4. **A-008** — reviewer-detail "Acerca de este documento" surfacing: expose the same `compliance_catalog.py` anatomy / where-to-obtain / common-errors block to reviewers (collapsed by default).
5. **A-010 follow-up** — replace `report-editor.tsx:566` placeholder and `requirement_service.py:153` fallback with dynamic year / approved copy.

## Backlog

See `docs/audits/admin-qa/admin-qa-backlog.json` for machine-readable detail
of every finding above (severity, files, acceptance criteria, test plan,
status).

## Priority legend

- **P0** — Admin correctness, trust, privacy, or security blocker.
- **P1** — Admin workflow blocker.
- **P2** — Clarity / polish.
- **P3** — Strategic improvement.
