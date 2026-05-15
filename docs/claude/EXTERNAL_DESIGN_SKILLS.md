# External Downloadable Design Skills

Last verified: 2026-05-15

These are real downloaded skill packages installed into `.agents/skills/`.
They replace the previous project-local adaptations named `/taste` and
`/impeccable-ui`, which have been removed.

## Registering as Project Skills

Claude Code only auto-discovers skills under `.claude/skills/<name>/SKILL.md`.
The Taste/Impeccable upstream packages install into `.agents/skills/<name>/`,
which is **not** scanned. Without a bridging step the skills exist on disk
but cannot be invoked as `/<name>` — agents have to read each `SKILL.md`
manually.

Run [`scripts/register-design-skills.sh`](../../scripts/register-design-skills.sh)
once after the upstream install to symlink the recommended subset into
`.claude/skills/`. The script is idempotent and refuses to overwrite real
files at the destination.

Run order on a fresh checkout:

1. `./install_checkwise_claude_skills.sh` — installs the CheckWise-prefixed
   project skills.
2. (your Taste/Impeccable installer of choice) — populates `.agents/skills/`.
3. `./scripts/register-design-skills.sh` — bridges the recommended subset
   into `.claude/skills/` so Claude Code surfaces them.

The recommended subset is `gpt-taste`, `design-taste-frontend`,
`high-end-visual-design`, `redesign-existing-projects`, and `impeccable`.
The banned local adaptations (`/taste`, `/impeccable-ui`) are deliberately
excluded.

## Impeccable

- Skill command: `/impeccable`
- Upstream package: `pbakaus/impeccable`
- Installed path: `.agents/skills/impeccable/`
- Runtime command verified: `npx impeccable --help`
- Main capability: frontend design, critique, polish, accessibility,
  responsive behavior, motion, tokens, and live visual iteration.

Important setup:

- `PRODUCT.md` now exists at the repo root for product context.
- `DESIGN.md` now exists at the repo root for visual context.
- `/impeccable` should read those before design work.

## Taste Package

- Upstream package: `Leonxlnx/taste-skill`
- Installed path: `.agents/skills/`
- Installed skills:
  - `/brandkit`
  - `/industrial-brutalist-ui`
  - `/gpt-taste`
  - `/image-to-code`
  - `/imagegen-frontend-mobile`
  - `/imagegen-frontend-web`
  - `/minimalist-ui`
  - `/full-output-enforcement`
  - `/redesign-existing-projects`
  - `/high-end-visual-design`
  - `/stitch-design-taste`
  - `/design-taste-frontend`

Recommended CheckWise redesign subset:

1. `/gpt-taste`
2. `/design-taste-frontend`
3. `/high-end-visual-design`
4. `/redesign-existing-projects`

## Provenance Note

The installed files are upstream package downloads, not CheckWise-specific
rewrites. Their repository/package provenance is verifiable from the install
commands and local package contents. This does not verify the personal identity
of the authors beyond the public upstream repository names.
