# CheckWise — Client Portal improvement task (Codex handoff)

> Self-contained brief. You (Codex) are picking up work on the CheckWise client portal
> based on a tester's functional/UX audit. This doc has everything: context, the source
> findings, a verified current-state verdict with file anchors, a phased scope with
> acceptance criteria, repo conventions, and the open product decisions. Verify file:line
> anchors before editing — they were captured 2026-06-15 and may drift.

## 1. Mission

CheckWise is a Mexican REPSE-compliance SaaS. Clients (buyers) track whether their
**providers** have uploaded the legally-required documents (SAT/IMSS/INFONAVIT/STPS, etc.)
per **period**. A tester audited the **client-facing compliance experience** and filed 16
findings (CW-01…CW-16). The root cause: **no single canonical "status" for a required
document (provider × period)** — each screen recomputes/relabels it, so users see
contradictions and can't get from an alert to the exact document to fix.

Goal: make the client portal "the best it's been yet" by closing the remaining gaps,
without regressing the consistency work already shipped.

## 2. Repo, stack, how to run & test

- Repo root: `apps/api` (FastAPI backend, Python 3.11) + `apps/web` (Next.js, TypeScript).
- Backend client endpoints: `apps/api/app/api/v1/client.py`. Provider portal: `portal.py`.
  Reports: `reports.py` + `app/services/reports/**`. Status model: `app/constants/statuses.py`,
  slot logic: `app/services/evidence_slots.py`.
- Frontend client routes: `apps/web/app/client/**`. Provider: `apps/web/app/portal/**`.
  Shared status glossary: `apps/web/lib/constants/statuses.ts`. API client: `apps/web/lib/api/client.ts`.
- **Tests (backend):** in-memory SQLite via `create_all` from the models (NOT alembic), so a
  new model column is picked up automatically. Run a focused file:
  `cd apps/api && .venv/bin/python -m pytest tests/test_client.py -q` (also `test_client_users.py`,
  `test_reports*.py`). Don't run the full suite blind — 9 tests are known-failing on HEAD
  (portal x3, dashboard x4, client-portal x2); don't attribute those to your change.
- **Frontend checks:** `cd apps/web && npx tsc --noEmit && npx eslint <changed files>`.
  NEVER run `npm run build` while a dev server is running (corrupts `.next/`).
- **Lint:** `apps/api/.venv/bin/ruff check <changed files>` (whole-app ruff has ~49
  pre-existing errors — scope ruff to files you touch).

## 3. Hard conventions (do not violate)

- **Dependency lock:** `apps/api` deps are pinned in `apps/api/requirements.lock`; Render builds
  with `pip install -e . -c requirements.lock`. If you add a Python dep, regenerate the lock
  (recipe in its header) — a fresh `pip install -e .` resolving newer FastAPI once crash-looped prod.
- **FastAPI gotcha:** FastAPI 0.137 includes sub-routers lazily; never introspect `app.routes`
  for route existence — use `app.openapi()["paths"]`.
- **Commits:** direct-to-`main`, explicit file paths (never `git add -A`), multi-paragraph commit
  bodies ending with a verification line. Split commits per logical surface (backend vs frontend).
  End commit messages with a Co-Authored-By trailer if your harness requires one.
- **Migrations:** alembic head is currently `0045_user_account_lockout`. New migration = next
  number, additive/backward-compatible. **Pushing a migration commit auto-deploys to prod Neon via
  Render preDeploy — the user takes a named Neon snapshot first.** Do NOT push migration commits
  without surfacing this to the user.
- **Do not stage** the uncommitted `apps/web/components/marketing/hero-*.tsx` files — they're a
  separate landing-redesign WIP.
- **Status vocabulary is canonical and unified** (shipped 2026-06-10): use
  `apps/web/lib/constants/statuses.ts` + `apps/api/app/constants/statuses.py`. There are drift
  guards in `statuses.test.ts`. Never invent new labels — extend the glossary.

## 4. The source findings (CW-01…CW-16)

