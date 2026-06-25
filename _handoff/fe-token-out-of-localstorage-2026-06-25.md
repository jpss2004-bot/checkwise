# CW-FE (F6) — move the staff/client bearer JWT out of localStorage

**Branch:** `fix/fe-token-out-of-localstorage` (off `fix/codex-security-findings` / PR #44)
**Status:** implemented + tsc-clean + vitest-green. **NOT merged — merge is gated on the cross-origin browser verification below.**

## What changed

The admin/client access token no longer sits in `localStorage`. It now lives in:
1. a **module-level in-memory variable** (`lib/session/admin.ts` → `setAdminAccessToken` / `getAdminAccessToken` / `adminAuthHeader`), gone on a full reload; and
2. the **httpOnly `checkwise_session` cookie** the backend already sets at `/auth/login` (and refreshes at `/auth/set-password`).

`localStorage` (`checkwise.admin.session.v1`) keeps only the **non-secret identity slice** (`user` / `roles` / `organization_ids` / `expires_at`) so the shells render synchronously. `AdminSession` no longer has an `access_token` field — that drove the tsc-complete sweep across every reader.

Every staff fetch now follows the proven provider-portal pattern (`lib/api/portal-session.ts`): **`credentials: "include"` always + `Authorization: Bearer <in-memory token>` when present** (JWT-first, cookie-fallback). On reload the in-memory token is gone, so the cookie authenticates; if the cross-site cookie is blocked (Safari ITP), the call 401s → re-login.

### Files (26)
- **Core:** `lib/session/admin.ts` (in-memory token + identity-only type + legacy-strip on read + `clearAdminSession` clears both).
- **auth.ts:** `login` returns the token transiently (seeded into memory, never persisted); `setPassword(newPassword)` / `enterPortal()` read in-memory+cookie; new `logoutAdmin()` → `POST /auth/logout`; `credentials:"include"` on all auth fetches.
- **API libs:** `admin, client, reports, search, notifications, corrections, download, portal, portal-session, reviewer, feedback` + hooks `use-generation`, `use-conversation` + `intake-wizard.tsx` — all swapped to `adminAuthHeader()` / `getAdminAccessToken()` + `credentials:"include"`. `reviewer.ts` & `feedback.ts` dropped their explicit `token` params.
- **Pages/shells:** `login` (in-memory + identity-only write), `activate` (adopts the re-minted token), reviewer pages (dropped token args), `feedback-launcher` (dropped token arg), all three shells' `onLogout` now `await logoutAdmin()`.
- **Portal coupling handled:** `with-portal-session.tsx` mints the portal cookie via `enterPortal()` which now reads the in-memory token / staff cookie instead of `localStorage`.

### Local verification (done)
- `npx tsc --noEmit` → **exit 0** (run on a clean tree; the gitignored `* 2.ts`/`* 2.tsx` Finder duplicates and `tmp/cw-next-stable` are not part of a real checkout — they were moved aside for the run and restored).
- `npx vitest run` → **95 pass / 1 fail**; the single failure (`components/checkwise/admin/lectura-del-documento.test.tsx`) is **pre-existing** — it fails identically with all my edits stashed and references none of the changed modules.

## MERGE GATE — must pass before merge (cannot be verified from CLI)

On a real **Vercel (web) ↔ Render (api)** preview deploy, in **BOTH Chrome and Safari** (Safari ITP is the cross-site-cookie risk):
1. **Admin login** → dashboard loads; reload the dashboard → API calls still 200 (cookie carries auth with no in-memory token).
2. **/activate set-password** → succeeds and the session survives (re-minted token adopted; no 401 on the post-activation redirect).
3. **Logout** → `POST /auth/logout` clears the cookie; re-opening an app route bounces to /login.
4. **Provider portal `/portal/enter`** → entering a workspace still works (cookie minted via `enterPortal()`).

### Backend config this depends on (confirm on the deploy)
- CORS `allow_credentials=True` with the **exact Vercel origin** allowlisted (not `*`).
- Cookie `SameSite=None; Secure` in prod.
- `allowed_csrf_origins` includes the Vercel origin — after a reload, **mutating** requests (POST/PUT/PATCH/DELETE) go cookie-only and hit `_enforce_cookie_csrf` (Origin/Referer allowlist). If the Vercel origin isn't allowlisted, those 403 after reload.

### If Safari ITP blocks the cross-site cookie
Expected fallback today: reload → cookie dropped → 401 → re-login. The robust end-state (separate task) is to put the API on a **same-site subdomain** (`api.<web-domain>`) so the cookie is first-party, then a clean cookie-only cutover is safe.
