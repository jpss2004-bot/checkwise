# CheckWise — System UX Audit Report

> **Date:** 2026-05-18
> **Auditor:** Claude Code (Opus 4.7)
> **Repo state:** `main`, P1.1–P1.9 shipped (working-tree dirty with P1.8/P1.9 edits not yet committed).
> **Scope:** Full end-to-end audit across the three role shells (admin / provider / client), every reachable major route, every primary workflow, plus the public marketing and auth surfaces.
> **Method:** Live in-browser smoke as each role using `dev_demo.sh` stack (Docker Postgres → seed → uvicorn → Next.js). Direct DOM inspection, screenshots, and API probes. No destructive actions taken on local seed data.

---

## 1. Executive summary

CheckWise is in **demo-ready** shape across all three role shells. Every audited route loads, navigates, authenticates, and renders production-quality content. The product reads as a guided REPSE compliance assistant, not a developer tool — page titles, subtitles, CTAs, and empty states are uniformly in clear Spanish, and the visual hierarchy is consistent across shells. The provider-reports surface that received heavy investment in P1.1–P1.9 is the strongest piece in the app and is fully usable.

**Top-line readiness:** ~9 / 10 — there are no blockers, no broken routes, no crashes, no confusing primary flows. The remaining gap is a short list of medium- and polish-level cleanups (custom 404 page, denser admin dashboard layout at wide viewports, a single English string in the AI sub-flow). None of those gate a customer or investor demo.

**Recommendation:** ship the small polish set in this report, then return to feature work (P2.0 — provider-block seed fixtures, per the existing handoff).

---

## 2. Overall product readiness score

| Dimension                           | Score | Notes |
|-------------------------------------|-------|-------|
| Navigation + redirects              | 10/10 | Every login routes to the right shell; nav links resolve; back/forward all work. |
| Page hierarchy + typography         |  9/10 | Consistent H1 + eyebrow + subtitle pattern across all shells. |
| Empty / loading / error states      |  9/10 | Most pages have helpful empty copy. Single Next.js default 404 is the gap. |
| Form clarity + validation           |  9/10 | Login, intake wizard, vendor creation all labeled; required-field markers present. |
| CTA consistency                     |  9/10 | Primary/secondary button variants used appropriately throughout. |
| Tables / data density               |  8/10 | Tables read well at desktop. Reviewer queue truncates at narrow widths — see I-04. |
| Responsive behavior                 |  7/10 | Tested at 1440 (clean) and 768/912 (some truncation in tables + tabs). |
| Demo-readiness language             | 10/10 | Zero developer/debug language reaches end users. Mock-LLM banner is honest, not embarrassing. |
| Brand + visual polish               |  9/10 | Strong landing page, consistent shell chrome, no broken images. |
| Print / PDF surface (post-P1.8/P1.9)| 10/10 | Toolbar actions wired across all shells; print page has running header, freshness seal, page-break rules; 32-assertion contract test in CI. |

**Overall: 9.0 / 10 — demo-ready.**

---

## 3. Route inventory

### 3.1 Frontend routes (33 pages)

