# Auth + role-flow audit — 2026-05-18

**Scope.** Verify the three intended login surfaces (provider /
client / admin-reviewer) route correctly with the seeded demo
accounts, the local AI key takes effect, and the credentials docs
match the seed. Bug-fix-grade, not redesign.

**Repo state.** `main` at commit `f294c31` (login spinner fix) +
local follow-up commit for the `boss.demo` membership bug.

## 1. Environment

Verified by name only (no values printed):

| Variable | `backend/.env` | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | set | Rotated on 2026-05-18 after an accidental terminal print exposed the previous key. |
| `CHECKWISE_LLM_BACKEND` | set (`anthropic`) | |
| `DATABASE_URL` | set | Local docker-compose Postgres. |
| `CORS_ORIGINS` | set | `http://localhost:3000,http://127.0.0.1:3000`. |
| `AUTH_JWT_SECRET` / `AUTH_JWT_ALGORITHM` / `AUTH_JWT_EXPIRES_MINUTES` | set | |
| `STORAGE_BACKEND` | set (`local`) | |

| Variable | `frontend/.env.local` |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | set (`http://127.0.0.1:8000`) |
| `NEXT_PUBLIC_DEMO_MODE` | set |

### Shadowing gotcha (root cause of the original "key not loading" symptom)

The user's `zsh` exports `ANTHROPIC_API_KEY=` (empty). Pydantic
Settings prefers OS env vars over `.env` file values, so the empty
shell var was winning. The local fix is to launch uvicorn with the
shadow stripped:

```bash
env -u ANTHROPIC_API_KEY .venv/bin/uvicorn app.main:app --reload --port 8000
```

Permanent fix is for the operator to remove the empty `export
ANTHROPIC_API_KEY=` line from `~/.zshrc` / `~/.zprofile` / `~/.zshenv`.

## 2. End-to-end AI verification

Verified against real Anthropic, not the mock:

- `GET /api/v1/reports/_engine` → `{"backend":"anthropic","planner_model":"claude-sonnet-4-5-20250929","content_model":"claude-haiku-4-5-20251001"}`
- `POST /api/v1/reports/{id}/generate` SSE → 30 events, ~11s, full sequence `plan` → `block_start` → `block_data` → `ai_summary_delta`(×N) → `block_complete` → `version_saved` → `done`.

## 3. Login matrix — verified

All four demo accounts authenticate via `POST /api/v1/auth/login`:

| Email | Roles returned by API | Routes to (per `decideDestination`) |
|---|---|---|
| `ada@legalshelf.mx` | `['internal_admin', 'reviewer']` | `/admin/reviewer` |
| `cliente.demo@checkwise.mx` | `['client_admin']` | `/client/dashboard` |
| `boss.demo@checkwise.mx` | `[]` | `/portal/entra-a-tu-espacio` |
| `proveedor.demo@checkwise.mx` | `[]` (+ `must_change_password=true`) | `/activate` |

Full credentials in `docs/DEMO_LOGIN_MATRIX.md`.

## 4. Bugs found and fixes applied

### B1 — `boss.demo` was being sent to `/client/dashboard` instead of provider flow

**Symptom.** A returning provider account whose docs (README, DEMO_1.7.1) say it should land on `/portal/dashboard` was routing through `/client/*`.

**Cause.** `backend/scripts/dev_seed.py` (former lines 1004-1026) injected a `client_admin` membership into `boss.demo` for both the LegalShelf org and the client-portfolio org. The stated reason was "give boss.demo memberships so the Reports surface is populated when she visits /portal/reports". Side effect: the login router saw `client_admin` and routed her to `/client/dashboard`.

**Fix.** Removed the membership injection. `boss.demo` now has no memberships → `decideDestination` falls through to `/portal/entra-a-tu-espacio`. `/portal/reports` will render empty for her until vendor report delivery ships in R1.2 — that's the honest state.

**Files touched.** `backend/scripts/dev_seed.py` (1 file).

### B2 — Login double-spinner (already fixed)

Committed as `f294c31`. The `<Button loading={...}>` injected its own `<Spinner>` and the page also rendered a `<CircleNotch>` in the children. One spinner now.

### B3 — `/admin/login` is a legacy double-hop redirect to `/login`

`frontend/app/admin/login/page.tsx` immediately `router.replace("/login")`. The admin shell and client shell still redirect to `/admin/login` on unauthorized — they hop through this stub instead of going to `/login` directly.

**Severity.** Cosmetic only. Functionally works. Filed for follow-up.

**Not fixed in this session.**

### B4 — Admin shell rejects reviewer-only users

`frontend/app/admin/_shell.tsx:74` checks `!current.roles.includes("internal_admin")` and bounces anyone without `internal_admin`. A user holding only `reviewer` (no `internal_admin`) would be blocked from `/admin/*` even though the role exists and `/admin/reviewer` is its primary surface.

**Severity.** Latent — no seeded account triggers it (`ada` holds both roles).

**Not fixed in this session.** Recommended fix: change to `!current.roles.some(r => ["internal_admin","reviewer"].includes(r))`.

