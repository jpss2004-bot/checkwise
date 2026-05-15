---
description: Handles PostgreSQL, SQLAlchemy, Alembic, canonical schema, migrations, seed data and data-integrity decisions for CheckWise.
---

# CheckWise Database Skill

Use this skill for SQLAlchemy models, Alembic migrations, seed/catalog data and database readiness.

## Canonical database rule

PostgreSQL should govern:

- clients
- vendors
- periods
- requirements
- submissions
- validations
- documents
- notifications
- reports
- audit_log

## Required process

1. Inspect existing models.
2. Inspect Alembic migrations.
3. Identify current database health.
4. Identify if the change needs migration.
5. Check relationships and constraints.
6. Keep document state separate from file metadata.

## Data modeling rules

- Avoid one-column-per-document-per-month.
- Use normalized requirement and period entities.
- Use stable IDs, not manual names.
- Use RFC and vendor_id to reduce supplier duplicates.
- Keep audit_log append-only.
- Store files outside DB and metadata inside DB.
- Version rules and requirements.

## Verification

Prefer:

- alembic current
- alembic history
- alembic upgrade head
- pytest for model/service behavior
