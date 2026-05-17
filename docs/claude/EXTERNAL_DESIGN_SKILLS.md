# External Downloadable Design Skills

Last verified: 2026-05-17

External design skill packages installed into `.agents/skills/` and bridged
into `.claude/skills/` as project skills.

## Three-layer skill system

CheckWise runs three layers of design skills side by side:

1. **CheckWise-prefixed project skills** — `.claude/skills/checkwise-*/`
   Built in-place by [`install_checkwise_claude_skills.sh`](../../install_checkwise_claude_skills.sh).
   Tracked in git. Cover architecture, backend, frontend, database, demo,
   QA, security, audit, redesign-prep, report-designer, ui-designer,
   visual-redesign, dependency-audit, and git-safe operations.

2. **CheckWise-local design overrides** — `.claude/skills/{impeccable-ui,taste,hero-redesign,emil-kowalski-design}/`
   Tracked in git. These are intentional **project-local overrides** of
   generic design skills, narrowed to CheckWise's compliance/legal-tech
   voice and the tokens in `frontend/app/globals.css`.

3. **Upstream design packages** — `.agents/skills/<name>/`
   Installed from external GitHub sources, untracked, reproducible from
   [`skills-lock.json`](../../skills-lock.json). A curated subset is
   symlinked into `.claude/skills/` by `scripts/register-design-skills.sh`
   so Claude Code can auto-discover them.

## Bridged subset (currently active)

The subset symlinked into `.claude/skills/` is:

- `gpt-taste`
- `design-taste-frontend`
- `high-end-visual-design`
- `redesign-existing-projects`
- `impeccable`

This list is the source of truth in two places:
[`scripts/register-design-skills.sh`](../../scripts/register-design-skills.sh)
(SKILLS array) and [`skills-lock.json`](../../skills-lock.json). Keep them
in sync — the lockfile only pins what is actually bridged.

Other upstream skills (`brandkit`, `industrial-brutalist-ui`,
`minimalist-ui`, `image-to-code`, `imagegen-frontend-{mobile,web}`,
`full-output-enforcement`, `stitch-design-taste`) were previously
installed but are **not currently registered**. They can be re-added by
appending to the SKILLS array and to `skills-lock.json`, then re-running
the install + register scripts.

## Run order on a fresh checkout

1. `./install_checkwise_claude_skills.sh` — generates the CheckWise-prefixed project skills.
2. (your Taste/Impeccable installer of choice) — populates `.agents/skills/` per `skills-lock.json`.
3. `./scripts/register-design-skills.sh` — bridges the recommended subset into `.claude/skills/`.

## Impeccable

- Skill command: `/impeccable`
- Upstream package: `pbakaus/impeccable`
- Installed path: `.agents/skills/impeccable/`
- Bridge: `.claude/skills/impeccable` → `../../.agents/skills/impeccable`
- Main capability: frontend design, critique, polish, accessibility,
  responsive behavior, motion, tokens, and live visual iteration.

The local override `/impeccable-ui` exists alongside it as a
CheckWise-narrowed variant. Use `/impeccable-ui` for CheckWise-bound
craftsmanship passes; reach for global `/impeccable` only when you
genuinely need the broader generic toolkit.

Important setup:

- `PRODUCT.md` exists at the repo root for product context.
- `DESIGN.md` exists at the repo root for visual context.
- Both `/impeccable` and `/impeccable-ui` should read those before design work.

## Taste

- Upstream package: `Leonxlnx/taste-skill` (specifically `skills/taste-skill/`)
- Skill command: `/design-taste-frontend`
- The local override `/taste` is CheckWise-narrowed and tuned to the
  compliance/legal-tech voice. Reach for the upstream `/design-taste-frontend`
  for cross-project taste judgments; use `/taste` when the question is
  specifically "is this CheckWise enough?"

## Provenance Note

`.agents/skills/` is the install output of upstream public packages.
Repository provenance is verifiable from `skills-lock.json` source URLs
and the local package contents. This does not certify the personal
identity of upstream authors beyond the public repository names.
