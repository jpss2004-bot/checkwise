---
description: Runs release-readiness, regression, demo readiness and verification checks for CheckWise before commits, demos or deployments.
---

# CheckWise QA Release Skill

Use this before commits, demos, deployments or after any meaningful patch.

## Required checks

Inspect or run the strongest available checks:

- git status
- frontend lint
- frontend typecheck
- frontend build
- backend ruff
- backend pytest
- Alembic migration status
- health endpoint
- catalogs endpoint
- form submission flow
- file upload/storage path

## Risk categories

Report:

- P0 blockers.
- P1 demo risks.
- P2 polish issues.
- Security/privacy concerns.
- Data integrity risks.
- UX confusion risks.

## Output format

Return:

- Checks run.
- Pass/fail results.
- Files inspected.
- Release confidence.
- Remaining risks.
- Exact next action.
