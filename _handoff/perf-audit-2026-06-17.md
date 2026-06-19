# Performance Audit — efficiency, loading, responsiveness (2026-06-17)

Goal: make all five surfaces (client `/client`, provider `/portal`, admin `/admin`, platform `/platform`, landing) feel **snappy, crisp, responsive — never frozen, no long times**.

Method: four parallel read-only audits (FE bundle/loading, FE data-fetching/responsiveness, BE latency/DB, heavy long-running ops). Every finding is grounded at file:line. No build, server, or migration was run — KB/latency figures are reasoned estimates, ranked by likely impact. Prior perf work (migrations 0046/0048/0049, `build_client_context` memo, audit-package batch, per-tx timeouts, async provider intake, OCR offload, landing lazy-load) was verified to hold and is **not** re-flagged.

---

## STATUS — Wave 1 implemented + verified (working tree, 2026-06-17)

**Shipped to working tree (9 changes), verified ruff/py_compile/pytest + tsc/eslint/vitest:**
- B-PERF-3 — `@lru_cache` on `compliance_catalog` builders (`recurring_for_year`, `recurring_for_year_v2`, `expediente_for_persona`) via internal cached-tuple + public list wrapper. Dataclasses are `frozen=True`; callers iterate or copy → safe.
- B-PERF-1 — batched the `can_cancel` N+1 in `_compute_recent_uploads` (portal.py): up to 10k per-row queries → one `IN` query. Result-identical to `_submission_can_be_cancelled`.
- B-PERF-6 — batched `_latest_reviewer_note` in provider onboarding via new `_latest_reviewer_notes` (one query for all slots). (Left the gated-small actionable-slots caller untouched.)
- B-PERF-7 — collapsed the duplicate notification COUNTs into one `FILTER`ed aggregate on both sides (`_provider_unread_counts`, `_client_unread_counts`). SQLite 3.53 supports FILTER.
- OP-1/B-PERF-8 — Wise Anthropic call bounded by `WISE_REQUEST_TIMEOUT_SECONDS` (20s) via `.with_options`, guarded with `getattr` so test doubles without `with_options` still work (caught + fixed a 15-test regression).
- F-RESP-2 (safe subset) — backgrounded the **save-path** `getReport` only (content already matches local state). Left regenerate/refresh blocking — see deferral.
- F-RESP-8 — deleted the discard-only 60s poll on the provider notifications page (shell already owns the bell).
- F-BUNDLE-4 — added `"motion"` to `optimizePackageImports`.
- F-BUNDLE-1 — `npm uninstall @blocknote/core @blocknote/mantine @blocknote/react` (zero imports anywhere; removed 58 packages).

**Verification:** backend ruff clean, py_compile clean, **252 passed / 14 failed** — all 14 are the documented pre-existing env baseline (uploads `requiere_aclaracion`, dashboard×4, client-portal×2), zero new. Frontend **typecheck + eslint clean**, vitest **78 passed / 1 failed** (pre-existing `lectura-del-documento` copy-assertion, not touched by this work).

**Deferred from Wave 1 → Wave 2 (audit over-rated these as safe/S; they are not):**
- F-RESP-2 (regenerate/refresh) — `RegenerateBlockResponse`/`RefreshDataResponse` return only summaries (block text / refreshed-block list), **not** full `content_json`. Dropping their re-fetch would show stale data. Needs the backend to return full content, or careful local patching — design it with the report-screen work.
- OP-4 (Reports FE default timeout) — a blanket 30s default would abort legitimately-slow AI POSTs (regenerate/explain/suggest/refresh, backend LLM cap 120s). Needs per-endpoint classification (timeout the quick writes, leave AI/SSE/downloads unbounded).

**Wave 1 committed** to local main (6 commits `ebbc278`→`5d9cdd3`), not pushed.

### Wave 2 — COMPLETE (9 commits, verified tsc/eslint/vitest + targeted pytest)