P0 = consistency, P1 = actionability, P2 = polish. CW-07…CW-10 are the **provider upload flow**
(`/portal/*`) — included because the client's providers use it; confirm with the user whether
they're in scope for this pass.

| ID | Area | Finding |
|---|---|---|
| CW-01 | Data/status | `/client/submissions` and `/client/calendar` show different results for the same doc |
| CW-02 | Calendar | Missing docs (no submission) are surfaced as "en revisión" |
| CW-03 | Taxonomy | Different status names across calendar/entregas/reports |
| CW-04 | Reports | Reports give %/recommendations but don't link to the doc/provider/period to fix |
| CW-05 | Client/Providers | Can't view/download a provider's contract |
| CW-06 | Client/Providers | Only percentages; can't see which document is missing |
| CW-07 | Upload | Period ambiguous; frequency (mensual/bimestral/…) unclear |
| CW-08 | Upload | Unclear which annexes/extra docs to upload (esp. "contrato original") |
| CW-09 | Upload | No way to cancel/replace an upload before review |
| CW-10 | Upload | "Vamos al calendario" button navigates to dashboard |
| CW-11 | Deliveries | Single filter; wants combinable filters |
| CW-12 | Calendar | Can't filter by bimestral/cuatrimestral frequency or period |
| CW-13 | Notifications | Notifications arrive but no visible link to change preferences |
| CW-14 | Metadata | Already-approved docs have no metadata |
| CW-15 | Exports | Excel maestro: global vs per-provider unclear |
| CW-16 | Risk matrix | Inconsistent risk language; "why" not explained |

## 5. Current-state verdict (verified against code 2026-06-15)

**✅ Already DONE — do not redo, just don't regress:**
- **CW-03** vocabulary unified (`statuses.ts` / `statuses.py` + drift tests).
- **CW-05** contract view/download: `ContractDocumentsCard` in
  `apps/web/app/client/vendors/[vendor_id]/page.tsx` → `GET /api/v1/client/submissions/{id}/document`
  (`client.py` ~1793) with audit + tenant scope.
- **CW-11** combinable entregas filters: `apps/web/app/client/submissions/page.tsx` (vendor + status +
  institución + periodo), backend `client_submissions()` AND-combines them (`client.py` ~2085).
- **CW-10** post-upload nav: success CTA → `/portal/calendar` (`intake-wizard.tsx` ~1943);
  dashboard link only in the no-requirement empty state. **Verify the exact button text the tester
  saw before assuming fully closed.**
- **CW-16** risk score: deterministic 0–100 from bad-state buckets (`data_fetchers.py` ~850),
  consistent colors. Missing only: a user-facing "why," and weighting upload-delay/rejections.

**🟡 PARTIAL:**
- **CW-01** calendar+reports share `build_workspace_calendar_slots()`; **`/client/submissions` reads raw
  `Submission.status` and never uses slots** (`client.py` ~2085-2222) → genuine divergence.
- **CW-04** `prioritized-actions.tsx` + vendor `suggested-actions` deep-link to the fix; **the
  `ai-recommendation` and `key-findings` report blocks are static text**.
- **CW-06** vendor page shows donut + "atención hoy" + upcoming deadlines; **no flat list of every
  missing/rejected/expiring doc** (`apps/web/app/client/vendors/[vendor_id]/page.tsx`).
- **CW-07** frequency shown in calendar drawer + wizard step 2; weak in the upload area itself.
- **CW-12** calendar filters = vendor + year only; **no frequency/bimestral/cuatrimestral filter**
  (`apps/web/app/client/calendar/page.tsx`, `client_calendar()` `client.py` ~1916).
- **CW-13** prefs page exists at `/client/configuracion/notificaciones`; **not linked from the
  notification center (`/client/notifications`) or the profile menu (`client/_shell.tsx`)**.
- **CW-14** metadata generated on upload going forward (`app/services/metadata_export.py`); **no
  retroactive backfill** for historical approved docs.
