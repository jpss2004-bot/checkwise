---
description: Applies an Emil Kowalski-inspired interaction design craft pass to CheckWise: refined motion, precise spatial rhythm, tactile product details, premium interface composition, and memorable microinteractions grounded in backend truth and design tokens.
---

# Emil Kowalski Design Skill

Use this skill during the future CheckWise frontend redesign when the work needs exceptional interaction craft, motion taste, and premium product feel.

This skill is not a license to copy any designer's work. Use it as a high-level craft lens: crisp motion, elegant interaction states, strong spatial composition, and restrained visual drama.

## Required Sources

Read these before applying the skill:

- `docs/design-system/VISUAL_REDESIGN_DOCTRINE.md`
- `docs/design-system/FRONTEND_REDESIGN_READINESS.md`
- `docs/design-system/ASSET_MANIFEST.md`
- `docs/DESIGN_SYSTEM.md`
- `frontend/app/globals.css`
- `frontend/tailwind.config.ts`
- `frontend/components/ui/`
- `frontend/components/checkwise/`

If the task touches architecture-backed surfaces, also read:

- `docs/WORKFLOW_STATE_MACHINE.md`
- `docs/EVIDENCE_SLOTS.md` if present

## Design Lens

Make CheckWise feel:

- precise,
- tactile,
- responsive,
- premium,
- almost inevitable in its layout,
- and visually memorable without becoming decorative.

The user should feel that the product is thinking with them: transitions are crisp, hierarchy is obvious, and every surface responds with purpose.

## What To Improve

Use this skill to improve:

- route transitions,
- evidence-slot interactions,
- timeline expansion,
- upload/validation feedback,
- reviewer decision panels,
- hover and focus states,
- command-center composition,
- progressive disclosure,
- loading skeletons,
- empty/error/success states,
- and component-level polish.

## Motion Principles

Motion must communicate state.

Use motion for:

- a document becoming uploaded,
- validation completing,
- an evidence slot resolving,
- a rejected submission being superseded,
- a timeline expanding,
- a review decision being committed,
- AI/confidence data appearing.

Avoid:

- ambient loops,
- decorative background motion,
- slow page entrances,
- gratuitous springiness,
- spinner-only loading states.

Preferred feel:

- fast,
- crisp,
- lightly physical,
- never cartoonish,
- never sluggish.

Use existing timing tokens first:

- `--duration-fast`
- `--duration-standard`
- `--duration-slow`
- `--duration-deliberate`
- `--ease-enter`
- `--ease-standard`
- `--ease-bounce` only for small success/confirmation moments.

## Interaction Rules

- Every hover state should reveal affordance, not decoration.
- Every focus state must be keyboard-visible.
- Every loading state should preserve layout geometry.
- Every success state should confirm what changed and what comes next.
- Every destructive/rejection action must feel deliberate.
- Every status transition should leave an audit-visible trace.
- Every animation must respect `prefers-reduced-motion`.

## Visual Composition Rules

- Use strong composition before adding ornament.
- Prefer one dominant operational object per screen.
- Let evidence slots, timelines, and document previews become the visual drama.
- Use density intentionally: compact for operations, more spacious for guided flows.
- Avoid generic equal-card grids unless each card answers a distinct operational question.
- Avoid decorative gradients unless they are extremely subtle and tied to brand/intelligence context.

## Component Craft Targets

When implementing, look for opportunities to strengthen:

- `EvidenceSlotGrid`
- `EvidenceSlotCard`
- `SubmissionTimeline`
- `ReplacementLineage`
- `NextActionRail`
- `ReviewDecisionPanel`
- `DocumentIntelligencePanel`
- `ReportReadinessPanel`
- `ComplianceMap`
- `ResolutionRoom`
- `AuditTrailRail`
- `DocumentPreviewFrame`

Do not invent all of these at once. Create only what the current phase needs.

## Output When Planning

Return:

- interaction thesis,
- motion language,
- route/layout opportunities,
- component polish opportunities,
- state coverage risks,
- reduced-motion strategy,
- exact surfaces where this craft layer should apply.

## Output When Implementing

Return:

- files changed,
- interaction details added,
- motion tokens used,
- reduced-motion behavior,
- states verified,
- accessibility checks,
- verification commands.

## Failure Conditions

Revise the work if:

- the motion is decorative,
- the screen feels like generic SaaS,
- animations hide slow data or missing states,
- hover/focus states are inconsistent,
- a component looks polished but communicates no compliance value,
- new visuals bypass tokens,
- or the interaction weakens traceability.