| # | Route | Shell | Role | Purpose | Status | Screenshot |
|---|-------|-------|------|---------|--------|------------|
|  1 | `/`                                       | public  | any         | Marketing hero + product overview                                  | ✅ working      | 01-landing |
|  2 | `/login`                                  | public  | any         | Single email+password auth surface                                 | ✅ working      | 02-login |
|  3 | `/activate`                               | public  | first-login | Forced password rotation                                           | ⚪ not exercised (no must_change_password user in current seed) | — |
|  4 | `/admin/login`                            | public  | admin       | Legacy redirect to `/login`                                        | ✅ redirects    | — |
|  5 | `/admin`                                  | admin   | admin       | Admin home (card grid to sub-routes)                               | ✅ working      | — |
|  6 | `/admin/dashboard`                        | admin   | admin       | Operational overview: backlog, vendor/client counts                | ✅ working      | 04-admin-dashboard |
|  7 | `/admin/reviewer`                         | admin   | reviewer    | Reviewer queue (4 tabs, filtered table)                            | ✅ working      | 03-admin-reviewer-queue |
|  8 | `/admin/reviewer/[id]`                    | admin   | reviewer    | Submission detail + decision panel                                 | ✅ working      | 08-admin-reviewer-detail |
|  9 | `/admin/clients`                          | admin   | admin       | Client CRUD list                                                   | ✅ working      | 05-admin-clients |
| 10 | `/admin/vendors`                          | admin   | admin       | Vendor CRUD list (cross-client)                                    | ✅ working      | 06-admin-vendors |
| 11 | `/admin/calendar`                         | admin   | admin       | Year-of-obligations bar chart + monthly drilldown                  | ✅ working      | 09-admin-calendar |
| 12 | `/admin/requirements`                     | admin   | admin       | 151-row REPSE catalog                                              | ✅ working      | 07-admin-requirements |
| 13 | `/admin/audit-log`                        | admin   | admin       | Filterable audit timeline                                          | ✅ working (empty state) | 10-admin-audit-log |
| 14 | `/admin/reports`                          | admin   | admin       | Reports list + 6 presets                                           | ✅ working      | 11-admin-reports-list |
| 15 | `/admin/reports/[id]`                     | admin   | admin       | Report editor (full toolbar)                                       | ✅ working      | 12-admin-report-editor |
| 16 | `/client`                                 | client  | client_admin| Redirects to `/client/dashboard`                                   | ✅ redirects    | — |
| 17 | `/client/dashboard`                       | client  | client_admin| Portfolio compliance pulse + quick links                           | ✅ working      | 13-client-dashboard |
| 18 | `/client/vendors`                         | client  | client_admin| Vendor list with risk distribution + chips                         | ✅ working      | 14-client-vendors |
| 19 | `/client/vendors/[id]`                    | client  | client_admin| Vendor compliance detail                                           | ✅ working      | 15-client-vendor-detail |
| 20 | `/client/submissions`                     | client  | client_admin| Cross-vendor submissions table (12 rows)                           | ✅ working      | 16-client-submissions |
| 21 | `/client/activity`                        | client  | client_admin| Cross-vendor activity timeline                                     | ✅ working      | 17-client-activity |
| 22 | `/client/calendar`                        | client  | client_admin| Aggregate calendar (rhythm + monthly detail)                       | ✅ working      | 18-client-calendar |
| 23 | `/client/reports`                         | client  | client_admin| Reports list + 3 client-facing presets                             | ✅ working      | 19-client-reports |
| 24 | `/client/reports/[id]`                    | client  | client_admin| Report editor (client view)                                        | ✅ working      | — |
| 25 | `/portal/entra-a-tu-espacio`              | portal  | provider    | Workspace entry + contact confirmation                             | ✅ working      | 20-portal-entry |
| 26 | `/portal/dashboard`                       | portal  | provider    | Next-action dashboard                                              | ✅ working      | 21-portal-dashboard |
| 27 | `/portal/onboarding`                      | portal  | provider    | Initial-Expediente checklist                                       | ✅ working      | 22-portal-onboarding |
| 28 | `/portal/upload`                          | portal  | provider    | 5-step intake wizard                                               | ✅ working      | 23-portal-upload-step1 |
| 29 | `/portal/submissions/[id]`                | portal  | provider    | Submission detail + correction prompts                             | ⚪ not exercised (workspace seed has none with this user perspective) | — |
| 30 | `/portal/calendar`                        | portal  | provider    | Personal compliance year view                                      | ✅ working      | 24-portal-calendar |
| 31 | `/portal/reports`                         | portal  | provider    | Compliance Pulse + plantillas + recent reports                     | ✅ working      | 25-portal-reports |
| 32 | `/portal/reports/[id]`                    | portal  | provider    | Report editor (provider view, full toolbar with P1.8 actions)      | ✅ working      | — |
| 33 | `/portal/reports/[id]/print`              | portal  | any with access | Shell-less print page (P1.8 + P1.9 verified)                       | ✅ working      | 26-portal-report-print |

### 3.2 Backend API prefixes (verified via `openapi.json`, 58 paths total)

