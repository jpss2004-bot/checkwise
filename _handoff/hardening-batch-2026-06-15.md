# Hardening batch — 4 deferred audit items (2026-06-15)

Follow-up to `_handoff/audit-security-perf-2026-06-15.md`. Implements the four deferred items. All changes are backward-compatible and validated; nothing here requires the risky frontend cutover to ship — except the final FE-SEC-1 step, which is intentionally staged (see below).

## Status

| # | Item | Status |
|---|---|---|
| 3 | **PERF-7** — submission indexes | ✅ Done + validated on local DB |
| 4 | **PERF-5** — background heavy intake work off the event loop | ✅ Done + tested |
| 1 | **Frontend CSP** | ✅ Done (report-only; ready to enforce after QA) |
| 2 | **FE-SEC-1/2** — JWT → httpOnly cookie + route guard | 🟡 Backend foundation done + tested; frontend cutover staged (plan below) |

---

## Item 3 — PERF-7 submission indexes (DONE)

- Migration `alembic/versions/0046_submission_perf_indexes.py`: `ix_submissions_vendor_id` and `ix_submissions_client_created (client_id, created_at)`, created with `CREATE INDEX CONCURRENTLY IF NOT EXISTS` inside an `autocommit_block()` (non-locking on Neon; Alembic wraps migrations in a transaction, which `CONCURRENTLY` forbids).
- Matching `Index(...)` entries added to the `Submission` model so the schema stays in sync.
- Validated on the local Postgres: applied cleanly, both indexes `valid=true ready=true`, downgrade/upgrade round-trips.

**⚠ Deploy gate:** this migration auto-runs via Render `preDeployCommand` (`alembic upgrade head`) on push. **Snapshot Neon before pushing** (team standard). `CONCURRENTLY` builds without an ACCESS EXCLUSIVE lock, but if it ever fails partway it can leave an INVALID index — drop it (`DROP INDEX CONCURRENTLY IF EXISTS …`) and re-run. Local dev DB was at `0044`; the migration also applied `0045` (lockout) there to catch local up to prod.

## Item 4 — PERF-5 offload intake heavy work (DONE)

- The provider upload endpoints (`create_workspace_submission`, `create_workspace_submission_batch`) called the synchronous `finalize_intake_submission` / `finalize_multi_document_submission` directly inside `async def`, blocking the event loop for the entire PDF-inspection + OCR + forensics + QR-decode + metadata-export(+R2) duration — freezing every other request on a single-worker deploy.
- Both calls now run via `await run_in_threadpool(...)`. Behaviour-preserving: the function (incl. its commit + background-task scheduling) runs in one worker thread, the coroutine awaits, so the session is never accessed concurrently. Same result, status, and response.
- Validated: uploads still return `202` (offload didn't break the session/flow); `ruff` clean. (The 16 pre-existing upload-test failures are environmental — the local `inspect_pdf` flags the stub PDFs — identical on HEAD.)

## Item 1 — Frontend CSP (DONE, report-only)

- `next.config.ts` now emits `Content-Security-Policy-Report-Only` alongside the five enforced headers from the prior batch. Directives derived from the real surface: `connect-src` includes the API origin (`NEXT_PUBLIC_API_BASE_URL`) + Calendly; `script-src`/`frame-src` allow the Calendly booking embed; `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'self'`.
- **Report-only never blocks**, so it's safe to ship while marketing v2 is in flight. To enforce: collect violations during QA (browser console / a `report-to` endpoint), tighten `script-src` (ideally drop `'unsafe-inline'` via a nonce), then rename the header key to `Content-Security-Policy`.

## Item 2 — FE-SEC-1/2 cookie auth: backend foundation DONE, frontend cutover STAGED

### What shipped (backend, safe, tested)
- `config.AUTH_SESSION_COOKIE_NAME = "checkwise_session"`.
- `login` now also deposits the JWT in an httpOnly cookie (`Secure`/`SameSite` follow `cookie_secure`/`cookie_samesite` — `None+Secure` in prod). Token is still returned in the body, so the current header flow is unchanged.
- `get_current_user` accepts the cookie **as a fallback only** — the bearer-header branch is byte-for-byte unchanged, so current sessions cannot regress. Cookie-authenticated **mutating** requests are CSRF-guarded (`_enforce_cookie_csrf`, mirrors `enforce_portal_csrf`: Origin/Referer allowlist, fail-closed in prod).
- New `POST /auth/logout` clears the cookie.
- Tests: `test_login_sets_session_cookie`, `test_me_authenticates_via_cookie_without_header`, `test_logout_clears_session_cookie` (+ all 44 existing auth tests still green).

> The cookie is **inert in prod** until the frontend opts in: a browser won't store a cross-origin `Set-Cookie` unless the login `fetch` uses `credentials:'include'`. So shipping this backend foundation changes nothing for live users — it's the tested groundwork.

### Why the frontend cutover is staged (not pushed blind)
1. **Logout-on-deploy:** removing the localStorage token makes auth rely entirely on the cookie; every current session (localStorage-only) would be logged out the moment it ships. That's acceptable for a security cutover but must be a deliberate, announced deploy.
2. **`middleware.ts` can't be added before the cutover:** an edge guard can only read cookies (not localStorage), so enforcing it now would bounce every existing localStorage session to `/login`.
3. **Concurrent edits:** a parallel Codex agent is actively editing `apps/web/lib/api/*` and the marketing tree; the cutover touches `lib/api/*` and would collide.
4. **Cross-origin cookie flow needs E2E verification** (Vercel↔Render, `SameSite=None`, CSRF) in staging before prod.

### Frontend cutover plan (execute as one focused, staging-verified change)
1. **Login call** (`lib/api/auth.ts`): add `credentials: "include"` so the browser stores the cookie. Stop writing the token to `localStorage` (`lib/session/admin.ts` `writeAdminSession`); keep only non-sensitive session metadata (email/roles) if the UI needs it, not the JWT.
2. **All API clients** (`lib/api/admin.ts`, `client.ts`, `reviewer.ts`, `corrections.ts`, `portal-session.ts`, `lib/reports/use-generation.ts`): add `credentials: "include"` to every `fetch`; remove the `Authorization: Bearer` header sourced from localStorage (the cookie now carries auth). Ensure unsafe requests send a same-origin `Origin` (browsers do automatically) so the backend CSRF guard passes.
3. **`apps/web/middleware.ts`** (new): on `/admin/*`, `/client/*`, `/platform/*`, `/portal/*`, redirect to `/login` when the session cookie is absent. Keep the existing client-side gates as defense-in-depth.
4. **Logout** (`lib/session/admin.ts` / shells): call `POST /api/v1/auth/logout` (with `credentials:'include'`) and clear any in-memory state.
5. **Verify in staging:** login → cookie set; navigation guarded at the edge; mutations succeed (CSRF passes same-origin) and a forged cross-origin mutation is 403; logout clears; hard-refresh keeps the session.
6. **Deploy** with a heads-up that active users will re-login once.
7. **Cleanup:** once stable, delete any remaining localStorage token code and consider shortening `AUTH_JWT_EXPIRES_MINUTES` (no refresh token today, so balance against re-login frequency).

### Rollback
Backend is additive — if the frontend cutover misbehaves, revert the frontend only; the header path still works and the cookie is harmless.
