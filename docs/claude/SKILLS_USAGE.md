# CheckWise Claude Skills Usage

Project-specific CheckWise skills live in `.claude/skills/`.

External downloadable design skills live in `.agents/skills/`. These are installed
from upstream packages and should be used instead of project-local adaptations.

Claude Code can invoke skills directly by slash command or automatically when the task matches the skill description.

## Core skills

- `/checkwise-audit`
- `/checkwise-redesign-prep`
- `/checkwise-architecture`
- `/checkwise-ui-designer`
- `/checkwise-visual-redesign`
- `/emil-kowalski-design`
- `/checkwise-frontend`
- `/checkwise-backend`
- `/checkwise-database`
- `/checkwise-qa-release`
- `/checkwise-security`
- `/checkwise-dependency-audit`
- `/checkwise-demo`
- `/checkwise-report-designer`
- `/checkwise-git-safe`

## External downloadable design skills

Installed real upstream skill packages:

- `/impeccable`
  - Source: `pbakaus/impeccable`
  - Local package: `.agents/skills/impeccable/`
  - Runtime command verified: `npx impeccable --help`
- Taste package from `Leonxlnx/taste-skill`
  - `/gpt-taste`
  - `/design-taste-frontend`
  - `/high-end-visual-design`
  - `/redesign-existing-projects`
  - `/image-to-code`
  - `/imagegen-frontend-web`
  - `/imagegen-frontend-mobile`
  - plus supporting style skills in `.agents/skills/`

Do not use `/taste` or `/impeccable-ui`; those were local adaptations and are
not the real downloadable packages.

## Recommended workflow

For most work:

1. `/checkwise-audit`
2. `/checkwise-architecture` or `/checkwise-ui-designer`
3. Implement the patch
4. `/checkwise-qa-release`
5. `/checkwise-git-safe`

## Frontend redesign workflow

For a full frontend redesign, start with preparation instead of code edits:

1. `/checkwise-redesign-prep`
2. `/checkwise-audit`
3. `/checkwise-ui-designer`
4. `/gpt-taste`
5. `/design-taste-frontend`
6. `/high-end-visual-design`
7. `/checkwise-visual-redesign`
8. `/emil-kowalski-design`
9. `/checkwise-frontend`
10. `/impeccable`
11. `/checkwise-qa-release`
12. `/checkwise-git-safe`

Primary redesign source files:

- `docs/design-system/FRONTEND_REDESIGN_READINESS.md`
- `docs/design-system/VISUAL_REDESIGN_DOCTRINE.md`
- `docs/design-system/ASSET_MANIFEST.md`
- `docs/design-system/claude-design-v0.1/AUDIT.md`
- `docs/DESIGN_SYSTEM.md`
- `frontend/app/globals.css`
- `frontend/tailwind.config.ts`

Do not paste Claude Design static HTML into the app. Convert the design direction into reusable Next.js/React/Tailwind primitives and CheckWise product patterns.

Use `/emil-kowalski-design` as the high-craft interaction pass for motion, microinteractions, tactile component behavior, and premium visual rhythm after architecture readiness is confirmed.

## Best first prompt after installing

Read CLAUDE.md and docs/claude/SKILLS_USAGE.md.

Then use the relevant CheckWise skills to audit the repo before editing.

Start with `/checkwise-audit`.

Do not change code yet. Return:
- current project map
- what works
- what is risky
- best next 5 patches
- exact files to inspect before patch 1