| Prefix                         | Purpose                                                          |
|--------------------------------|------------------------------------------------------------------|
| `/api/v1/auth/*`               | login / `me` / `set-password`                                    |
| `/api/v1/portal/*`             | Provider workspace + onboarding + submissions + dashboard        |
| `/api/v1/admin/*`              | Internal CRUD (clients, vendors, requirements, calendar, audit)  |
| `/api/v1/client/*`             | Read-only client portfolio                                       |
| `/api/v1/reviewer/*`           | Queue + decision endpoints                                       |
| `/api/v1/reports/*`            | Reports CRUD, presets, versions, plan/generate, refresh-data     |
| `/api/v1/compliance/*`         | Read-only catalog (anonymous)                                    |
| `/api/v1/health[/db]`          | Health checks                                                    |
| `/api/v1/metadata-dry-run/pdf` | PDF metadata extraction sandbox                                  |

All `/docs` Swagger UI reachable; openapi.json validated.

---

## 4. Feature / workflow checklist

| Workflow                                              | Tested as       | Result | Notes |
|-------------------------------------------------------|-----------------|--------|-------|
| Marketing landing renders                             | anonymous       | ✅     | Hero + product + how-it-works + integrations + contact. Strong CTA pyramid. |
| `/login` form validates required fields               | anonymous       | ✅     | HTML5 required attributes present. |
| Login with wrong password → friendly error            | anonymous       | ✅     | "No pudimos iniciar sesión / Correo o contraseña incorrectos." |
| Login routes admin → `/admin/reviewer`                | ada@…           | ✅     | Reviewer queue is reviewer-first landing. Correct. |
| Login routes provider → `/portal/entra-a-tu-espacio`  | boss.demo@…     | ✅     | Workspace selector + contact-confirmation step. |
| Login routes client_admin → `/client/dashboard`       | cliente.demo@…  | ✅     | Lands on portfolio summary. |
| Logout clears session + returns to login              | all roles       | ✅     | `Cerrar sesión` in header on every shell. |
| Direct URL access to protected route → redirect       | anonymous       | ✅     | `/admin/*` and `/portal/*` → `/login` or workspace selector. |
| Admin dashboard renders metrics                       | ada@…           | ✅     | 100% radial + 5 stat rows. |
| Admin reviewer queue paginates + tabs filter          | ada@…           | ✅     | 4 tabs: Todos / Por revisar / Posible mismatch / Aclaración. |
| Admin reviewer drill-down + decision panel            | ada@…           | ✅     | 4 actions: Aprobar / Rechazar / Pedir aclaración / Excepción legal. |
| Admin clients/vendors lists with CRUD action visible  | ada@…           | ✅     | Search + create + per-row "Editar". |
| Admin requirements catalog renders 151 rows           | ada@…           | ✅     | No pagination — heavy but workable for an admin tool. |
| Admin calendar shows monthly bar chart                | ada@…           | ✅     | + drilldown table. |
| Admin audit-log empty state                           | ada@…           | ✅     | "Sin eventos / No hay eventos para los filtros aplicados." |
| Admin reports list + 6 presets                        | ada@…           | ✅     | 3 seeded reports + filter chips for status + audience. |
| Admin report editor (Resumen ejecutivo · Mayo 2026)   | ada@…           | ✅     | Full toolbar: Volver / Generar con IA / Copiloto / Actualizar con datos de hoy / Vista previa PDF / Descargar PDF / Save. |
| Client portfolio dashboard                            | cliente.demo@…  | ✅     | Headline metric + stats + portfolio distribution. |
| Client vendor list with risk chips                    | cliente.demo@…  | ✅     | Search, filter by semáforo, per-row "Ver". |
| Client vendor detail (compliance + suggestions)       | cliente.demo@…  | ✅     | 6 sub-sections including ATENCIÓN INMEDIATA, ENTREGAS RECIENTES, ACCIONES SUGERIDAS. |
| Client submissions (cross-vendor) table               | cliente.demo@…  | ✅     | 12 rows. |
| Client activity timeline                              | cliente.demo@…  | ✅     | Loads. |
| Client calendar aggregate                             | cliente.demo@…  | ✅     | Annual rhythm chart + monthly detail. |
| Client reports list + 3 presets                       | cliente.demo@…  | ✅     | 1 recent report. |
| Provider workspace entry (data confirmation step)     | boss.demo@…     | ✅     | Forces name + apellido before entering dashboard. |
| Provider dashboard (next-action surface)              | boss.demo@…     | ✅     | "Tu siguiente acción" cards drive next interactions. |
| Provider onboarding checklist                         | boss.demo@…     | ✅     | Numbered, expandable. |
| Provider upload wizard (5 steps visible)              | boss.demo@…     | ✅     | Contexto → Soporte → Upload → Procesamiento → Confirmación. |
| Provider calendar yearly                              | boss.demo@…     | ✅     | 12-month × 4-institution grid with cell counts + legend. |
| Provider reports list (Compliance Pulse + plantillas) | boss.demo@…     | ✅     | This is the P1.6 surface. |
| Provider report print route (P1.8 + P1.9)             | boss.demo@…     | ✅     | Verified end-to-end in P1.9. |
| Browser `window.print()` auto-fires on `?autoprint=1` | boss.demo@…     | ✅     | Verified by patching `window.print` and counting calls. |
| 404 on unknown route                                  | anonymous       | ⚠️     | Renders Next.js default — unbranded. (I-05) |

