# CheckWise — Security, Performance & Code-Quality Audit (2026-06-15)

Full-system engineering pass across backend (FastAPI), frontend (Next.js), database (Neon/Postgres), auth, file handling, deployment, and integrations. Findings are confirmed against real code paths; fixes implemented this pass are production-safe, surgical, and validated. Nothing has been committed or deployed — all changes are in the working tree for review.

> **Concurrent-editing note:** during this audit a parallel Codex agent was actively editing the frontend (`apps/web/components/marketing/*`, `app/globals.css`, a new `app/v2/` tree; handoff at `_handoff/codex-client-portal-scope.md`). To avoid collisions, backend changes were kept isolated and frontend changes were limited to the single, isolated `next.config.ts`. Coordinate before larger frontend work (esp. the FE-SEC-1 cookie migration).

---

## 1. Executive summary

CheckWise is a **mature, well-hardened codebase** — it has had multiple prior security passes (JWT-secret boot validation, account lockout, login rate-limiting, constant-time auth, password-history reuse checks, security-headers middleware, tightened CORS, a route-policy manifest, broad audit logging). The audit therefore concentrated on the **remaining** gaps.

Headline results:

- **1 CRITICAL security bug** — cross-tenant data exfiltration via report create/patch. **Fixed + regression-tested.**
- **1 HIGH privilege-escalation** — `platform_admin` could self-grant `internal_admin`. **Fixed.**
- **2 HIGH frontend structural items** — JWT in `localStorage` + no server-side route guard. **Documented; deferred** (large, and the frontend is under concurrent edit).
- **3 CRITICAL/HIGH performance items** — N+1 portfolio rebuilds, blocking I/O on the upload event loop, missing indexes. **2 of 3 batching wins fixed; index migration drafted as a recommendation.**
- A set of MEDIUM/LOW file-handling, header, audit-coverage, and config items — **most fixed.**

Dependencies are clean (backend OSV scan: 0 advisories; frontend: 1 moderate transitive `js-yaml`, non-runtime).

---

## 2. Security audit summary

### CRITICAL
- **REPORT-1 — Cross-tenant data exfiltration via report create/patch.** `create_report`/`patch_report` trusted the body-supplied `client_id`/`vendor_id` and only validated the *owning org*. A `client_admin` for tenant A could author/patch a `client_facing` report scoped at tenant B's `client_id`, then generate it to pull B's full portfolio (vendor names, RFCs, risk scores) into a report they own and can export/share. **FIXED** (`report_service.py`) + 3 regression tests.

### HIGH
- **ADMIN-1 — `platform_admin` → `internal_admin` self-escalation.** The user-management endpoints are gated by `PlatformUser` (internal_admin OR the IT-only platform_admin), but `provision_user(role="admin")` and `grant_user_membership` would hand out `internal_admin`/`platform_admin` to a pure platform_admin — defeating the privilege split. Latent today (every operator also holds internal_admin via migration 0044) but it would bite the first IT-only account. **FIXED** (`admin.py`).
- **FE-SEC-1 — Admin/Client/Reviewer JWT stored in `localStorage`.** XSS-exfiltratable; grants the most powerful scopes. The provider portal already uses an httpOnly cookie — the pattern exists. **DEFERRED** (structural; needs the cookie migration + coordination with the in-flight frontend work).
- **FE-SEC-2 — No `middleware.ts`; route protection is 100% client-side.** Protected route code/markup ships regardless of auth (data is still API-protected, so no data leak); role gating is advisory and pages flash blank before the JS redirect. **DEFERRED** (pairs with FE-SEC-1).

