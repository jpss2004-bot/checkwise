#!/usr/bin/env bash
set -euo pipefail

echo "== Installing CheckWise Claude Code skills =="

if [ ! -d ".git" ]; then
  echo "ERROR: Run this from the root of the CheckWise repository."
  echo "Example:"
  echo "cd /Users/josepablosamano/Desktop/Personal/legalshelf/checkwise/CheckWise"
  exit 1
fi

mkdir -p .claude/skills
mkdir -p .claude/agents
mkdir -p docs/claude

create_skill() {
  local name="$1"
  local description="$2"
  local body="$3"

  mkdir -p ".claude/skills/$name"
  cat > ".claude/skills/$name/SKILL.md" <<EOF
---
description: $description
---

$body
EOF
}

create_agent() {
  local name="$1"
  local description="$2"
  local body="$3"

  cat > ".claude/agents/$name.md" <<EOF
---
name: $name
description: $description
tools: Read, Grep, Glob, Bash, Edit, Write
---

$body
EOF
}

create_skill "checkwise-audit" "Deeply audits the current CheckWise repository before changes. Use before planning any patch, cleanup, redesign, demo, or release." '# CheckWise Audit Skill

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

CheckWise is a REPSE/document compliance platform. Do not treat it as a generic upload app. Preserve the JotForm/Sheets bridge while moving toward a canonical PostgreSQL model.'

create_skill "checkwise-architecture" "Plans CheckWise architecture, canonical data model, backend, migration strategy, REPSE workflow and source-of-truth decisions." '# CheckWise Architecture Skill

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
- Never allow automatic legal/fiscal approval without human review.'

create_skill "checkwise-ui-designer" "Legacy CheckWise-local UI design guidance. Do not activate for new visual direction unless the user explicitly asks for the old CheckWise-local design standard; prefer external design tools and upstream design skills." '# CheckWise UI Designer Skill

Legacy note: use this only to understand prior CheckWise-local UI assumptions.
For new visual design, landing page, motion, and premium interface direction,
prefer external design tools and upstream design skills. Keep CheckWise system
docs as product constraints.

Historical guidance follows. Do not use this as the default skill for landing
pages, new visual direction, or premium frontend polish.

## Design target

CheckWise should look like a premium legal-tech compliance platform.

It should feel:

- Executive.
- Calm.
- Precise.
- Trustworthy.
- Traceable.
- Professional.
- Not generic SaaS.
- Not student-project UI.

## Audit criteria

Evaluate:

- Visual hierarchy.
- Typography.
- Spacing.
- Contrast.
- Empty states.
- Component consistency.
- Dashboard usefulness.
- Form clarity.
- Accessibility.
- Responsiveness.
- Data visualization usefulness.
- Whether the UI explains risk and next action.

## Design rule

Every dashboard section should answer at least one of:

- What is missing?
- What is risky?
- Who owns it?
- What is due?
- What changed?
- What is the next action?

## Avoid

- Decorative charts.
- Fake metrics.
- Random gradients.
- Overcrowded cards.
- Low-contrast gray UI.
- Generic SaaS templates.
- Useless animations.'

create_skill "checkwise-frontend" "Improves CheckWise frontend code quality, Next.js structure, TypeScript safety, reusable components, forms and client-side UX." '# CheckWise Frontend Skill

Use this skill for Next.js, TypeScript, Tailwind, shadcn-style components, forms, dashboards and frontend build quality.

## Required workflow

1. Inspect current frontend structure.
2. Identify routes, components, API helpers, types and styling conventions.
3. Avoid renaming routes or contracts unless necessary.
4. Prefer typed interfaces and reusable components.
5. Preserve existing working flows.
6. Run lint/typecheck/build if available.

## Frontend principles

- Make state clear.
- Make errors useful.
- Make loading states professional.
- Make forms guided and forgiving.
- Keep supplier/client/admin mental models separate.
- Use domain language consistently: client, vendor, period, requirement, submission, validation, document, report.

## Output after changes

Always summarize:

- Files changed.
- UX improved.
- Type/build verification.
- Remaining frontend risk.'

create_skill "checkwise-backend" "Improves CheckWise FastAPI backend, API contracts, services, validation rules, storage handling and tests." '# CheckWise Backend Skill

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
- Remaining backend risk.'

create_skill "checkwise-database" "Handles PostgreSQL, SQLAlchemy, Alembic, canonical schema, migrations, seed data and data-integrity decisions for CheckWise." '# CheckWise Database Skill

Use this skill for SQLAlchemy models, Alembic migrations, seed/catalog data and database readiness.

## Canonical database rule

PostgreSQL should govern:

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

## Required process

1. Inspect existing models.
2. Inspect Alembic migrations.
3. Identify current database health.
4. Identify if the change needs migration.
5. Check relationships and constraints.
6. Keep document state separate from file metadata.

## Data modeling rules

- Avoid one-column-per-document-per-month.
- Use normalized requirement and period entities.
- Use stable IDs, not manual names.
- Use RFC and vendor_id to reduce supplier duplicates.
- Keep audit_log append-only.
- Store files outside DB and metadata inside DB.
- Version rules and requirements.

## Verification

Prefer:

- alembic current
- alembic history
- alembic upgrade head
- pytest for model/service behavior'

create_skill "checkwise-qa-release" "Runs release-readiness, regression, demo readiness and verification checks for CheckWise before commits, demos or deployments." '# CheckWise QA Release Skill

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
- Exact next action.'

create_skill "checkwise-security" "Audits CheckWise for local security, secret exposure, permission issues, tenant isolation, risky commands, dependency concerns and data privacy." '# CheckWise Security Skill

Use this for security, privacy, local configuration and risky operations.

