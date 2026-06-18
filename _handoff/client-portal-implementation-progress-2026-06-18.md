# Client Portal Audit — Implementation Progress (2026-06-18)

Implementing the approved **full world-class pass (Phases 0–3)** of
`_handoff/client-portal-audit-2026-06-18.md`. **Nothing committed/pushed** without user OK.

## ⚠️ ISOLATED WORKTREE (read first)
A concurrent **Codex client-calendar agent** shares the original tree
(`…/checkwise/CheckWise`, branch `feat/client-calendar-parity`) and its git ops clobbered my
uncommitted edits once. Per user decision all my work lives in an **isolated worktree**:
- **Worktree (EDIT HERE):** `/Users/josepablosamano/checkwise-wt-clientportal` — branch
  `feat/client-portal-audit` (based off HEAD f7aff86, so it contains the calendar agent's committed
  work + my audit work; coherent + typechecks).
- **Dedicated stack:** web `:3001` (preview `checkwise-clientportal-wt`) → API `:8001`
  (`cd <wt>/apps/api && '<shared>/apps/api/.venv/bin/python' -m uvicorn app.main:app --port 8001`)
  → shared Postgres `:5432`. Worktree `apps/web/.env.local`→`:8001`; `apps/api/.env` CORS adds `:3001`.
- Backups: `/tmp/cw-audit-backup-1781814699`. Login `cliente.demo@checkwise.mx` / `ClienteDemo!2026`.
- Shared tree still has my pre-isolation edits as harmless leftovers (user can revert).

## STATUS: 18 / 20 roadmap items DONE — tsc clean · vitest 58/58 · backend only 2 PRE-EXISTING fails · 0 console errors
### Phase 0 (5/5) — front door & trust
P0.1 CRITICAL provider name search (accent-insensitive, deduped) · P0.2 report/audit timeouts ·
P0.3 search focus ring + mobile/Auditoría nav · P0.4 submissions deep-links + stale-limit fix ·
P0.5 role=alert page errors (ErrorState `tone`; vendor-detail 404/403→NotFoundState).
### Phase 1 (4/4) — decision-grade dashboard
P1.6 "Requieren tu atención" worklist + worst-first vendor sort (`top_risk_vendors`) ·
P1.7 Vencidos+Rechazos KPIs, drill, denominator, reordered ·
P1.8 momentum trend chip (single-query `_approval_trend`/`approval_trend_points`) ·
P1.9 vendor `sort` param + sort control.
### Phase 2 (5/5) — truth in data + open dead-ends
P2.10 metadata table virtualized + "Mostrando N de TOTAL" on vendors/submissions ·
P2.11 submissions `en_revision` collapsed filter (`_EN_REVISION_STATUSES`) ·
P2.12 open docs from Submissions (SubmissionFileButton) + actionable vendor-detail cards (focusOnDocuments) ·
P2.13 ES label maps (activity-labels.ts + statuses.ts contract/reviewer/suggested) + vitest lock ·
P2.14 `withClientId` helper on nav/bell/logo/search/BackBar + scope-blind pages read useUrlClientId
       (reports list = thin shared-view wrapper, minor follow-up).
### Phase 3 (4/6)
P3.15 mobile drawer dialog (focus trap + Escape + restore + aria-modal) ·
P3.16 skip link + main landmark + semáforo tooltip a11y + Surface h2 heading hierarchy + mark-read live region
       (ARIA-tabs sub-item = minor follow-up) ·
P3.19 Auditoría in nav + dual-back reconciliation (BackBar prefix hiddenOn) + settings hub in UserMenu ·
P3.20 StoryView client_facing copy fix + read-viewer bundle split (dynamic imports).

## REMAINING (2 largest items — deliberately deferred, NOT rushed)
- **P3.17 design-system reconciliation** — single type-scale source (tailwind↔globals), the `--state-*`
  report-token migration (NOTE: `--state-red` is OVERLOADED — used as both strong text `#dc2626` and
  light bg `#fee2e2`, so it needs careful per-usage migration onto `--status-*`, not a single global
  define), wire-or-delete `--density-*`, eyebrow `.cw-eyebrow` sweep, card-radius rule.
- **P3.18 responsive tables** — DataTable mobile card/priority mode; metadata mobile cards; vendors
  mobile stack. (Tables currently horizontal-scroll on mobile.)
- Minor: notifications ARIA-tabs proper pattern; reports-list client_id scope; per-page `<p>`→heading
  promotions (dashboard hero, calendar SelectionDetail).

Task list (TaskCreate #1–#20) tracks per-item status (#17, #18 still pending).
