# CheckWise — Next Session Handoff

> **Last updated:** 2026-05-19
> **Last activity:** Full readiness audit + 3 safe edits (CI eslint migration, README, two API-URL fallbacks). No commits yet.
> **Authoritative report for this session:** [AUDIT_NEXT_SESSION_READINESS.md](AUDIT_NEXT_SESSION_READINESS.md)
> **Prior session notes (kept for history):** [SYSTEM_UX_AUDIT_REPORT.md](SYSTEM_UX_AUDIT_REPORT.md) · [PROVIDER_REPORTS_SESSION_HANDOFF.md](PROVIDER_REPORTS_SESSION_HANDOFF.md)

---

## TL;DR

- **Repo is green.** `main` is at `f06108c`, in sync with `origin/main`. Working tree was clean at audit start.
- **All checks pass:** ruff · 427/427 pytest · tsc · eslint · 29/29 `next build` · print contract.
- **This pass produced 8 file changes** (3 small consistency fixes + 3 unused-import cleanups + 2 new docs). No commits made yet — see §"How to commit" below.
- **Pre-existing local edits** in the working tree from before this audit: `scripts/record_demo.py` (cursor/animation rewrite), `scripts/finalize_demo.py` (modified), and untracked folder `docs/audit-screenshots/2026-05-18-system-audit/_raw_demo/`. Not from this audit — left alone.
- **Recommended next coding action:** delete the 9 orphan frontend files documented in `AUDIT_NEXT_SESSION_READINESS.md` §5.4 as a single focused commit, then verify the gauntlet stays green.

---

## What is stable (do not regress)

- **Backend** — every route under `/api/v1/{auth,admin,client,compliance,endpoints,metadata_dry_run,portal,reports,reviewer}` is tested. 427 pytest assertions, 9 Alembic migrations applied through `0009_reports_core`.
- **Frontend** — every page in `app/{admin,client,portal}/**` compiles and renders. Print-contract test guarantees that all 8 reports block types expose their `data-block-type` attribute.
- **Auth + RBAC** — JWT (HS256), bcrypt(12) for staff; httpOnly signed cookie for portal sessions; `withOnboardingGate` + `withPortalSession` HOCs gate every protected portal route.
- **Storage** — local-FS in dev, S3-compatible (R2/S3) for prod. Streamed upload with hash + size cap (15 MB · `.pdf` only).
- **Dev-seed prod guard** — `backend/scripts/dev_seed.py:1018` refuses to run against non-local hosts. Documented after the 2026-05-18 P0.

## What is unstable / not yet wired

Mock-backed surfaces marked with `TODO[backend-integration]` in `frontend/lib/mock/*`, `frontend/lib/workspace/*`, `frontend/lib/api/portal-adapters.ts`. None block any user flow; they are V2.0/V2.1 deferred work scheduled as V2.2.

| Area | What's still mocked | Next step |
|---|---|---|
| `/portal/workspaces/{id}/onboarding` adapter | `portal-adapters.ts` synthesises `why` / `format` / `next_action` / `reviewer_note` fields | Backend enrichment lands → drop the adapter |
| Client dashboard / admin dashboard tiles | `lib/mock/*` (calendar, contact-requests, corrections, expediente, invitations) | Wire to real `/api/v1/clients/*` payloads |
| Provider portal auth | V1.2 opaque `X-Workspace-Token` still in use | Replace with the JWT/RBAC stack already used by `/admin/*` |
| Welcome email | template only (`frontend/lib/email/welcome.ts`) | Pick provider, add backend service |

## What should NOT be touched yet

- The `lib/mock/*` modules — they are intentionally still mocked; replace them as part of V2.2, not piecemeal.
- The `X-Workspace-Token` portal-session token — substitution is a V2.2 migration that also requires a backend change.
- `docs/audit-screenshots/2026-05-18-system-audit/` (~26 MB of binaries) — decide on an asset-storage strategy before any rearrangement; don't just `git rm`.
- `scripts/record_demo.py` — has a local uncommitted edit not made by this audit.

