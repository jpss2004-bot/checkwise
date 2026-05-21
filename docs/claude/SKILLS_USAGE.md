# CheckWise Claude Skills Usage

Project-specific CheckWise skills live in `.claude/skills/`.

External downloadable design skills live in `.agents/skills/` and are bridged
into `.claude/skills/` by `scripts/register-design-skills.sh`.

Claude Code can invoke skills directly by slash command or automatically when
the task matches the skill description.

## Current policy

Use CheckWise docs as product truth, not as a premade visual recipe.

For design direction, landing page work, visual polish, motion, interaction
craft, and high-end UI judgment, prefer external design tooling and the real
downloaded upstream skills.

For implementation, architecture, QA, security, backend, database, reports,
demo readiness, and git safety, keep using the CheckWise project skills.

## Product truth sources

Read these before changing major frontend surfaces:

- `PRODUCT.md`
- `DESIGN.md`
- `docs/DESIGN_SYSTEM.md`
- `docs/design-system/VISUAL_DIRECTION_2_X.md`
- `docs/design-system/VISUAL_REDESIGN_DOCTRINE.md`
- `docs/design-system/ASSET_MANIFEST.md`
- `frontend/app/globals.css`
- `frontend/tailwind.config.ts`
- relevant route, component, API, and mock-data files

These files constrain domain language, trust model, REPSE workflow, brand
tokens, accessibility, and implementation boundaries. They should not force a
stale hero, placeholder imagery, or the old CheckWise-local design taste.

## Installed upstream design skills

The real upstream skills currently installed and bridged are:

- `/impeccable`
  - Source: `pbakaus/impeccable`
  - Local package: `.agents/skills/impeccable/`
- Taste package from `Leonxlnx/taste-skill`
  - `/gpt-taste`
  - `/design-taste-frontend`
  - `/high-end-visual-design`
  - `/redesign-existing-projects`

Do not document or request unavailable skills as installed. At the time of
this audit, `image-to-code`, `imagegen-frontend-web`, and
`imagegen-frontend-mobile` were not present in `.agents/skills/`.

## External tools to add for the next design pass

These are intended tools for the landing page and frontend redesign direction,
but they are not currently configured in the repo:

- UI UX Pro Max
- 21st.dev / Magic MCP
- Motion for React, installed as the `motion` package and imported from
  `motion/react`

Once configured, use them as the main design-generation, component-discovery,
and animation stack. Keep CheckWise docs as constraints around product,
compliance, brand, copy, and engineering behavior.

## Active CheckWise implementation skills

Use these for non-visual or implementation-bound work:

- `/checkwise-audit`
- `/checkwise-architecture`
- `/checkwise-frontend`
- `/checkwise-backend`
- `/checkwise-database`
- `/checkwise-qa-release`
- `/checkwise-security`
- `/checkwise-dependency-audit`
- `/checkwise-demo`
- `/checkwise-report-designer`
- `/checkwise-git-safe`

## Legacy local design skills

Do not use these as visual direction for new design work unless the user
explicitly asks to inspect or preserve the old CheckWise-local design system:

- `/taste`
- `/impeccable-ui`
- `/hero-redesign`
- `/emil-kowalski-design`
- `/checkwise-ui-designer`
- `/checkwise-visual-redesign`
- `/checkwise-redesign-prep`

These are retained for historical context and for understanding prior design
decisions. They should not drive the next landing page hero, screenshot
strategy, motion approach, or premium UI direction.

## Recommended workflow

For normal product/engineering work:

1. `/checkwise-audit`
2. `/checkwise-architecture` if contracts, data flow, or domain model are
   affected
3. `/checkwise-frontend` or the relevant backend/database/report skill
4. Implement the patch
5. `/checkwise-qa-release`
6. `/checkwise-git-safe`

For landing page or visual redesign work:

1. Audit the current route, assets, screenshots, tokens, and product docs.
2. Use external design tooling and upstream design skills for visual direction.
3. Use Motion only for purposeful product motion, not decorative noise.
4. Implement with Next.js, React, Tailwind, existing components, and real
   product screenshots/assets.
5. Verify responsive layout, copy, animation behavior, accessibility, and
   build health.

## Best first prompt after installing

Read `CLAUDE.md`, `PRODUCT.md`, `DESIGN.md`, and
`docs/claude/SKILLS_USAGE.md`.

Then audit the repo before editing.

Return:

- current project map
- installed skills and missing tools
- what works
- what is risky
- best next 5 patches
- exact files to inspect before patch 1
