# CheckWise Agent Rules

## Product Context

CheckWise is a REPSE compliance platform for Mexico. Treat it as a recurring regulatory evidence system, not as a generic file uploader.

The current operation uses JotForm, Google Sheets, human/legal review, and Looker Studio. New work must preserve gradual migration paths while making PostgreSQL the future source of truth.

## Non-Negotiables

- Model regulation as versioned requirements, never as improvised spreadsheet columns.
- Keep documents outside the database. Store metadata, hash, status, storage key, relationships, validation output, and audit events in PostgreSQL.
- Every document/submission must be traceable to client, vendor, period, institution, requirement, status, validation, and audit history. Contract is required when applicable.
- Critical approvals require authorized human review. Automation may prevalidate objective signals only.
- Keep Google Sheets/JotForm as import/export bridges, not canonical domain models.
- Preserve existing source files and generated reports unless the user explicitly asks to change them.

## Architecture Preferences

- Frontend: Next.js, TypeScript, Tailwind CSS, shadcn/ui-style components.
- Backend: FastAPI, Pydantic, SQLAlchemy, Alembic, OpenAPI.
- Database: PostgreSQL.
- Storage: S3-compatible design, local filesystem only for development.
- Jobs: leave room for Redis + RQ/Celery workers.
- Auth: leave room for Auth0, Clerk, or Supabase Auth.

## Coding Guidelines

- Prefer small, typed modules with clear ownership.
- Keep domain terms in English for code identifiers and Spanish for user-facing copy where appropriate.
- Add migrations for schema changes.
- Add audit events for important state transitions.
- For native intake, record validation events and document inspection signals instead of hiding decisions in UI-only state.
- Avoid broad refactors unless they directly support the requested change.
- Do not hardcode regulation into form-only logic; update requirements/catalogs or seed data instead.

## Current Phase Definition

V1.4 is operational: provider portal, reviewer queue + decision workflow, real auth + RBAC, brand application, and motion polish are all shipped. Next planned work is V1.5 — Client Overview (read-only client_admin view across a vendor portfolio).

The structural-cleanup branch (`cleanup/structural-pass`) has reorganized routes, services, components, and sample fixtures. See `docs/ROADMAP.md` for the full phase log.
