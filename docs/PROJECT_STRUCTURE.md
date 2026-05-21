# CheckWise Project Structure

Date: 2026-05-21
Companion to: [REPO_CLEANUP_PLAN.md](REPO_CLEANUP_PLAN.md)

This document is the contract for "where things live" in the CheckWise
repo. New work must follow it. If a placement question is ambiguous,
default to the closest existing pattern and update this file in the
same PR.

---

## 1. Top-level layout (current, accepted)

```
CheckWise/
  AGENTS.md
  CONTRIBUTING.md
  DESIGN.md
  PRODUCT.md
  README.md
  .env.example
  .gitignore
  .github/                # CI workflows
  docker-compose.yml      # local Postgres only
  render.yaml             # production backend blueprint (Render)
  dev.sh                  # local dev runner
  dev_demo.sh             # local demo runner
  install_checkwise_claude_skills.sh
  setup_claude_desktop_optimized.sh
  skills-lock.json

  apps/
    api/                  # FastAPI backend (was backend/)
    web/                  # Next.js frontend (was frontend/)

  brand_assets/           # logos, brand-mark guidance
  demo_assets/            # sample PDFs, screenshots, demo guide
  design-concepts/        # inspo screenshots, peer references
  docs/                   # all written documentation
  scripts/                # repo-wide dev/demo/render scripts
```

Tracked top-level dotfiles are limited to `.env.example`, `.gitignore`,
`.github/`, and the curated subtree under `.claude/skills/`. Everything
else under `.claude/` is local-only (see `.gitignore`).

## 2. Frontend (`apps/web/`)

Next.js App Router project.

```
apps/web/
  app/                    # routes only
    activate/
    admin/
    client/
    dev/                  # local-only dev pages (must not ship)
    forgot-password/
    login/
    portal/
    reset-password/
    layout.tsx
    page.tsx
    not-found.tsx
    globals.css

  components/
    ui/                   # reusable primitives (button, table, dialog…)
    checkwise/            # domain components, including /portal/
    marketing/            # public-site components
    feedback/             # feedback launcher

  lib/
    api/                  # typed API clients, one file per surface
    session/              # auth/session, route gates
    reports/              # report-specific client logic
    constants/            # shared constants
    mock/                 # demo-only / mock data. Fenced out of prod.
    email/                # email helpers (client-side)
    workspace/            # workspace-scoped helpers
    catalogs.ts           # static catalogs
    utils.ts              # generic helpers
    types.ts              # shared types

  public/                 # static assets served at /

  scripts/                # frontend-local dev scripts
  next.config.ts
  tailwind.config.ts
  tsconfig.json
  postcss.config.mjs
  eslint.config.mjs
  package.json
  package-lock.json
```

Folder responsibilities:
- `app/` only declares routes, layouts, loading/error boundaries. No
  business logic.
- `components/ui/` is import-safe from anywhere. No app or domain
  imports inside it.
- `components/checkwise/` is allowed to import from `ui/`, `lib/api`,
  `lib/session`, `lib/reports`, `lib/constants`.
- `components/marketing/` is public-site only — does not import from
  `lib/session` or any authenticated surface.
- `components/feedback/` is the feedback launcher; isolates the
  `contact_service` integration on the client side.
- `lib/api/` has one file per backend surface (auth, admin, portal,
  reports, reviewer, contact, corrections, feedback, catalogs,
  client). Each module owns its request shapes and JSON parsing.
- `lib/session/` owns route gates (`withOnboardingGate`,
  `withPortalSession`) and the read/refresh primitives.
- `lib/mock/` is **demo-only**. Modules here are imported by demo
  surfaces and the Phase-3 dashboards that still consume mocks
  through `portal-adapters.ts`. As real endpoints land, the
  corresponding mock file is deleted, not stubbed out.
- `public/` is for assets that must be served at a URL. Branded source
  files (PSD, AI, raw logo exports) belong under `brand_assets/` at
  the repo root, not `public/`.

