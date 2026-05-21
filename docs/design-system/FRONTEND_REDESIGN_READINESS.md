# Frontend Redesign Readiness Packet

Last updated: 2026-05-15

## Purpose

This packet prepares CheckWise for a future full frontend redesign without starting that redesign yet. It tells Claude Code where the source material lives, which project-local skills to use, and how to sequence the work so the redesign becomes a reusable Next.js/React/Tailwind implementation instead of pasted static HTML.

## Current Readiness State

Ready:

- Claude Design export is preserved under `docs/design-system/claude-design-v0.1/`.
- Asset manifest exists at `docs/design-system/ASSET_MANIFEST.md`.
- Visual doctrine exists at `docs/design-system/VISUAL_REDESIGN_DOCTRINE.md`.
- Package audit exists at `docs/design-system/claude-design-v0.1/AUDIT.md`.
- Phase 1 token hardening has started in the real frontend.
- Existing UI primitives live in `apps/web/components/ui/`.
- Existing CheckWise product patterns live in `apps/web/components/checkwise/` and `apps/web/app/portal/`.

Not ready:

- The full v0.1 editable Claude Design source is incomplete. The HTML references CSS/JSX files that were not included in the export.
- The screenshots are references, not implementation assets.
- The redesign should not begin until primitives and pattern inventory are audited screen-by-screen.

## Source Of Truth

Read in this order before any redesign work:

1. `docs/design-system/claude-design-v0.1/AUDIT.md`
2. `docs/design-system/ASSET_MANIFEST.md`
3. `docs/design-system/VISUAL_REDESIGN_DOCTRINE.md`
4. `docs/DESIGN_SYSTEM.md`
5. `docs/design-system/claude-design-v0.1/uploads/DESIGN_SYSTEM.md`
6. `apps/web/app/globals.css`
7. `frontend/tailwind.config.ts`
8. `apps/web/components/ui/`
9. `apps/web/components/checkwise/`
10. `apps/web/app/portal/`

## Design Intent

CheckWise is a REPSE/document compliance SaaS. It should feel like a guided compliance assistant, not a generic database.

The redesign must communicate:

- What is missing.
- What is risky.
- Who owns the next action.
- What is due.
- What changed.
- What CheckWise recommends next.

The UI voice is:

- Executive.
- Calm.
- Precise.
- Traceable.
- Professional.
- Guided.

Avoid:

- Decorative dashboards.
- Generic SaaS cards without decision value.
- Copying the static Claude HTML into the app.
- Changing working flows without preserving backend truth and user outcomes.
- New visual systems that bypass `apps/web/app/globals.css`.

Creative permission after architecture is ready:

- The redesign may change layouts, add routes, split pages, add new visual components, and introduce purposeful animation.
- The redesign should not be limited to polishing current screens.
- New routes are welcome when they clarify evidence slots, replacement lineage, review decisions, reports, or next actions.
- Existing backend/API/session contracts must remain the source of truth.

## Claude Skill Stack

Use this sequence for a future full redesign under the current external-design policy:

1. `/checkwise-audit`
   - Confirm actual repo state before edits.
2. External design tools
   - Use UI UX Pro Max, 21st.dev / Magic MCP, and Motion once configured.
3. `/gpt-taste`
   - Apply the real downloaded Taste skill's high-variance design guardrails.
4. `/design-taste-frontend`
   - Translate Taste direction into implementable React/Tailwind decisions.
5. `/high-end-visual-design`
   - Push visual hierarchy, motion, spacing, and materiality above generic SaaS.
6. `/redesign-existing-projects`
   - Upgrade the existing app without breaking functionality or inventing a parallel system.
7. `/checkwise-frontend`
   - Implement reusable Next.js/React/Tailwind components.
8. `/impeccable`
   - Polish state coverage, responsive behavior, accessibility, and demo-day details.
9. `/checkwise-qa-release`
   - Verify typecheck/lint/build and smoke routes.
10. `/checkwise-git-safe`
   - Commit safely only after scope is clear.

## Recommended Redesign Phases

Phase 0: Source consolidation.

