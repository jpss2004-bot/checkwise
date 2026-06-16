---
Document: Change Management Procedure
ID: CW-ISO-change-mgmt
Owner: Lead Engineer / acting CISO (Jose Pablo Samano)
Version: 0.1 (draft)
Effective: 2026-06-16
Review cadence: annual + on material change
ISO refs: ISO/IEC 27002:2022 8.32 (change management), 8.31 (separation of development, test and production environments), 5.4 (management responsibilities)
Status: DRAFT — ISO-readiness evidence, NOT a certification claim
---

> This document is engineering-governance evidence for an ISO/IEC 27001 readiness effort. It describes how changes to the CheckWise platform are proposed, reviewed, tested, approved, deployed, verified, and rolled back. It is **not** a claim of certification. Where a control is aspirational rather than currently enforced, it is marked in the **Current vs target state** table.

## 1. Scope and purpose

CheckWise is a multi-tenant SaaS for Mexican REPSE labour-compliance, operated by LegalShelf. This procedure governs all changes to:

- Application code — FastAPI/Python 3.11 backend (`apps/api`) and Next.js/TypeScript frontend (`apps/web`).
- Database schema — Alembic migrations under `apps/api/alembic/versions/`.
- Infrastructure-as-config — `render.yaml` (backend on Render), Vercel project config (frontend), environment variables, CI/CD workflows under `.github/`.

Source of truth is GitHub (`jpss2004-bot/checkwise`), default branch `main`. The backend auto-deploys from `main` to Render; the frontend auto-deploys from `main` to Vercel; the database is Postgres on Neon; object storage is Cloudflare R2.

## 2. Change lifecycle

Every change SHOULD move through the seven stages below. The tooling column maps each stage to a concrete, repo-grounded control.

| # | Stage | What happens | Tooling / evidence |
|---|-------|--------------|--------------------|
| 1 | **Propose** | A change starts as a branch + Pull Request against `main`. The PR body carries a `## Summary` (2–4 bullets) and a `## Test plan` (manual + automated checks). | GitHub PR. Format mandated in `CONTRIBUTING.md` → "Commit + PR style". |
| 2 | **Review** | A second person reviews. PRs touching security-critical surfaces auto-request the Code Owner. | `.github/CODEOWNERS` auto-requests review on `auth.py`, `core/`, `admin.py`, `models/`, `alembic/versions/`, `storage.py`, `submission_service.py`, `audit_log.py`, `render.yaml`, `.github/`, `middleware.ts`, `next.config.ts`, `docs/compliance/`. **⚠ TO VERIFY** — this is currently *advisory*; see §6. |
| 3 | **Test** | Automated gates run on every PR and every push to `main`. | **CI** (`.github/workflows/ci.yml`): backend `ruff check` + `pytest -q`; frontend `tsc --noEmit` + `eslint` + `next build`. Local pre-commit gauntlet is the same set (`CONTRIBUTING.md` → "Verification gauntlet"). |
| 4 | **Approve** | Security gates plus human approval. | **Security** (`.github/workflows/security.yml`): gitleaks + pip-audit (`--strict`) + npm audit (`--audit-level=high`). **CodeQL** (`.github/workflows/codeql.yml`): SAST over Python + TS/JS, `security-and-quality` query suite. Approval = PR review (Code Owner where matched). |
| 5 | **Deploy** | Merge to `main` triggers auto-deploy. Backend: Render runs `buildCommand` → `preDeployCommand: alembic upgrade head` → swaps traffic only if migration + health check pass. Frontend: Vercel builds and promotes. | `render.yaml` (`autoDeploy: true`, `preDeployCommand`, `healthCheckPath: /health`). Migrations auto-run on deploy — see §4. |
| 6 | **Verify** | Post-deploy smoke test of the critical path against production. | Manual smoke pass: login → a mutation (e.g. save a report or upload a document) → logout. `/health` gates Render's rollout automatically. Browser smoke of home page, provider portal, reviewer queue (`CONTRIBUTING.md`). |
| 7 | **Rollback** | If verification fails, roll back. Code: revert the merge commit (never `--amend` a pushed commit — stack a new one). Render: redeploy the previous successful deploy from the dashboard. DB: restore the pre-deploy Neon snapshot. | Render deploy history + Neon point-in-time / named snapshot branch. See §4 and §5. |