### B5 — Pytest fails when a real `ANTHROPIC_API_KEY` is present in the environment

Four tests rely on the deterministic mock LLM:

- `test_reports_copilot.py::test_explain_block_returns_text`
- `test_reports_copilot.py::test_regenerate_block_creates_new_version`
- `test_reports_planner.py::test_plan_endpoint_returns_structured_plan`
- `test_reports_planner.py::test_factory_returns_mock_when_backend_env_set`

When the test session inherits an `ANTHROPIC_API_KEY` and `CHECKWISE_LLM_BACKEND=anthropic`, the factory builds the real client and tries to call Anthropic. Tests then fail on shape mismatch or rate.

**Severity.** Pre-existing test-isolation bug. Surfaces only locally where the operator has put a real key in `.env`. CI doesn't see it.

**Not fixed in this session.** Recommended fix: a session-level pytest fixture sets `CHECKWISE_LLM_BACKEND=mock` and unsets `ANTHROPIC_API_KEY` for the duration of the test run. ~5 lines in `conftest.py`.

## 5. Page surface — static audit (not browser-tested)

This audit was done by reading code, not by clicking. Browser
verification of each surface is the user's next session.

### Provider (`/portal/*`)
- `/portal/entra-a-tu-espacio` — login target for role-less users. Exists.
- `/portal/onboarding` — gated by `withOnboardingGate` HOC until `onboarding_completed_at` is set on the workspace. Exists.
- `/portal/dashboard` — gated by `withOnboardingGate`. Exists.
- `/portal/calendar` — exists.
- `/portal/submissions/[submission_id]` — dynamic route, exists.
- `/portal/upload` — exists.
- `/portal/reports` — exists. List endpoint scopes by `actor.organization_ids` — accounts with no membership see an empty list (correct behavior).
- `/portal/reports/[id]` — editor; gated by `withOnboardingGate`; preset hint pre-fills the AI prompt when present.
- `/portal/reports/[id]/print` — exists.

### Client (`/client/*`)
- `/client` — redirects to `/client/dashboard`.
- `/client/dashboard` — guarded by shell allowing `client_admin` OR `internal_admin`.
- `/client/activity`, `/client/calendar`, `/client/submissions`, `/client/vendors`, `/client/vendors/[vendor_id]` — all routed through the same shell.

### Admin (`/admin/*`)
- `/admin` — landing tile page (not the shell).
- `/admin/dashboard`, `/admin/clients`, `/admin/vendors`, `/admin/requirements`, `/admin/calendar`, `/admin/reviewer`, `/admin/audit-log` — all routed through `AdminShell` which currently rejects everyone except `internal_admin` (see B4).
- `/admin/reports` *(R1.0)* — list + 3 preset cards.
- `/admin/reports/[id]` *(R1.0)* — redirects to `/portal/reports/[id]`; shared-editor extraction deferred to R1.0.1.

### Public / auth
- `/login` — single email/password form. Routes per `decideDestination`.
- `/admin/login` — redirects to `/login` (legacy).
- `/activate?token=…` — public, forced password change for `must_change_password=true`.

## 6. Buttons / redirects — static audit

Tier-1 buttons grepped + traced:

| Surface | Button | Target |
|---|---|---|
| `/login` | "Entrar" (`type=submit`) | `decideDestination(session, must_change_password)` |
| `/admin` (landing tiles) | Tile → review queue | `/admin/reviewer` |
| `/admin/_shell` nav | "Reportes" *(R1.0)* | `/admin/reports` |
| `/admin/reports` | "Usar plantilla" | `POST /reports/from-preset` → `/portal/reports/<new-id>` |
| `/portal/reports` | "Nuevo reporte" | inline create form, `POST /reports`, redirects to `/portal/reports/<id>` |
| All shells | Logout | clears session, `router.replace("/login")` |

**Not verified by clicking.** Static-only audit. Several "view detail" buttons in dashboards and tables were skipped.

## 7. Gauntlet results

- `ruff check app tests` — **clean**
- `next lint --quiet` — **clean**
- `tsc --noEmit` — **clean**
- `pytest -q` (with real `ANTHROPIC_API_KEY` in env) — **4 failed, 316 passed** (see B5 — pre-existing test-isolation issue, not a regression)
- `next build` — not re-run this session; last verified green at commit `6ba0d33`.

## 8. What remains blocked / deferred

- **Browser smoke** of every role flow — not done from this session. Requires the user to manually log in as each of the four accounts and click around.
- **B3, B4, B5** — filed but not fixed (see §4).
- Pytest fixture isolation (B5) — single-file fix in `conftest.py`, ~5 lines, ready for a follow-up slice.
- Vendor / external-signed report delivery — out of scope (R1.2 territory).
- Shared editor component for `/admin/reports/[id]` — deferred to R1.0.1.

## 9. Recommended next action

1. **In the browser**, log in as each of the four accounts in the matrix and confirm the landing route matches the table.
2. If everything looks right, commit the seed fix and push to `main`.
3. Pick one: fix B4 (admin shell role gate) **or** fix B5 (pytest isolation) — both are short single-file changes — **or** start R1.1 (client preset gallery).