- Keep the Claude Design package in `docs/design-system/claude-design-v0.1/`.
- Recover missing v0.1 CSS/JSX files if possible.
- Keep `ASSET_MANIFEST.md` current.

Phase 1: Token hardening.

- Continue using `apps/web/app/globals.css` and `frontend/tailwind.config.ts` as canonical runtime token files.
- Preserve compatibility aliases until all components migrate.
- Do not change page layouts in this phase.

Phase 2: Primitive alignment.

- Update existing primitives instead of creating parallel components.
- Primary files:
  - `apps/web/components/ui/button.tsx`
  - `apps/web/components/ui/badge.tsx`
  - `apps/web/components/ui/alert.tsx`
  - `apps/web/components/ui/card.tsx`
  - `apps/web/components/ui/field.tsx`
  - `apps/web/components/ui/input.tsx`
  - `apps/web/components/ui/progress.tsx`
  - `apps/web/components/ui/select.tsx`
  - `apps/web/components/ui/textarea.tsx`

Phase 3: Pattern alignment.

- Map Claude Design patterns into existing CheckWise surfaces.
- Add new surfaces when the architecture-backed workflow deserves a stronger task-specific route.
- Primary surfaces:
  - `apps/web/app/page.tsx`
  - `apps/web/app/login/page.tsx`
  - `apps/web/app/activate/page.tsx`
  - `apps/web/app/portal/entra-a-tu-espacio/page.tsx`
  - `apps/web/app/portal/onboarding/page.tsx`
  - `apps/web/app/portal/dashboard/page.tsx`
  - `apps/web/app/portal/calendar/page.tsx`
  - `apps/web/app/portal/reports/page.tsx`
  - `apps/web/app/portal/upload/page.tsx`
  - `apps/web/app/admin/reviewer/page.tsx`

Possible new surfaces after architecture read models exist:

- `/portal/command-center`
- `/portal/obligations`
- `/portal/obligations/[slot_id]`
- `/portal/resolution/[submission_id]`
- `/portal/report-readiness`
- `/admin/reviewer/queue`
- `/admin/reviewer/submissions/[submission_id]/workbench`

Phase 4: Visual QA.

- Run typecheck, lint, build.
- Smoke desktop and mobile routes.
- Verify loading, empty, error, success, and unauthorized states.
- Confirm no page uses screenshots/static HTML as product UI.

## First Full Redesign Prompt

Use this only after Phase 1 token hardening, design-package setup, and the architecture phases for workflow/evidence slots are complete:

```text
Use /checkwise-audit, external design tools, /gpt-taste, /design-taste-frontend, /high-end-visual-design, /redesign-existing-projects, /checkwise-frontend, and /impeccable.

Goal: plan the full CheckWise frontend redesign, but do not edit code yet.

Read:
- docs/design-system/VISUAL_REDESIGN_DOCTRINE.md
- docs/design-system/FRONTEND_REDESIGN_READINESS.md
- docs/design-system/ASSET_MANIFEST.md
- docs/design-system/claude-design-v0.1/AUDIT.md
- docs/DESIGN_SYSTEM.md
- docs/WORKFLOW_STATE_MACHINE.md
- docs/EVIDENCE_SLOTS.md
- apps/web/app/globals.css
- frontend/tailwind.config.ts
- apps/web/components/ui/
- apps/web/components/checkwise/
- apps/web/app/portal/

Return:
1. Current frontend surface inventory.
2. Component inventory and reuse map.
3. Token gaps still blocking redesign.
4. Asset usage plan.
5. Route-by-route redesign priority.
6. Exact implementation phases with file scopes.
7. What not to touch.
8. Visual thesis for the evidence-slot compliance cockpit.
9. Proposed new routes, layouts, and visual components.
10. Animation/motion plan tied to real state changes.
11. Emil Kowalski-inspired interaction craft opportunities.

Do not paste static HTML.
Do not implement yet.
Do not create a parallel component system.
```

## Implementation Guardrails

- Convert visual direction into reusable primitives and patterns.
- Keep CheckWise domain vocabulary in Spanish where user-facing.
- Use the existing API/session architecture.
- Preserve working portal/admin flows.
- Treat the Claude Design screenshots as references, not UI assets.
- Keep changes reviewable by phase.