### 2.1 Release gates summary

A change is releasable when **all** of the following are green:

- [ ] CI `backend` job (ruff + pytest) passes.
- [ ] CI `frontend` job (tsc + eslint + next build) passes.
- [ ] Security workflow (gitleaks, pip-audit, npm audit) passes — no committed secrets, no high/critical CVEs.
- [ ] CodeQL analysis surfaces no new high-severity alert.
- [ ] At least one reviewer approved (Code Owner where the path matches). **⚠ TO VERIFY** — not yet *blocking* (see §6).
- [ ] For schema changes: a Neon snapshot was taken before merge (§4).

## 3. Environments and separation (8.31)

| Environment | Hosts | Database | Storage | Notes |
|-------------|-------|----------|---------|-------|
| **Local / dev** | Developer machine (`bash dev.sh`) | Local Postgres (Docker) or SQLite for tests | Local filesystem (`STORAGE_BACKEND` unset/local) | `CHECKWISE_ENV=local`. Boot-security guard is a no-op locally so the in-code JWT placeholder works without env files. |
| **Production** | Render (backend), Vercel (frontend) | Neon Postgres (pooled `DATABASE_URL` at runtime; direct `DIRECT_DATABASE_URL` for Alembic) | Cloudflare R2 (`STORAGE_BACKEND=s3`, bucket `checkwise-prod`) | `CHECKWISE_ENV=production`. Boot guard refuses to start with the placeholder JWT secret or an insecure `sslmode`. |

**Separation controls:**

- Production secrets are injected via Render/Vercel environment variables with `sync: false` (never committed). See `SECURE_SDLC.md` §5.
- Production database TLS is enforced in code: non-local Postgres URLs are normalised to `sslmode=require` (`apps/api/app/core/config.py` `_normalize_pg_url`), and the boot guard rejects `sslmode=disable|allow|prefer` on a non-local deploy.
- The local in-code JWT placeholder cannot authenticate in production — `_validate_boot_security` aborts boot if it leaks into a non-local environment.

> **⚠ TO VERIFY — no dedicated staging environment.** There is currently no always-on staging tier; pre-production verification for risky changes (e.g. the cookie-auth cutover) is done by deliberate, low-traffic-window deploys with rollback ready, per `_handoff/hardening-batch-2026-06-15.md`. **Target:** stand up a Render preview + Neon branch as a staging tier for cross-origin/auth/CSRF E2E before prod.

## 4. Database / migration change procedure (8.32)

Schema is managed by **Alembic**. Migrations are **append-only** — never edit a merged migration; add a new one (`CONTRIBUTING.md` → "Migrations are append-only").

**Authoring:**

```bash
cd apps/api
.venv/bin/alembic revision --autogenerate -m "describe the change"
.venv/bin/alembic upgrade head     # apply locally, verify round-trip
```

- Add the matching SQLAlchemy `Index(...)` / model change so the ORM stays in sync with the migration.
- For data-only migrations, write an explicit no-op `downgrade`.

**Index discipline (`CONCURRENTLY`):** index builds on production MUST be non-locking. Alembic wraps each migration in a transaction, which Postgres forbids for `CREATE INDEX CONCURRENTLY`, so use an autocommit block and the idempotent form:

```python
with op.get_context().autocommit_block():
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_... ON ... (...)")
```

Reference implementation: `alembic/versions/0046_submission_perf_indexes.py`. Current head: **0046**.

**Mandatory pre-deploy snapshot (team standard):**

1. Take a **Neon snapshot** (named sibling branch) of `checkwise-prod` *before* pushing any commit that adds a migration. Migrations auto-run on deploy via `render.yaml` `preDeployCommand: alembic upgrade head`, so the snapshot is the rollback anchor.
2. Push during a low-traffic window.
3. `preDeployCommand` runs `alembic upgrade head` against `DIRECT_DATABASE_URL` *before* traffic shifts. If it fails, the new instance never goes live and the old one keeps serving (`render.yaml` comments).
4. Smoke-test the affected surface post-deploy.

