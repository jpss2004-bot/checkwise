# CheckWise

REPSE-compliance SaaS for Mexico. Vendors upload monthly / bimonthly / four-monthly / annual evidence (SAT, IMSS, INFONAVIT, acuses, corporate file); LegalShelf reviewers approve, reject, or request clarifications; clients (companies being audited) read a portfolio-wide risk view.

## Status

**V2.1 is operational locally** — closes the five-phase 2.x rework: a locked visual direction applied across every inner surface, a Reports flagship with embedded copilot, the marketing hero rework, and the final polish + roll-out pass.

### Shipped in 2.1

- **Reports flagship** (Phase 3) — six block types, AI planner + streaming generator + embedded copilot, per-block Regenerate / Explain, print mode. 320+ backend tests including AI-safety suite. Architecture: [docs/REPORTS_ARCHITECTURE.md](docs/REPORTS_ARCHITECTURE.md).
- **Marketing hero + auth rework** (Phase 4) — `/`, `/login`, `/activate`, `/portal/entra-a-tu-espacio` lifted to the V2.x visual register.
- **Internal polish + roll-out** (Phase 5) — locked direction applied to the remaining ~20 admin / client / portal surfaces:
  - Shared `<DataTable>` primitive extracted from `/admin/reviewer` and rolled out to 7 roster surfaces.
  - Shared `<MetadataStrip>` primitive promotes workspace identity to mono key/value rows, replacing the "Hola, [vendor]" greeting blocks.
  - All F2 identical-card grids killed (`/admin/dashboard` 4-up, `/client/dashboard` 4-up, `/portal/onboarding` 2×2) and replaced with bordered vertical lists or asymmetric layouts.
  - Admin and client shells run at `data-density="dense"` with a drawer fallback below 1024px.
  - All `bg-gradient-to-br` hero ornaments dropped in the product surfaces; marketing register kept.
  - State coverage normalised: loading skeleton + error state with retry + empty state on every changed surface.
  - Role-aware `withOnboardingGate` (internal_admin / reviewer bypass the expediente check) so admin users can reach `/portal/*` without bouncing.
  - New `cliente.demo@checkwise.mx` seed user with a 3-vendor portfolio so `/client/*` is reachable in dev / demo.

Full detail: [docs/CHECKWISE_2_0.md](docs/CHECKWISE_2_0.md) + [docs/design-system/VISUAL_DIRECTION_2_X.md](docs/design-system/VISUAL_DIRECTION_2_X.md).

### Shipped earlier (V1.x)

- Public marketing page (`/`) with the "CheckWise 2.0 launch hero" reveal, dual CTAs, and contact form
- Role-aware login (`/login`) for provider · cliente · administrador
- Welcome-email activation flow (`/activate?token=…`) with 3-step wizard + role confirmation
- Workspace confirmation gate (`/portal/entra-a-tu-espacio`) with tenant-locked field display + correction-request form
- Initial expediente gate (`/portal/onboarding`) with mandatory/optional pills, provisional-access banner
- REPSE calendar (`/portal/calendar`) with institution × month grid + detail drawer
- Reports center scaffold (`/portal/reports`) with 5 report types and `ready`/`generating`/`needs_review`/`blocked`/`unavailable` states
- Reviewer queue + decision workflow (`/admin/reviewer/*`) with real JWT auth and tenant-scoped detail
- Real backend auth (`/api/v1/auth/login`), RBAC (`require_role` / `require_org_role`), audit log

**Important.** Several 2.0 dashboards still consume `lib/mock/*` data through the new `portal-adapters.ts` bridge. The backend already has many of the equivalent endpoints — finishing that wiring is the headline 2.1 task (see [docs/CHECKWISE_2_0.md](docs/CHECKWISE_2_0.md) §Carry-forward and [docs/CHECKWISE_1_6.md](docs/CHECKWISE_1_6.md) §Backend integration TODOs).

## Stack

- **Backend** — FastAPI · SQLAlchemy · Alembic · Python 3.11 · bcrypt · PyJWT (HS256)
- **Frontend** — Next.js 15 · React 19 · Tailwind 3 · Geist + Geist Mono · Phosphor icons · shadcn-style primitives
- **Database** — PostgreSQL 16 (local dev via docker-compose; prod-bound on Neon or equivalent managed Postgres)
- **Auth** — bcrypt + JWT for staff users; provider portal still uses the V1.2 opaque `X-Workspace-Token` (replacement is a roadmap item)
- **Storage** — local filesystem in dev (`STORAGE_BACKEND=local`); S3-compatible target in prod (not yet implemented)

## Quick start

**First time:**

```bash
docker compose up -d postgres                       # local Postgres on :5432
bash backend/scripts/dev_setup.sh                   # venv, deps, alembic migrate, seed demo
cd frontend && npm install && cd ..
```

**Every run (one command, both services):**

```bash
bash dev.sh
```

Or in two terminals:

```bash
bash backend/scripts/dev_start.sh                   # http://localhost:8000
cd frontend && npm run dev                          # http://localhost:3000
```

