# CheckWise Repo Cleanup Plan

Date: 2026-05-21
Owner: Jose Pablo Samano
Scope: this pass — hygiene, documentation, and low-risk organization only.
Out of scope: backend → `apps/api` and frontend → `apps/web` moves, route-auth
behavior changes, dependency bumps.

The next milestone after this plan is the **cybersecurity remediation pass**.
That pass owns auth/route hardening, secret-handling, and dependency review.
This document deliberately stays away from those areas.

**Status update (2026-05-21):** Stages 0–4 of §7 have landed on `main`.
The cybersecurity remediation pass (see
[audits/security/SECURITY_REMEDIATION_PLAN.md](audits/security/SECURITY_REMEDIATION_PLAN.md))
shipped before the monorepo move; the monorepo move
(`backend/ → apps/api/`, `frontend/ → apps/web/`) shipped immediately
after. Stage 5 (`packages/`) remains future-only. The historical
sections below reflect the state at the time of writing; references
to `backend/` and `frontend/` describe the pre-move layout.

---

## 1. Current repo classification

Inventoried from `git status --short`, `git ls-files`, and a walk of the top
level + `docs/`, `backend/`, `frontend/`.

### 1.1 Application code (tracked, must stay tracked)
- `apps/api/app/**` — FastAPI app, routers, models, schemas, services, db, core.
- `apps/api/alembic/**` — migrations.
- `apps/web/app/**` — Next.js App Router routes.
- `apps/web/components/**` — UI primitives, domain components, marketing,
  feedback.
- `apps/web/lib/**` — API clients, session, reports, mocks, catalogs.
- `apps/web/public/**` — static public assets.

### 1.2 Production config (tracked)
- `render.yaml` — Render blueprint for `checkwise-api`.
- `docker-compose.yml` — local Postgres only; not the production topology,
  but tracked because every contributor needs the same dev DB shape.
- `apps/api/pyproject.toml`, `apps/api/alembic.ini`.
- `apps/web/package.json`, `apps/web/package-lock.json`,
  `apps/web/tsconfig.json`, `apps/web/next.config.ts`,
  `apps/web/tailwind.config.ts`, `apps/web/postcss.config.mjs`,
  `apps/web/eslint.config.mjs`.
- `.env.example`, `apps/web/.env.local.example` (templates only — real env
  files are ignored).

### 1.3 Local-only config (ignored by `.gitignore`)
- `.env`, `.env.*` (real secrets), every variant except `.env.example`.
- `apps/api/*.db`, `apps/api/*.db-journal` (sqlite dev DB).
- `apps/api/storage/`, `apps/api/uploads/` (dev file storage).
- `postgres-data/` (docker volume mount, if used).
- `.vercel/`, `.next/`, `apps/web/.cw-next-*/`.

### 1.4 Generated artifacts (ignored — should stay ignored)
- `node_modules/`, `__pycache__/`, `*.tsbuildinfo`, `*.egg-info/`,
  `.ruff_cache/`, `.pytest_cache/`, `.mypy_cache/`, `.next/`, `out/`,
  `dist/`, `coverage/`.
- `outputs/`, `*.zip`.
- `docs/video-production/renders/`, `docs/video-production/audit/frames*/`,
  `docs/video-production/remotion/node_modules/`, and the rest of
  `docs/video-production/.gitignore` (nested ignore already in place).
- `docs/system-workflow-v2/node_modules/`.
- `docs/audit-screenshots/**/_raw_demo/`,
  `docs/audit-screenshots/**/demo.silent.mp4`,
  `docs/audit-screenshots/**/*.webm` (newly ignored — heavy
  intermediates, the final `demo.mp4` stays tracked).

### 1.5 Reference / demo materials (mixed)
- `brand_assets/` — logos, brand README. Tracked, intentional.
- `demo_assets/` — sample PDFs, screenshots, demo guide. Tracked,
  intentional.