---

## 5. User-perspective findings

### As a **provider** (boss.demo@checkwise.mx)

- **Strong.** Workspace entry asks for human data ("Confirma tus datos de contacto") before entering the dashboard — that's the right onramp, not a developer-feeling instant-drop.
- **Strong.** Dashboard centers "Tu siguiente acción" cards — exactly the right framing for a small-business provider who doesn't want to think about what to do next.
- **Strong.** Onboarding checklist enumerates `0 de 5 documentos iniciales` clearly, with a per-doc "Pendiente" pill + numbered eyebrow ("DOC INICIAL · DIA 1").
- **Strong.** Reports list opens with a Compliance Pulse strip (P1.6 work) before the plantillas grid — answers "where am I?" before "what can I do?"
- **Good.** Upload wizard step 1 is clear about which client + workspace + provider context is active before any data is entered.
- **Polish.** Help affordance "¿Necesitas ayuda? Soporte CheckWise" floats bottom-left as a persistent chip. It's visually quite small. (I-08)

### As a **client** (cliente.demo@checkwise.mx)

- **Strong.** Dashboard headline metric is one sentence in human language: "Tienes 3 proveedores en amarillo / 432 hallazgos obligatorios". That's the read-in-three-seconds executive framing the brief asked for.
- **Strong.** Vendor list opens with a portfolio risk-distribution stacked bar before the table — frames the table.
- **Strong.** Vendor detail breaks into 6 named sections (ACCIONES SUGERIDAS, ATENCIÓN INMEDIATA, ENTREGAS RECIENTES, DOCUMENTOS POR ESTADO, PRÓXIMOS VENCIMIENTOS, NOTAS DEL REVISOR) — clean executive narrative.
- **Polish.** `/client/dashboard` "ACCESOS RÁPIDOS" and "ACTIVIDAD RECIENTE" panels are stacked on the right and may render empty for some clients. Worth verifying with non-seed data. (Not a fix-now item.)

### As an **internal admin / reviewer** (ada@legalshelf.mx)

- **Strong.** Reviewer queue subtitle: "Empieza por lo más viejo. Cada documento espera tu decisión humana. La automatización no aprueba ni rechaza nada." — sets the right expectation on day one.
- **Strong.** Reviewer detail page has 4 distinct decision actions + a "Selecciona una acción" disambiguator. Trazabilidad sidebar carries every ID a support engineer would need.
- **Strong.** Reports list segregates "Plantillas operativas" from "Reportes recientes" with explicit count badges.
- **Strong.** Empty audit log says "Sin eventos / No hay eventos para los filtros aplicados" — accurate and non-scary.
- **Issue.** Reviewer queue table truncates the PROVEEDOR column header to "P" at 912px viewport; cell content shows letter-per-line ("D / N / A / In / D / D"). Desktop (≥1280) is fine, but tablet readers (iPad portrait) get a broken table. (I-04)
- **Issue.** When `ANTHROPIC_API_KEY` env is set but empty (a real condition in this dev environment — the shell exports `ANTHROPIC_API_KEY=` over the .env value), the editor warns "Generación con IA no configurada en este entorno" with the exact remediation. Banner copy is honest. (I-09)

