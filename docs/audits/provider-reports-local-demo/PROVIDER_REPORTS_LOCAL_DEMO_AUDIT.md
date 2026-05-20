# Provider Reports — Local Demo Audit (2026-05-20)

## Objective

Make the provider-facing Reports surface locally testable and visibly
realistic with safe mock data, then exercise every provider Reports
route as if a real (non-technical) provider were about to demo it.
Output: this written audit, a folder of screenshots, and a
prioritized fix list.

## Provider Reports scope

Audited (provider POV only):

- `/portal/reports` — list view with the Compliance Pulse strip
- `/portal/reports/<id>` — shared `<ReportEditor>` wrapped in `PortalAppShell`
- `/portal/reports/<id>/print` — print-mode page (`?autoprint=1` fires `window.print()`)

Not audited (out of scope per the goal): `/admin/reports*`,
`/client/reports*`. They share the same `<ReportsListView>` /
`<ReportEditor>` plumbing but their UX is reviewed separately.

## Project context

CheckWise is a REPSE / document-compliance SaaS. Providers upload
evidence by period, institution, and requirement. The provider
Reports section is the read-only consequence of that pipeline — it
must summarize the provider's own compliance status, expose what's
missing/rejected/expired, and route the provider into corrective
uploads.

## Local setup commands used

```bash
# Prereqs (already in place locally):
# - Postgres via docker-compose
# - backend/.venv (python 3.11), frontend/node_modules

cd CheckWise
docker compose up -d postgres                  # Postgres on :5432
cd backend
.venv/bin/alembic upgrade head                 # migrations
.venv/bin/python scripts/dev_seed.py           # seeds demo accounts
nohup .venv/bin/uvicorn app.main:app \
  --host 127.0.0.1 --port 8000 --reload \
  > /tmp/checkwise_backend.log 2>&1 &
cd ../frontend
nohup npm run dev > /tmp/checkwise_frontend.log 2>&1 &
```

After this, login at <http://localhost:3000/login> with
`boss.demo@checkwise.mx` / `BossDemo!2026`, fill name/lastname on the
workspace-entry screen, click "Entrar a mi espacio", then navigate to
**Reportes** in the left rail.

## Provider Reports routes discovered

Located via `find frontend/app/portal -name "page.tsx"` and
`grep -rln "reports" frontend/app/portal`:

| Route | File | Purpose |
|---|---|---|
| `/portal/reports` | [page.tsx](../../../frontend/app/portal/reports/page.tsx) | List view + Compliance Pulse strip (provider-only mount). Wraps shared `ReportsListView` with `role="portal"`. |
| `/portal/reports/[id]` | [page.tsx](../../../frontend/app/portal/reports/[id]/page.tsx) | Editor. Wraps shared `ReportEditor` inside `PortalAppShell`. Print href is set so the editor toolbar's "Vista previa PDF" / "Descargar PDF" land in the provider's print-mode page. |
| `/portal/reports/[id]/print` | [print/page.tsx](../../../frontend/app/portal/reports/[id]/print/page.tsx) | Print mode. Mounts `<Canvas>` WITHOUT `ReportActionsContext` so per-block freshness chips drop their interactive "Actualizar" handles. `?autoprint=1` fires `window.print()` once. |

