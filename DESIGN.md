---
name: CheckWise Design Context
description: Product design context for real downloadable design skills such as impeccable and Taste.
---

# CheckWise Design Context

CheckWise should look like a premium legal-tech compliance system: precise, calm, auditable, and unusually memorable. It should not look like a generic SaaS template.

## Visual Source Of Truth

Use these files before frontend redesign work:

- `docs/design-system/VISUAL_REDESIGN_DOCTRINE.md`
- `docs/design-system/FRONTEND_REDESIGN_READINESS.md`
- `docs/design-system/ASSET_MANIFEST.md`
- `docs/design-system/claude-design-v0.1/AUDIT.md`
- `docs/DESIGN_SYSTEM.md`
- `frontend/app/globals.css`
- `frontend/tailwind.config.ts`

## Runtime Tokens

The canonical runtime token files are:

- `frontend/app/globals.css`
- `frontend/tailwind.config.ts`

Do not create a parallel visual system. Do not paste Claude Design static HTML into the app. Convert visual direction into reusable Next.js/React/Tailwind primitives and CheckWise-specific patterns.

## Visual Signature

- Navy carries structure, authority, and navigation.
- Teal marks intelligence, extraction, confidence, and "Wise" moments.
- White and cool gray provide calm operational space.
- Status colors are reserved for compliance state.
- Documents, timelines, slot grids, review rails, and decision panels should replace decorative cards.
- Motion should clarify state changes, not decorate.

## Distinctive Product Surfaces

- Compliance Command Center
- Evidence Slot Grid
- Submission Timeline
- Guided Upload Resolver
- Reviewer Workbench
- Report Readiness Surface
- Compliance Map / Operations Canvas

## Craft Rules

- Reuse existing primitives in `frontend/components/ui/`.
- Extend CheckWise patterns in `frontend/components/checkwise/`.
- Prefer route-level experiences when a workflow deserves a focused surface.
- Preserve backend/session/API contracts.
- Show loading, empty, error, success, unauthorized, and replacement states.
- Keep UI dense enough for operations, but never chaotic.
- Avoid marketing hero composition inside product surfaces.

## Banned Patterns

- Static HTML as app UI
- Screenshots as app UI
- Fake metrics
- Generic 3-column card grids
- Random gradients or glows
- Low-contrast gray dashboards
- Unlabeled icon-only actions
- New colors outside the token system
- Animations that hide or delay required compliance information