Reset DB:

```bash
bash backend/scripts/dev_reset.sh                   # drops + re-migrates + re-seeds
```

## Demo credentials

Created by `backend/scripts/dev_seed.py`.

| Surface | URL | Auth |
| --- | --- | --- |
| Public marketing | `http://localhost:3000/` | none |
| Login (provider / cliente) | `http://localhost:3000/login` | seeded demo accounts (below) |
| Activation demo | `http://localhost:3000/activate?token=demo` | resolves to a seeded provider invitation |
| Reviewer / admin | `http://localhost:3000/admin/login` | `ada@legalshelf.mx` / `demo1234` |

Seeded demo accounts (`backend/scripts/dev_seed.py`):

| Role | Email | Password | Reaches |
| --- | --- | --- | --- |
| internal_admin · reviewer | `ada@legalshelf.mx` | `demo1234` | `/admin/*` + `/portal/*` (gate bypass) |
| provider (boss demo, expediente complete) | `boss.demo@checkwise.mx` | `BossDemo!2026` | `/portal/*` |
| provider (first login, expediente pending) | `proveedor.demo@checkwise.mx` | `CheckWiseDemo!2026` (temp) | `/activate` → `/portal/onboarding` |
| **client_admin (V2.1)** | `cliente.demo@checkwise.mx` | `ClienteDemo!2026` | `/client/*` (3-vendor portfolio) |

Pre-seeded provider workspace:

- `workspace_id`: `ws-demo-0001`, `access_token`: `demo-token`
- 4 demo submissions in states `pendiente_revision`, `posible_mismatch`, `aprobado`, `rechazado`

## Repo layout (tracked)

```
CheckWise/
├── backend/                          FastAPI app, Alembic migrations, pytest suite
│   ├── app/
│   │   ├── api/v1/                   auth · portal · reviewer · compliance · endpoints
│   │   ├── services/                 auth · audit_log · storage · pdf_validation ·
│   │   │                             document_intelligence · prevalidation ·
│   │   │                             submission_service · requirement_service
│   │   ├── models/                   SQLAlchemy entities (20 tables)
│   │   ├── schemas/                  Pydantic request/response schemas
│   │   ├── constants/                statuses · institutions · roles (StrEnums)
│   │   ├── core/                     config · catalogs · compliance_catalog
│   │   └── db/                       session · base · seed
│   ├── alembic/versions/             6 migrations (initial → auth/RBAC)
│   ├── scripts/                      dev_setup · dev_start · dev_reset · dev_seed
│   └── tests/                        7 pytest modules, 82 tests
├── frontend/                         Next.js 15 app
│   ├── app/
│   │   ├── (marketing)               page.tsx · login · activate
│   │   ├── portal/                   entra-a-tu-espacio · onboarding · dashboard ·
│   │   │                             calendar · reports · upload · submissions/[id]
│   │   └── admin/                    login · reviewer · reviewer/[id]
│   ├── components/
│   │   ├── ui/                       Button · Field · Input · Alert · Progress ·
│   │   │                             Skeleton · Spinner · Badge · DataTable ·
│   │   │                             MetadataStrip · PageHeader · …
│   │   ├── checkwise/                BrandLogo · IntakeWizard · DocStateBadge · …
│   │   ├── checkwise/portal/         PortalAppShell · SemaphoreCard ·
│   │   │                             ExpedienteCard · ComplianceCalendar ·
│   │   │                             OnboardingChecklist · …
│   │   ├── checkwise/workspace/      WorkspaceIdentityCard · ProtectedFieldNotice
│   │   ├── checkwise/reports/        list/ · editor/ · blocks/ · canvas ·
│   │   │                             chat-copilot · freshness-label
│   │   └── marketing/                ContactForm
│   └── lib/
│       ├── api/                      admin · auth · catalogs · client · contact ·
│       │                             portal · portal-adapters · portal-session ·
│       │                             reports · reviewer
│       ├── constants/                statuses (mirror of backend)
│       ├── email/                    welcome (HTML + plaintext templates)
│       ├── mock/                     calendar · corrections · expediente ·
│       │                             invitations (remaining V1.x bridges)
│       ├── routing/                  post-login (decision helper)
│       ├── session/                  admin · portal · with-portal-session HOC
│       └── workspace/                resolver · types
├── docs/                             14 docs incl. DESIGN_SYSTEM, CHECKWISE_1_5,
│                                     CHECKWISE_1_6, ONBOARDING_V1, ARCHITECTURE,
│                                     DATA_MODEL, ROADMAP, PROVIDER_PORTAL_FLOW, …
├── scripts/                          register-design-skills + reports/ generators
├── brand_assets/                     CANONICAL CheckWise logos (see README)
├── demo_assets/                      screenshots + demo guide PDF
├── design-concepts/                  active design inspiration (inspo-screenshots/)
├── .claude/skills/                   project-discoverable Claude Code skills
│                                     (14 checkwise-* + 4 local design overrides
│                                     + 5 bridged upstream skills via symlink)
├── .agents/skills/                   untracked upstream design skill installs
│                                     (reproducible from skills-lock.json)
├── .github/workflows/ci.yml          backend (ruff + pytest) + frontend (tsc + lint + build)
├── dev.sh                            one-shot launcher for the whole stack
├── docker-compose.yml                local Postgres
├── .env.example                      env-var template
├── install_checkwise_claude_skills.sh  generator for .claude/skills/checkwise-*
├── skills-lock.json                  pins the upstream design skills bridged via
│                                     scripts/register-design-skills.sh
├── CONTRIBUTING.md                   conventions, commit style, PR process
├── PRODUCT.md                        product context for AI design skills
├── DESIGN.md                         visual context for AI design skills
└── AGENTS.md                         rules for AI agents working on this repo
```