- **CW-15** global Excel export exists (`GET /api/v1/client/metadata/download`, `client.py` ~2612);
  **no per-provider filtered export**.

**❌ NOT DONE:**
- **CW-02** calendar KPI folds missing slots into the `pending_total` counter rendered as
  "En revisión" (`client.py` ~2024-2035 → `apps/web/app/client/calendar/page.tsx` ~232). The
  per-item label may be correct ("Por entregar"); the **summary counter** is the bug. **Reproduce
  the exact rendering before fixing.**
- **CW-08** bare multi-file picker; backend `minimum_documents` exists but isn't surfaced as an
  expected-annexes checklist (`intake-wizard.tsx` ~1517).
- **CW-09** no cancel/delete of an un-reviewed submission; only reject→re-upload (no DELETE/cancel
  endpoint in `portal.py`; no draft state).

## 6. Scope to execute (phased; acceptance criteria are the definition of done)

### Phase 1 — Close the truth gap (do first; smallest + highest trust)
- **CW-02:** A required document with no submission must never be counted/labeled as "En revisión"
  anywhere on the calendar. Split "faltante/por entregar" out of the in-review counter.
  *Accept:* a missing slot shows "Por entregar" (or the glossary's missing label) in both the
  per-item view and the KPI counters; a regression test asserts a no-submission slot is never
  classified in-review.
- **CW-01:** Make `/client/submissions` reconcilable with the calendar — either consume the slot
  model, or explicitly frame submissions as "documents submitted" vs the calendar's "obligations
  required," using the shared glossary for any status shown.
  *Accept:* a backend test loads the same (provider, period, requirement) via the submissions path
  and the calendar/slot path and asserts the status label matches (or documents why they differ by
  design).

### Phase 2 — Make alerts actionable
- **CW-06:** On the vendor detail page, add a concrete list/table of that provider's missing /
  rejected / expiring documents (institución, periodo, fecha límite, estado), each deep-linking to
  its fix (reuse the existing upload-href builders in `portal.py` ~3231).
  *Accept:* from a provider's page the client can see and click into every missing/rejected doc.
- **CW-04:** Give the `ai-recommendation` and `key-findings` report blocks the same deep links the
  `prioritized-actions` block already uses.
  *Accept:* every "hay faltantes"-style finding opens those exact faltantes; no static dead-ends.

### Phase 3 — Upload flow (provider-side; confirm in scope)
- **CW-08** per-requirement anexos checklist (surface `minimum_documents` + expected attachments +
  examples). **CW-09** cancel/replace a pending (un-reviewed) submission (+ optional draft).
  **CW-07** make period + frequency prominent in the upload area.

### Phase 4 — Clarity & polish
- **CW-12** calendar frequency/period filters · **CW-13** link notification prefs from the bell +
  profile menu · **CW-15** per-provider Excel export · **CW-14** metadata policy for historical docs
  (retroactive backfill job vs on-demand + explain absence) · **CW-16** add "why this risk"
  explanation; consider weighting upload-delay & rejection frequency.

## 7. Open product decisions — ASK THE USER before Phase 2+ (don't guess)
1. The **definitive status set** (faltante / pendiente / en revisión / aprobado / rechazado /
   vencido / por vencer) — confirm the exact list + Spanish labels.
2. **Who may correct a document** — provider, client, admin, or role-dependent?
3. **Metadata policy** for historical approved docs — retroactive backfill, on-demand extract, or
   "explain absence"?
4. **Excel maestro** — global, per-provider, per-period, or all?
5. **Anexos for "contrato original"** + when "acta constitutiva" applies (CW-08).
6. **Notification config granularity** — per user / client / provider / document type?

## 8. Definition of done (every phase)
- `tsc --noEmit` + eslint clean on touched frontend files; ruff clean on touched backend files.
- New/updated tests pass; relevant existing client/reports tests still pass.
- Use the canonical status glossary; no new label vocabulary.
- Commit per surface with a verification line; surface any migration to the user before pushing
  (Neon snapshot first).