### MEDIUM
- **FILE-1 — PDF upload accepted on extension/MIME only.** Magic-byte check was advisory (routed to review, still stored). Arbitrary bytes named `*.pdf` (HTML/SVG/script) were persisted as "evidence" and rode into expediente/audit ZIPs. **FIXED** — hard `%PDF-` content check at the HTTP boundary.
- **FILE-2 — No image decompression-bomb cap.** Synchronous QR/forensics decode of attacker-supplied embedded images had only PIL's ~178M-px default ceiling (≈0.5 GB+/image). **FIXED** — `Image.MAX_IMAGE_PIXELS = 64M`.
- **FILE-3 — Header injection via `Content-Disposition` filename.** Provider/client download endpoints interpolated the raw, attacker-controlled `original_filename` into the header (the reviewer path was already sanitized). **FIXED** — shared `content_disposition_header()` util used by all three routers.
- **INFRA-1 — No Content-Security-Policy.** **PARTIAL FIX** — strict CSP (`default-src 'none'; frame-ancestors 'none'`) now set on JSON API responses; the user-facing frontend CSP is the top recommended next step (report-only rollout).
- **INFRA-2 — In-memory rate limiter under-enforces if workers > 1 without Redis.** Correct today (single worker), latent footgun on scale-out. **FIXED** — boot-time warning when non-local + `REDIS_URL` unset.
- **INFRA-3 — No authentication trail.** Login success/failure and share mint/consume/revoke were unaudited — a gap for a compliance product. **PARTIAL FIX** — login success + failure now audited with IP/UA; share-event auditing recommended.
- **FE-SEC-5 — No frontend security headers.** **FIXED** — `next.config.ts` now sets `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, HSTS (full CSP deferred to report-only rollout).
- **ADMIN-2 — Bulk metadata-export downloads unaudited.** XLSX workbooks of client/vendor compliance metadata stream with no audit row. **RECOMMENDED.**

### LOW
- **INFRA-6 — `str(exc)` leaked JWT decoder internals on 401.** **FIXED** — generic message.
- **ADMIN-3 — No "last internal_admin" floor on disable/delete** (availability). **RECOMMENDED.**
- **ADMIN-4 — Audit rows hardcode `actor_type="internal_admin"`** (mis-attributes a future pure platform_admin). **RECOMMENDED.**
- **REPORT-2 — `_actor_from` can widen report visibility** under cross-tenant `owner_user_id` misconfig (latent; no in-scope self-service trigger). **RECOMMENDED** (defense-in-depth).
- **SHARE-1 — Public share render has no view-count cap** (leaked link is a standing credential until expiry/revoke). **RECOMMENDED** (by-design; decide per audience).
- **INFRA-4 — Rate-limit/audit IP trusts the *first* `X-Forwarded-For` hop** (spoofable behind Render; per-account controls still bound the attack). **RECOMMENDED** — prefer the last hop.
- **FILE-4 — Whole-expediente ZIP built in memory** (bounded at 500 MB; concurrent pulls spike RAM). **RECOMMENDED** — stream the zip.
- **FILE-5 — Served PDFs may carry active content** (`/JavaScript`, `/OpenAction`); detected but not stripped. **RECOMMENDED** — surface to reviewers.

### Already strong (do not re-audit)
JWT secret boot guard + algorithm pinning; account lockout (DB-backed, multi-worker-safe); login enumeration resistance (dummy-hash constant time, generic 401/202); password rules + history reuse; CORS locked to an explicit allowlist with credentials; `/docs` off in prod; cookie `Secure`/`SameSite=None` correct for the Vercel↔Render split; Redis limiter fail-closed; portal workspace tenant isolation (every by-id fetch re-checked); client.py tenant isolation via `_resolve_client_id`; reports read/write chokepoint `get_report` (404, no enumeration); share tokens (256-bit, hashed at rest, expiry/revoke honored, brute-force throttled); upload path traversal closed (content-addressed keys, sanitized names); per-file + multi-file size caps enforced during streaming; no SSRF; `.env` gitignored + gitleaks; secrets via `sync: false` in render.yaml.

---

## 3. Performance audit summary

### CRITICAL / HIGH
- **PERF-2 — `build_client_context` was N+1 over vendors** (2–3 queries/vendor) on the cliente Wise dock and every report block. **FIXED** — single batched submissions query + institutions map (the proven `_portfolio_slot_inputs` pattern).
- **PERF-4 — `client_calendar` rebuilt slots per workspace** with no prefetch (O(N) full `submissions` scans). **FIXED** — batched.
- **PERF-1 — Reports pipeline recomputed the whole portfolio 4–5× per report.** Largely collapsed by PERF-2 (each `build_client_context` is now O(1) queries); the remaining "compute once per report" optimization in the executor is **RECOMMENDED**.
- **PERF-5 — Heavy synchronous PDF work (OCR/forensics/QR) runs inline on the async upload event loop**, stalling the whole worker. **RECOMMENDED** — move to the existing post-commit `BackgroundTask`, or `run_in_threadpool`.
- **PERF-6 — boto3 S3/R2 upload blocked the event loop** in `async save_upload`. **FIXED** — `run_in_threadpool`.
- **PERF-7 — Missing indexes**: `submissions(vendor_id)` and `submissions(client_id, created_at)` (the 6-month history runs 12 unindexed range scans/report; `vendor_id IN (...)` can't use the `(client_id, vendor_id)` composite). **RECOMMENDED** — additive migration; build with `CONCURRENTLY` + snapshot Neon first (auto-deploys via preDeployCommand).

### MEDIUM
- **PERF-9 — DB engine had no `pool_recycle`/`statement_timeout`.** **PARTIAL FIX** — `pool_recycle=1800` added (pooler-safe). `statement_timeout` deferred: delivering it through Neon's pgbouncer transaction pooler needs care (see report).
- **PERF-8 — Static catalogs (institutions, compliance) refetched/recomputed per request.** **RECOMMENDED** — `lru_cache`.
- **PERF-10 — Single uvicorn worker** amplifies any event-loop stall. **RECOMMENDED** — raise workers *after* provisioning Redis (INFRA-2).
- **FE-PERF-2 — No `optimizePackageImports` for `@phosphor-icons/react`** (130+ barrel imports). **FIXED** — `next.config.ts`.
- **FE-PERF-1 — Unused `@blocknote/*` deps (~12 MB, zero imports).** **RECOMMENDED** — remove (deferred: `npm install` lockfile churn conflicts with concurrent frontend work).
- **FE-PERF-3 — Dashboards client-render with fetch waterfalls + a duplicated `/me` fetch + no caching.** **RECOMMENDED.**
- **FE-PERF-4/5 — High client-component ratio; no `loading.tsx`/`error.tsx`.** **RECOMMENDED.**

---

## 4. Code-efficiency / maintainability findings

- **Duplication removed:** the `Content-Disposition` builder existed only in `reviewer.py`; lifted to `app/core/http_utils.py` and reused (also fixes FILE-3). 
- **FE-Q-1 — `lib/mock/*` ships to prod** as a portal fallback. **RECOMMENDED** — retire once backend ownership confirmed.
- **FE-Q-3 — 1 failing frontend unit test** (`lectura-del-documento.test.tsx`, copy drift). **RECOMMENDED.**
- Backend tooling discipline is strong (clean ruff on changed files); frontend `tsc` + `eslint` are clean. Pre-existing ruff debt in 4 untouched report-service files (44 lints) is out of scope.

---

## 5. Prioritized roadmap

| Priority | Item | Status |
|---|---|---|
| **Critical security** | REPORT-1 cross-tenant report scoping | ✅ Fixed + tested |
| **High security** | ADMIN-1 privilege-escalation guard | ✅ Fixed |
| High security | FE-SEC-1 JWT→httpOnly cookie; FE-SEC-2 `middleware.ts` | ◻ Deferred (coordinate w/ frontend) |
| **High perf** | PERF-2, PERF-4 N+1 batching; PERF-6 threadpool | ✅ Fixed |
| High perf | PERF-7 indexes; PERF-5 background OCR/forensics; PERF-1 executor context | ◻ Recommended |
| **Med security** | FILE-1/2/3, INFRA-1/2/3/6, FE-SEC-5 | ✅ Fixed (CSP/audit partial) |
| Med security | ADMIN-2 export audit; full frontend CSP | ◻ Recommended |
| Med perf | PERF-9 statement_timeout, PERF-8 caching, PERF-10 workers, FE-PERF-1/2/3 | ◻ FE-PERF-2 + pool_recycle done; rest recommended |
| **Low** | ADMIN-3/4, REPORT-2, SHARE-1, INFRA-4, FILE-4/5, FE-Q-1/3 | ◻ Recommended |

---

## 6. Fixes implemented this pass

**Backend (security)**
- `app/services/report_service.py` — REPORT-1: `_allowed_client_ids_for_actor()` + `_enforce_report_tenant_scope()` called in `create_report` and `patch_report`.
- `app/api/v1/admin.py` — ADMIN-1: `_assert_can_grant_role()` in `provision_user` (role=admin) and `grant_user_membership`.
- `app/services/submission_service.py` — FILE-1: `%PDF-` magic-byte check in `assert_pdf_upload` (stream rewound; non-PDF → 400).
- `app/services/document_verification.py`, `app/services/document_image_forensics.py` — FILE-2: `Image.MAX_IMAGE_PIXELS = 64_000_000`.
- `app/core/http_utils.py` (new) + `portal.py`, `client.py`, `reviewer.py` — FILE-3: shared injection-safe `content_disposition_header()`.
- `app/main.py` — INFRA-1: strict CSP on JSON responses.
- `app/core/config.py` — INFRA-2: Redis/multi-worker boot warning.
- `app/api/v1/auth.py` — INFRA-3: `auth.login.succeeded`/`auth.login.failed` audit events (+ provenance helper); INFRA-6: generic 401 token message.

**Backend (performance)**
- `app/services/wise/client_context.py` — PERF-2: batched portfolio prefetch.
- `app/api/v1/client.py` — PERF-4: batched `client_calendar`.
- `app/services/storage.py` — PERF-6: `run_in_threadpool` around S3 upload.
- `app/db/session.py` — PERF-9: `pool_recycle=1800`.

**Frontend**
- `apps/web/next.config.ts` — FE-SEC-5 security headers; FE-PERF-2 `optimizePackageImports`.

**Tests**
- `tests/test_cross_tenant_reports_shares_exports.py` — 3 REPORT-1 regression tests (attack create, attack patch, positive control).

---

## 7. Checks run

- **ruff** — clean on all 15 changed backend files + new test (pre-existing 44 lints in 4 untouched files left as-is).
- **Import smoke test** — `app.main` builds (171 routes).
- **Behavior validation** — `content_disposition_header` neutralizes `"`/`;` injection; `assert_pdf_upload` accepts real PDFs, rejects HTML-as-PDF (400), leaves the stream intact.
- **pytest (SQLite-isolated, no dev-DB risk):**
  - `test_cross_tenant_reports_shares_exports` + `test_reports` + `test_report_shares` + `test_auth` + `test_admin` + `test_client_users` → **199 passed** (now 202 with the 3 new tests; suite green).
  - Upload/document/portal suites → 232 passed, **16 pre-existing environmental failures** (proven unrelated to these changes by stashing FILE-1 and reproducing the identical `requiere_aclaracion` failure on HEAD — the local `inspect_pdf` flags the tests' stub PDFs).
- **Frontend** — `tsc --noEmit` → 0 errors (incl. `next.config.ts`).

---

## 8. Remaining risks

- **FE-SEC-1/FE-SEC-2 (HIGH)** — admin/client JWT in `localStorage` + no edge route guard remain. The API is the real authz boundary, so there's no *data* leak today, but token theft via XSS would be high-impact. Needs the cookie migration.
- **PERF-5 (CRITICAL latency)** — uploads still block the event loop during OCR/forensics; worst on a single worker.
- **PERF-7** — unindexed submission scans grow with tenant data.
- **No full CSP** on the frontend yet (only the safe header subset).
- **16 pre-existing test failures** in the local env (not introduced here) — worth fixing so the suite is a clean signal.
- The `statement_timeout` runaway-query backstop is not yet in place (pgbouncer delivery caveat).

---

## 9. Recommended next steps (in order)

1. **Frontend CSP** — add `Content-Security-Policy-Report-Only` in `next.config.ts`, tune `script-src`/`style-src`/`connect-src` (must allow the API origin + Calendly/Slack embeds + Vercel analytics) against the live app, then enforce.
2. **FE-SEC-1 + FE-SEC-2** — mirror the portal's httpOnly-cookie pattern for the admin/client JWT, then add `middleware.ts` for edge route protection. Unlocks RSC server-fetching (kills the dashboard waterfalls too).
3. **PERF-7 indexes** — `CREATE INDEX CONCURRENTLY` for `submissions(vendor_id)` and `submissions(client_id, created_at DESC)`; snapshot Neon before the migration deploys.
4. **PERF-5** — background the OCR/forensics/verification step (reuse the `run_shadow_analysis` BackgroundTask pattern).
5. **PERF-1** — compute `build_client_context` once per report in the executor and inject into all blocks.
6. **INFRA-3 (rest) + ADMIN-2** — audit share mint/consume/revoke and metadata-export downloads.
7. **PERF-10 + INFRA-2** — provision Redis, set `REDIS_URL`, then raise uvicorn workers.
8. **Cleanup** — remove `@blocknote/*` (FE-PERF-1), retire `lib/mock/*` (FE-Q-1), fix the failing frontend test (FE-Q-3), clear the 4-file ruff debt.
9. **Low-priority hardening** — ADMIN-3/4, REPORT-2, SHARE-1, INFRA-4, FILE-4/5.

---

*No changes committed or deployed. Migrations that auto-deploy (PERF-7) must be paired with a Neon snapshot per the team's standard workflow.*