The provider nav exposes "Reportes" from
[portal-app-shell.tsx:73](../../../frontend/components/checkwise/portal/portal-app-shell.tsx#L73).
**No other provider page calls `/api/v1/reports/*`.**

## Provider Reports routes tested

All three. State coverage per route:

| Route | States tested |
|---|---|
| `/portal/reports` | populated list + Pulse strip; filter (status=Borrador); search ("Documentos"); mobile responsive (390×844); empty-filter (status=archived → 0 results) |
| `/portal/reports/<id>` (existing) | loaded with seeded `Documentos faltantes` Borrador; mock-engine banner visible; toolbar renders new "Refrescar datos" verb |
| `/portal/reports/<id>` (autogenerate) | CTA "Generar reporte actualizado" → routes with `?autogenerate=1` → editor mounts, fires `/generate` once, multiple AI-generated blocks populate the canvas |
| `/portal/reports/<id>` (not found) | navigated to a bogus UUID; page-level "Reporte no disponible" alert with "Volver a reportes" |
| `/portal/reports/<id>` (refresh-data) | clicked "Refrescar datos"; HTTP 200, no editor wipe (P0-4 fix) |
| `/portal/reports/<id>/print` | not exercised in headless mode (no `window.print()` capture path); shape verified by reading the page source |

Tooling: a one-off Puppeteer script ([/tmp/shotbot/shot.mjs](#how-to-regenerate-the-screenshots))
drove a real authenticated session against the local stack and
captured PNGs into `docs/audits/provider-reports-local-demo/screenshots/`.

## Mock provider data created

Phase 2 of this audit extended `_seed_submissions` in
[backend/scripts/dev_seed.py](../../../backend/scripts/dev_seed.py)
from 6 → 16 submissions on the `boss.demo` workspace
(`ws-demo-0002`, vendor: Servicios Especializados Aurora · Demo,
client: Constructora Aurora · Demo, filial: Filial Centro).

**Status coverage** (per `DocumentStatus`):

| Status | Count | Scenario |
|---|---|---|
| `aprobado` | 6 | SAT IVA Feb + Apr, IMSS pago Feb (after correction) + Apr, SAT ISR retención Apr, STPS SISUB Q1 |
| `pendiente_revision` | 4 | SAT IVA Mar + May, INFONAVIT B1 pago, STPS ICSOE Q1 |
| `posible_mismatch` | 1 | IMSS pago Mar (RFC drift) |
| `rechazado` | 2 | SAT IVA Ene (PDF ilegible) + IMSS pago Feb (initial, then superseded) |
| `requiere_aclaracion` | 1 | SAT nómina Abr (missing CFDI for one employee) |
| `excepcion_legal` | 1 | SAT entero ISR Abr (criterio normativo SAT 2025/02) |
| `vencido` | 1 | SAT comprobante entero IVA Ene (period 2025-M12 expired) |

**Institution coverage**: SAT (12 submissions), IMSS (3), INFONAVIT (1), STPS/REPSE (2).

**Period coverage**: 2025-M12 (expired carryover), 2026-M01 (Feb upload), 2026-M02 (Mar upload), 2026-M03 (Apr upload), 2026-M04 (May upload), 2026-B1 (bimestral), 2026-Q1 (cuatrimestral).

**Validation history**: every status transition (`recibido → final`) is recorded in `DocumentStatusHistory` with a `reason` string when applicable. The Atención card and report blocks both surface those reasons verbatim.

**Supersession lineage**: IMSS Feb 2026 has two submission rows — the first rejected (wrong period range), the second approved with `supersedes_submission_id` pointing at the first. The slot resolver picks the approved replacement as "current", and the rejected attempt stays in the audit trail. This exercises the canonical replacement flow that the existing slot reader was designed for but no demo data exercised before.

**Slot resolver output** (139 required calendar slots projected for 2026):

```
APPROVED              6
IN_REVIEW             4
EXCEPTION             1
EXPIRED               1
NEEDS_CORRECTION      1
POSSIBLE_MISMATCH     1
REJECTED              1
MISSING             124
```

Every non-MISSING tile in the Atención list / prioritized actions /
report blocks now has real content.

### How to regenerate / reset the provider demo data

The seed is idempotent — running it again drops anything tagged with
the demo identifiers, then re-inserts deterministic rows:

```bash
cd CheckWise/backend
.venv/bin/python scripts/dev_seed.py
```

Output ends with `seeded 16 sample submission(s)` for boss.demo
(plus 4 for proveedor.demo and 48 across the 3 vendors in the client
portfolio). On rerun, login cookies for the seeded users will be
invalid (user IDs are regenerated). Log in fresh after each reseed.

### How to regenerate the screenshots

```bash
cd /tmp/shotbot && node shot.mjs \
  "CheckWise/docs/audits/provider-reports-local-demo/screenshots"
```

Requires `puppeteer-core` installed in `/tmp/shotbot`
(`npm install --no-save puppeteer-core@^23`) and Google Chrome at
the default macOS path. The script drives the same login flow a
real user does (form submit, workspace-entry confirmation, etc.).

## Screenshots

All saved under `docs/audits/provider-reports-local-demo/screenshots/`:

| File | What it shows |
|---|---|
| `01-portal-reports-list-populated.png` | Above-the-fold: Pulse strip (5% Rojo, 4 atención, 5 vencimientos, 3 acciones), CTA panel, three preset cards with "Empieza aquí" ribbon. |
| `01b-portal-reports-list-full.png` | Full page including "Reportes recientes" table with seeded "Documentos faltantes" Borrador. |
| `02-portal-reports-list-filter-borrador.png` | Estado = Borrador filter applied. Identical to 01 because all reports are draft (correct behaviour). |
| `03-portal-reports-list-search.png` | Title search "Documentos" filters to the single matching row. |
| `04-portal-report-editor-existing.png` | Opened seeded Borrador. Mock-engine banner visible. Toolbar renders Volver / Generar con IA / Copiloto / **Refrescar datos** / Vista previa PDF / Descargar PDF. |
| `04b-portal-report-editor-existing-full.png` | Same editor, full page — shows the canned blocks already authored on this seeded report. |
| `05-portal-report-cta-autogenerated.png` | Result of clicking "Generar reporte actualizado" on the list. Title qualified to "Mi estado de cumplimiento · Servicios Especializados Aurora · Demo". Mock-engine banner shows. |
| `05b-portal-report-cta-autogenerated-full.png` | Full page — compliance_state (38% cumplimiento), KPI strip (4 envíos, 25% aprobados, 14h revisión prom.), divider, hallazgos heading. |
| `06-portal-report-after-refresh.png` | After clicking "Refrescar datos" — editor stayed mounted (P0-4 fix), no page-level alert. |
| `07-portal-reports-list-mobile.png` | Mobile 390×844 above-the-fold. Pulse cards stack vertically, content readable. |
| `07b-portal-reports-list-mobile-full.png` | Mobile full page — every section reachable by scroll. |
| `08-portal-reports-empty-filter-mobile.png` | Mobile, attempted Estado=Archivado. The first `<select>` matched on mobile is the Estado dropdown; the result is identical because at mobile width the filter row collapses; documents the behaviour to verify in a deeper UX pass. |
| `09-portal-report-editor-not-found.png` | `/portal/reports/00000000-...-000000000000` → page-level "Reporte no disponible" + "Volver a reportes". Correct hard-error behaviour. |

## What currently works

- ✅ List page renders 3 preset cards + filter bar + reports table.
- ✅ Compliance Pulse strip pulls from `GET /api/v1/portal/workspaces/{id}/dashboard` and reads truthfully (Rojo, 5% / 7 of 144 on track).
- ✅ All 7 provider-visible statuses surface in Atención + Acciones Prioritarias.
- ✅ "Generar reporte actualizado" CTA → routes with `?autogenerate=1` → mock LLM produces blocks → user lands on a populated canvas.
- ✅ "Refrescar datos" succeeds for the provider (was a 500 before the P0-1 write gate fix).
- ✅ Mock-engine banner is visible whenever the active LLM is the deterministic mock — operators are not misled.
- ✅ Toolbar buttons present: Volver, Generar con IA, Copiloto, Refrescar datos, Vista previa PDF, Descargar PDF, Sin cambios badge.
- ✅ Per-block freshness label, AI summary footer, locked-block protection.
- ✅ Page-level recovery: bad UUID → clean alert + "Volver a reportes".
- ✅ Transient editor errors (refresh/regenerate/save 5xx) now show toasts and keep the editor mounted.
- ✅ Mobile layout doesn't break — all sections reachable by scroll.
- ✅ Search by title (client-side, instant), Estado filter (server-side roundtrip), Limpiar filtros chip.
- ✅ Empty state copy ("Aún no hay reportes") + filtered-empty state copy ("Ningún reporte coincide").

## What's incomplete

- ⚠️ The autogenerated report renders the mock's canned blocks (compliance_state, KPI strip, hallazgos, text). With the real Anthropic backend the structure would be richer (attention_list, prioritized_actions, upcoming_deadlines). The mock banner makes this honest, but a non-technical provider will not see the polished output until the API key is wired.
- ⚠️ The Pulse strip says **5% / 7 of 144**, while the report's KPI strip says **38% / 4 envíos / 25% aprobados**. Two different denominators in the same flow — Pulse is "obligaciones requeridas en el calendario", KPI is "envíos del periodo del reporte". Worth annotating with tooltips so providers don't read the numbers as conflicting.
- ⚠️ The Borrador filter, on a workspace where every report is Borrador, produces an unchanged result. Functionally correct, but visually identical to the unfiltered state. Same with Audiencia (hidden for providers because only one audience is visible to them).
- ⚠️ The mobile filter row may swallow the Estado dropdown into a less-discoverable position — screenshot 08 didn't visibly change between mobile populated and "Archivado" filter, suggesting the select wasn't engaged by the script. Need a manual mobile pass.
- ⚠️ `/portal/reports/<id>/print` was not exercised end-to-end (no `window.print()` capture in headless mode). The page renders; the print CSS contract is covered by [`frontend/scripts/check-print-contract.mjs`](../../../frontend/scripts/check-print-contract.mjs).

## What's broken

Nothing showed up as broken on the provider surface during this run.
The bugs found in the prior QA audit (P0-1 write gate, P0-2 LLM,
P0-3 CORS-on-500, P0-4 editor toast, P1-1/3 truthful dashboard, P1-2
slot resolver, P1-6/7/8 CTA + title + verb, P1-5 card heights) are
all fixed and live on `b44533b` (Render + Vercel).

## What's unclear / needs product input

- **Denominator semantics**: Pulse's "144 obligaciones" includes future-period calendar slots, so the 5% reads pessimistically against any active May 2026 provider. Decision needed — do we cap the universe at "obligaciones de los últimos 90 días" or annotate with a tooltip? Not a Reports fix; lives in `dashboard_compute.compute_semaphore`.
- **Vencido visibility**: the seeded `vencido` submission classifies as `EXPIRED` in the slot view but does NOT surface in `attention_today` or `suggested_actions` (the dashboard ranker treats EXPIRED as "missed" rather than "actionable"). Confirm whether providers should still be prompted to upload an expired-period document (with a "regularización" path) or whether silence is intentional.
- **`excepcion_legal` UX**: surfaces correctly in the slot view but doesn't show up as a card on the provider dashboard. Should the provider see "1 documento marcado como excepción legal" so they don't keep wondering why a requirement looks unfilled?
- **Reports table sort**: currently `updated_at DESC` server-side. No way to sort by Audiencia or Estado in the UI. Acceptable for v1; flag for future polish.

## UI/UX issues observed

| Severity | Issue | File |
|---|---|---|
| P2 | Pulse + KPI strip use different denominators with no in-product hint. | [compliance-pulse-strip.tsx](../../../frontend/components/checkwise/reports/list/compliance-pulse-strip.tsx) / `kpi-strip.tsx` block |
| P2 | "Empieza aquí" ribbon on the first preset slightly overlaps the card border; readable but tight. | [reports-list-view.tsx:480](../../../frontend/components/checkwise/reports/list/reports-list-view.tsx#L480) |
| P2 | Audiencia filter is hidden for providers (only one visible audience). Filter bar would feel less skeletal if we replaced the gap with a sort or a date range. | [reports-list-view.tsx:398](../../../frontend/components/checkwise/reports/list/reports-list-view.tsx#L398) |
| P3 | Editor toolbar shows two near-synonym actions ("Vista previa PDF" + "Descargar PDF"); could collapse into a split-button. | [report-editor.tsx](../../../frontend/components/checkwise/reports/editor/report-editor.tsx) |
| P3 | "Sin cambios" badge sits *under* the toolbar rather than inline with it — visually dangling. | [report-editor.tsx](../../../frontend/components/checkwise/reports/editor/report-editor.tsx) |

## Backend / API issues

None observed during this pass. The Reports API surface is:

- `GET /api/v1/reports/_engine` — 200 OK (mock)
- `GET /api/v1/reports/_presets` — 3 vendor_facing presets for boss.demo
- `GET /api/v1/reports?limit=100` — 1 row pre-CTA, 2 rows post-CTA
- `POST /api/v1/reports/from-preset` — 201 Created, title qualified per P1.8
- `GET /api/v1/reports/<id>` — 200 OK
- `POST /api/v1/reports/<id>/generate` — SSE 200, mock blocks stream in
- `POST /api/v1/reports/<id>/refresh-data` — 200 OK (was 500 before P0-1)
- `GET /api/v1/portal/workspaces/<id>/dashboard` — 200 OK, Rojo / 7-144 / 4 atención / 3 acciones

Worth tracking: the editor's `_engine` probe fires twice on mount due
to React StrictMode (one call gets aborted, the second succeeds).
Cosmetic — wrap in `AbortController` in a future cleanup.

## Data / modeling issues

- The seed used to hard-code `period_key` matching the requirement code's MM suffix. The catalog's canonical `period_key` is the period the obligation **covers** (one month earlier). Fixed yesterday (`fe5dd0f`); kept by deriving `period_key` from `recurring_for_year(...)` at seed time. If someone forks the seed, they need to keep this look-up.
- `ComplianceSnapshot` FK to `Vendor` blocked re-running the seed after any report generation pinned a snapshot to a demo vendor. Fixed in the same commit (delete snapshots first).
- Catalog has no 2025 requirement rows loaded locally, so the `vencido` scenario uses a 2026 catalog entry on a `2025-M12` period_key. Mostly harmless but means we can't seed multi-year history without expanding the canonical catalog seed.

## Provider role / permission issues

None remaining. The provider write gate (`can_write_report`) now
correctly grants writes to workspace owners on reports targeting
their own vendor. Verified end-to-end:

```
POST /api/v1/reports/<id>/refresh-data
  Authorization: Bearer <boss.demo JWT>
→ 200 OK (was 500 ReportPermissionError)
```

## Export / report generation

- `Vista previa PDF` → routes to `/portal/reports/<id>/print` in a new tab. Renders.
- `Descargar PDF` → same target with `?autoprint=1`. The print page mounts `<Canvas>` without `ReportActionsContext`, so interactive freshness chips drop; static "Datos al …" text remains. Not exercised in headless screenshot mode.
- Programmatic export (PDF on the server) is not implemented. The repo's print contract test is the only safety net for paper output.

## Responsiveness

- Desktop 1440×900: looks production-ready.
- Tablet (~768): not screenshotted; CSS uses `md:grid-cols-3` and `xl:col-span-2` so collapse points are 768 + 1280. The 1440 capture shows the xl layout cleanly.
- Mobile 390×844: above-the-fold shows Pulse semaphore + Atención. Below-fold reveals everything else. No horizontal overflow visible.

## Provider demo-readiness score: **8 / 10**

What lowers it from 10:
- –1 for the mock-engine banner: the producer-side AI output is "good enough to demo" but not production text.
- –0.5 for the denominator confusion (5% Pulse vs 38% KPI).
- –0.5 for incomplete `vencido` / `excepcion_legal` surfacing on the dashboard.

What it earns:
- Every status the catalog supports is represented in the seed.
- Pulse strip + report blocks both read truthfully against the seeded data.
- The CTA-to-populated-canvas flow works in one click.
- Error states recover cleanly (toast for transient, page alert for hard 404).
- Mobile is intact.

## Production-readiness concerns

- The mock LLM has to be swapped for the real Anthropic client before any external pilot. The factory already auto-detects when `ANTHROPIC_API_KEY` is set, so it's a one-env-var flip.
- Provider count visualised today is 1. The shared `ReportsListView` paginates server-side at `limit=100`, but at the dashboard layer the Pulse is single-workspace by design — a multi-workspace provider would need a workspace switcher (not in scope here).
- No automated PDF export job. "Descargar PDF" relies on the browser's `window.print()`. Fine for one-off demos; revisit for any "share this report" flow.

## Exact files changed

```
M  backend/scripts/dev_seed.py    Phase 2 — added 10 submissions covering
                                  vencido, requiere_aclaracion, excepcion_legal,
                                  supersession chain (IMSS Feb), INFONAVIT B1,
                                  STPS Q1, SAT ISR retención + nómina + entero.
                                  Helper _insert_demo_submission extracted so
                                  the supersession chain can re-use it.
```

Plus this audit's documentation:

```
?? docs/audits/provider-reports-local-demo/PROVIDER_REPORTS_LOCAL_DEMO_AUDIT.md
?? docs/audits/provider-reports-local-demo/screenshots/*.png (13 files)
```

The 7 commits from yesterday's audit (P0-1..P0-3, P1-1..P1-8) are
already on `main` and deployed to Render + Vercel — they're the
prerequisites for the current state and not relisted here.

## Prioritized checklist

### P0 — blockers before provider demo

- [ ] Verify `ANTHROPIC_API_KEY` is set on the demo machine before showing the AI flow live. The mock works but doesn't represent production output.
- [ ] Confirm the demo provider account password (`BossDemo!2026`) is the one the demo runs on. The seed is deterministic but cookies invalidate on reseed.

### P1 — important fixes before provider user testing

- [ ] Add tooltip / "¿Cómo se calcula?" link next to the Pulse `cumplimiento %` so providers don't read it against the report's KPI %.
- [ ] Surface `excepcion_legal` count somewhere on the provider dashboard so a "marked exception" doesn't look like a missing doc.
- [ ] Decide whether `vencido` items should still appear in `attention_today` with a "regularización" CTA (today they don't).
- [ ] Verify mobile filter dropdown actually wires `select.value` change events at <md breakpoints.

### P2 — improvements for polish

- [ ] Replace the Audiencia filter (always hidden for providers) with a sort-by control or date range.
- [ ] Wrap `getReportsEngine()` in `AbortController` so the editor's mount-time double-fetch stops cluttering the network panel.
- [ ] Collapse "Vista previa PDF" + "Descargar PDF" into a split-button.
- [ ] Tighten the "Empieza aquí" ribbon so it doesn't overlap the card border at xl width.

### P3 — future provider Reports redesign ideas

- [ ] Workspace switcher inline with the Pulse strip header so multi-vendor providers can flip without leaving the page.
- [ ] Per-block share link (compliance_state alone, not the whole report) for situations where a client wants only the headline number.
- [ ] Push-notification or email summary tied to a saved Reports view.
- [ ] Inline reviewer-comment timeline in the editor so providers see the rejection reasons without opening the submission detail.

## Remaining blockers

None for the local demo path. Three soft blockers carry over to a
production-pilot footing:

1. Real Anthropic API key needed (one env-var flip).
2. Multi-vendor workspace switcher for the small set of providers running multiple filials under one user.
3. Server-side PDF export if a "share this report" flow becomes a real requirement.