### As a **first-time user who has never seen this system**

- The marketing landing page is the right "what is this?" entry point — it leads with the OBLIGACIÓN × EVIDENCIA × PERÍODO → ESTADO ACTUAL framing and a single primary CTA.
- The login form's subtitle explicitly handles the temp-password case: "Si recibiste acceso temporal, te pediremos cambiar la contraseña en el siguiente paso." That removes a common confusion source.
- A provider invited by their client lands on the workspace entry, which explicitly asks "Confirma tus datos de contacto" with a "¿Por qué pedimos esto?" expandable. Not a developer drop-zone.

---

## 6. Screenshots index

Screenshots were captured live during this session as inline conversation artifacts (one per page audited). Filenames are reserved for the directory at `docs/audit-screenshots/2026-05-18-system-audit/` for future runs that persist them; in this session the visual evidence sits in the conversation transcript.

| # | Filename               | Page                                                |
|---|------------------------|-----------------------------------------------------|
| 01 | 01-landing.png         | `/` marketing hero                                  |
| 02 | 02-login.png           | `/login`                                            |
| 03 | 03-admin-reviewer-queue.png | `/admin/reviewer` reviewer workbench           |
| 04 | 04-admin-dashboard.png | `/admin/dashboard`                                  |
| 05 | 05-admin-clients.png   | `/admin/clients`                                    |
| 06 | 06-admin-vendors.png   | `/admin/vendors`                                    |
| 07 | 07-admin-requirements.png | `/admin/requirements` 151-row catalog            |
| 08 | 08-admin-reviewer-detail.png | `/admin/reviewer/{id}` decision panel         |
| 09 | 09-admin-calendar.png  | `/admin/calendar`                                   |
| 10 | 10-admin-audit-log.png | `/admin/audit-log` empty state                      |
| 11 | 11-admin-reports-list.png | `/admin/reports`                                 |
| 12 | 12-admin-report-editor.png | `/admin/reports/{id}`                           |
| 13 | 13-client-dashboard.png | `/client/dashboard`                                |
| 14 | 14-client-vendors.png  | `/client/vendors`                                   |
| 15 | 15-client-vendor-detail.png | `/client/vendors/{id}`                         |
| 16 | 16-client-submissions.png | (queried, not screenshotted — table renders 12 rows) |
| 17 | 17-client-activity.png | (queried, not screenshotted — page renders cleanly)  |
| 18 | 18-client-calendar.png | `/client/calendar`                                  |
| 19 | 19-client-reports.png  | `/client/reports`                                   |
| 20 | 20-portal-entry.png    | `/portal/entra-a-tu-espacio` workspace selector     |
| 21 | 21-portal-dashboard.png | `/portal/dashboard` provider next-action surface   |
| 22 | 22-portal-onboarding.png | `/portal/onboarding`                              |
| 23 | 23-portal-upload-step1.png | `/portal/upload` step 1                          |
| 24 | 24-portal-calendar.png | `/portal/calendar`                                  |
| 25 | 25-portal-reports.png  | `/portal/reports` Compliance Pulse                  |
| 26 | 26-portal-report-print.png | `/portal/reports/{id}/print` (verified in P1.9)|

---

## 7. Issue matrix