## CheckWise security priorities

- Protect client/supplier documents.
- Protect secrets.
- Prevent data leakage between clients.
- Preserve auditability.
- Avoid automatic legal/fiscal approvals.
- Avoid accidental GitHub pushes or secret commits.

## Audit items

Review:

- .env handling.
- Git ignored files.
- Secret-like files.
- Dependency advisories.
- Upload validation.
- Tenant isolation assumptions.
- RBAC assumptions.
- Signed URL/storage assumptions.
- Audit log coverage.
- Destructive scripts.
- Git commands.

## Rules

Never print secrets.
Never read .env unless explicitly authorized.
Never approve sensitive legal/fiscal documents automatically.
Never recommend bypassing 2FA/RBAC/audit controls.'

create_skill "checkwise-dependency-audit" "Audits frontend/backend dependencies, npm advisories, Python packages, lockfiles and safe upgrade paths." '# CheckWise Dependency Audit Skill

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
- Remaining deployment risk.'

create_skill "checkwise-demo" "Prepares CheckWise for a clean 5-minute demo with screenshots, sample report, traceability story, UX polish and local run instructions." '# CheckWise Demo Skill

Use this when preparing a demo, presentation, PDF sample, script or walkthrough.

## Demo goal

Show CheckWise as a traceable REPSE compliance platform, not a generic document uploader.

## Required demo story

The 5-minute demo should show:

1. Problem: recurring supplier compliance is fragmented.
2. Current bridge: JotForm/Sheets/human review works but is fragile.
3. CheckWise V1: source of truth, checklist, status, evidence and audit trail.
4. Validation: objective prechecks plus human legal review.
5. Report: executive status with missing docs, responsible party, deadline and next action.

## Demo assets

Prepare:

- Clean local run instructions.
- Test supplier/vendor scenario.
- Sample documents or placeholders.
- Dashboard walkthrough.
- Report walkthrough.
- Known limitations.
- Next roadmap.

## Design standard

The demo must feel professional, legal-tech, executive and credible.'

create_skill "checkwise-report-designer" "Designs executive reports, PDF/DOCX report structures, visual hierarchy, traceability summaries and client-facing compliance narratives." '# CheckWise Report Designer Skill

Use this for monthly reports, PDF/DOCX design, client-facing summaries and executive compliance storytelling.

## Report purpose

A CheckWise report must explain:

- Compliance status.
- Missing documents.
- Risk level.
- Responsible party.
- Deadline.
- Evidence.
- Next action.
- Auditability.

## Required sections

A strong report includes:

1. Executive summary.
2. Supplier compliance overview.
3. Period and institution filters/context.
4. Critical missing documents.
5. Rejected/expired documents.
6. Validation notes.
7. Evidence/audit trail.
8. Actions required.
9. Appendix with document list.

## Visual rules

- Use clear headings.
- Use executive cards.
- Use semantic status labels.
- Avoid decorative graphics.
- Prefer tables and timelines when useful.
- Every visual must support a decision.'

create_skill "checkwise-git-safe" "Safely reviews git status, diffs, commit readiness, commit message suggestions and push safety for CheckWise." '# CheckWise Git Safe Skill

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

Do not run git push without explicit user approval.'

create_agent "checkwise-platform-architect" "Use for architecture, data model, migrations, backend strategy, source-of-truth decisions and REPSE workflow." 'You are the CheckWise platform architect.

You specialize in FastAPI, PostgreSQL, SQLAlchemy, Alembic, document compliance workflows, REPSE operational modeling, source-of-truth architecture and auditability.

Always protect:
- canonical PostgreSQL model
- normalized entities
- audit log
- human-in-the-loop validation
- bridge-first migration from JotForm/Sheets

Never recommend automatic legal/fiscal approval by AI.'

create_agent "checkwise-product-designer" "Use for UX, UI, frontend polish, dashboard design, report design, visual hierarchy and premium legal-tech product quality." 'You are the CheckWise senior product designer.

You specialize in enterprise SaaS, legal-tech, compliance dashboards, executive report UX, accessible UI, visual hierarchy and frontend product quality.

Your job is to make CheckWise feel credible, calm, professional, traceable and demo-ready.

Every recommendation must improve clarity, trust, actionability or compliance confidence.'

create_agent "checkwise-release-auditor" "Use before commits, demos or deployments to check build, tests, risks, UX, security and release readiness." 'You are the CheckWise release auditor.

You specialize in QA, regression risk, demo readiness, build verification, dependency hygiene, security posture and Git safety.

Always report:
- blockers
- demo risks
- verification commands
- exact changed files
- next safest action.'

cat > docs/claude/SKILLS_USAGE.md <<'EOF'
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
EOF

echo ""
echo "== Verification =="
find .claude/skills -maxdepth 2 -name SKILL.md | sort
echo ""
find .claude/agents -maxdepth 1 -name "*.md" | sort
echo ""
python3 - <<'PY'
from pathlib import Path
skills = sorted(Path(".claude/skills").glob("*/SKILL.md"))
agents = sorted(Path(".claude/agents").glob("*.md"))
print(f"OK: {len(skills)} skills installed")
print(f"OK: {len(agents)} agents installed")
missing = [p for p in skills if not p.read_text().strip().startswith("---")]
if missing:
    print("WARNING: Some skills may be missing frontmatter:")
    for p in missing:
        print(" -", p)
else:
    print("OK: all skills have frontmatter")
PY

echo ""
echo "Done."
echo ""
echo "Next:"
echo "1. Restart Claude Code Desktop or open a new Claude Code session from this repo."
echo "2. Type / and check if these skills appear."
echo "3. Try: /checkwise-audit"
