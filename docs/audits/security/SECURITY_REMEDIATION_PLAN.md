# CheckWise Security Remediation — Pass 1

Date: 2026-05-21
Owner: Jose Pablo Samano
Scope: smallest production-safe patch addressing the known cybersecurity
risks documented at the start of this pass. No restructuring, no
dependency churn, no auth migration.

Companion to: [docs/REPO_CLEANUP_PLAN.md](../../REPO_CLEANUP_PLAN.md) §11.

---

## 1. Risks addressed in this pass

| # | Risk | Severity | Status |
| - | ---- | -------- | ------ |
| 1 | Anonymous legacy `POST /api/v1/submissions` trusting browser-posted tenant identity | High | Fixed — gated behind `internal_admin` outside `CHECKWISE_ENV=local`. |
| 2 | Anonymous `POST /api/v1/metadata-dry-run/pdf` accepting PDFs without auth | High | Fixed — same `internal_admin` gate; plus a max-upload-size guard before reading the full body. |
| 3 | Portal cookie auth without CSRF protection (`SameSite=None; Secure` in prod) | High | Fixed — strict Origin/Referer check on all mutating `/api/v1/portal/*` requests that rely on the portal cookie. Bearer-token flows bypass. |
| 4 | `auth/login` and `auth/forgot-password` lacked rate limiting | Medium | Fixed — sliding-window in-memory limiter keyed by IP and email hashes. Returns 429 when budget is exhausted. |
| 5 | `/docs`, `/redoc`, `/openapi.json` exposed in every environment | Medium | Fixed — disabled automatically when `CHECKWISE_ENV != "local"`. `ENABLE_API_DOCS=true` is the explicit opt-in. |

## 2. Risks deferred (documented, not fixed)

| # | Risk | Severity | Reason for deferral |
| - | ---- | -------- | ------------------- |
| 6 | Admin/staff JWTs stored in frontend `localStorage` | Medium | Full auth migration (HttpOnly cookie + CSRF token, or short-lived access + refresh rotation) is out of scope for this pass. Tracked in §6 below. |
| 7 | Backend dependencies are broad ranges with no lockfile / audit workflow | Medium | Avoiding dependency churn was an explicit constraint. Tracked in §7 below. |

## 3. Files changed

Backend (production code):
- [backend/app/core/config.py](../../../backend/app/core/config.py) — added `ENABLE_API_DOCS`, `EXPOSE_LEGACY_SUBMISSIONS`, `EXPOSE_METADATA_DRY_RUN`, `AUTH_LOGIN_RATE_LIMIT_PER_MINUTE`, `AUTH_FORGOT_PASSWORD_RATE_LIMIT_PER_HOUR`, and the `is_local_env`, `api_docs_enabled`, `allowed_csrf_origins` properties.
- [backend/app/core/security_gates.py](../../../backend/app/core/security_gates.py) — new module. `require_local_or_internal_admin` dependency used by the two legacy endpoints.
- [backend/app/core/rate_limit.py](../../../backend/app/core/rate_limit.py) — new module. `SlidingWindowRateLimiter`, plus the `login_limiter` / `forgot_password_limiter` instances and the `hash_identifier` helper.
- [backend/app/main.py](../../../backend/app/main.py) — `/docs`, `/redoc`, `/openapi.json` URLs gated by `settings.api_docs_enabled`; root redirect targets `/health` when docs are off.
- [backend/app/api/v1/endpoints.py](../../../backend/app/api/v1/endpoints.py) — legacy `POST /submissions` now declares `dependencies=[Depends(require_local_or_internal_admin)]`.
- [backend/app/api/v1/metadata_dry_run.py](../../../backend/app/api/v1/metadata_dry_run.py) — router-level `require_local_or_internal_admin` gate; `Content-Length` check + capped `file.read(...)` so an oversized upload is rejected with 413 before the full body lands in memory.
- [backend/app/api/v1/portal.py](../../../backend/app/api/v1/portal.py) — `enforce_portal_csrf` dependency mounted at the router. Mutating methods that rely on the portal cookie must present an allowed `Origin` (or `Referer`); bearer-token requests, safe methods, and requests not carrying the cookie are bypassed.
- [backend/app/api/v1/auth.py](../../../backend/app/api/v1/auth.py) — login + forgot-password call `_enforce_login_rate_limit` / `_enforce_forgot_password_rate_limit`. Both throttles run before any DB work so a brute-force flood cannot ramp bcrypt CPU.

Backend (tests):
- [backend/tests/conftest.py](../../../backend/tests/conftest.py) — autouse fixture resets the in-memory limiter buckets between tests so the process-global state cannot leak across cases.
- [backend/tests/test_security_hardening.py](../../../backend/tests/test_security_hardening.py) — new file. 15 tests covering: anonymous legacy submissions allowed in local + blocked in production + accepted with internal_admin in production; metadata dry-run blocked in production + 413 on oversize upload; portal CSRF reject on foreign origin + accept on allowed origin + reject on missing Origin in production + bearer-token bypass + GET no-op; login + forgot-password 429 on exhaustion; `/docs` gated by env and flag.

No frontend code was changed in this pass.

## 4. Verification

```
cd backend && .venv/bin/python -m pytest -x -q
```

Result: **639 passed, 11 warnings in 87.51s**. All pre-existing tests
remain green; the 15 new tests pass.

Targeted runs during development:
- `pytest tests/test_health.py tests/test_config.py tests/test_metadata_dry_run_api.py` → 13 passed.
- `pytest tests/test_auth.py tests/test_submissions.py tests/test_portal.py` → 66 passed.
- `pytest tests/test_security_hardening.py` → 15 passed.