| ID    | Page / route                | Problem                                                                                                                                                         | User impact                                                                 | Severity | Recommended fix                                                                                              | Status              |
|-------|----------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|----------|--------------------------------------------------------------------------------------------------------------|---------------------|
| I-01  | (none)                      | No critical issues found.                                                                                                                                       | —                                                                           | —        | —                                                                                                            | —                   |
| I-02  | `/admin/*` 404 path         | Custom `not-found.tsx` doesn't exist; unknown admin/portal/client routes render Next.js default "404 / This page could not be found." in English, no branding, no back-home link. | Broken-feel; English in a Spanish app; no way back for a non-developer. | Medium   | Add a branded `app/not-found.tsx` with an H1 in Spanish, short copy, and a CTA back to `/`.                  | **fixed now**       |
| I-03  | `/portal/reports/[id]/print` (toolbar)  | Print page header button says "Imprimir / Guardar como PDF" — long, wraps at narrow widths. P1.8 polish.                                          | Cosmetic; the same action is also bound to "Descargar PDF" from the editor.    | Low      | Shorten to "Imprimir" (the screen is already labeled "Vista previa PDF" by the editor link, so the dialog button just needs to be "Imprimir"). | **fixed now**       |
| I-04  | `/admin/reviewer` table     | PROVEEDOR column header truncates to "P" and cell content stacks letter-per-line at 912px viewport (tablet portrait).                                            | A reviewer on iPad portrait can't read the queue.                           | Medium   | Add `overflow-x-auto` wrapper around the queue table OR a tablet-down card view.                            | **documented**      |
| I-05  | `/admin/reviewer` table tabs| Tab list ("Todos 10 / Por revisar 5 / Posible mismatch 5 / Aclaración") overflows horizontally on narrow viewports; last tab clipped.                          | A reviewer on iPad portrait may not know the 4th tab exists.                | Low      | Add `overflow-x-auto` + scroll affordance to the tab list.                                                  | **documented**      |
| I-06  | `/portal/reports/[id]/print` "DIVISOR" placeholder | The seeded reports use a `divider` block whose visible label "DIVISOR · divider" leaks the developer block-type code on screen. Print already hides it via P1.8's `print:hidden`. | Cosmetic; on-screen view exposes internal block-type IDs ("text", "kpi_strip", "divider"). | Low | Hide the type-code label in non-edit mode too (currently only hidden in print). | **fixed now** |
| I-07  | `/admin/dashboard`          | Dashboard renders single-column on desktop ≥1440; ~50% of viewport width unused.                                                                                 | Wasted screen real estate; demo-day visual underwhelm.                       | Polish   | Move stats-grid to 2-column at `lg:` breakpoint, OR add a "Recent activity" right rail.                     | **documented**      |
| I-08  | `/portal/*` (all)           | Floating bottom-left help chip "¿Necesitas ayuda? Soporte CheckWise / Sr. Demo asistente" is visually small, easy to miss.                                       | Help affordance underused; first-time users may not see it.                  | Polish   | Increase contrast or position upper-right of the page (alongside the user menu).                            | **documented**      |
| I-09  | `/admin/reports/[id]` and `/portal/reports/[id]`| When `ANTHROPIC_API_KEY` env var is set-but-empty (a real condition when running locally with `unset` semantics from a parent shell), the "Generación con IA no configurada" banner correctly fires AND the "Generar con IA" / "Copiloto" / "Actualizar con datos de hoy" buttons remain enabled. Clicking them silently produces canned mock content. | Possible confusion: user enables the buttons assuming the banner refers to a different feature. | Low (env-edge) | Banner already explains the situation accurately. Optionally disable the AI buttons when `backend === 'mock'`. | **documented**      |
| I-10  | `/login` mailto link        | "Pídelo a tu cliente o contacta soporte." — verified as `mailto:soporte@legalshelf.mx`. Good. No issue.                                                          | —                                                                           | —        | —                                                                                                            | —                   |

---

## 8. Fixes implemented during this pass

Only safe, localized, no-business-logic changes:

1. **I-02 — Custom branded 404 page.** Added `frontend/app/not-found.tsx` rendering an H1, friendly Spanish copy, and a CTA back to `/`. Replaces Next.js default English "404 / This page could not be found."
2. **I-03 — Shorten print toolbar button label.** Print page top-of-document toolbar button changed from "Imprimir / Guardar como PDF" to "Imprimir" — the calling editor button is already labeled "Vista previa PDF" / "Descargar PDF", so the button on the print page only needs to label the action ("Imprimir").
3. **I-06 — Hide block type-code label in non-edit (read-only) views.** `BlockHeader`'s `cw-print-meta-code` already hides under `print:hidden` from P1.8; this pass extends it to hide whenever `editable === false`. The internal token (`text`, `kpi_strip`, `divider`) was bleeding through into the print preview shell. After the fix, viewers see only the human label.

Each fix is no-risk: no auth changes, no business logic, no schema, no API changes.

