# CheckWise

REPSE-compliance SaaS for Mexico. Vendors upload monthly / bimonthly / four-monthly / annual evidence (SAT, IMSS, INFONAVIT, acuses, corporate file); LegalShelf reviewers approve, reject, or request clarifications; clients (companies being audited) read a portfolio-wide risk view.

## Status

V1.2 is operational. Provider portal, reviewer queue + decision workflow, real auth + RBAC, official brand palette, and motion polish are all shipped. Client overview ("Patch 8") is next.

## Stack

- **Backend** — FastAPI · SQLAlchemy · Alembic · Python 3.11
- **Frontend** — Next.js 15 · React 19 · Tailwind 3 · shadcn-style components · lucide-react
- **DB** — SQLite (local dev) · PostgreSQL (prod)
- **Auth** — bcrypt + JWT (HS256). Provider portal uses opaque `X-Workspace-Token`.
- **Storage** — local filesystem for dev, S3-compatible in prod (controlled by `STORAGE_BACKEND`).

## Quick start

**First time:**

```bash
bash backend/scripts/dev_setup.sh   # venv, deps, alembic migrate, seed demo
cd frontend && npm install && cd ..
```

**Every run (one command, both services):**

```bash
bash dev.sh
```

Or in two terminals:

```bash
bash backend/scripts/dev_start.sh        # http://localhost:8000
cd frontend && npm run dev               # http://localhost:3000
```

Reset DB:

```bash
bash backend/scripts/dev_reset.sh        # drops SQLite, re-migrates, re-seeds
```

## Demo credentials

Created by `backend/scripts/dev_seed.py`.

| Surface | URL | Auth |
| --- | --- | --- |
| Reviewer / admin | `http://localhost:3000/admin/login` | `ada@legalshelf.mx` / `demo1234` |
| Provider portal | `http://localhost:3000/` | Any client/vendor combo mints a fresh workspace |

Pre-seeded provider workspace:

- `workspace_id`: `ws-demo-0001`
- `access_token`: `demo-token`
- 4 demo submissions in states `pendiente_revision`, `posible_mismatch`, `aprobado`, `rechazado`

## Repo layout

```
CheckWise/
├── backend/                 FastAPI app, Alembic migrations, pytest suite
│   ├── app/                 routers, services, models, schemas, db
│   ├── alembic/             migrations 0001–0006
│   ├── scripts/             dev_setup.sh, dev_start.sh, dev_reset.sh, dev_seed.py
│   └── tests/               7 test modules, 82 passing
├── frontend/                Next.js 15 app
│   ├── app/                 routes (portal/, admin/)
│   ├── components/          ui (shadcn), checkwise/ (brand, wizard, validation),
│   │                        portal/ (calendar, checklist, badges, state surfaces)
│   ├── lib/                 portal-client, admin-client, reviewer-client, sessions
│   └── public/brand/        official logos (mirror of brand_assets/Logos CW/)
├── docs/                    architecture, data model, roadmap, regulatory model,
│                            portal flow, intake, validation, intelligence, JotForm exit
├── demo_assets/             screenshots + demo guide PDF + fictitious SAT sample
├── brand_assets/            source logo files
├── scripts/reports/         one-off report + demo-asset generators (off the hot path)
├── dev.sh                   one-shot launcher for the whole stack
├── docker-compose.yml       optional Postgres for parity with prod
├── AGENTS.md                rules for AI agents working on this repo
└── .env.example             env-var template
```

Off-repo (lives in `../  _reference/`): exported Google Drive docs (FRD, Matriz Regulatoria, Tier deck, UAT), historical screenshots, sample-doc fixtures. See `_reference/README.md`.

## Verification gauntlet

Run before every commit / PR.

```bash
# Backend
cd backend
.venv/bin/ruff check .
.venv/bin/pytest -q

# Frontend
cd frontend
node_modules/.bin/tsc --noEmit
node_modules/.bin/next lint --quiet
node_modules/.bin/next build
```

## Conventions

- **Status vocabulary (Spanish, plain-language)** — `Esperando revisión` · `Posible inconsistencia` · `Necesita aclaración` · `Aprobado` · `Rechazado`. Canonical codes stay English in code (`pendiente_revision`, `posible_mismatch`, `requiere_aclaracion`, `aprobado`, `rechazado`).
- **Brand colors only via HSL CSS variables** in `frontend/app/globals.css`. Semantic colors (success/attention/destructive) via Tailwind defaults (`emerald` / `amber` / `red`).
- **One icon family** — `lucide-react`. No emoji in UI.
- **Domain terms** — English in code identifiers, Spanish in user-facing copy.
- **Migrations append-only** — never edit a merged migration; add a new one.
- **Documents live outside the DB** — PostgreSQL holds metadata, hash, status, storage key, audit events.

## Where to go next

- Architecture overview → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Data model → [docs/DATA_MODEL.md](docs/DATA_MODEL.md)
- Regulatory framework → [docs/REGULATORY_MODEL.md](docs/REGULATORY_MODEL.md)
- Provider portal walkthrough → [docs/PROVIDER_PORTAL_FLOW.md](docs/PROVIDER_PORTAL_FLOW.md)
- Roadmap → [docs/ROADMAP.md](docs/ROADMAP.md)
- Demo guide → [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md)
- Contributing (conventions, commit style, PR process) → [CONTRIBUTING.md](CONTRIBUTING.md)
- AI-agent rules → [AGENTS.md](AGENTS.md)