---

## How to run the stack locally

**Recommended (one command):**

```sh
./dev_demo.sh
```

Brings up Docker Postgres → migrates → seeds → starts uvicorn (`:8000`) and Next.js (`:3000`) with linked logs.

**Two terminals:**

```sh
# T1: backend
bash backend/scripts/dev_start.sh           # http://127.0.0.1:8000/docs

# T2: frontend
cd frontend && npm run dev                  # http://localhost:3000/
```

**First-time setup:**

```sh
docker compose up -d postgres
bash backend/scripts/dev_setup.sh           # venv, deps, alembic upgrade, seed
cd frontend && npm install
```

**Reset DB:**

```sh
bash backend/scripts/dev_reset.sh           # drop → migrate → seed
```

---

## Demo credentials (from `backend/scripts/dev_seed.py`)

| Role | Email | Password | Reaches |
|---|---|---|---|
| internal_admin · reviewer | `ada@legalshelf.mx` | `demo1234` | `/admin/*` + `/portal/*` (gate bypass) |
| provider (full expediente, boss demo) | `boss.demo@checkwise.mx` | `BossDemo!2026` | `/portal/*` |
| provider (first login, expediente pending) | `proveedor.demo@checkwise.mx` | `CheckWiseDemo!2026` (temp) | `/activate` → `/portal/onboarding` |
| client_admin (V2.1) | `cliente.demo@checkwise.mx` | `ClienteDemo!2026` | `/client/*` (3-vendor portfolio) |

Demo provider workspace token: `demo-token` (workspace `ws-demo-0001`).

---

## Environment variables you need

Template at root: [`.env.example`](../.env.example). Highlights:

- **Backend** (`backend/.env`):
  - `DATABASE_URL` — required. Local default points at `docker compose` postgres.
  - `CORS_ORIGINS` — comma-separated origins for the deployed frontend(s).
  - `AUTH_JWT_SECRET` — must be 32+ chars in any non-local env. Default value contains "change-me".
  - `STORAGE_BACKEND` — `local` in dev, `s3` in prod. Pair with `STORAGE_BUCKET`, `AWS_*` keys.
  - `ANTHROPIC_API_KEY` — optional. Empty falls back to the deterministic mock LLM (used in CI). `CHECKWISE_LLM_BACKEND=mock|anthropic|''` overrides auto-detection.
  - `MAX_UPLOAD_SIZE_BYTES`, `ALLOWED_FILE_EXTENSIONS` — upload limits.

- **Frontend** (`frontend/.env.local`):
  - `NEXT_PUBLIC_API_BASE_URL` — defaults to `http://127.0.0.1:8000` if unset (kept consistent across the codebase as of this pass).
  - `NEXT_PUBLIC_DEMO_MODE=true` — exposes the "Usar PDF demo" affordance.
  - `NEXT_PUBLIC_WHATSAPP_SUPPORT_URL`, `NEXT_PUBLIC_SUPPORT_QR_PLACEHOLDER_URL` — display-only support links.

---

## Known deployment URLs

| Surface | URL |
|---|---|
| Frontend (Vercel) | `https://checkwise-six.vercel.app` |
| Backend (Render) | `https://checkwise-api.onrender.com` |
| Health probe | `https://checkwise-api.onrender.com/health` |
| OpenAPI docs | `https://checkwise-api.onrender.com/docs` |

Backend deploys via `render.yaml` (Render Blueprint). Sensitive env vars (`DATABASE_URL`, `DIRECT_DATABASE_URL`, `CORS_ORIGINS`, `AUTH_JWT_SECRET`, `AWS_*`, `ANTHROPIC_API_KEY`, `SUPPORT_WHATSAPP_URL`) are `sync: false` so Render reads them from the dashboard.

---

## How to run the audit gauntlet

