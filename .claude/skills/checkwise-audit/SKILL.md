---
description: Deeply audits the current CheckWise repository before changes. Use before planning any patch, cleanup, redesign, demo, or release.
---

# CheckWise Audit Skill

Use this skill before editing CheckWise.

## Goal

Produce a grounded audit of the actual repository state.

## Required process

1. Inspect the repository tree.
2. Identify frontend, backend, database, scripts, docs, config, tests and generated files.
3. Identify what is already implemented.
4. Identify what is fragile, duplicated, outdated or risky.
5. Separate facts from assumptions.
6. Do not edit code unless explicitly asked.

## Output format

Return:

- Current project map.
- What works.
- What is incomplete.
- UX/design risks.
- Backend/API risks.
- Database/migration risks.
- Testing gaps.
- Demo-readiness gaps.
- Next 5 best patches.
- Exact files to inspect before patch 1.

## CheckWise rules

CheckWise is a REPSE/document compliance platform. Do not treat it as a generic upload app. Preserve the JotForm/Sheets bridge while moving toward a canonical PostgreSQL model.