> Workspace-level orientation (one folder up from this repo) lives in
> [../MAP.md](../MAP.md). It explains where `brand-identity/`,
> `_reference/`, and this repo fit together.

## Verification gauntlet

Run before every commit / PR. CI runs the same.

```bash
# Backend
cd backend
.venv/bin/ruff check .
.venv/bin/pytest -q

# Frontend
cd frontend
node_modules/.bin/tsc --noEmit
node_modules/.bin/eslint . --quiet
node_modules/.bin/next build
```

## Conventions

- **Status vocabulary (Spanish, plain-language UI)** — `Esperando revisión` · `Posible inconsistencia` · `Necesita aclaración` · `Aprobado` · `Rechazado`. Canonical codes stay English in code (`pendiente_revision`, `posible_mismatch`, `requiere_aclaracion`, `aprobado`, `rechazado`).
- **REPSE document states (8)** — `pending`, `uploaded`, `in_review`, `approved`, `rejected`, `expired`, `needs_review`, `empty`. Single source of truth in `frontend/lib/constants/statuses.ts` and `backend/app/constants/statuses.py`.
- **Brand colors only via HSL CSS variables** in `frontend/app/globals.css`. Primary navy `#013557`, accent teal `#09c1b0`. Semantic colors (success/attention/destructive) via Tailwind defaults (`emerald` / `amber` / `red`).
- **One icon family** — `@phosphor-icons/react`. No emoji in product UI.
- **Fonts** — `Geist` for UI, `Geist Mono` for RFCs, hashes, IDs, technical metadata.
- **Domain terms** — English in code identifiers, Spanish in user-facing copy.
- **Migrations append-only** — never edit a merged migration; add a new one.
- **Documents live outside the DB** — PostgreSQL holds metadata, hash, status, storage key, audit events.
- **Tenant isolation** — Backend is the source of truth for every protected field (workspace_id, role, RFC, company). `localStorage` and token-prefilled UI values are display hints only.

## Deployment architecture (notes, not yet production)

The frontend (Next.js) and backend (FastAPI) have different runtime needs:

- **Frontend → Vercel** is the natural target (Next.js native, edge-rendered routes, ISR).
- **Backend → not Vercel.** FastAPI is a long-lived Python server. Vercel can run Python via serverless functions, but the stack here uses SQLAlchemy + Alembic + pg connection pooling that maps poorly to that runtime. Better targets: **Render**, **Railway**, **Fly.io**, **Cloud Run**, or self-hosted via Docker.
- **Database → Neon** (or any managed Postgres) using the existing SQLAlchemy/Alembic setup. The `DATABASE_URL` env var feeds `backend/app/core/config.py`.
- **Storage → S3-compatible** (R2 / S3 / GCS) — currently `LocalStorageService` writes to `./storage`. Vercel's filesystem is read-only outside `/tmp`, so this **must** be migrated before any production-style deploy.

Production blockers and the full integration plan live in [docs/CHECKWISE_1_6.md](docs/CHECKWISE_1_6.md). A 1.7 production-readiness audit is tracked in this branch's session notes.

## Where to go next

- Architecture overview → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Data model → [docs/DATA_MODEL.md](docs/DATA_MODEL.md)
- Regulatory framework → [docs/REGULATORY_MODEL.md](docs/REGULATORY_MODEL.md)
- Provider portal walkthrough → [docs/PROVIDER_PORTAL_FLOW.md](docs/PROVIDER_PORTAL_FLOW.md)
- Roadmap → [docs/ROADMAP.md](docs/ROADMAP.md)
- Demo guide → [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md)
- CheckWise 1.5 implementation → [docs/CHECKWISE_1_5.md](docs/CHECKWISE_1_5.md)
- CheckWise 1.6 implementation → [docs/CHECKWISE_1_6.md](docs/CHECKWISE_1_6.md)
- CheckWise 2.0 implementation → [docs/CHECKWISE_2_0.md](docs/CHECKWISE_2_0.md)
- Design system → [docs/DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md)
- Contributing (conventions, commit style, PR process) → [CONTRIBUTING.md](CONTRIBUTING.md)
- AI-agent rules → [AGENTS.md](AGENTS.md)