No frontend changes were made, so no frontend typecheck was needed. No
dependency installs or upgrades were performed.

## 5. Operational notes for the next deploy

- `CHECKWISE_ENV` must be set to a non-`local` value (e.g. `production`,
  `staging`) in Render. The hygiene of this single env var now governs
  docs exposure, the legacy-endpoint gate, the metadata dry-run gate,
  and the cookie-secure flag.
- `CORS_ORIGINS` and `FRONTEND_BASE_URL` must list every UI origin that
  is allowed to issue cookie-authenticated mutating portal requests.
  Anything not in that set will 403 against the new CSRF guard.
- Rate-limit defaults (10 logins / minute / (ip, email), 5 forgot /
  hour / email) are conservative. Tune via env if real traffic patterns
  argue for adjustment; setting either to `0` disables that limiter.
- To keep `/docs` reachable in a non-local environment (e.g. a private
  staging tier), set `ENABLE_API_DOCS=true`. Do not set it in production.

## 6. localStorage JWT — follow-up

`frontend/lib/session/admin.ts` stores the staff JWT in `localStorage`.
That exposes it to any XSS payload that reaches the React tree. Migration
is non-trivial and stays deferred:

1. Decide cookie model:
   - Option A — HttpOnly cookie with a CSRF double-submit token. Mirrors
     the new portal pattern. Requires server-issued CSRF endpoint and a
     fetch wrapper that attaches the token.
   - Option B — short-lived access token in memory + HttpOnly refresh
     cookie. More moving parts; better for SPA-style apps.
2. Server changes: `/api/v1/auth/login` must `Set-Cookie` the access
   token, never include it in the JSON body. `Authorization: Bearer` is
   replaced or retained as a secondary path for non-browser clients only.
3. Frontend: drop all `localStorage.getItem("checkwise-admin-jwt")`
   reads; `withCredentials` on fetches; redirect-to-login on 401.
4. Backend: extend the existing portal CSRF approach to the admin
   surface, OR adopt a token-based double-submit pattern.
5. Add a `Content-Security-Policy` middleware tightening `script-src`
   ahead of the migration so an XSS bug does not silently weaponize the
   new cookie path either.

Estimated effort: 1–2 days for the cookie + CSRF migration, plus a
frontend sweep to convert every admin API client.

## 7. Backend dependency lock / audit — follow-up

`backend/pyproject.toml` pins minimum versions only (`fastapi>=0.111`,
`sqlalchemy>=2.0`, etc.). There is no resolved lockfile and no scheduled
audit. Recommended remediation:

1. Adopt `pip-tools` (`pip-compile pyproject.toml -o requirements.lock`)
   or `uv`'s `uv pip compile` to materialize a versioned lock from
   `pyproject.toml`. Commit the lock alongside the manifest.
2. Pin the lock in CI: `pip install -r requirements.lock` before tests.
3. Run `pip-audit -r requirements.lock` on a schedule (weekly), failing
   CI on any HIGH/CRITICAL finding. Add to `.github/workflows/`.
4. Mirror the same approach for `pyproject.toml`'s `dev` extras so
   developer dependencies are also audited.

Frontend has `package-lock.json` so `npm audit --omit=dev` is already
runnable. Adding it to CI is a smaller follow-up.

## 8. Redis / distributed rate limiter — follow-up

`backend/app/core/rate_limit.py` is in-memory per worker. Today the
backend runs single-worker on Render, so the counters are effectively
global. Before horizontal scaling:

1. Provision Redis (Upstash, Render Redis, or self-hosted).
2. Replace `SlidingWindowRateLimiter._events` with a Redis-backed
   sorted-set per bucket. The class shape stays the same; only the
   storage layer changes.
3. Move the `check` call into a Lua script for atomic eviction + size
   check.
4. Add `Retry-After` headers on the 429 response based on the bucket's
   oldest event.

This is a load-driven follow-up — small deploys don't need it. But the
upgrade should happen *before* the second uvicorn worker is enabled,
not after, otherwise effective per-cluster limits would relax by a
factor of N silently.

## 9. Recommended next hardening milestone

In priority order:

1. **localStorage JWT migration (§6).** Single biggest residual risk.
2. **Dependency lockfile + scheduled audit (§7).** Cheap, high signal.
3. **Add a `Content-Security-Policy` header** in `frontend/next.config.ts`
   or a Next middleware. Even a conservative report-only policy gets us
   telemetry on inline-script surfaces.
4. **Audit logging completeness.** Ensure every state transition we
   already record in audit_log also captures actor IP hash + user agent
   (the portal correction-request endpoint already does this — extend
   the pattern to admin/reviewer mutating endpoints).
5. **CSRF token-based defense for the admin surface.** Mirrors the
   portal-cookie pattern but adds a per-session token; required if §6
   adopts Option A.
6. **WAF / rate-limit at the edge.** Render + Cloudflare in front would
   absorb most volumetric attacks before the FastAPI process sees them.

## 10. What was NOT changed in this pass

- No frontend code.
- No dependency versions.
- No database migrations.
- No CORS allowlist contents (only the property derived from it).
- No auth flow semantics — `/auth/login`, `/auth/me`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/set-password` all behave the same as before for legitimate callers within budget.
- No route paths, response shapes, or status codes for the happy paths.
- No restructuring, no file moves, no formatting passes.

Confirmed by: the full `pytest` suite passing without modifications to
any pre-existing test assertion.
