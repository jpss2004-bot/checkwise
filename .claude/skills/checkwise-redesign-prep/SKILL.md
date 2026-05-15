---
description: Prepares CheckWise for a full frontend redesign by consolidating design docs, assets, screenshots, tokens, existing components, and implementation phases before any UI code is changed.
---

# CheckWise Redesign Prep Skill

Use this skill before any full frontend redesign or large UI refactor.

The goal is preparation, not implementation. This skill should produce a grounded redesign plan that can later be executed by `checkwise-frontend`, `checkwise-ui-designer`, the real downloaded Taste skills (`gpt-taste`, `design-taste-frontend`, `high-end-visual-design`, `redesign-existing-projects`), and the real downloaded `impeccable` skill.

## Required Sources

Read these before making recommendations:

- `docs/design-system/FRONTEND_REDESIGN_READINESS.md`
- `docs/design-system/VISUAL_REDESIGN_DOCTRINE.md`
- `docs/design-system/ASSET_MANIFEST.md`
- `docs/design-system/claude-design-v0.1/AUDIT.md`
- `docs/DESIGN_SYSTEM.md`
- `frontend/app/globals.css`
- `frontend/tailwind.config.ts`
- `frontend/components/ui/`
- `frontend/components/checkwise/`
- `frontend/app/portal/`

Optional context:

- `docs/design-system/claude-design-v0.1/uploads/DESIGN_SYSTEM.md`
- `docs/ONBOARDING_V1.md`
- `docs/PROVIDER_PORTAL_FLOW.md`
- `docs/NATIVE_INTAKE_ARCHITECTURE.md`

## Product Frame

CheckWise is a REPSE/document compliance SaaS. It should feel like a guided compliance assistant, not a generic upload database.

Every redesigned surface must answer at least one of:

- What is missing?
- What is risky?
- Who owns it?
- What is due?
- What changed?
- What is the next action?

## Non-Negotiables

- Do not paste static HTML into the app.
- Do not use screenshots as product UI.
- Do not create a parallel component system.
- Do not bypass `frontend/app/globals.css` or `frontend/tailwind.config.ts`.
- Do not remove compatibility tokens until all consumers are migrated.
- Do not touch backend/API/session behavior unless the user explicitly asks.

## Creative Permission

After architecture readiness is confirmed, a future redesign may:

- change layouts,
- add routes,
- split complex flows,
- create new product-specific components,
- add purposeful animations,
- and rethink navigation.

The prep task should identify where this is desirable. Preserve backend contracts and user outcomes, not necessarily the current page shape.

## Prep Workflow

1. Verify the design package exists at `docs/design-system/claude-design-v0.1/`.
2. Confirm which Claude Design source files are present and missing.
3. Inventory brand/photo/screenshot assets from `ASSET_MANIFEST.md`.
4. Inventory current UI primitives in `frontend/components/ui/`.
5. Inventory current CheckWise patterns in `frontend/components/checkwise/`.
6. Inventory frontend routes in `frontend/app/`.
7. Identify token gaps, duplicate components, and inconsistent styling.
8. Produce a phase plan with small, reviewable file scopes.

## Required Output

Return:

- Source package status.
- Visual doctrine readiness.
- Asset usage plan.
- Current route inventory.
- Current primitive/component inventory.
- Token readiness.
- Redesign risks.
- Recommended phases.
- Proposed new routes and layout changes.
- Exact files to edit in Phase 1.
- Exact files not to touch.

## Phase Template

Use this phase structure unless the repo state clearly requires a safer split:

1. Token hardening.
2. Primitive alignment.
3. Provider portal shell and navigation.
4. Onboarding and access flow.
5. Dashboard, calendar, reports.
6. Upload/OCR/review flow.
7. Admin reviewer flow.
8. Visual QA and responsive pass.

## Completion Criteria

This skill is complete when another agent can start implementation without rediscovering:

- where the design source lives,
- which files are missing,
- which assets are canonical,
- which UI primitives already exist,
- which routes matter,
- and which phase should happen first.
