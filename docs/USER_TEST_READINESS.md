# CheckWise — First Real Online User-Test Readiness

> **Date:** 2026-05-19
> **Verdict:** **READY WITH CAUTION** ⚠️
> **What that means:** the deployed product works and is safe to expose to a single non-technical tester **once the operator has (a) confirmed the production demo accounts are rotated/removed and (b) created a fresh isolated test account out-of-band**. Do not send credentials before §6 is complete.
> **Author:** Claude Code (Opus 4.7) readiness pass.
> **Companion docs:** [AUDIT_NEXT_SESSION_READINESS.md](AUDIT_NEXT_SESSION_READINESS.md) · [PROD_AUDIT_2026-05-18.md](PROD_AUDIT_2026-05-18.md) · [NEXT_SESSION_HANDOFF.md](NEXT_SESSION_HANDOFF.md)

---

## 1. Verdict at a glance

| Layer | Status |
|---|---|
| Local code quality (ruff · pytest · tsc · eslint · build · print-contract) | ✅ READY |
| Production backend (Render) reachability + /health | ✅ READY |
| Production frontend (Vercel) reachability | ✅ READY |
| CORS between Vercel frontend ↔ Render backend | ✅ READY |
| Auth endpoints reject bad/empty creds with 401 (not 5xx) | ✅ READY |
| Secret hygiene in tracked files | ✅ READY |
| `/activate` cancel-button password-skip vulnerability | ✅ READY (CW-AUD-P1-01 fix applied) |
| **Demo credentials present in production database** | ⚠️ **CAUTION — operator must verify rotation** |
| **`AUTH_JWT_SECRET` rotated off the docs default in Render** | ⚠️ **CAUTION — operator must verify** |
| Mock data still feeds parts of `/client/*` dashboards | ⚠️ Expected, scope around it |
| No document-redownload endpoint for client/admin | ⚠️ Tester won't try this; out-of-scope for first test |
| No real welcome-email transport | ⚠️ Operator must hand creds over out-of-band |

**Net call:** safe to test **after** the two ⚠️ items in §6 are confirmed by the operator.

---

## 2. What was tested in this readiness pass

### 2.1 Local gauntlet (clean checkout of `main` after this session's edits)

| Check | Command | Result |
|---|---|---|
| Backend lint | `.venv/bin/ruff check .` | ✅ All checks passed |
| Backend tests | `.venv/bin/pytest -q` | ✅ **427 passed**, 2 upstream deprecation warnings |
| Backend import | `python -c "import app.main"` | ✅ Clean import |
| Frontend typecheck | `node_modules/.bin/tsc --noEmit` | ✅ 0 errors |
| Frontend lint | `node_modules/.bin/eslint .` | ✅ 0 warnings/errors |
| Frontend build | `node_modules/.bin/next build` | ✅ **29/29 routes**, build successful |
| Print contract | `npm run check:print` | ✅ 32 assertions pass |
| Secret pattern scan | `grep -E "sk-ant-…|sk-…|password=…"` over tracked files | ✅ Only pytest fixture strings — no live secrets |

### 2.2 Production probes (network, unauthenticated)

| Probe | Result |
|---|---|
| `GET https://checkwise-api.onrender.com/health` | HTTP 200 · `{"status":"ok","service":"checkwise-api","environment":"production"}` · 0.39s |
| `GET https://checkwise-six.vercel.app/` | HTTP 200 (served by Vercel, content-type text/html) · 0.29s |
| `GET https://checkwise-api.onrender.com/openapi.json` | HTTP 200 · ~1s |
| `OPTIONS …/api/v1/auth/login` from `Origin: https://checkwise-six.vercel.app` | HTTP 200 with `access-control-allow-origin: https://checkwise-six.vercel.app`, `allow-credentials: true`, `allow-methods: …POST…` |
| `GET …/api/v1/auth/me` (no token) | HTTP **401** (correct rejection, not 5xx) |
| `POST …/api/v1/auth/login` with fake creds | HTTP **401** (correct rejection, not 5xx) |

The deployed frontend can reach the deployed backend, CORS is locked to the Vercel origin (not `*`), and auth properly rejects without leaking 500s.

### 2.3 Code spot-checks for tester-facing surfaces

- `/activate` Cancel button — confirmed it calls `clearAdminSession()` before redirect to `/login` (security fix CW-AUD-P1-01 in `apps/web/app/activate/page.tsx:174`, `apps/web/lib/session/admin.ts:28`).
- `apps/web/app/login/page.tsx:45` honors `must_change_password` on login (security fix CW-AUD-P1-01).
- `apps/web/app/portal/dashboard/page.tsx:126` references finding CW-AUD-P2-02 — the corresponding control is in place.
- `apps/api/scripts/dev_seed.py:1018` refuses to run against non-local DB hosts. This means the operator cannot accidentally re-seed prod with documented passwords.
- `.gitignore` properly blocks `.env`, `.env.*` (except `.env.example`), `*.pem`, `*.key`, `*credentials*`, `service-account*.json`, `*-secret.json`, `*.db`, `__pycache__/`, etc.
- No hardcoded prod URL/secret in frontend or backend source. API base URL is env-driven via `NEXT_PUBLIC_API_BASE_URL`; backend secrets are `BaseSettings`-driven.

