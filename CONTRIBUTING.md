# Contributing to CheckWise

How to work on this repo without breaking anything important. Read once, refer back as needed.

## Getting set up

```bash
bash apps/api/scripts/dev_setup.sh      # venv, deps, alembic migrate, seed
cd frontend && npm install && cd ..
bash dev.sh                            # boots both services
```

If anything in setup feels off, see [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) for the long-form walkthrough.

## Verification gauntlet

Run before every commit. CI does the same.

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

If you change something user-visible, also do a smoke pass in the browser. The home page, provider portal, and reviewer queue all need to render without console errors.

## Repo conventions

### Status vocabulary

Submission / document statuses are the canonical Spanish codes (`pendiente_revision`, `posible_mismatch`, etc.). They live in:

- Backend → [`apps/api/app/constants/statuses.py`](apps/api/app/constants/statuses.py) as a `DocumentStatus` StrEnum.
- Frontend → [`apps/web/lib/constants/statuses.ts`](apps/web/lib/constants/statuses.ts) as a mirror.

Never inline a status string in a conditional. Import the constant and compare.

User-facing labels are plain-language Spanish: `Esperando revisión`, `Posible inconsistencia`, `Necesita aclaración`, `Aprobado`, `Rechazado`. The mapping is in `STATUS_LABELS_ES` in both files.

### Roles

`internal_admin`, `reviewer`, `client_admin` — defined in `apps/api/app/constants/roles.py`. Wire new RBAC guards via `require_role` / `require_any_role` from [`apps/api/app/api/v1/auth.py`](apps/api/app/api/v1/auth.py).

### Institutions

`stps_repse`, `sat`, `imss`, `infonavit`, `interno_cliente` — defined in `apps/api/app/constants/institutions.py`. The frontend gets the human label from `INSTITUTION_LABELS` exported by [`apps/web/lib/api/portal.ts`](apps/web/lib/api/portal.ts).

### Brand colors

- **Brand palette only via HSL CSS variables** in [`apps/web/app/globals.css`](apps/web/app/globals.css). Navy `#013557`, mid-blue `#02558a`, teal `#09c1b0`, slate `#4b90a4`.
- **Semantic colors via Tailwind defaults**: `emerald` (success), `amber` (attention), `red` (destructive).
- **No emoji** in UI. One icon family: `lucide-react`.

### Typography

Open Sans, set in `apps/web/app/layout.tsx`. Don't add a second font without explicit design buy-in.

### Domain language

- Code identifiers, file names, paths, and routes: **English**.
- User-facing UI copy and Spanish-domain strings (status codes, period keys, requirement codes): **Spanish**.

### Files outside the DB

PDFs always live in storage (local FS in dev, S3-compatible in prod via `STORAGE_BACKEND`). PostgreSQL holds metadata, hash, status, storage key, validation output, and audit events.

### Migrations are append-only

Never edit a merged migration. Add a new one.

```bash
cd backend
.venv/bin/alembic revision --autogenerate -m "describe the change"
.venv/bin/alembic upgrade head
```

Data migrations are fine, but the `downgrade` for a data-only migration should be a no-op — write that explicitly.

### Audit events

State transitions worth tracking go through `services/audit_log.add_audit_event` and validation timeline events go through `services/validation_events.add_validation_event`. Don't hide decisions in UI-only state.

## Service-layer expectations

- Routers under `apps/api/app/api/v1/` stay **thin**: parse, dispatch, respond.
- Business logic lives in `apps/api/app/services/`.
  - `submission_service.py` — intake helpers (PDF gate, get-or-create, status derivation, validation timeline).
  - `requirement_service.py` — canonical-vs-legacy resolution + period resolution.
  - One service per cross-cutting concern; don't lump.
- If a helper crosses module boundaries, make it public (no leading `_`).

## Frontend layout

```
frontend/
├── app/                 routes only
├── components/
│   ├── ui/              shadcn primitives
│   ├── checkwise/       brand, wizard, validation, shared product surfaces
│   └── checkwise/portal one-portal-specific surfaces
└── lib/
    ├── api/             typed clients per backend area
    ├── session/         portal + admin session token storage
    ├── constants/       mirrors of backend canonical values
    └── utils.ts         classNames, formatDate, etc.
```

When you add a new API client, drop it in `lib/api/<area>.ts`. When you add a new constant set, mirror the backend in `lib/constants/<topic>.ts`.

## Sample data

Real-shape test PDFs live OFF-REPO at `_reference/sample-docs/` (rebuilt via [`scripts/reports/build_sample_sandbox.py`](scripts/reports/build_sample_sandbox.py)). Read `_reference/sample-docs/README.md` for the layout. Use these for manual upload testing and as fixtures.

## Commit + PR style

- Commit message format: `<type>(<scope>): <subject>` — e.g. `feat(reviewer): queue + decision workflow`, `refactor(backend): extract submission_service`, `docs(roadmap): mark V1.4 shipped`.
- Body: explain *why*, not *what*. Bullet the surfaces touched.
- Include the `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` trailer when AI-assisted.
- Never `--amend` a pushed commit. Stack a new one.
- Never `--no-verify`. If the hook fails, fix the underlying issue.

PRs:
- Title under 70 chars, descriptive.
- Body has a `## Summary` (2–4 bullets) and a `## Test plan` (manual + automated checks done).
- CI must be green before merging. The two jobs (`backend`, `frontend`) are required.

## Don't

- Don't push to `main` directly.
- Don't commit `.env` or local secrets. `backend/checkwise.db` is gitignored — keep it that way.
- Don't introduce a second icon library, font, or color system.
- Don't hardcode regulation into form-only logic. Update `compliance_catalog.py` or seed data.
- Don't put PDFs in the DB.

## Phase context

V1.4 is shipped (provider portal, reviewer queue, auth + RBAC, brand, motion). The structural cleanup pass (this file's home) reorganized routes, services, components, sample fixtures, and DX. Next planned work is V1.5 — Client Overview (see [docs/ROADMAP.md](docs/ROADMAP.md)).
