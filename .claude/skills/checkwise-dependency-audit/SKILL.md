---
description: Audits frontend/backend dependencies, npm advisories, Python packages, lockfiles and safe upgrade paths.
---

# CheckWise Dependency Audit Skill

Use this skill when checking npm audit, dependency updates, package-lock changes, security advisories, or Python package hygiene.

## Required process

1. Inspect package files and lockfiles.
2. Identify frontend/backend package managers.
3. Run safe audit commands if allowed.
4. Prefer minimal version bumps.
5. Avoid broad upgrades unless necessary.
6. Verify build after dependency changes.

## Commands to consider

Frontend:

- npm audit
- npm audit fix
- npm install package@version --save-dev
- npm run lint
- npm run typecheck
- npm run build

Backend:

- pip list
- pip-audit if installed
- ruff check .
- pytest

## Output

Return:

- Vulnerability/advisory summary.
- Files changed.
- Why the upgrade is safe.
- Verification commands and results.
- Remaining deployment risk.