---

## 3. What works (verified)

| Surface | Evidence |
|---|---|
| Landing `/` | Vercel returns HTTP 200 |
| Login `/login` | bundled in build (29/29), auth API responds correctly |
| `/activate?token=…` | rendered, security fix verified in source |
| Admin shell `/admin/*` | 11 routes built; admin login bundled |
| Client portal `/client/*` | 9 routes built; consumes `/api/v1/clients/*` + mocks |
| Provider portal `/portal/*` | 9 routes built; upload, calendar, reports, dashboard, onboarding |
| `/portal/upload` | `intake-wizard` 5-step flow; backend caps 15 MB and `.pdf` only |
| `/portal/reports`, `/portal/reports/[id]`, `/portal/reports/[id]/print` | all built; print contract validates 8 block types |
| Auth + JWT + bcrypt | 427 tests including auth + RBAC |
| Multi-tenant isolation | enforced server-side; documented in `AGENTS.md` and `ARCHITECTURE.md` |

---

## 4. What is unstable / out of scope for this first test

(All known. Not regressions.)

| Item | Why it matters for the tester |
|---|---|
| Some `/client/*` dashboard tiles still consume `apps/web/lib/mock/*` | Tester may see plausible-looking but mock-derived numbers on parts of the client dashboard / activity feed. Functional, not deceptive. |
| Welcome email is **not wired** | Operator hands credentials over out-of-band (Signal / Telegram / 1Password / whatever). Tester won't get an automated email. |
| No client/admin endpoint to **re-download** their own uploaded PDFs | Tester can upload and see status, but if they ask "where do I download my submitted PDF?" the answer is "not in this test". |
| Provider auth still uses opaque `X-Workspace-Token` (V1.2 surface) | Internal mechanism; tester won't notice. Roadmapped for V2.2. |
| Report async PDF/DOCX export worker | Print-mode HTML works; server-rendered export is deferred. Tester gets browser-Print, which is fine. |
| Backwards on cold start (Render `starter` plan) | ~30s spin-up if instance idled. Currently warm (0.39s). |

---

## 5. Blocking issues

**None.** Nothing in the audit warrants delaying the test once the §6 operator items are checked off.

---

## 6. Operator pre-flight (MUST do before sending creds)

These cannot be verified from inside the repo. They are the only true gates between the current state and READY.

### 6.1 Confirm the production database does **not** still hold the documented demo accounts

Background: `docs/PROD_AUDIT_2026-05-18.md` recorded a P0 where `ada@legalshelf.mx` / `demo1234` was reachable on the prod API. The audit was marked "closed by operator" — confirm that closure is still in effect.

```
Run from the Render shell (or any psql with prod DATABASE_URL):

  SELECT id, email, created_at
    FROM users
   WHERE email IN (
     'ada@legalshelf.mx',
     'boss.demo@checkwise.mx',
     'cliente.demo@checkwise.mx',
     'proveedor.demo@checkwise.mx'
   );

Expected: 0 rows. If any row is returned, DELETE that user
(and cascading membership rows) before sending tester credentials.
```

### 6.2 Confirm `AUTH_JWT_SECRET` in Render is NOT the documented default

In `core/config.py:43` the default value is `checkwise-local-dev-secret-change-me-please-min-32-chars`. `render.yaml` declares it as `sync: false`, so it must be set in the Render dashboard. Spot-check:

```
Render dashboard → checkwise-api → Environment →
  AUTH_JWT_SECRET → "Reveal" → confirm it is NOT
  the "change-me-please" string and is ≥ 32 chars.

If it's the default, regenerate:  openssl rand -hex 32
and paste into Render. (Existing user sessions will be invalidated.)
```

### 6.3 Confirm `CORS_ORIGINS` in Render contains exactly the prod frontend

Probed above and it works. Just spot-check that `CORS_ORIGINS` is e.g. `https://checkwise-six.vercel.app` (or whatever your real prod frontend is) — and not `*`.

### 6.4 Create the tester's account

**Do not paste the password into chat.** Two safe paths:

**Option A — One-off SQL** (fastest):

```sql
-- Run from the Render shell with prod DATABASE_URL.
-- Replace <BCRYPT_HASH> with a hash you generate locally:
--   python -c "import bcrypt; print(bcrypt.hashpw(b'<password>', bcrypt.gensalt(12)).decode())"

INSERT INTO users (id, email, password_hash, full_name, must_change_password, is_active, created_at)
VALUES (
  gen_random_uuid(),
  'tester+01@<your-domain>',
  '<BCRYPT_HASH>',
  'External tester #01',
  true,                -- forces password change on first login (CW-AUD-P1-01 path)
  true,
  now()
);
```