## 3. Backend (`apps/api/`)

FastAPI app on Python 3.11.

```
apps/api/
  alembic/                # migrations
  alembic.ini
  app/
    api/v1/               # routers only
    constants/            # domain constants and catalogs
    core/                 # config, security, settings, domain rules
    db/                   # engine, session, base
    models/               # SQLAlchemy ORM
    schemas/              # Pydantic
    services/             # business logic
    main.py
  docs/                   # backend-local docs (kept terse; canonical
                          # docs live under /docs at the repo root)
  fixtures/               # pytest golden fixtures
  scripts/                # operator/dev scripts (seed, reset, setup)
  storage/                # local dev file storage (ignored)
  tests/                  # full pytest suite
  tools/                  # LOCAL-ONLY tooling. Never in production.
  pyproject.toml
```

Folder responsibilities:
- `api/v1/` files declare routes and call into `services/`. No SQL, no
  ORM, no business rules.
- `services/` owns business logic. May call `models/`, `schemas/`,
  `core/`, and other services. Never returns ORM objects to routers
  unless wrapped in a schema.
- `models/` is SQLAlchemy only. No request/response shapes.
- `schemas/` is Pydantic only. No ORM imports.
- `db/` is engine, session, dependency-injection wiring.
- `core/` is config, security primitives, JWT, password hashing, role
  decorators, catalogs, and regulation rules.
- `constants/` holds plain constants (institutions, periods, status
  enums where appropriate).
- `alembic/` — every schema change is a migration. No
  auto-create-on-startup in production.

## 4. Where local tools and scripts belong

- `apps/api/tools/` — local-only Python. Examples currently present:
  `build_n8n_review_payload.py`, `export_n8n_metadata_templates.py`,
  `test_pdf_metadata_dry_run.py`. **Rule: nothing under `apps/api/app/`
  may import from `apps/api/tools/`.** These files must not be on the
  production image's `PYTHONPATH` and must not be referenced by
  `render.yaml`.
- `apps/api/scripts/` — operator one-shots (`dev_reset.sh`,
  `dev_seed.py`, `dev_setup.sh`, `dev_start.sh`, `add_test_provider.py`,
  `add_internal_admin.py`, `generate_sample_pdfs.py`,
  `provision_test_provider.py`). Run by hand or by `dev.sh`. Same rule:
  not imported by `app/`.
- `scripts/` at the repo root — cross-cutting helpers (audit
  screenshot capture, demo recording, PDF rendering). These can use
  both backend and frontend artifacts but are never deployed.
- `apps/web/scripts/` — frontend-local dev scripts. Same rule: never
  imported by `apps/web/app/` or `apps/web/components/`.

## 5. Where docs, audits, and reference material live

- `docs/` is the single tracked home for project documentation.
  Subfolders:
  - `docs/architecture/` — system design.
  - `docs/audits/` — recurring audits (one folder per audit topic).
  - `docs/security/` — security findings and recommendations.
  - `docs/design-system/` — V2.x visual direction, doctrine, audits,
    inspo maps.
  - `docs/claude/` — notes about Claude Code skills, prompts,
    workflows used to build CheckWise.
  - `docs/codex-route-workflow-audit/` — Codex audits.
  - `docs/system-workflow-map/` — system-flow assets.
  - `docs/audit-screenshots/<date-slug>/` — one folder per audit
    session, holds final screenshots, voice, music, and the rendered
    `demo.mp4`.
- `brand_assets/` — logos and brand-mark guidance. Tracked.
- `demo_assets/` — sample PDFs, screenshots, demo guide. Tracked.
- `design-concepts/` — inspo screenshots and peer references.
  Tracked.
- Operator artifacts under `docs/` that are local-only:
  `docs/CREDENTIALS.md`, `docs/EXECUTIVE_REPORT*.html`,
  `docs/executive-evidence/`. These are explicitly ignored.
