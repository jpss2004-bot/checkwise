# Client Portal — Performance, Loading, Responsiveness & Hardening Audit

**Date:** 2026-06-18
**Scope:** `/client/*` only — frontend (`apps/web/app/client/**`, `apps/web/lib/api/client.ts`) and backend (`apps/api/app/api/v1/client.py`, `client_users.py`, `services/client_metadata.py`, `services/client_notifications.py`, plus followed helpers).
**Mode:** Read-only audit. No code changes made. Findings are prioritized; each cites `file:line`, root cause, impact, and a suggested fix (not implemented).
**Method:** 3 parallel agents (frontend perf, backend perf, hardening) + manual spot-verification of the top anchor claims.

---

## Verdict

The client portal is **secure** (no exploitable cross-tenant access — see below) but has a **systemic responsiveness risk**: the "fetch-all → filter/sort/render in the browser" pattern, backed by list endpoints that cap rows with **no offset/pagination** (silent truncation) and one endpoint that does heavy synchronous work with no caching or external-call timeout. This is the same architectural debt flagged as "deferred" in prior perf passes — it was never closed for the client surfaces. As tenants grow (more vendors × periods × documents), these pages will feel progressively "frozen," exactly as reported.

### What's already solid (don't touch)
- **Tenant isolation is clean.** Every id-based endpoint (vendor, submission, notification, metadata, report, audit-package whitelist, user mgmt) was traced and correctly scopes to the caller's organization/client. Same 404 shape for absent vs. foreign resources (no enumeration oracle). No IDOR found.
- **Auth gating is uniform** — every client route requires `client_admin`/`internal_admin`; `must_change_password` gate enforced centrally.
- **DB statement/lock timeouts exist** globally (`db/session.py:51-60`, default 30s/10s) — protects ordinary query handlers (the prior reports-outage class of bug is mitigated for DB work).
- **Write paths are owner-scoped**, profile update uses a field allow-list (no mass-assignment), credentials never leak in responses.
- Route-level `loading.tsx` / `error.tsx` boundaries exist for `/client`.

---

## P0 — Can hang/freeze a worker or render unbounded work