**Migration rollback:**

- A failed `CONCURRENTLY` build can leave an INVALID index — drop it with `DROP INDEX CONCURRENTLY IF EXISTS …` and re-run.
- For a bad schema change that deployed, restore the pre-deploy Neon snapshot; do not hand-edit production schema.

## 5. Emergency / hotfix change process

Hotfixes follow the same pipeline on a compressed timeline — the gates are **not** bypassed:

1. **Branch** off `main` for the fix. Do not push to `main` directly (`CONTRIBUTING.md` → "Don't").
2. **Never use `--no-verify`** to skip the pre-commit hook; never `--amend` a pushed commit.
3. CI + Security + CodeQL still run. A hotfix may be approved by a single available reviewer, but the approval is recorded on the PR.
4. If the hotfix includes a migration, the Neon snapshot in §4 is still mandatory.
5. **Verify** the fix on production immediately (smoke the affected path).
6. **Rollback path** stays ready: revert the merge + redeploy previous Render build + (if schema touched) restore the snapshot.
7. Record the incident and the change in the next security-review handoff (`_handoff/audit-*.md`).

## 6. Current state vs target state (honest assessment)

| Control | Current state (2026-06-16) | Target state |
|---------|----------------------------|--------------|
| Branch protection on `main` | **Not enforced.** Team works direct-to-main; merges and even pushes to `main` are technically possible. `CONTRIBUTING.md` *asks* contributors not to push to `main`, but nothing blocks it. | Enable GitHub branch protection on `main`: no direct pushes, PR required. |
| Required Code Owner review | **Not enforced.** `.github/CODEOWNERS` exists and *auto-requests* the owner, but review is not *required* to merge. The CODEOWNERS file notes it is "the FIRST half of the control". | Turn on "Require review from Code Owners" so security-critical paths cannot merge without owner sign-off. |
| Required status checks | **Not enforced as a merge gate.** CI / Security / CodeQL run on every PR and report status, but a red check does not hard-block a merge. | Mark `backend`, `frontend`, Security, and CodeQL as **required** status checks on `main`. |
| CodeQL SAST | **Just added** (`.github/workflows/codeql.yml`); runs on PR + push + weekly cron. Alerts land in the Security tab. | Triage cadence + treat new high-severity alerts as release-blocking once branch protection lands. |
| Dependabot | **Just added** (`.github/dependabot.yml`); weekly grouped minor/patch PRs, individual major PRs. | Same review SLA as any other PR (see `SECURE_SDLC.md` §2). |
| Linear commit history / signed commits | Not enforced. | Consider "Require linear history"; signed commits optional. |
| Dedicated staging environment | **None** (see §3). | Render preview + Neon branch staging tier. |

> Net: the **tooling** for a strong change-management control is in place (CI, Security, CodeQL, CODEOWNERS, Dependabot, Neon snapshots, health-gated deploys). The remaining gap is **enforcement** — enabling GitHub branch protection so the advisory controls become blocking. This is the single highest-leverage next step for this clause.

## 7. Roles and responsibilities (5.4)

| Role | Responsibility |
|------|----------------|
| Lead Engineer / acting CISO (Jose Pablo Samano) | Owns this procedure, the CODEOWNERS allowlist, the security workflows, the pre-deploy snapshot discipline, and the branch-protection rollout. Default Code Owner for security-critical paths. |
| Contributors (incl. AI-assisted) | Follow the lifecycle in §2, run the local gauntlet before commit, write PR Summary + Test plan, never bypass hooks. |
| Reviewer | Confirms the change matches its stated intent, the test plan is real, and no secret/regression slips in. |

## 8. Records

- Change records: GitHub PRs + merge commits on `main`.
- Deploy records: Render deploy history; Vercel deployment list.
- DB snapshots: named Neon sibling branches (rollback anchors).
- Periodic review evidence: `_handoff/audit-*.md` (e.g. `audit-security-perf-2026-06-15.md`, `hardening-batch-2026-06-15.md`) and this `docs/compliance/` tree.