- Local workshop dirs (e.g. `docs/video-production/`,
  `docs/system-workflow-v2/`) carry their own `.gitignore` and stay
  untracked end-to-end until a deliverable is signed off.

## 6. Naming conventions

- Folders: kebab-case (`design-concepts/`, `audit-screenshots/`).
  Exceptions: language-conventional folders (`__pycache__`,
  `node_modules`).
- Python modules: snake_case (`contact_service.py`,
  `provider_dashboard.py`).
- TypeScript files: kebab-case for non-component modules
  (`portal-client.ts`, `contact-requests.ts`); PascalCase only for
  default-export React components when the file *is* the component.
  Otherwise kebab-case for component files too (matches the existing
  pattern in `components/checkwise/`).
- React component identifiers: PascalCase (`ProviderContextBar`).
- API route paths: lowercase, hyphenated, versioned under `/api/v1/`.
- Database tables: snake_case, plural (`providers`, `submissions`).
- Migrations: Alembic default naming, with a short imperative slug.
- Docs: SCREAMING_SNAKE_CASE for top-level docs that act as canonical
  references (`README.md`, `AGENTS.md`, `REPORTS_ARCHITECTURE.md`),
  kebab-case for subordinate docs inside a subfolder.
- Branches: `main` is the only long-lived branch. Feature branches
  follow `username/short-slug` when they exist.
- Env vars: SCREAMING_SNAKE_CASE, prefixed by surface
  (`AUTH_JWT_SECRET`, `STORAGE_BACKEND`, `DATABASE_URL`).
- Dates in filenames: `YYYY-MM-DD`
  (e.g. `CLAUDE_CODE_HANDOFF_2026-05-21.md`,
  `AUTH_ROLE_FLOW_AUDIT_2026-05-18.md`).

## 7. Rules for not mounting local-only tools in production

These rules apply to `apps/api/tools/`, `apps/api/scripts/`, top-level
`scripts/`, `apps/web/scripts/`, and anything new added to those
folders.

1. **No imports.** Production code in `apps/api/app/` and
   `apps/web/app/`+`apps/web/components/`+`apps/web/lib/` must not
   import from any `tools/` or `scripts/` folder. If a helper needs to
   be reused by `app/`, promote it into `app/services/` or
   `lib/<surface>/` first.
2. **Not in the deploy artifact.** `render.yaml` should run from
   `rootDir: apps/api` (update post-monorepo-move) and starts
   `uvicorn` against `app.main`. Tools and scripts live in sibling
   folders and are not part of the running process. Do not add
   `tools/` to any module path or sys.path.
3. **No production env reads at import time.** A tool may need
   `DATABASE_URL` to run locally, but it must read env at execution,
   not at module import, so accidental imports do not crash a prod
   boot.
4. **Document the local-only nature.** Every script/tool file should
   have a one-line header naming the intended environment ("local
   dev", "operator one-shot", "demo capture"). When in doubt, add a
   sanity guard:

   ```python
   if os.getenv("RENDER") == "true":
       raise SystemExit("This script must not run in production.")
   ```

5. **Frontend equivalent.** Files under `apps/web/scripts/` and
   anything in `apps/web/lib/mock/` must not be imported from server
   components or route handlers that ship to production. Demo and
   mock surfaces are gated behind explicit demo routes
   (`apps/web/app/dev/*`, anything imported by `portal-adapters.ts`'s
   demo branch) and are removed as backend endpoints land.

## 8. Open questions deferred to later passes

- Whether `apps/web/lib/demo-clients.ts` should live under `lib/mock/`
  (currently untracked at the root of `lib/`). Decision pending the
  Phase-3 mock-removal sweep.
- Whether to extract design tokens to `packages/design/` (deferred to
  Stage 5 of the migration plan).
- Whether to lint the import-boundary rules in §7 with `import-linter`
  (Python) and `eslint-plugin-boundaries` (TS). Deferred.