**Shipped + committed:**
- F-RESP-1 (`5f2bbf5`) — new `lib/api/request-cache.ts` (in-flight coalescing + optional short TTL, errors never cached). `getClientMe` → coalesce + 30s TTL; notification summary coalesced; `acceptClientLegalConsent` invalidates `client:me`. Kills the duplicate `getClientMe` + per-navigation re-fetch. (Follow-up: extend to provider/admin reads + pass `me` via context.)
- F-RESP-3 stream-batching (`70cbb48`) — generation coalesces per-token SSE flushes into one rAF flush; terminal events flush final content synchronously. New `use-generation.test.ts`. **Block-memoization half deferred** (stream mutates blocks in place → `React.memo` by ref would render stale; needs immutable-streaming refactor).
- B-PERF-2 (`6ddb310`) — admin correction-requests: SQL pagination on the no-filter path (count + LIMIT/OFFSET on the 0048 index) + batched `_load_correction_contexts`.
- OP-4 (`3f0cf6a`) — Reports FE per-endpoint timeouts: `WRITE_TIMEOUT_MS` on quick writes, `READ_TIMEOUT_MS` on the reads that lacked it; AI/SSE/downloads/`getReportsEngine` left unbounded.
- F-RESP-5 portal (`68fdc06`) — provider dashboard renders without waiting on the secondary onboarding fetch. **Admin dashboard deferred** (OpsHero needs both overview + rollup.queue → deeper restructure).
- OP-3 (`8b36650`) — report `/generate` plan call moved inside the SSE generator behind a heartbeat comment (no more blank pre-stream wait); plan failure → in-stream error frame.
- OP-2 (`1a62aaa`) — audit-package INDICE Chromium render bounded (launch/goto/page timeouts) + animated FE "Preparando" spinner with aria-busy.
- F-BUNDLE-2/3 (`39e9bf8`) — ShareDialog/ExportButton/PreviewPdfButton → `next/dynamic`; editable drag stack extracted to lazily-loaded `editable-block-list.tsx`, Canvas keeps a type-only `DragControls` import → read-only/print/StoryView carry zero motion runtime.
- F-RESP-4 formatter (`72fcf31`) — new `lib/format/datetime.ts` caches one `Intl.DateTimeFormat` per options signature; submissions (≤500 rows) + platform users format through it (byte-identical). **Virtualization half deferred** (needs a windowing lib + cross-consumer testing of the shared DataTable).

**Deferred from Wave 2 (with rationale):**
- B-PERF-5 (admin clients/vendors/workspaces pagination) — the pages fetch-all + filter client-side, so a backend cap would break search + silently hide rows; serializers have no N+1. Needs a coordinated FE+BE server-side-search rework (pairs with virtualization).
- F-RESP-4 virtualization, F-RESP-5 admin OpsHero restructure, F-RESP-3 block memoization, F-RESP-2 regenerate/refresh re-fetch (needs backend to return full content).

**Waves 1 + 2 PUSHED to origin/main** (`c85c009..72fcf31`, 15 commits) — auto-deploys Render + Vercel. Full backend suite at baseline (24 failed / 1796 passed, all pre-existing env/manifest — zero introduced).

### Wave 3 — infra (2 safe wins shipped; the rest is a coordinated FE+BE project)

**Committed (not yet pushed):**
- B-PERF-4 (`8cc6501`) — migration **0050** adds `ix_contracts_client_vendor` CONCURRENTLY (+ declared on the Contract model). `contracts` was a seq scan per upload/expediente. **Auto-runs via Render preDeployCommand on push → snapshot Neon first** + set `idle_in_transaction_session_timeout` (per the 0049 stall). Verified: alembic head 0050 linear, create_all smoke green.
- B-PERF-10 (`0c5fbb3`) — `db/session.py` now sets `pool_size`/`max_overflow` (defaults 10/20, env-tunable `DB_POOL_SIZE`/`DB_POOL_MAX_OVERFLOW`). The single uvicorn worker's ~40-thread sync pool was starving on the default 15. Postgres-only. Safe to push anytime.

**Deferred — all blocked on the same architectural finding:** B-PERF-9 (calendar/audit-tree/submissions payloads), B-PERF-5 (admin lists), F-RESP-4 virtualization — **the read endpoints aren't paginated because the FE fetches the full dataset and filters/renders it client-side** (admin clients/vendors/workspaces, provider submission history, the audit-package tree, the 12-month calendar grid). Capping any backend would break search / hide rows / truncate the grid. The correct fix is a coherent **server-side search + pagination + table virtualization** pass (FE+BE together), which deserves its own browser-verified project. B-PERF-11 skipped (marginal per-submission cleanups on env-fragile upload paths). F-RESP-6 streaming download progress + F-RESP-7 skeleton shaping deferred (moderate FE, hard to verify blind).