### P0-1 · `/client/metadata` re-parses the master XLSX synchronously every request (+ possible untimed R2 fetch, no cache)
- **Backend:** `apps/api/app/api/v1/client.py:2939-2945` → `apps/api/app/services/client_metadata.py:45-72`
- **Frontend:** `apps/web/app/client/metadata/page.tsx:28-62` (load) and `:142-196` (render)
- **What:** On every page load the endpoint calls `ensure_local_export` (can pull the file from R2) then `read_xlsx_preview(...max_rows_per_sheet=500...)`, which unzips + XML-parses the workbook in the request thread. No caching (identical bytes re-parsed every visit). The frontend pulls the resulting rows, substring-scans the full array on every keystroke, and renders every row as a `<tr>` with no virtualization. Capped at 500 rows with **no offset** → silent truncation beyond 500.
- **Impact:** For the flagship tenant (610+ documents backfilled per memory) this pins a pool connection on CPU-bound parse work, and the R2 re-materialize has no explicit timeout (DB `statement_timeout` doesn't cover it). This is the endpoint most likely to read as "frozen," and it scales with document count — the fastest-growing dimension.
- **Fix:** Cache the parsed preview keyed by file mtime/etag (or serve a precomputed JSON sidecar); add server-side search + `limit/offset`; virtualize the table; move the R2 re-materialize off the request path.

### P0-2 · `/client/auditoria` audit-package tree: unbounded list rebuilt + rendered eagerly, backed by an N+1
- **Frontend:** `apps/web/app/client/auditoria/page.tsx:194-220` (fetch), `:692-748` (`buildGroupedTree`), `:750-841` (`DocumentTree`), `:252-259` (`selectionBytes`)
- **Backend:** `apps/api/app/services/audit_package.py:448-490` (per-workspace `SELECT submissions` + per-loop `Document IN` query)
- **What:** The tree request returns *all* documents matching the (default wide) filters with no limit; the page rebuilds a Vendor→Institution→Period→Document tree and renders every leaf checkbox eagerly. Each toggle re-`flatMap`s per branch and re-sums `selectionBytes` over the whole tree. The backend `build_entries` issues a submissions query **per workspace** plus a documents query per loop (N+1 in vendor count) — and this runs again on every filter change because the live preview counter re-requests it.
- **Impact:** A 50-vendor client = ~100 queries before any byte streams, plus a heavy eager DOM and per-click tree walks. Rapid chip toggling multiplies it (no debounce — see P3-1).
- **Fix:** One client-scoped submissions query bucketed by `vendor_id` in Python + a single `Document IN (...)`; cap/paginate the tree request; lazy-render leaves on branch expand; precompute per-branch doc-id arrays once.

---

## P1 — Clearly slow / stuck at realistic data sizes

### P1-1 · `/client/vendors`: compute-then-filter backend + fetch-all + 200-notification side-fetch + unvirtualized render
- **Backend:** `apps/api/app/api/v1/client.py:1289-1339` — computes `_vendor_compliance` for **every** workspace, then `continue`s if `semaphore_level` doesn't match (`:1310`); `limit` cap (`:1338`) is post-filter. Plus `_next_renewal_for_workspace` (`:240-286`) re-walks the catalog the compliance pass already covered.
- **Frontend:** `apps/web/app/client/vendors/page.tsx:80-106` — `listClientVendors` (server caps 100 default / 500 max, **no offset**) **and** `listClientNotifications({unread_only, limit:200})` just to build a per-vendor unread badge map; table renders all rows unvirtualized.
- **Impact:** Filtering can't reduce backend work (full O(vendors) compliance regardless of how few rows match); large portfolios silently truncate at the cap with no "next page"; the 200-notification payload is a second large fetch the page doesn't really need.
- **Fix:** Server-side `limit/offset`; server-computed `unread_count` per vendor (or a counts endpoint); derive `next_renewal` from the already-computed `onboarding_slots`; virtualize the table.

### P1-2 · `/client/submissions`: hard cap with no real pagination + stale-state page-size refresh
- **Backend:** `apps/api/app/api/v1/client.py:2440` — caps at 500, no offset.
- **Frontend:** `apps/web/app/client/submissions/page.tsx:73-91`, page-size handler `:206-214` — "Mostrar N por página" changes `limit`, not offset (no way past the cap); `onChange` does `setFilters(...)` then `window.setTimeout(refresh, 0)`, and `refresh` closes over the **previous** `filters.limit` → first refresh after a size change can use the stale value.
- **Impact:** Submissions volume (provider × requirement × period) exceeds 500 quickly → silently truncated view; setTimeout pattern risks an off-by-one/wasted fetch.
- **Fix:** Offset-based pagination; drive refresh off the new limit via effect dependency, not setTimeout.

### P1-3 · `/client/activity`: over-fetch-then-truncate (backend) + client-side grouping (frontend)
- **Backend:** `apps/api/app/api/v1/client.py:2624-2725` — fetches up to `limit` uploads **and** up to `limit` events, then a third `IN` query re-loads the events' submissions (`:2648-2654`), merges + sorts in Python, discards ~half.
- **Frontend:** `apps/web/app/client/activity/page.tsx:46` (`limit:200`) + `groupByDay` `:211-234`.
- **Impact:** At `limit=200`, ~400 rows materialized + a redundant submission re-fetch to render 200; no offset so older activity is unreachable.
- **Fix:** Single UNION/keyset query ordered by `created_at` with one `LIMIT`, reuse already-loaded upload rows; server-side pagination.

### P1-4 · `ValidationEvent` missing composite index for the hot reviewer/activity queries
- **File:** `apps/api/app/models/entities.py:359` (no `__table_args__`); consumers at `client.py:381-390`, `:1600-1614`, `:2633-2644`.
- **What:** Queries filter `event_type == 'reviewer_decision'` grouped by `submission_id` and `ORDER BY created_at DESC`, but the table only has the implicit FK index on `submission_id`.
- **Impact:** As `validation_events` grows (every reviewer + intake action), `/vendors`, `/vendors/{id}`, `/activity` scan/sort large row sets.
- **Fix:** Add `Index("ix_validation_events_submission_type", "submission_id", "event_type")` and an `(event_type, created_at)` index (new migration).

### P1-5 · File/blob downloads have NO request timeout — the "Abriendo…/Descargando…" buttons can spin forever
- **Frontend:** `apps/web/lib/api/download.ts:48-82`; `fetchClientSubmissionDocumentBlob` `client.ts:723-746`; `downloadClientMetadata` `client.ts:650-670`; contract blob fetch `vendors/[vendor_id]/page.tsx:406-445`.
- **What:** The JSON client `fetchJson` has a 30s `AbortController` timeout (`client.ts:40-61`), but the download/blob helpers use bare `fetch` with no abort/timeout.
- **Impact:** A stalled R2/zip stream leaves the button stuck with no recovery — squarely the "it gets stuck" symptom.
- **Fix:** Add `AbortController` + timeout to `downloadAuthenticatedFile`, `fetchClientSubmissionDocumentBlob`, `downloadClientMetadata`.

### P1-6 · `/client/notifications`: fetch-100-then-group/count client-side, no pagination
- **Frontend:** `apps/web/app/client/notifications/page.tsx:138` (`limit:100`) + `computeCounts`/`visible`/`categoryChips` `:157-187`.
- **Impact:** Inbox grows unbounded; 100-cap hides older items; 3 derived structures recomputed over the full array on every tab/category toggle.
- **Fix:** Server-side pagination + server-provided category/tab counts; "cargar más".

---

## P2 — Noticeable jank / wasted work

- **P2-1 · Dashboard `/me`→data waterfall.** `apps/web/app/client/dashboard/page.tsx:76-139` — the 4-call `Promise.all([overview, submissions, activity, notifications])` is gated behind `/me` returning first, even when `?client_id` is already in the URL. Adds one serial RTT to first paint. *Fix:* when `urlClientId` is set, fire the batch in parallel with `/me`.
- **P2-2 · Shell notification summary refetched on every navigation.** `_shell.tsx:152-157`; `getClientNotificationSummary` uses `dedupeRead` with **no TTL** (`client.ts:609-612`), and the shell remounts per route. *Fix:* short TTL, or lift the shell so it doesn't remount.
- **P2-3 · Redundant per-vendor compliance recompute.** `client.py:1302-1336` — `_vendor_compliance` then `_next_renewal_for_workspace` re-walk overlapping catalog/slot work per vendor (×100 at cap). *Fix:* derive renewal from already-computed slots.
- **P2-4 · `Institution` full-table read per request.** `client.py:419-424` (dup'd in `evidence_slots.py:526-529`, `client_context.py`, `audit_package.py:421`) — `select(Institution)` on every `/overview`, `/vendors`, `/calendar`, Wise call for a near-static catalog. *Fix:* `lru_cache` the id→code map.
- **P2-5 · boto3/R2 client has no explicit connect/read timeout.** `services/storage.py:422-434` — relies on botocore defaults (~60s × 3 retries = up to ~180s); streaming responses (`client.py:2034-2045`, `:3511-3532`, `:2141-2156`) run outside the DB timeout net. *Fix:* set `connect_timeout`/`read_timeout` in the botocore `Config`. (Agent rated P3; elevated to P2 given the "doesn't get stuck" goal + prior spinner incident — caps on file count/bytes do bound the worst case.)
- **P2-6 · Per-row `toLocale*` date formatting instead of the cached formatter.** `activity/page.tsx:123-127,226-231`; `notifications/page.tsx:502`; `vendors/[vendor_id]/page.tsx:461-465,888`. Hundreds of `Intl` calls per render on long lists; `submissions` correctly uses `formatDateTime`. *Fix:* route all through the shared cached formatter.
- **P2-7 · `mark_all_client_notifications_read` loads every unread row + audits each id.** `client.py:2848-2883`. *Fix:* single bulk `UPDATE ... WHERE read_at IS NULL`; store only a count in the audit row.
- **P2-8 · No rate limit on heavy ZIP/PDF endpoints (top hardening gap).** `client.py:3309` / `:3343` (`/audit-package.zip` POST+GET) and `:1925` (`/vendors/{id}/expediente.zip`) stream up to 200 files / 500 MB and render an INDICE.pdf via Chromium; only `/wise/ask` carries `enforce_ai_heavy_rate_limit`. An authenticated `client_admin` can repeatedly trigger this → resource-exhaustion DoS. *Fix:* per-user rate-limit bucket mirroring `enforce_ai_heavy_rate_limit`. (Agent rated P3; this is the single biggest *remaining* hardening risk.)

---

## P3 — Minor / defense-in-depth

- **P3-1 · `/client/auditoria` fires paired unbounded preview+tree requests on every filter change, no debounce.** `auditoria/page.tsx:164-220`. *Fix:* debounce ~250ms.
- **P3-2 · Onboarding refetches the full vendor list after every provider add.** `onboarding/page.tsx:409-429,466`. *Fix:* optimistically append.
- **P3-3 · Vendors/calendar `router.replace` per keystroke.** `vendors/page.tsx:76-78`, `calendar/page.tsx:89-91`. *Fix:* sync URL on submit only.
- **P3-4 · Submissions sorts the vendor dropdown unmemoized every render.** `submissions/page.tsx:117-121`. *Fix:* `useMemo`.
- **P3-5 · Calendar flattens all 12 months across ~6 memos per filter change.** `calendar/page.tsx:145-223`, `portfolio-matrix.tsx:61-68`. Currently fine (~417 obligations/yr flagship) but scales linearly. *Fix:* push institution filtering server-side if portfolios grow.
- **P3-6 · Error/identifier leakage in metadata XLSX parse failure.** `services/client_metadata.py:68-72` echoes `{exc}` into the 422 response. *Fix:* static Spanish message, log `exc` server-side.
- **P3-7 · `internal_admin` cross-tenant vendor reads are unaudited (by design).** `client.py:1650-1657`, `:1846`. Intentional support access; inline doc views deliberately unaudited. *Fix (optional):* emit an audit row when `internal_admin` resolves a vendor outside their membership scope (ISO access-logging).

---

## Recommended fix order (if/when you greenlight changes)

1. **P0-1 metadata** — cache the parsed preview + add R2/boto3 timeout (P2-5). Biggest "frozen" win, smallest blast radius.
2. **P1-5 download timeouts** — quick, directly kills the "stuck button" symptom.
3. **P0-2 / P1-1 / P1-3** — server-side `limit/offset` + the audit-package single-query rewrite + `/activity` single-query. This is the architectural core; do it as one "client server-side pagination + virtualization" slice mirroring the Bandeja/admin pass already shipped.
4. **P1-4 index migration** + **P2-3/P2-4/P2-7** backend cleanups.
5. **P2-8 rate limit** on ZIP endpoints (hardening).
6. P2/P3 frontend polish (memoization, cached formatter, debounce, dashboard waterfall).

Note: items 3 is the same shape as the work already done for Bandeja (`091f162`) and admin rosters (`c49d7e7`) — the client surfaces were the deferred remainder of that pass.