- `design-concepts/` — inspo screenshots, peer references. Tracked.
- `docs/audit-screenshots/2026-05-18-system-audit/` — final demo PNGs +
  `demo.mp4` + `music.mp3` + voice MP3s. Tracked.

### 1.6 Docs (tracked)
- `docs/*.md` — architecture, audits, product specs, demo guides.
- `docs/architecture/`, `docs/audits/`, `docs/design-system/`,
  `docs/security/`, `docs/codex-route-workflow-audit/`,
  `docs/system-workflow-map/`, `docs/claude/`.
- `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `DESIGN.md`, `PRODUCT.md`.

### 1.7 Claude / session / AI tooling (mostly local-only)
- `.claude/skills/**/SKILL.md` — tracked (shared skill definitions).
- `.claude/agents/`, `.claude/launch.json`, `.claude/settings.local.json`,
  `.claude/worktrees/` — ignored.
- `.agents/` — ignored (skill installer output, reproducible from
  `skills-lock.json` + `install_checkwise_claude_skills.sh`).
- `skills-lock.json`, `install_checkwise_claude_skills.sh`,
  `setup_claude_desktop_optimized.sh`,
  `scripts/register-design-skills.sh` — tracked.
- `CLAUDE_CODE_HANDOFF_*.md` at root — now ignored (local handoff
  scratch). Tracked planning docs go under `docs/`.
- `Checkwise-slack-feedback.txt`, `*-slack-feedback.txt` — now ignored.

### 1.8 Test assets (tracked)
- `apps/api/fixtures/` — golden fixtures for `pytest`.
- `apps/api/tests/` — full test suite.
- `apps/web/scripts/` — frontend dev helpers.

### 1.9 Dev tooling and scripts (tracked)
- `dev.sh`, `dev_demo.sh` — local dev runners.
- `scripts/` (top level) — capture, demo, audit-rendering helpers.
- `apps/api/scripts/` — operator and dev scripts (seed, reset, setup,
  start, provision).
- `apps/api/tools/` — local-only tooling, **never mounted in
  production**. See §6.

---

## 2. What should remain tracked

- Everything under §1.1, §1.2, §1.6, §1.8, §1.9.
- The shared assets in §1.5 (`brand_assets/`, `demo_assets/`,
  `design-concepts/`, final demo media under `docs/audit-screenshots/`).
- Skill definitions: `.claude/skills/**/SKILL.md`.
- The two new docs from this pass: this file and
  [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md).

## 3. What should remain local-only

- Real env files (`.env`, `.env.*`).
- Dev sqlite DB + journal.
- Dev storage and uploads dirs.
- All `node_modules/`, `.next/`, `__pycache__/`, lint/test caches.
- Local Claude session state: `.claude/launch.json`,
  `.claude/settings.local.json`, `.claude/worktrees/`, `.agents/`.
- Local handoff/scratch files at root (`CLAUDE_CODE_HANDOFF_*.md`,
  `CodexConvo.txt`, `*-slack-feedback.txt`).
- Heavy demo intermediates (`_raw_demo/`, `demo.silent.mp4`, `*.webm`).
- Operator artifacts in `docs/`: `docs/CREDENTIALS.md`,
  `docs/EXECUTIVE_REPORT*.html`, `docs/executive-evidence/`.

## 4. Generated-artifact policy

Rules:
1. Generated artifacts **must be reproducible from tracked sources**
   (lockfiles, scripts, migrations).
2. If something is reproducible in <5 minutes from a tracked source, it
   does not get tracked.
3. Final deliverables (the rendered `demo.mp4`, the executive PDF, the
   demo PDFs in `demo_assets/`) **can** be tracked if they are linked
   from external surfaces (README, marketing, customer comms) and
   re-rendering them is non-trivial.
4. Intermediate render artifacts (raw recordings, silent masters,
   per-frame PNGs, Remotion node_modules) **never** get tracked.
5. Nested `.gitignore` files inside a workshop dir (e.g.
   `docs/video-production/.gitignore`) are the source of truth for that
   workshop. The top-level `.gitignore` covers everything else.

## 5. Proposed future monorepo structure

```
CheckWise/
  apps/
    web/        # current frontend/
    api/        # current backend/
  packages/
    design/     # shared design tokens, brand, type, color
  infra/
    render.yaml
    docker-compose.yml
  docs/
    audits/
    architecture/
    product/
  scripts/
    dev/
    reports/