Shared tree with concurrent agents — committed per surface to avoid clobbering.

---

## The one architectural finding that frames everything

**There is no data-fetching library.** No React Query / SWR / TanStack in `package.json`. Every screen is hand-rolled `useEffect` + `useState` + raw `fetch()` via `apps/web/lib/api/*`. The base `fetchJson` (`apps/web/lib/api/client.ts:29-67`) attaches the token + a 30s abort, but does **no caching, no dedupe, no stale-while-revalidate**. Consequence: every mount and every nav re-fetches identity, notifications, and overviews; the same endpoint requested by two components on one screen fires twice. The code is clean in the small (effects cancel, dashboards use `Promise.all`, skeletons exist) — so the "feels slow on every click" is **architectural** (no cache layer), plus a handful of concrete heavy-render and blocking hotspots.

---

## Action plan (waves)

### Wave 1 — safe, high-leverage, no migration, low risk
| ID | Fix | Impact | Effort |
|----|-----|--------|--------|
| B-PERF-3 | `@lru_cache` the two `compliance_catalog` builders (pure static data) | High | S |
| B-PERF-1 | Batch the `can_cancel` N+1 in provider submissions (up to 10k queries → 1) | High | S |
| F-RESP-2 | Drop the redundant full `getReport()` after every report save/regenerate/refresh | High | S |
| B-PERF-7 | Collapse the duplicate COUNT queries on notifications lists (3 round-trips → 2) | Med | S |
| B-PERF-6 | Batch the `_latest_reviewer_note` N+1 in provider onboarding | Med | S |
| OP-1 / B-PERF-8 | Add a backend timeout to the Wise Anthropic call (only the FE 30s abort guards it today) | Med | S |
| OP-4 | Default the Reports FE client to a 30s timeout (align with portal/client clients) | Med | S |
| F-RESP-8 | Delete the wasteful 60s "keep-warm" poll on the provider notifications page | Low | S |
| F-BUNDLE-4 | Add `"motion"` to `optimizePackageImports` (one line, no code change) | Med | S |
| F-BUNDLE-1 | Remove the unused `@blocknote/*` + `@mantine` dependency (never imported) | Med | S |

### Wave 2 — medium effort, high impact, needs verification
| ID | Fix | Impact | Effort |
|----|-----|--------|--------|
| F-RESP-1 | Shared fetch cache + in-flight dedupe (TTL) around `fetchJson`; pass `me` via context — kills duplicate `getClientMe`/notif/overview on every nav across all portals | High | M |
| F-RESP-3 | Memoize report blocks (`React.memo`) + batch AI-stream SSE deltas (rAF/100ms) + `useTransition` — fixes "frozen while report generates" | High | M |
| F-BUNDLE-2 | Stop shipping the full `ReportEditor` to read-only report routes; lazy-load ShareDialog/ExportButton; thin `ReportViewer` for viewers | High | M |
| F-BUNDLE-3 | Split the editable `Reorder` stack out of `Canvas` so read-only/print carry zero `motion` runtime | High | S |
| F-RESP-4 | Virtualize the shared `DataTable` (or cap to ~50-100 server-paginated); hoist date formatting to a reused `Intl.DateTimeFormat` | High | M |
| B-PERF-2 | Admin correction-requests: push pagination into SQL (index exists), batch the workspace→vendor/client + actor loads | High | M |
| B-PERF-5 | Paginate `GET /admin/clients`, `/admin/vendors`, `/admin/workspaces` | Med | S |
| F-RESP-5 | Progressive dashboard reveal — render KPI strip as soon as it lands instead of gating on the slow rollup (`Promise.allSettled`) | Med | M |
| OP-3 | Move the report `plan_report` Claude call inside the SSE generator + emit an early `planning` frame (kills the blank pre-stream wait) | Med | S/M |
| OP-2 | Bound the audit-package INDICE Chromium render with a timeout + animate the FE "Preparando…" spinner | Med | M |

