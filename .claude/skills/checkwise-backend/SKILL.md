---
description: Improves CheckWise FastAPI backend, API contracts, services, validation rules, storage handling and tests.
---

# CheckWise Backend Skill

Use this skill for FastAPI routes, schemas, services, validations, storage, tests and backend architecture.

## Required workflow

1. Inspect relevant routes, schemas, models, services and tests.
2. Identify current API contracts.
3. Avoid breaking frontend callers.
4. Keep domain logic testable.
5. Add or update tests for critical paths.
6. Run ruff and pytest when available.

## Backend principles

- Separate routes, schemas, services and persistence.
- Keep validation rules deterministic where possible.
- Keep AI/OCR as advisory/prevalidation only.
- Record validation outcomes with severity, rule, result and comment.
- Use structured errors.
- Keep uploads idempotent where possible using hash and domain identifiers.

## Output after changes

Always report:

- Files changed.
- API impact.
- Tests/checks run.
- Data/model impact.
- Remaining backend risk.
