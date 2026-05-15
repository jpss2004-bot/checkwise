---
description: Plans CheckWise architecture, canonical data model, backend, migration strategy, REPSE workflow and source-of-truth decisions.
---

# CheckWise Architecture Skill

Use this skill for backend, database, domain model, migrations, compliance workflow and architecture decisions.

## Core architecture principle

CheckWise must evolve from JotForm + Google Sheets + human review into a traceable compliance platform with PostgreSQL as the source of truth.

## Non-negotiable model

Protect these entities:

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

## Required reasoning

Before proposing code:

1. Identify which entities are affected.
2. Identify API contract impact.
3. Identify migration impact.
4. Identify frontend state impact.
5. Identify audit/security impact.
6. Identify whether the change belongs in temporary bridge logic or core domain logic.

## Rules

- Do not let Sheets become the permanent source of truth.
- Do not store files directly in PostgreSQL.
- Use file hashes to detect duplicates.
- Tie every upload to vendor_id, period_id, requirement_id and document/file metadata.
- Keep REPSE/legal rules versioned.
- Keep AI/OCR as objective prevalidation only.
- Never allow automatic legal/fiscal approval without human review.