### Wave 3 — infra / migration / needs prod info
| ID | Fix | Impact | Effort |
|----|-----|--------|--------|
| B-PERF-4 | `CREATE INDEX CONCURRENTLY ix_contracts_client_vendor ON contracts(client_id, vendor_id)` (Neon snapshot ritual) | Med | S |
| B-PERF-10 | Set `pool_size`/`max_overflow` explicitly in `app/db/session.py` (needs Render worker count + Neon ceiling) | Med | S |
| B-PERF-9 | Scope the heaviest payloads — calendar `month_from/to` range, audit-tree LIMIT, cap submissions list | Med | M |
| F-RESP-6 | Streaming download progress (ReadableStream/XHR onprogress) for expediente ZIP + large blobs | Med | M |
| F-RESP-7 | Shape skeletons to final layout; keep reviewer table mounted (stale-while-revalidate) on filter change | Med | S |
| B-PERF-11 | Reviewer/finalize over-fetch: SQL-side severity predicate + `selectinload` on finalize + batched SHA256 check | Low | S |
| F-BUNDLE-8 | Pre-compress the large source PNGs in `public/marketing/` (200-460KB each) to WebP | Low | S |

---

## Full findings

### Frontend bundle & loading
- **F-BUNDLE-1** (Med/S) — `@blocknote/core|mantine|react` installed but **zero imports** app-wide; reserved for a prose mode that never shipped (`components/checkwise/reports/canvas.tsx:23-25` comments admit it). Not in shipped bundles today (tree-shaken), but bloats install/CI and risks a stray import dragging ~300-500KB into a route. → uninstall.
- **F-BUNDLE-2** (High/M) — All three portals mount the same 700-line `ReportEditor` for `/reports/[id]` even on `readOnly` (`app/{client,admin,portal}/reports/[id]/page.tsx`); it statically imports Canvas + ExportButton + ShareDialog + StoryView (`components/checkwise/reports/editor/report-editor.tsx:24-31`). Read-only viewers pay for the whole edit surface. → lazy-load ShareDialog/ExportButton via `next/dynamic`; thin viewer for read-only. (The old "~6-10KB ceiling" note predates this `readOnly`-everywhere wiring — win is now larger.)
- **F-BUNDLE-3** (High/S) — `import { Reorder } from "motion/react"` at `canvas.tsx:5` is static; `Reorder` only renders in the `editable` branch but can't be tree-shaken, so the ~40-60KB motion runtime ships to every read-only/print report view. → extract editable drag stack to a `dynamic(ssr:false)` child.
- **F-BUNDLE-4** (Med/S) — `next.config.ts:78` `optimizePackageImports` lists only phosphor. `motion/react` is used in 22 files. → add `"motion"`. One line, no code change.
- **F-BUNDLE-5** (Low/S) — `FeedbackLauncher` ("use client") mounted on landing + every portal shell; its heavy html2canvas is already lazy (`feedback-launcher.tsx:282`), residual cost minor. → optionally `dynamic` it on `app/page.tsx`.
- **F-BUNDLE-8** (Low/S) — `next/image` used correctly everywhere (no raw `<img>`); but source PNGs in `public/marketing/` are 200-460KB (portal-reports.png 462KB, etc.). Delivered bytes are optimized by Next, but pre-compressing to WebP cuts origin transfer + optimizer work. Verify none load via CSS `backgroundImage` (bypasses optimizer).
- **Clean (no action):** fonts optimal (geist self-hosted + next/font `display:swap`, `app/layout.tsx:2-21`); Calendly is a post-hydration iframe; analytics is a no-op shim; **no three.js/gsap/lenis leak into any product portal** — they stay confined to landing/legal marketing surfaces.

