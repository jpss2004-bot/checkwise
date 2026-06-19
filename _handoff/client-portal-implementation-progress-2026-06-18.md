# Client Portal Audit — Implementation Progress (2026-06-18)

Implementing **Phases 0–3** of `_handoff/client-portal-audit-2026-06-18.md` (user approved the
"full world-class pass"). Working tree only — **nothing committed/pushed** without user OK.

## Environment facts
- Stack runs locally: web dev server :3000 (preview id changes on restart), API :8000, Postgres :5432 (docker `checkwise-postgres`).
- Client login: `cliente.demo@checkwise.mx` / `ClienteDemo!2026` (org "Operadora Multinacional · Demo", 3 providers all red, 5% compliance). Inject session via POST /api/v1/auth/login → localStorage key `checkwise.admin.session.v1`.
- Local DB creds: `postgresql://checkwise:checkwise@localhost:5432/checkwise`. Real client_id for demo: `7649726d-1736-4ac3-80ba-f9fc07ac1f4b`.
- **API has NO --reload** — restart after backend edits: `kill <pid>; cd apps/api && nohup .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/checkwise-api.log 2>&1 &`
- **node_modules was corrupted** (43 `" 2"` dup dirs + zeroed package.json from the workspace cleanup) → repaired with `npm ci` in apps/web (551 pkgs). If build errors like "Cannot find module '@jridgewell/...'" reappear, re-run `npm ci`.
- typecheck: `cd apps/web && npx tsc --noEmit` (clean as of Phase 0). Em-dash path: use `CHECKWISE_DIST_DIR=/tmp` for `next build` if needed (dev is fine).

## DONE (Phase 0) — all verified live, tsc clean
- **P0.1 CRITICAL provider name search**: `search_service.py` adds `name` QueryType + accent_ci_contains(Vendor.name/Client.name) in the free-text branch, dedupe-per-vendor; FE `search.ts` SearchMatchType+`name`, `search-results.tsx` label/placeholder/empty-hint, `search-bar.tsx` placeholder/docstring/aria, `buscar/page.tsx` copy. Verified vs real Postgres (accent-insensitive) + live UI ("Constructora"→1 NOMBRE result).
- **P0.2 timeouts**: `reports.ts` GENERATE_TIMEOUT_MS=180s on createReportFromPreset(autoGenerate); `client.ts` AbortController+120s on downloadClientAuditPackageZipPost.
- **P0.3 search a11y/mobile**: focus ring on result rows (`search-results.tsx`); `_shell.tsx` mobile drawer "Buscar" link; docstring fix.
- **P0.4 submissions deep-links**: `submissions/page.tsx` reads `useSearchParams` to seed filters, writes URL on apply (preserves client_id), passes client_id to API, fixed stale-limit race (URL-driven fetch effect + reloadKey retry).
- **P0.5 role=alert errors**: extended shared `ErrorState` (state-surfaces.tsx) with `tone: warning|error` (default warning, backward-compatible); dashboard + vendor-detail page errors now route through ErrorState (role=alert, error tone, Reintentar); vendor-detail distinguishes 404/403 → NotFoundState + "Volver a proveedores".
- Also folded in **P3.19 partial**: Auditoría added to NAV (reordered: Reportes before Auditoría, both before Notificaciones).

## NEXT
- Phase 1: P1.6 at-risk worklist + worst-first vendor sort, P1.7 overdue/rejected KPIs + drill + denominator, P1.8 trend delta, P1.9 vendor sortable headers. (All extend `ClientOverview` in `apps/api/app/api/v1/client.py` + `lib/api/client.ts` + dashboard/page.tsx.)
- Phase 2: P2.10 pagination, P2.11 En-revisión filter, P2.12 open docs/actionable cards, P2.13 localize tokens, P2.14 finish scope-preserving nav (withClientId helper for the rest of the pages).
- Phase 3: P3.15 mobile nav dialog, P3.16 a11y cluster, P3.17 design-system, P3.18 responsive tables, P3.19 remainder (dual-back, settings hub), P3.20 viewer bundle split + StoryView copy.

Task list (TaskCreate #1–#20) tracks per-item status.