Then attach the user to a workspace/organization with the right role. Use the `Membership` row pattern visible in `apps/api/scripts/dev_seed.py` (and copy the role you want: `provider`, `client_admin`, or `internal_admin` for a reviewer view).

**Option B — One-off helper script (recommended if you'll repeat this)**:

Build `apps/api/scripts/create_prod_user.py` that takes `--email`, `--role`, `--workspace-id`, reads the password from stdin (no command-line history leak), bcrypt-hashes locally, inserts the row. **Do not include this script in this commit** — it deserves its own PR with tests. For now use Option A.

### 6.5 Send credentials out-of-band

Email is fine if encrypted. Signal/WhatsApp are fine. Slack DM is fine. **Do not paste the password in any GitHub issue, PR, or this repo.**

---

## 7. Recommended test scope

### Tester should test

1. **Landing** — visit `https://checkwise-six.vercel.app/`, scroll, click CTAs.
2. **Login** — sign in with the credentials they were given.
3. **First-time password change** — they should be forced to set a new password (CW-AUD-P1-01 path). Confirm this fires.
4. **Provider portal happy path** (if their account is a provider):
   - `/portal/dashboard` loads with their workspace identity
   - `/portal/onboarding` shows the expediente checklist
   - `/portal/calendar` shows the REPSE calendar
   - `/portal/upload` — upload a real PDF (≤ 15 MB). Watch for the 5-step wizard. Confirm the upload completes and lands in `/portal/submissions/<id>` with status `pendiente_revision`.
   - `/portal/reports` — opens; report list visible. Open one report.
5. **Logout** — confirms session ends cleanly.

### Tester should NOT test (yet)

- Anything involving real money or signed legal documents.
- Anything that would require admin access (admin login, reviewer queue) — give them a provider or client account, not admin.
- Cross-tenant boundaries (i.e., they can only see their own workspace by design; not a test target).
- Email flows (no transport).
- Bulk uploads, ZIP uploads, multi-PDF uploads (single PDF only, by design).
- The mocked tiles in `/client/*` dashboard activity / calendar (still mock-fed).
- Mobile if time-constrained — desktop first; the V2.x design is desktop-dense.

### Recommended account type

**`provider` role** is the most natural target for the first user test. It exercises the headline flow (login → onboarding → upload → see status → read report) without exposing internal admin surfaces.

A `client_admin` test is also viable if the tester needs to evaluate the read-only portfolio view, but be aware some tiles are mock-fed.

**Don't** give the first external tester an `internal_admin` / `reviewer` role.

---

## 8. Rollback plan if something breaks during the test

1. **Backend regression** — Render keeps prior deploys. From the Render dashboard → checkwise-api → Deploys → previous green build → "Rollback to this deploy". Healthcheck will block traffic shift if the rollback also fails.
2. **Frontend regression** — Vercel keeps every deploy. Dashboard → checkwise project → Deployments → previous prod alias → "Promote to Production".
3. **DB regression from a tester-driven action** — Tester uploads + status changes won't break canonical catalog tables. If they corrupt their own workspace, the recovery path is to delete that workspace's submissions and re-invite. No full-DB rollback is anticipated to be necessary; if it ever is, Neon has point-in-time restore on its non-free tiers — check your plan.
4. **Auth/JWT regression** — If `AUTH_JWT_SECRET` is rotated mid-test, all sessions invalidate. Tester just re-logs in.
5. **CORS regression** — If a typo lands in `CORS_ORIGINS`, the tester sees "blocked by CORS" in the browser console. Fix the env var in Render and re-deploy.

Tell the tester upfront that if they hit anything broken they should screenshot and stop — don't try to "work around it".

---

## 9. Recommended next step after the first test

1. Triage what the tester found. Spec out bug fixes vs. UX changes.
2. Resume the deferred non-blockers: the orphan-file cleanup (see [AUDIT_NEXT_SESSION_READINESS.md §5.4](AUDIT_NEXT_SESSION_READINESS.md)) and the V2.2 mock→real backend wiring (see [ROADMAP.md](ROADMAP.md) §V2.2).
3. If the test surfaces P1 issues, hold them in a new branch and re-run this readiness pass before the next tester.

---

## 10. Quick reference for the operator

```
PROD URLs
  Frontend (Vercel):  https://checkwise-six.vercel.app
  Backend (Render):   https://checkwise-api.onrender.com
  Backend health:     https://checkwise-api.onrender.com/health
  Backend docs:       https://checkwise-api.onrender.com/docs

VERDICT
  READY WITH CAUTION — proceed once §6 operator items are confirmed.

DO NOT
  - Paste passwords in any chat, PR, issue, or commit.
  - Give the external tester an internal_admin/reviewer account.
  - Run dev_seed.py against prod (the guard will refuse).
```