### Frontend data-fetching & responsiveness
- **F-RESP-1** (High/M) — No cache/dedupe. `getClientMe` fetched twice on the client dashboard (`app/client/_shell.tsx:180` + `app/client/dashboard/page.tsx:93`); shell re-runs consent check + notification summary on every nav (deps include `pathname`). → module-level TTL cache + in-flight dedupe, or SWR on authed surfaces; pass `me` via context.
- **F-RESP-2** (High/S) — Report editor throws away the mutation response and re-fetches the whole report: `report-editor.tsx:348-372` (save), `:174-196` (regenerate), `:208-231` (refresh). Doubles perceived latency of every save/regenerate on the heaviest screen. → apply mutation response to local state, drop the follow-up `getReport()`.
- **F-RESP-3** (High/M) — Zero `memo(` in `components/checkwise/reports/`; `patchBlock` spreads whole content (`canvas.tsx:66-84`); SSE sets state per frame (`lib/reports/use-generation.ts:256-291`). Whole canvas re-renders on every streamed character → "feels frozen while building". → `React.memo` blocks, batch SSE flush, `useTransition`.
- **F-RESP-4** (High/M) — No virtualization lib. Audit log (`app/platform/audit-log/page.tsx:379`), submissions (page size up to **500**, `app/client/submissions/page.tsx:57`), metadata (hundreds of rows, `app/client/metadata/page.tsx:135`), platform users — all render every row + `new Date().toLocaleString()` per row. → virtualize shared `DataTable` or cap+paginate; reuse one `Intl.DateTimeFormat`.
- **F-RESP-5** (Med/M) — Dashboards gate the whole view on the slowest parallel fetch: `app/admin/dashboard/page.tsx:70` (overview hidden behind heavy rollup), `app/portal/dashboard/page.tsx:110` (blocks on non-fatal `getOnboarding`). → progressive reveal with `Promise.allSettled` + per-section skeletons.
- **F-RESP-6** (Med/M) — Blocking blob downloads with no progress: `app/client/vendors/[vendor_id]/page.tsx:82-93,99-112,410,427-430` (expediente ZIP, metadata, PDF view). Button flips to "Descargando…" but no progress → reads as frozen. → stream with progress.
- **F-RESP-7** (Med/S) — Monolithic full-page skeletons cause reflow on data arrival; reviewer queue **unmounts** the table to a skeleton on every filter change (`app/admin/reviewer/page.tsx:373`). → shape skeletons to layout; keep table mounted at reduced opacity (SWR-style).
- **F-RESP-8** (Low/S) — `app/portal/notifications/page.tsx:138-149` polls `getProviderNotificationSummary` every 60s and **discards** it (`void s`); the shell already polls the same. → delete the interval.
- **Clean (no action):** search fires on submit not keystroke (`search-bar.tsx:33-37`); metadata filter is client-side `useMemo`; submission-detail poll is bounded (4s × 30); client dashboard already uses `Promise.all` + skeleton + cancellation.

