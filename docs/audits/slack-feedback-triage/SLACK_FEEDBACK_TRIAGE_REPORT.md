# CheckWise — Slack Feedback Triage Report

**Source:** `#checkwise-feedback` Slack channel (workspace `LegalShelf-SPD`).  
**Review date:** 2026-05-20.  
**Reviewer:** triage planning pass (no code changes yet).  
**Tester:** `jluna@legalshelf.mx` — single tester, role label `—` (no assigned role on the membership record; treated as a workspace-owner provider per the routes accessed).  
**Time window:** 10:56 AM → 12:46 PM (≈110 minutes of one tester session).  
**Viewport:** 1802×862 (desktop Windows Chrome 148).  
**Production target:** `checkwise-six.vercel.app`.

---

## 1. Objective

Convert the seven Slack feedback messages into a structured, prioritized roadmap with explicit page mapping, suspected files, acceptance criteria, and a phased implementation sequence. **Triage only — no implementation in this pass.**

---

## 2. Summary

| Metric | Count |
|---|---:|
| Feedback messages reviewed | 7 |
| Bug reports | 1 |
| Improvement suggestions | 6 |
| Console-error attachments | 3 (same RSC chunk error across 4 portal routes) |
| Unique product surfaces touched | 5 (`/portal/upload`, `/portal/dashboard`, `/portal/reports`, `/portal/calendar`, plus production chunk runtime) |
| Distinct underlying issues | 8 (6 product gaps + 1 backend role gate + 1 production chunk runtime regression) |
| Critical (P0) items | 1 |
| High (P1) items | 4 |
| Polish (P2) items | 3 |
| Strategic (P3) items | 1 |

**The single tester sees production CheckWise as a mostly-functional product with one clear bug and a consistent confusion pattern: not enough plain-Spanish guidance during upload, and not enough document-level detail when reviewing what was already submitted.**

---

## 3. Per-message inventory

### F1 — `/portal/upload` · Improvement · 10:56 AM

> "Considero que en esta parte se podrían poner las partes de cada documento, es decir, lo que debe de llevar un poco más a detalle y si es posible, una imagen o referencia visual sobre cómo es el documento, para guiar a quien va a cargarlo y que pueda tener idea de cuál documento subir."

