---
description: Safely reviews git status, diffs, commit readiness, commit message suggestions and push safety for CheckWise.
---

# CheckWise Git Safe Skill

Use this before commits or when reviewing changed files.

## Required workflow

1. Run or inspect git status.
2. Review git diff.
3. Identify accidental files.
4. Identify secrets or local-only files.
5. Identify generated files that should not be committed.
6. Suggest a precise commit message.
7. Do not push unless explicitly instructed.

## Commit message style

Use conventional commits:

- feat:
- fix:
- chore:
- docs:
- refactor:
- test:
- ci:
- design:

## Safety rules

Never commit:

- .env
- settings.local.json
- credentials
- secrets
- private data
- generated junk
- accidental logs

Do not run git push without explicit user approval.