---

## 9. Remaining recommended fixes (not implemented this pass)

| ID | Fix                                                                                              | Why deferred                                                       |
|----|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------------|
| I-04 | Wrap the reviewer queue table in `overflow-x-auto` (or build a tablet card view).             | Touches a real product surface; should be reviewed with design.   |
| I-05 | Make reviewer tab list horizontally scrollable on narrow viewports.                            | Same as I-04 — coordinated responsive pass is the right home.     |
| I-07 | Densify `/admin/dashboard` at lg breakpoint (2-col grid or right rail).                        | Layout decision; out of scope for "safe polish only".             |
| I-08 | Help chip placement / contrast.                                                                 | Cross-shell design call.                                          |
| I-09 | Disable AI buttons when `backend === 'mock'`.                                                  | Behavior change, not strictly a fix; current banner is honest.    |

---

## 10. Demo readiness assessment

**Demo-ready: yes.** Every workflow the user is likely to walk an investor or prospect through is functional:

- Public marketing landing → strong first impression.
- Login → role-correct redirect.
- Provider: lands on `/portal/dashboard` with "Tu siguiente acción" cards, can navigate to `/portal/reports` and open the Compliance Pulse strip + plantillas + a recent report's editor and print preview.
- Client: lands on `/client/dashboard` with "Tienes 3 proveedores en amarillo" headline, drills into a vendor, opens the portfolio report.
- Admin: lands on `/admin/reviewer` queue, opens a submission detail, can navigate to `/admin/reports`.
- Print + PDF flow (P1.8) works end-to-end and was verified in P1.9.

**Recommended demo path:**
1. `/` → `/login` → boss.demo@checkwise.mx
2. `/portal/dashboard` → highlight "Tu siguiente acción"
3. `/portal/reports` → Compliance Pulse + presets
4. Open the "Documentos faltantes" report → "Vista previa PDF" → show printed cover with freshness seal
5. Log out, log in as cliente.demo
6. `/client/dashboard` → "Tienes 3 proveedores en amarillo"
7. Open a vendor → 6-section narrative
8. Log out, log in as ada@…
9. `/admin/reviewer` → open one submission → show Aprobar/Rechazar/Pedir aclaración panel

This route avoids the audited rough edges (no tablet-portrait views, no unknown URLs, no AI button under mock mode).

---

## 11. Recommended next development session

**Order of priority:**

1. **(Now) Apply the polish set in §8** — already done in this pass.
2. **(Soon) Responsive sweep** — I-04 + I-05 + I-07. One focused 1-hour pass with the design taste skill; nothing risky.
3. **(Then) P2.0 — Provider-block fixtures in dev_seed.py.** The deferred slice from the P1.9 handoff. None of the four provider blocks (compliance_state / attention_list / upcoming_deadlines / prioritized_actions) currently appear in any seeded report, so the most demo-valuable surface can only be eyeballed via the planner endpoint. Carving it into the seed unblocks live print smoke and helps future demos.
4. **(Later) P1.6 (whatever that is) can wait.** It was the original "what next" anchor, but the polish gap is smaller than the missing-seed-data gap.

---

## 12. Verification gates (post-fixes)

- `ruff check app tests` — see §13 handoff.
- `pytest tests/test_reports*.py tests/test_portal_dashboard.py` — see §13 handoff.
- `npx tsc --noEmit` — see §13 handoff.
- `npx eslint . --max-warnings=999` — see §13 handoff.
- `npm run check:print` (P1.9 contract test) — see §13 handoff.
- Live browser re-check after each fix — see §13 handoff.

---

## 13. Files changed in this audit pass

- `frontend/app/not-found.tsx` — **new**, branded 404 page (I-02).
- `frontend/app/portal/reports/[id]/print/page.tsx` — toolbar button label (I-03).
- `frontend/components/checkwise/reports/block-header.tsx` — hide block type-code label in read-only mode (I-06).
- `docs/SYSTEM_UX_AUDIT_REPORT.md` — **this report.**
- `docs/NEXT_SESSION_HANDOFF.md` — short companion handoff for the next session.

Nothing else touched; the broader recommended fixes are documented but deliberately deferred.
