---
description: Legacy CheckWise-local full visual redesign guidance. Do not activate for new visual direction unless the user explicitly asks to inspect prior CheckWise redesign doctrine; prefer external design tools and upstream design skills.
---

# CheckWise Visual Redesign Skill

Legacy note: this skill preserves prior redesign doctrine. For new landing page
and visual redesign direction, use external design tools and upstream design
skills, with CheckWise docs as product, token, workflow, and compliance
constraints.

Historical guidance follows. Do not use this as the default full visual
redesign plan.

This skill is not for backend architecture phases. It is not for generic UI polish. It exists to make the eventual redesign distinctive, product-specific, and grounded in CheckWise's real compliance state.

For new interaction craft, motion, and tactile product details, prefer Motion,
external design tools, and upstream `/impeccable`.

## Required Sources

Read these before proposing or implementing any redesign:

- `docs/design-system/VISUAL_REDESIGN_DOCTRINE.md`
- `docs/design-system/FRONTEND_REDESIGN_READINESS.md`
- `docs/design-system/ASSET_MANIFEST.md`
- `docs/design-system/claude-design-v0.1/AUDIT.md`
- `docs/DESIGN_SYSTEM.md`
- `docs/WORKFLOW_STATE_MACHINE.md`
- `docs/EVIDENCE_SLOTS.md` if present
- `frontend/app/globals.css`
- `frontend/tailwind.config.ts`
- `frontend/components/ui/`
- `frontend/components/checkwise/`

If `docs/EVIDENCE_SLOTS.md` does not exist yet, do not invent evidence-slot behavior. State that the visual redesign is blocked until that architecture layer is documented.

## Product Standard

CheckWise must not look like a generic SaaS dashboard.

It should feel like:

- a guided REPSE compliance cockpit,
- a live evidence-slot state map,
- an auditable document timeline,
- and a precise legal-tech operations console.

Every screen must answer at least one of:

- What obligation exists?
- What is missing?
- What is risky?
- What is current?
- What was replaced?
- Who owns the next action?
- What should happen next?

## Non-Negotiables

- Do not paste static HTML.
- Do not use screenshots as runtime UI.
- Do not build fake dashboards.
- Do not add decorative charts.
- Do not create a parallel component library.
- Do not bypass existing tokens.
- Do not invent backend states.
- Do not redesign around mock data when backend read models exist.
- Do not hide audit/replacement lineage if the architecture exposes it.

## Creative Permission

When architecture readiness is confirmed, you are free to substantially change the frontend experience.

Allowed:

- new layouts,
- new routes,
- new navigation,
- new task-specific pages,
- new reusable product components,
- richer animation,
- split flows,
- focused resolution rooms,
- compliance maps,
- evidence-slot matrices,
- and more visual density where the work is operational.

Do not preserve the current page structure just because it exists. Preserve domain contracts, auth/session behavior, backend truth, accessibility, and token discipline.

Every bold visual decision must have a product reason: faster triage, clearer risk, better traceability, stronger next action, or more trustworthy review.

## Visual Direction

Use these as product-specific design anchors:

- Evidence slot grid over generic KPI cards.
- Next-action rail over passive summaries.
- Submission timeline over hidden audit data.
- Replacement lineage over isolated upload attempts.
- Review decision panels over generic forms.
- Report readiness over decorative progress charts.
- Compliance maps over passive dashboard summaries.
- Resolution rooms over generic re-upload forms.
- Audit rails over hidden history.

## Token Rules

Use tokens from `frontend/app/globals.css`.

- Navy: structure, authority, navigation, primary action.
- Teal: intelligence, extraction, confidence, "Wise" moments only.
- Status colors: compliance meaning only.
- Document states: use `--doc-*`.
- Confidence states: use `--confidence-*`.
- Surfaces: use `--surface-*`.
- Text: use `--text-*`.
- Shadows and radii: use `--shadow-*` and `--radius-*`.

If a needed token does not exist, propose the smallest token addition before using a raw color.

## Required Redesign Method

For each screen:

1. Identify the backend truth powering the screen.
2. Identify the user's decision or next action.
3. Identify the evidence slot, workflow, or timeline objects shown.
4. Decide whether the existing route/layout is strong enough or whether a new route/split layout is justified.
5. Choose existing primitives before creating new components.
6. Create new product-specific components when they clarify evidence slots, timelines, risk, or review decisions.
7. Design the dominant visual around obligation state.
8. Add animation only where it communicates real state change.
9. Verify loading, empty, error, unauthorized, and success states.
10. Verify mobile, tablet, and desktop.

## Output When Planning

Return:

- Architecture readiness check.
- Screen-by-screen visual thesis.
- Component reuse map.
- New product-specific components needed.
- Token additions needed, if any.
- Asset usage plan.
- Proposed route/layout changes.
- Proposed animation language.
- Emil Kowalski-inspired interaction craft opportunities.
- Implementation phases.
- Explicit non-goals.

## Output When Implementing

Return:

- Files changed.
- Screens redesigned.
- Backend data powering each screen.
- Components created or reused.
- Token changes.
- Accessibility and responsive checks.
- Verification commands.
- Remaining visual debt.

## Failure Conditions

Reject or revise the work if:

- the screen could belong to any SaaS product,
- a card does not expose risk, owner, state, due date, or next action,
- a chart does not change a user decision,
- a status color is used decoratively,
- screenshots are pasted into the UI,
- replacement lineage is invisible where relevant,
- evidence slot state is hidden behind generic labels,
- or visual impact comes from decoration instead of product truth.