```

Note: `apps/` houses runnable services. `packages/` houses anything
shared across services (today: design tokens only). `infra/` holds
deploy/runtime topology; not application code. `docs/` keeps its
existing audit/architecture/product structure but tightens the
top-level naming.

## 6. Near-term layout (this pass)

Frontend (`apps/web/`):
- `app/` — Next.js App Router routes only.
- `components/ui/` — reusable primitives.
- `components/checkwise/` — domain components.
- `components/marketing/` — public site.
- `components/feedback/` — feedback launcher.
- `lib/api/` — typed API clients.
- `lib/session/` — auth/session.
- `lib/reports/` — report-specific client logic.
- `lib/constants/` — shared constants.
- `lib/mock/` — demo-only/mock logic. **Must not** be imported from
  production code paths once Phase-3 mocks are removed.
- `public/` — static public assets.

Backend (`apps/api/`):
- `app/api/v1/` — routers only. No business logic.
- `app/core/` — config, catalogs, domain rules.
- `app/services/` — business logic.
- `app/models/` — SQLAlchemy ORM models.
- `app/schemas/` — Pydantic schemas.
- `app/db/` — engine, session, base.
- `app/constants/` — domain constants and catalogs.
- `tools/` — **local-only** tooling. Not imported by `app/`. Not on the
  production image's `PYTHONPATH`. Safe to break.
- `scripts/` — operator/dev scripts (seed, reset, setup, provision).
  These are imperative one-shots, not services.

## 7. Staged migration plan

Each stage must land green before the next stage starts.

**Stage 0 (this pass)** — hygiene and docs only.
- Update `.gitignore`.
- Write this plan + PROJECT_STRUCTURE.md.
- Identify cleanup candidates (see §10).

**Stage 1 — cybersecurity remediation pass.**
- Out of scope here. Documented as the next milestone in §11.

**Stage 2 — frontend internal tidy.**
- Confirm all `lib/mock/*` are import-fenced to routes/components that
  still need them.
- Confirm `apps/web/lib/demo-clients.ts` (currently untracked) belongs
  under `lib/mock/` or `lib/demo/` and rename accordingly.
- No path changes that would break import graphs.

**Stage 3 — backend internal tidy.**
- Confirm `apps/api/tools/` is not imported by `apps/api/app/`.
- Confirm `apps/api/scripts/` is not imported by `apps/api/app/`.
- Add a lint check or import-linter rule (deferred — not in this pass).

**Stage 4 — monorepo move.**
- `git mv backend apps/api`
- `git mv frontend apps/web`
- Update `render.yaml` `rootDir`, Vercel project root, every `docs/*`
  reference, `.github/workflows/*`, `dev.sh`, `dev_demo.sh`,
  `docker-compose.yml`, `scripts/*`, `apps/api/scripts/*`.
- Roll out behind a single PR. Do not split — partial moves break
  import paths and CI.

**Stage 5 — packages.**
- Extract design tokens to `packages/design/` if and only if the
  frontend and a second consumer (e.g. a future marketing site) actually
  share them.

## 8. Risks of moving `backend/` → `apps/api` and `frontend/` → `apps/web` too early

- **Deploy regression.** `render.yaml` sets `rootDir: backend`; Vercel's
  project root setting points at `frontend/`. Both must change in the
  same PR as the directory rename, with the Render/Vercel dashboards
  updated **before** merge.
- **Import path breakage.** Top-level `apps/api/scripts/*`,
  `apps/api/tools/*`, and many docs reference `apps/api/app/...` as a
  string. A grep-and-replace must be exhaustive.
- **Test-asset paths.** `apps/api/fixtures/` is referenced by relative
  path from tests; pytest's `rootdir` must follow.
- **Documentation drift.** Every `docs/*.md` linking to
  `apps/api/app/...` or `frontend/...` will go stale. There are ~60+ such
  references today.
- **Open work.** Several frontend files are currently untracked but
  in-progress (new components, new lib files). A directory move on top
  of an unfinished checkout creates merge pain.
- **CI matrix.** `.github/workflows/` paths and any path-filter triggers
  must match the new layout.

Mitigation: do the move in a single, focused PR after the cybersecurity
pass lands and after the in-flight frontend components are either
committed or shelved.

## 9. Verification checklist (this pass)

- [x] `git status --short` reviewed before any change.
- [x] No tracked file moved, renamed, deleted, or reformatted.
- [x] `.gitignore` changes are purely additive and target only
      observed local artifacts.
- [x] Two new docs added under `docs/`.
- [ ] `git status --short` re-reviewed after change; only intentional
      diffs remain.
- [ ] No frontend code changed → no frontend typecheck run.
- [ ] No backend code changed → no backend tests run.
- [ ] No dependency installs.
- [ ] No server starts.

## 10. Cleanup candidates found but not touched

These are **flagged**, not changed in this pass.

- `apps/api/.ruff_cache/` and root `.ruff_cache/` — both exist on disk.
  Both are covered by `.gitignore`. Safe to delete locally any time.
- `apps/api/checkwise.db` + `apps/api/checkwise.db-journal` — local dev
  sqlite, already ignored. Safe to delete locally to force a fresh seed.
- `apps/api/checkwise_backend.egg-info/` — generated; ignored.
- `apps/web/tsconfig.tsbuildinfo` — generated; ignored.
- `.claude/settings.local.json.save` — looks like an editor backup of
  `settings.local.json`. The `.save` file is ignored (matches
  `.claude/*`). Candidate for manual local deletion.
- `docs/audit-screenshots/2026-05-18-system-audit/_raw_demo/` (one
  ~webm file inside) and `demo.silent.mp4` — newly ignored. Candidate
  for local deletion once the final `demo.mp4` is signed off.
- `docs/video-production/` — 586MB on disk, fully untracked. Nested
  `.gitignore` already covers the heavy paths. Candidate for archival
  off-repo once the demo cycle is closed.
- `docs/system-workflow-v2/` — 220MB on disk, fully untracked. Same
  archival recommendation; its `node_modules/` is the heavy item.
- Root `Checkwise-slack-feedback.txt` and `CLAUDE_CODE_HANDOFF_*.md` —
  now ignored. Move to a local notes folder outside the repo when
  convenient.
- `setup_claude_desktop_optimized.sh` — tracked but only invoked once
  per machine. Consider relocating to `scripts/setup/` in Stage 2.
- `scripts/__pycache__/` — generated, already ignored. Local cleanup.

No deletion is performed in this pass.

## 11. Recommended next milestone — cybersecurity remediation

Out of scope for this pass, queued next:

- Audit every route in `apps/api/app/api/v1/**` for `require_role` /
  `require_org_role` / `Depends(get_current_user)` coverage. The
  current README still flags the V1.2 opaque `X-Workspace-Token` for
  the provider portal as a roadmap item.
- Review `apps/api/app/core/` for secret handling, JWT secret rotation,
  CORS origins, and storage-backend credential surface.
- Sweep `apps/web/lib/api/*` for any client-side trust of role claims
  the backend should be enforcing.
- Confirm `apps/api/tools/` cannot reach a production import path.
- Confirm Render's `preDeployCommand` and `healthCheckPath` semantics
  against the current `app/main.py`.
- Re-verify `.env.example` has no real secret values and that no
  real `.env*` file has ever been committed (`git log -p -- .env*`).

**This pass changed no security behavior.** Auth, CORS, secret
handling, role gating, and token issuance are untouched.