```sh
# Backend
cd backend
.venv/bin/ruff check .
.venv/bin/pytest -q
.venv/bin/python -c "import app.main"

# Frontend
cd frontend
node_modules/.bin/tsc --noEmit
node_modules/.bin/eslint . --quiet
node_modules/.bin/next build
npm run check:print
```

Expected on a clean checkout (as of `f06108c` + this pass's 3 edits): all green, 427 backend tests, 29 frontend route bundles, 32 print-contract assertions.

Two upstream pytest warnings (`HTTP_422_UNPROCESSABLE_ENTITY` deprecation from `starlette`/`anyio`) are external and clear on dependency bump.

---

## Recommended first task for the next coding session

**Delete the 9 confirmed orphan frontend files documented in `AUDIT_NEXT_SESSION_READINESS.md` §5.4.**

```
components/ui/stepper.tsx
components/checkwise/support-card.tsx
components/checkwise/confidence-badge.tsx
components/checkwise/portal/provider-context-bar.tsx
components/checkwise/portal/suggested-actions.tsx
components/checkwise/workspace/correction-request-form.tsx
components/checkwise/document-submission-form.tsx
lib/demo-clients.ts
lib/portal-client.ts
```

Before deleting each one, re-grep its exported symbol(s) against `app/`, `components/`, `lib/` to confirm zero importers. Then run the full gauntlet. Commit as one change. ~30 min, low risk.

After that lands, the existing handoff items remain valid:

1. Responsive cleanup pass (I-04 / I-05 / I-07 from `SYSTEM_UX_AUDIT_REPORT.md`).
2. P2.0 — provider-block seed fixtures in `dev_seed.py`.
3. V2.2 — mock→real backend wiring (multi-session).

---

## How to commit (if you decide to)

```sh
cd "/Users/josepablosamano/Desktop/Work — LegalShelf/checkwise/CheckWise"

# 1) audit edits only (excluding the pre-existing record_demo.py change)
git add .github/workflows/ci.yml \
        README.md \
        frontend/components/checkwise/document-submission-form.tsx \
        frontend/components/checkwise/intake-wizard.tsx \
        frontend/app/admin/dashboard/page.tsx \
        frontend/app/admin/reviewer/page.tsx \
        frontend/app/admin/vendors/page.tsx \
        docs/AUDIT_NEXT_SESSION_READINESS.md \
        docs/NEXT_SESSION_HANDOFF.md
git commit -m "chore(audit): readiness audit 2026-05-19 + safe fixes

- CI + README move off deprecated next lint to eslint . (Next 16 removal).
- Normalize 2 API-URL fallbacks to 127.0.0.1:8000 (matches the other 9).
- Drop 3 unused imports flagged by next build (EmptyState, Button,
  DataTableColumn). Build now emits 0 warnings, 0 errors.
- Add docs/AUDIT_NEXT_SESSION_READINESS.md.
- Refresh docs/NEXT_SESSION_HANDOFF.md."

# 2) (separate decision) the pre-existing edits to scripts/record_demo.py and
# scripts/finalize_demo.py, plus the untracked _raw_demo/ folder, stay
# untouched in the working tree until you decide what to do with them.
```

---

## Open questions for the operator

- Commit this audit pass now, or hold until the orphan-removal commit lands and ship them together?
- What to do with the uncommitted edits to `scripts/record_demo.py` and `scripts/finalize_demo.py`, plus the untracked `docs/audit-screenshots/2026-05-18-system-audit/_raw_demo/` folder? (Keep · revert · commit as their own change.)
- Is the prod `ada@legalshelf.mx` user confirmed deleted/rotated on the Render side? The code guard prevents recurrence but the historical seed needs operator confirmation. See `PROD_AUDIT_2026-05-18.md` and §9 of the audit report.
- Should the heavy `docs/audit-screenshots/2026-05-18-system-audit/` (26 MB) move to release-asset storage / Git LFS, or stay tracked as-is?