### Backend latency & DB
- **B-PERF-1** (High/S) — `_compute_recent_uploads` calls `_submission_can_be_cancelled` per row (`portal.py:4055` → `:1866-1874`), a query each; `list_workspace_submissions` runs it with `limit=10_000` (`:4080-4090`). Up to 10k round-trips to Neon in one request. → batch the supersession lookup into one `IN (...)` query + set membership.
- **B-PERF-2** (High/M) — `GET /admin/correction-requests` (`admin.py:3353`) fetches **every** `audit_log` row for the action (append-only, unbounded, no LIMIT) + all resolutions (`:3354`), filters/paginates in Python (`:3367-3369`), then per page row lazy-loads `workspace.vendor`/`.client` (`:3310-3313`). → SQL pagination (index `ix_audit_log_action_created` exists) + batched `selectinload`.
- **B-PERF-3** (High/S) — `compliance_catalog.recurring_for_year` rebuilds ~120 dataclasses every call; `expediente_for_persona` re-filters each call (`compliance_catalog.py:566,571-667`). Pure functions of `(year, persona)`, no caching, called on every dashboard/calendar/onboarding/report-block render. → `@lru_cache` both (return immutable copies).
- **B-PERF-4** (Med/S) — `contracts` has no index on `client_id`/`vendor_id`; queried on every upload + expediente analysis (`submission_service.py:346-347`, `document_analysis/expediente.py:337-338`) → seq scan per upload. → `CREATE INDEX CONCURRENTLY ix_contracts_client_vendor`.
- **B-PERF-5** (Med/S) — `GET /admin/clients` (`admin.py:844-848`), `/admin/vendors` (`:2440-2451`), `/admin/workspaces` (`:2553-2567`) return whole tables, no LIMIT. (audit-log/users/correction-requests/metadata/feedback/contact already paginate.) → add `limit`/`offset` + `func.count()`.
- **B-PERF-6** (Med/S) — Provider onboarding loops the expediente calling `_latest_reviewer_note` per slot (`portal.py:1535`), preloaded with the dashboard. → one grouped `IN (...)` query into a dict.
- **B-PERF-7** (Med/S) — Notifications lists run the page query + two separate `func.count()` (`portal.py:4612-4614`, `client.py:2793-2810`). → single aggregate with `count(*) FILTER (WHERE ...)`.
- **B-PERF-8 / OP-1** (Med/S/M) — Wise `ask_wise` (`portal.py:4369`, `client.py:3862`) calls Anthropic **inline in a sync handler** with no backend timeout (`wise/ai.py:462-471` — no `.with_options(timeout=)`; SDK default 600s + retries). Only the FE 30s abort guards it; the worker thread keeps running after the user gives up. → `.with_options(timeout=20.0)` + `WISE_REQUEST_TIMEOUT_SECONDS`.
- **B-PERF-9 / OP-2/3 payloads** (Med/M) — Biggest single responses: client calendar materializes every vendor × requirement × 12 months (`client.py:~2180-2418`); audit-package tree returns every doc flat, no limit (`client.py:~3235-3306`); submissions list 10k. → range/scope params + LIMIT.
- **B-PERF-10** (Med/S) — `app/db/session.py:16-21` sets `pool_pre_ping`+`pool_recycle` but not `pool_size`/`max_overflow` → QueuePool default 5+10=15 conns/process. Slow sync paths (Wise LLM, PDF render, 10k list) hold a connection while doing non-DB work → pool starvation under concurrency looks like "DB is slow". → set explicitly from config, sized to worker concurrency under Neon's ceiling.
- **B-PERF-11** (Low/S) — Reviewer detail loads all `Validation` rows then filters in Python (`reviewer.py:598-604`); `finalize_intake_submission_background` lazy-loads ~6 relationships (`submission_service.py:1247-1264`); per-file SHA256 check (`:1484-1487`). → SQL predicate + `selectinload` + batched `IN (...)`.

### Heavy / long-running operations — "spinner forever" risks
- **OP-1** (Med/S) — Wise chatbot Anthropic call has no backend timeout (see B-PERF-8). Most exposed "spinner forever if FE abort ever changes".
- **OP-2** (Med/M) — Audit-package `INDICE.pdf` renders a **cold headless Chromium synchronously before the first ZIP byte**, untimed (`audit_package_manifest.py:82-115`, called from `client.py:3482`); FE button has no animated spinner (`app/client/auditoria/page.tsx:643`). Slow render → frozen "Preparando…" or 502 past the gateway. → Playwright `timeout=`, animate the spinner, optionally append INDICE last.
- **OP-3** (Med/S-M) — Report `/generate` runs the `plan_report` Claude call **before** the SSE `StreamingResponse` opens (`reports.py:838,859`); FE generate POST has no client timeout. Blank wait (no frame, no heartbeat) up to the 120s LLM cap. → move plan inside the generator + emit early `planning` frame.
- **OP-4** (Low-Med/S) — Reports FE client only sets a timeout when `timeoutMs` is passed (`reports.ts:55-58`); all mutations unbounded, unlike the portal/client clients (default 30s). → default 30s with explicit opt-out for SSE/downloads.
- **Verified clean:** provider upload async finalize + receipt + 4s×30 poll + reconcile cron; metadata XLSX is pre-built (downloads only filter/serve); report export is async with a capped poll; deep/expediente Claude always backgrounded; reports LLM client + document-analysis provider carry explicit timeouts; per-tx statement/lock timeouts + crons wired in `render.yaml`.

---

## Notes for implementation
- Shared repo + concurrent agents this session — commit per logical surface with explicit pathspecs; never bare `git add -A` / `git commit`.
- Verify backend with `.venv/bin/python -m pytest` (stale venv shebangs); local uvicorn has no `--reload` (restart after edits). The 7 env-dependent `requiere_aclaracion`/upload test failures are pre-existing baseline.
- Index migration (B-PERF-4): `CREATE INDEX CONCURRENTLY` + Neon snapshot + watch the `idle_in_transaction_session_timeout` stall noted in the 0049 work.
- Query rewrites (B-PERF-1/2/11) must be result-identical — preserve the exact predicate semantics.