- **What the user wants:** A detailed description of each required document plus a visual reference (sample image / annotated example) so the provider knows what they are uploading.
- **Why it matters:** Providers are non-technical. Today the upload screen shows the requirement code (e.g. `SAT-FED-MN-001`) and a one-line title but no anatomy of the document. First-time users do not know what a "Constancia de Situación Fiscal vigente" should actually look like.
- **Type:** UX / content gap.
- **Severity:** medium.
- **Confidence:** likely (well-described, consistent with the platform's "guided compliance assistant" thesis).
- **Console attached:** yes — RSC chunk error (see RX-1 below).
- **Likely owners:** `apps/web/app/portal/upload/page.tsx`, `apps/web/components/checkwise/intake-wizard.tsx`, `apps/web/components/checkwise/document-submission-form.tsx`, backend catalog source `apps/api/app/core/catalogs.py` (where per-requirement description metadata lives or would need to be added).

### F2 — `/portal/upload` · Improvement · 11:12 AM

> "Esta parte está bien por que permite justificar mediante los comentarios el documento que se está cargando, la vista previa del documento puede servir para asegurarse de que el documento elegido es el correcto a cargar. De igual manera es buena idea si se pudieran tener las referencias de los documentos."

- **What the user is saying:** Positive feedback on the comment field and preview. **Repeats** the document-reference ask from F1.
- **Type:** Confirmation + duplicate of F1.
- **Severity:** medium (drives priority of F1 up — same person asked twice in 16 minutes).
- **Confidence:** confirmed pattern.
- **Likely owners:** same as F1.

### F3 — `/portal/upload` · Improvement · 11:28 AM

> "En esta parte, considero que lo está como `file_exists` o `allowed_file_type` y ese tipo de detalles, se conviertan en lenguaje humano, ya que, quien va a realizar la carga no podrá entenderlo del todo y probablemente tenga confusiones al momento de navegar en esta parte de la plataforma."

- **What the user wants:** Validation rule labels translated from developer codes to plain Spanish.
- **Root cause located:** `apps/web/components/checkwise/validation-summary.tsx:29` renders `{validation.rule_code}` verbatim. The backend service `apps/api/app/services/prevalidation.py` defines codes like `file_exists`, `allowed_file_type`, `pdf_magic_header`, `pdf_encrypted`, `pdf_readable_text`, `max_file_size`, `sha256_hash`, `duplicate_hash`, `vendor_match` — every one of those is shown to non-technical users.
- **Type:** Copy / UX. Direct, fixable.
- **Severity:** high (this is exactly the kind of detail that erodes trust on a compliance product).
- **Confidence:** confirmed (root cause grepped).
- **Likely owners:** `apps/web/components/checkwise/validation-summary.tsx`, plus a new `apps/web/lib/constants/validation.ts` (or extend `apps/web/lib/constants/statuses.ts`) holding the `rule_code → human label` map.

### F4 — `/portal/dashboard` · Improvement · 12:14 PM

> "En este apartado puede que sea buena idea ver los documentos que se llevan cargados y que vayan ordenados ya sea por Institución, Mes y Año y que se puedan consultar, posiblemente editarlos pero se puede correr el riesgo de que estos puedan ser alterados… Por ende, solo se sugiere que se visualicen el/los documento(s) que se han cargado mediante ese orden. Lo demás está bien, los estatus y avisos de la plataforma, aunque también es necesario ajustar la gráfica para que el cliente pueda entender mejor que le hace falta para completar su expediente."

- **What the user wants:** Two things:
  1. A read-only history of uploaded documents grouped by `Institución × Mes × Año`. They explicitly call out the risk of allowing edits — they want **view + consult**, not edit.
  2. The compliance gauge / chart on the dashboard should communicate "what is missing" more clearly.
- **Type:** Feature gap (history view) + UX clarity (gauge copy).
- **Severity:** high (history view is the primary trust artifact for a provider's own expediente).
- **Confidence:** likely.
- **Likely owners:** `apps/web/app/portal/dashboard/page.tsx`, `apps/web/components/checkwise/portal/*` (gauge + suggested-actions strip), and a new history component (`provider-history-list.tsx` or similar). Backend: an enriched submissions-list endpoint that returns vendor submissions grouped by institution/period (probably already covered by `apps/api/app/api/v1/portal.py` calendar or submissions endpoints).

### F5 — `/portal/reports` · Improvement · 12:42 PM

> "la muestra de las estadísticas de los documentos es muy clara y logra el cometido del estatus del expediente… también es buena idea si pudieran ver detalles sobre su expediente, en caso de que haga falta o motivos sobre el por qué aún no se ha completado al 100% su progreso. En la parte de los reportes, considero que se pueden juntar los 3 en uno solo, y que si se quieren descargar individuales, estos se puedan configurar de mejor manera al momento de poderlos descargar."

- **What the user is saying:** Reports stats are clear, but: (a) provider-side expediente reports should explain *why* progress is < 100 %, and (b) the three vendor-facing presets could be merged into one with downloadable sub-views.
- **Type:** UX clarity (today's gauge does not explain causes) + strategic (collapse three presets into one configurable report).
- **Severity:** medium — but pairs naturally with the F6 bug since it's on the same surface.
- **Confidence:** likely.
- **Likely owners:** `apps/web/components/checkwise/reports/list/compliance-pulse-strip.tsx` (the gauge), `apps/web/components/checkwise/reports/list/reports-list-view.tsx` (preset gallery), `apps/api/app/services/reports/templates.py` (preset definitions — `_PROVIDER_CURRENT_STATE`, `_PROVIDER_MISSING_DOCUMENTS`, `_PROVIDER_RECENT_REJECTIONS`).

### F6 — `/portal/reports` · Bug · 12:43 PM

> "En esta parte no deja ver las plantillas de los reportes."

- **What the user observes:** The Plantillas section either renders empty ("Tu rol todavía no tiene plantillas asignadas") or the preset request fails silently.
- **Root cause hypothesis:** The presets API requires `actor.is_workspace_owner = True` to surface the three `vendor_facing` provider presets (`apps/api/app/services/report_service.py:121`, `apps/api/app/services/reports/templates.py:293`). `is_workspace_owner` is defined as `not self.roles and self.workspace_vendor_id is not None`. **If `jluna@legalshelf.mx`'s session has any non-empty `roles` tuple AND a `workspace_vendor_id`, the gate returns `False` and the provider presets disappear.** The tester's Slack message lists `Roles —` (i.e. no role shown in the feedback payload's role echo) but that field is the *feedback payload* role echo, not necessarily the membership record. Needs reproduction.
- **Type:** Bug — backend role gate OR seed-data classification.
- **Severity:** **critical** (it is the only explicit "bug" in the channel, it blocks the report flow the user just praised one minute earlier in F5, and it makes the provider experience visibly broken on a demo route).
- **Confidence:** needs reproduction — but a clear failure mode is identified.
- **Likely owners:** `apps/api/app/services/report_service.py` (the `ReportActor.is_workspace_owner` property), `apps/api/app/api/v1/reports.py` (how `actor` is built — check if it includes the `workspace_vendor_id` for users who also have a legalshelf.mx email), `apps/web/components/checkwise/reports/list/reports-list-view.tsx` (the silent fallback from `listPresets()` to `[]` on non-401 errors hides the real failure mode and should surface a debug message during testing).

### F7 — `/portal/calendar` · Improvement · 12:46 PM

> "Para este apartado, sugiero que se pueda visualizar de mejor manera el calendario, con detalle sobre el día en el que se hizo la carga y el nombre del documento que se cargó a la plataforma, para así tener una mejor pista y seguimiento de los documentos y el expediente en general."

- **What the user wants:** Cell-level (or hover/drawer-level) information about (a) the actual upload date and (b) the filename of the document submitted in that slot.
- **Today's behavior:** The calendar slot exposes `submission_id` and links into the submission detail, but the grid view itself does not surface upload date or filename. The detail drawer at `apps/web/app/portal/calendar/page.tsx` line 421 has the data slot for it but the cell preview does not.
- **Type:** UX / information density.
- **Severity:** medium.
- **Confidence:** likely.
- **Likely owners:** `apps/web/app/portal/calendar/page.tsx`, `apps/web/lib/api/portal.ts` (extend `CalendarItem` to include `uploaded_at` + `filename` if the backend doesn't already return them), `apps/api/app/api/v1/portal.py` calendar endpoint.

### RX-1 — Production runtime · console-error pattern (attached to F1, F2, F3)

> Repeated console errors timestamped 16:31:51 – 16:57:58:  
> `Failed to fetch RSC payload for https://checkwise-six.vercel.app/portal/... TypeError: Cannot read properties of undefined (reading 'call') at r (webpack-9513878bb031f797.js:1:128)`  
> Affected routes: `/portal/entra-a-tu-espacio`, `/portal/upload`, `/portal/onboarding`, `/portal/dashboard`.

- **What this is:** Vercel served a stale webpack chunk hash after a deploy; the client's prefetched RSC payload referenced a chunk the new bundle no longer contains. Next.js falls back to a hard navigation, which is functional but kills perceived snappiness and produces user-visible flashes.
- **Why it matters:** It happens across **four** of the most-visited portal routes, in the **same tester session**, for **26 minutes**. On a public testing session this looks like the product is broken even when the underlying surfaces work.
- **Type:** Production runtime regression / build-deploy hygiene.
- **Severity:** high.
- **Confidence:** confirmed (the error signature is canonical for stale-chunk-after-deploy on Next 15 + Vercel).
- **Likely owners:** `apps/web/next.config.ts` (we recently changed `distDir` for non-ASCII paths — verify it does NOT apply on Vercel; Vercel builds run from an ASCII path so the override is inert there, but worth confirming), the Vercel project settings (ensure long-term caching headers are not preserved across deploys), and possibly the `next.config.ts` `output`/`generateBuildId` strategy. May also be aggravated by the recent visual redesign push and a subsequent stale tab.

---

## 4. Grouping by product area

| Area | Feedback IDs | Total |
|---|---|---:|
| Provider uploads | F1, F2, F3 | 3 |
| Provider dashboard | F4 | 1 |
| Provider reports | F5, F6 | 2 |
| Provider calendar | F7 | 1 |
| Production runtime / infra | RX-1 (attached to F1, F2, F3) | 1 |
| Authentication / login | — | 0 |
| Internal review workflow | — | 0 |
| Document validation (rule labels) | F3 (cross-cuts upload + admin) | 1 |
| Notifications | — | 0 |
| Visual design / design system | — | 0 |
| Mobile / responsive | — | 0 (all feedback at 1802×862 desktop) |
| Security / permissions | F6 (role gate) | 1 |

---

## 5. Duplicate / pattern analysis

- **F1 ≈ F2** — same tester restates "document references" within 16 minutes. Treat as **one P1 item** (BL-002) with two source feedbacks.
- **F1/F2 + F3** share the same underlying theme: **the upload surface speaks engineer dialect to a non-technical user.** F3 fixes the validation copy, F1/F2 fix the requirement guidance. Independent but adjacent — group into the same implementation batch.
- **F5 + F6** are 60 seconds apart on the same page. The tester praised the stats (F5) and then noticed the preset gallery was empty (F6). Likely the gallery was empty *the whole time* and the tester only mentioned the bug after they'd appraised the rest of the page. **Schedule F6 before F5** — fixing the bug may also resolve part of F5's "I want more details about my expediente" because today the three vendor presets *are* the way to consult those details.
- **F4 + F7** are different surfaces but the same underlying request: "show me *which documents* I've uploaded, *when*, and *what they cover*." Both are calls for a document-history surface. Reasonable to bundle the data layer (one enriched endpoint) and ship two presentation views.
- **RX-1** appears on every page the tester visited that day, but it is **not page-specific** — it is a production runtime issue. Schedule it as a pre-flight checklist for the next deploy rather than a per-page fix.

---

## 6. Severity distribution

| Severity | Count | Items |
|---|---:|---|
| Critical | 1 | F6 |
| High | 4 | F3, F4, RX-1, F1/F2 (as a single bundle) |
| Medium | 3 | F5, F7, (F1/F2 separately if not bundled with F3) |
| Low | 0 | — |

---

## 7. Page / route impact map

| Route | Feedback | Surface confidence |
|---|---|---|
| `/portal/upload` | F1, F2, F3 + RX-1 | high — three messages, well-described |
| `/portal/dashboard` | F4 + RX-1 | high |
| `/portal/reports` | F5, F6 | high (F6 needs repro to lock the cause) |
| `/portal/calendar` | F7 | high |
| `/portal/entra-a-tu-espacio` | RX-1 | indirect (only the chunk error) |
| `/portal/onboarding` | RX-1 | indirect |
| Backend `report_service.ReportActor.is_workspace_owner` | F6 | high (root-cause candidate) |

---

## 8. Roadmap — P0 / P1 / P2 / P3

### P0 — Critical blocker

**BL-001 — Provider presets do not render on `/portal/reports` ("no deja ver las plantillas")**  
- Source: F6.  
- Page: `/portal/reports`.  
- User: provider (workspace owner).  
- Problem: The Plantillas section is empty for the tester's account. Either the `listPresets()` endpoint returned `[]` (role gate excluded all three `vendor_facing` presets) or the silent catch in `reports-list-view.tsx` swallowed a non-401 error.  
- Expected behavior: A provider whose session resolves to `is_workspace_owner=True` sees the three vendor-facing preset cards (Estado actual del expediente, Documentos faltantes, Rechazos recientes).  
- Suggested approach:  
  1. Reproduce as `jluna@legalshelf.mx` against staging. Capture the actual `/api/v1/reports/_presets` response body + status.  
  2. If response is `200 { items: [] }`: investigate `actor.is_workspace_owner` construction. The current property requires `not self.roles AND workspace_vendor_id is not None`. If jluna has *any* role attached (even an unintended one) the gate flips to `False`. Either (a) fix the seed data, or (b) loosen the property to "has workspace_vendor_id, regardless of roles" — and adjust the docstring + safety branches accordingly.  
  3. If response is non-200: replace the silent `.catch(() => setPresets([]))` in `reports-list-view.tsx` with a visible warning so the empty-state copy distinguishes "no plantillas para tu rol" from "error cargando plantillas".  
- Likely files: `apps/api/app/services/report_service.py`, `apps/api/app/api/v1/reports.py`, `apps/web/components/checkwise/reports/list/reports-list-view.tsx`.  
- Test plan: (a) backend unit test that constructs a `ReportActor` for the actual seed shape of jluna's account and asserts `is_workspace_owner=True` + `presets_for_roles(...).length === 3`; (b) frontend integration test that mocks `listPresets()` to throw a non-401 and asserts the warning surfaces.  
- Acceptance criteria: Logged in as jluna, `/portal/reports` shows three preset cards, "Estado actual del expediente" featured first. The empty-state warning never fires for valid workspace owners.  
- Risk: low (single-surface fix, well-contained).

### P1 — High-priority user-testing fixes

**BL-002 — Document guidance on `/portal/upload` (anatomy + visual reference)**  
- Source: F1 + F2 (bundled).  
- Page: `/portal/upload`.  
- User: provider.  
- Problem: First-time uploaders cannot tell what a given requirement document should look like or what fields it must contain.  
- Expected behavior: Each requirement card exposes (a) a 2-4-sentence Spanish description of the document's anatomy, and (b) an optional reference image (sample of what the document looks like, with sensitive data redacted).  
- Suggested approach: Extend the requirement catalog in `apps/api/app/core/catalogs.py` with optional `anatomy_es: str` and `sample_image: str | None` fields. Surface them in the existing requirement card / submission form. Sample images live under `apps/web/public/marketing/requirement-samples/` (new folder) — start with the five highest-volume requirements (CSF, REPSE, IMSS opinion, INFONAVIT certificate, ISR declaration) and ship the rest incrementally.  
- Likely files: `apps/api/app/core/catalogs.py`, `apps/api/app/schemas/portal.py`, `apps/web/components/checkwise/document-submission-form.tsx`, `apps/web/components/checkwise/intake-wizard.tsx`, `apps/web/public/marketing/requirement-samples/*`.  
- Test plan: Visual QA on five seeded requirements. Confirm the anatomy text and sample image render in both intake-wizard and the standalone upload flow.  
- Acceptance criteria: For at least the five priority requirements, the upload card shows an anatomy paragraph and either a sample image or a clear "Sample coming soon" note. No layout breakage at the user's tested viewport (1802×862) or at the responsive breakpoints we already QA'd.  
- Risk: medium (requires content + image curation, not just code).

**BL-003 — Translate validation `rule_code` to plain Spanish on `/portal/upload`**  
- Source: F3.  
- Page: `/portal/upload`, also `/portal/submissions/[id]` and `/admin/reviewer/[id]` since `ValidationSummary` is shared.  
- User: provider (and internal reviewer benefits too).  
- Problem: `validation-summary.tsx:29` renders `validation.rule_code` directly. Users see `file_exists`, `allowed_file_type`, `pdf_magic_header`, etc.  
- Expected behavior: Each signal shows a Spanish-language title (e.g. "Archivo recibido", "Tipo de archivo permitido", "Estructura PDF válida") with the existing `message` as the supporting sentence. The raw `rule_code` may stay as a small mono tag for QA reproducibility but it cannot be the primary label.  
- Suggested approach: Add `apps/web/lib/constants/validation.ts` with a `RULE_CODE_LABELS_ES` map mirroring every code defined in `apps/api/app/services/prevalidation.py`. Render `RULE_CODE_LABELS_ES[code] ?? code` from the validation-summary component. Add a `?` icon with the rule_code on hover for engineer fallback.  
- Likely files: `apps/web/lib/constants/validation.ts` (new), `apps/web/components/checkwise/validation-summary.tsx`, optionally `apps/web/components/checkwise/document-submission-form.tsx` if it has its own rendering.  
- Test plan: Unit test of the label map covers every code emitted by `prevalidation.py`. Visual regression on the existing submissions detail page.  
- Acceptance criteria: No raw `rule_code` strings render on any user-facing surface. Reviewers can still see the original code via tooltip or `title` attribute.  
- Risk: low.

**BL-004 — Submitted-documents history on `/portal/dashboard` (and dashboard gauge clarity)**  
- Source: F4.  
- Page: `/portal/dashboard`.  
- User: provider.  
- Problem: There is no read-only view of the documents already uploaded, grouped by Institution × Month × Year. The dashboard's compliance gauge does not communicate what specifically is missing.  
- Expected behavior: A new "Documentos cargados" section on the dashboard (and a deeper drilldown route if needed) listing every submission grouped by institution, then month/year, with status pill, submitted date, and a link to the submission detail. Read-only — no edit affordance to prevent the alteration risk the tester explicitly warned about. The gauge gets a "Te faltan N documentos" subtitle with the count + a chip listing the top 1-2 missing requirements.  
- Suggested approach: New component `provider-history-list.tsx` powered by the existing `GET /api/v1/portal/workspaces/{id}/submissions` endpoint (or extend it to return grouped output). Render under the dashboard hero block. For the gauge, derive the missing-count from the same payload that already drives the percentage.  
- Likely files: `apps/web/app/portal/dashboard/page.tsx`, `apps/web/components/checkwise/portal/*` (gauge), `apps/api/app/api/v1/portal.py`, `apps/api/app/services/submission_service.py`.  
- Test plan: Seed a provider with 5 mixed submissions across 3 months and 4 institutions. Assert grouping order and counts. Smoke-test the gauge subtitle.  
- Acceptance criteria: Submissions appear grouped Institution → Year → Month with month names in Spanish. No edit/delete buttons. Gauge displays "Te faltan N documentos" when N > 0 and the chip lists the highest-priority missing requirement.  
- Risk: medium (touches a dashboard layout we just stabilized).

**BL-005 — Production runtime stability: stale RSC chunk on `/portal/*`**  
- Source: RX-1 (console attachment under F1, F2, F3).  
- Page: production-wide on Vercel.  
- User: every visitor whose tab spans a deploy.  
- Problem: `TypeError: Cannot read properties of undefined (reading 'call')` on `webpack-9513878bb031f797.js` indicates the browser tried to consume a chunk that the new deploy renamed. Symptom: every client-side nav across portal routes hard-reloads.  
- Expected behavior: Client-side navigation works for at least the standard 24 h CDN window after a deploy, or hard-reloads gracefully without a console error and without a perceptible flash.  
- Suggested approach: (a) Verify the recent `distDir` override in `apps/web/next.config.ts` is inert on Vercel (Vercel cwd is ASCII; the resolver should return `.next`). (b) Confirm Vercel's "Auto-cleanup of build artifacts" / chunk-fallback config; consider enabling `experimental.optimisticClientCache: false` for the portal segment, or adopt the standard Next pattern `if (event.error?.name === 'ChunkLoadError') window.location.reload()` at the layout level. (c) Validate that `output: 'standalone'` is NOT silently engaged with the new `distDir`. (d) Smoke-test a fresh deploy + browser-back + nav.  
- Likely files: `apps/web/next.config.ts`, possibly a new `apps/web/app/portal/error.tsx` or `apps/web/app/portal/layout.tsx` for ChunkLoadError handling.  
- Test plan: Manual — deploy a no-op change to Vercel preview, leave a tab on `/portal/dashboard`, deploy again, navigate. Confirm no console error and no hard nav.  
- Acceptance criteria: A fresh Vercel deploy does not produce the chunk error for users navigating between portal routes within the next 60 minutes.  
- Risk: medium (production change; benefits from a Vercel preview before promotion).

### P2 — Polish & UX clarity

**BL-006 — Calendar cell-level upload metadata on `/portal/calendar`**  
- Source: F7.  
- Page: `/portal/calendar`.  
- User: provider.  
- Problem: Calendar cells show status but not the upload date or filename.  
- Expected behavior: Hovered or focused cells reveal upload date and filename (truncated). The drawer already has the data but the cell preview doesn't.  
- Suggested approach: Extend `CalendarItem` (frontend type + backend response) with `uploaded_at: string | null` and `filename: string | null` (already-stored values for the latest submission). Render under the status badge on the cell. Mobile/tablet keep the drawer pattern.  
- Likely files: `apps/web/app/portal/calendar/page.tsx`, `apps/web/lib/api/portal.ts`, `apps/api/app/api/v1/portal.py` calendar endpoint, `apps/api/app/schemas/portal.py`.  
- Test plan: Seed a workspace with one filled and one empty cell. Verify upload-date format `DD/MM/YYYY` and filename rendered with `truncate` on overflow.  
- Acceptance criteria: Provider can see the upload date and filename of every populated cell without opening the drawer. Empty cells stay empty.  
- Risk: low.

**BL-007 — Provider-side report "why am I not at 100 %" callout**  
- Source: F5 (first half).  
- Page: `/portal/reports` (Compliance Pulse strip) and the in-report executive summary.  
- User: provider.  
- Problem: Provider does not understand *what* is keeping the expediente below 100 %.  
- Expected behavior: The Compliance Pulse strip subtitle includes the top reason ("3 documentos pendientes en IMSS", "1 documento rechazado por aclarar"). The "Estado actual del expediente" preset's generated executive summary mentions the same blockers explicitly.  
- Suggested approach: Extend `apps/web/components/checkwise/reports/list/compliance-pulse-strip.tsx` to render the top missing/rejected requirement chip. Backend: reuse the existing `provider_current_state` block executor output to surface the blocker list.  
- Likely files: `compliance-pulse-strip.tsx`, `apps/api/app/services/reports/blocks/*` (provider-state block).  
- Test plan: Seed a provider at 70 % completion. Verify the chip lists the top blocker.  
- Acceptance criteria: Whenever compliance % < 100, the strip shows at least one specific reason.  
- Risk: low.

**BL-008 — Soften silent error fallback in `reports-list-view.tsx`**  
- Source: F6 (secondary cause).  
- Page: `/portal/reports`, `/admin/reports`, `/client/reports`.  
- User: all roles.  
- Problem: A failed `listPresets()` collapses to empty silently. During testing this hides real bugs and looks identical to a legitimately empty role.  
- Expected behavior: On non-401/403 errors, render a small inline warning that distinguishes "no presets for your role" from "presets endpoint failed."  
- Suggested approach: Add a `presetsError` state, render an Alert above the gallery when populated.  
- Likely files: `apps/web/components/checkwise/reports/list/reports-list-view.tsx`.  
- Test plan: Mock `listPresets()` to throw a 500. Assert Alert renders. Mock to throw 403. Assert role-scoped message renders (existing behavior).  
- Acceptance criteria: Real preset-loading failures are visible during testing.  
- Risk: low.

### P3 — Strategic improvements

**BL-009 — Collapse three vendor-facing presets into one configurable report**  
- Source: F5 (second half).  
- Page: `/portal/reports`.  
- User: provider.  
- Problem: Three presets ("Estado actual", "Documentos faltantes", "Rechazos recientes") show as three separate cards; the tester would prefer one unified report with section-level download/export.  
- Expected behavior: A single "Estado del expediente" preset that includes all three sections, with per-section export buttons in the report editor.  
- Suggested approach: Define a new combined preset in `apps/api/app/services/reports/templates.py`. Keep the three existing presets behind a feature flag for backward compat. Add per-section download in `apps/web/components/checkwise/reports/editor/report-editor.tsx`.  
- Likely files: `apps/api/app/services/reports/templates.py`, `apps/web/components/checkwise/reports/editor/report-editor.tsx`, `apps/web/components/checkwise/reports/canvas.tsx`.  
- Test plan: Generate the combined report, verify each section renders. Verify download of an individual section.  
- Acceptance criteria: One preset card creates a report whose three sub-sections match the legacy three presets, with per-section export.  
- Risk: high (changes data model and demo flow; do not rush).

---

## 9. Suggested implementation sequence

Each stage should be a single reviewable PR with the verification listed.

**Stage 1 — Bug containment (½ day)**  
1. BL-008 (visible error in `reports-list-view.tsx`) — lands first because it makes BL-001 easier to reproduce.  
2. BL-001 (`is_workspace_owner` reproduction + fix).  

**Stage 2 — Plain-language polish (1 day)**  
3. BL-003 (validation rule labels).  
4. BL-006 (calendar cell metadata).  

**Stage 3 — Provider guidance (2 days)**  
5. BL-002 (upload anatomy + sample images).  
6. BL-007 (Compliance Pulse "why" callout).  

**Stage 4 — Dashboard history surface (2 days)**  
7. BL-004 (submissions history + gauge subtitle).  

**Stage 5 — Production hygiene, gated on a Vercel preview (½ day)**  
8. BL-005 (ChunkLoadError fallback + verify distDir inert on Vercel).  

**Stage 6 — Strategic (later, separate planning pass)**  
9. BL-009 (combined provider preset).  

Each stage preserves the current token system, does not delete existing endpoints, and is independently shippable. **Do not start any of them until this triage is explicitly approved.**

---

## 10. Suggested test plan

- **Unit (backend):** `tests/test_reports_presets.py` already exists — add a case asserting jluna's seed shape resolves to `is_workspace_owner=True` and lists three presets.  
- **Unit (frontend):** new `validation-label.test.ts` for the `rule_code → ES` map; the map must cover every code declared in `prevalidation.py` (assertable via a fixture export).  
- **Integration (Playwright):** Provider session smoke that walks `entra-a-tu-espacio → onboarding → upload → dashboard → calendar → reports` with one mock document. Assert no console error on chunk load, three preset cards visible, validation labels in Spanish, document appears in dashboard history.  
- **Manual QA after each stage:** at the user's reported viewport (1802×862 Chrome on Windows), plus 1440×900 desktop and 390×844 mobile from the recent responsive matrix.  

---

## 11. Risks & assumptions

- **Assumption (BL-001):** the tester's account behaves like a normal workspace owner. If `jluna@legalshelf.mx` has been seeded as `internal_admin` + workspace owner, the `is_workspace_owner` property correctly returns `False` (internal staff branch wins). In that case the fix is in seed data, not in the property. To be confirmed in repro.  
- **Assumption (BL-002):** sample images for each requirement can be sourced without redaction risk. If not, ship anatomy text first and the image set behind a CMS-style admin.  
- **Risk (BL-004):** adding a history list to `/portal/dashboard` increases the page height and could compete with the existing "tu siguiente acción" cards. Place the history below the action cards and behind a "Ver historial" expand to keep the first viewport calm.  
- **Risk (BL-005):** Vercel chunk behavior cannot be fully tested locally. Stage on a preview deploy.  
- **Risk (BL-009):** Collapsing three presets into one breaks existing reports the tester (or other providers) may already have. Behind a feature flag, with read backward-compat.

---

## 12. Questions still needing clarification

1. **BL-001 / F6:** What roles + workspace bindings does `jluna@legalshelf.mx` actually have on staging? Need the raw row from `memberships` and `provider_workspaces`. Without this, BL-001 is "needs reproduction" not "ready to fix."  
2. **BL-002 / F1:** Is there a sanctioned source for "this is what a Constancia de Situación Fiscal looks like" sample images (Legal Shelf marketing assets? SAT public docs?), or do we need to commission them?  
3. **RX-1 / BL-005:** Is the Vercel project configured with `outputFileTracingRoot` or a non-default `assetPrefix`? That would affect the chunk-fallback strategy.  
4. **F5 second half:** Is "the 3 reports could be one" tester preference, or has anyone else (sales, Pedro, Legal Shelf operations) said the same thing? If only one tester, hold at P3.  
5. **F4 graphic:** Is the "ajustar la gráfica" comment specifically about the percentage gauge, or about the side-by-side cards too? Confirm via a quick screenshot ask before BL-004 starts.

---

## 13. Recommended first implementation batch

After this triage is approved, ship Stage 1 (BL-008 → BL-001) as the very next PR. It:
- closes the only declared bug,
- unblocks Compliance-Pulse-led demos,
- includes its own visibility net (BL-008) so the same bug cannot hide silently again,
- is small enough to keep reviewable.

Hold Stage 2-5 for sequential follow-up PRs. Hold Stage 6 / BL-009 for a separate planning pass.

---

*End of triage report.*
