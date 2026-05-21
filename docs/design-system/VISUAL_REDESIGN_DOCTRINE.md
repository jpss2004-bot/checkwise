# CheckWise Visual Redesign Doctrine

Last updated: 2026-05-15

## Purpose

This doctrine defines what the future CheckWise frontend redesign should become after the architecture gap is closed. It is not an implementation task yet. It is the visual and product standard future Claude Code sessions must use when redesigning the app.

The redesign should make CheckWise feel unlike a generic SaaS dashboard. It should feel like a guided REPSE compliance command system: precise, auditable, intelligent, and calm under operational pressure.

## Architecture First

Do not begin the full visual redesign until the architecture phases are complete enough to provide real product semantics:

- authenticated workspace identity
- reviewer workflow state machine
- evidence slots
- replacement lineage
- obligation current-state read models
- audit and validation timelines

The redesign must be powered by those concepts. A beautiful interface over mock cards is a failure. A strong CheckWise redesign makes the product's real compliance truth visible.

## Creative Mandate

When the architecture is ready, the visual redesign is allowed to be bold.

Future agents may:

- change page layouts completely,
- add new frontend routes when they clarify a workflow,
- split overloaded pages into focused task surfaces,
- add new reusable visual components,
- add product-specific animation and transition patterns,
- redesign navigation and information architecture,
- create richer document/timeline/review surfaces,
- and introduce new interaction models for evidence slots, replacement lineage, and compliance operations.

The constraint is not "keep the current UI shape." The constraint is "do not break backend truth, auth boundaries, domain semantics, or token discipline."

Be inventive with experience, not with data contracts. If a new route or component makes the compliance workflow easier to understand, it is allowed. If a visual idea hides state, invents fake state, or bypasses architecture, it fails.

## The Core Product Metaphor

CheckWise is not a file cabinet. It is not an upload form. It is not a generic compliance database.

CheckWise is a guided compliance cockpit built around evidence slots:

```text
workspace + requirement + period -> current obligation state
```

Every redesigned screen should help the user understand:

- what obligation exists,
- what evidence is current,
- what is missing,
- what is risky,
- what changed,
- who owns the next action,
- and what CheckWise recommends now.

## Visual Signature

The future UI should be immediately recognizable as CheckWise.

Use:

- navy as structure, authority, and navigation
- teal only for intelligence, extraction, confidence, or "Wise" moments
- white and cool gray as calm operational space
- status colors only when communicating compliance state
- compact density for operational surfaces
- generous but purposeful spacing for guided flows
- document-centered surfaces, not decorative cards
- slot grids, timelines, review rails, and decision panels
- strong first-viewport hierarchy with an obvious next action

Avoid:

- generic equal-card dashboards
- marketing hero layouts inside the app
- decorative gradients, glow, or ambient effects
- fake metrics
- charts without an operational decision
- screenshots pasted into product UI
- static HTML copied from Claude Design
- new colors that bypass the token system

## Signature Surfaces

The redesign should produce a small set of memorable, reusable CheckWise surfaces.

### 1. Compliance Command Center

The primary provider landing surface. It should not feel like a dashboard template.

It should show:

- current compliance period
- missing obligations
- risky/rejected obligations
- items awaiting CheckWise review
- next best action
- deadline pressure
- report readiness

The dominant visual should be an operational state map, not a hero card.

### 2. Evidence Slot Grid

The core product object made visible.

Each slot represents one obligation for one period. It should display:

- requirement
- period
- current status
- current submission
- replacement lineage marker when relevant
- due/expired signal
- owner of next action

This is where CheckWise can look genuinely different from other SaaS products: a compliance lattice rather than a pile of cards.

### 3. Submission Timeline

Every submission should have a traceable timeline:

- upload received
- prevalidation
- document intelligence signals
- reviewer decision
- replacement/supersession
- final state
- audit metadata

The timeline is not decorative. It is the trust layer.

### 4. Guided Upload Resolver

Upload should feel like resolving a specific obligation, not sending a file into a bucket.

The flow must show:

- workspace context
- requirement being resolved
- period
- whether this replaces a prior submission
- expected document signals
- validation outcome
- next step after upload

### 5. Reviewer Workbench

For internal operators, the visual center should be triage and decision quality.

It should show:

- queue grouped by risk and deadline
- evidence slot context
- document preview and extracted metadata
- validation findings
- prior attempts
- decision actions with required reasons

### 6. Report Readiness Surface

Reports should be a consequence of evidence slots.

The UI should say:

- report-ready
- blocked
- waiting on provider
- waiting on reviewer
- missing/rejected slots preventing close

### 7. Compliance Map / Operations Canvas

The redesign may introduce a richer route or mode that visualizes obligations as a map across providers, periods, and requirements.

This can become a signature CheckWise experience if it remains operational:

- filter by period, institution, risk, and owner
- show evidence-slot state at a glance
- let users drill into timelines and replacement attempts
- never become decorative graph art

### 8. Focused Resolution Rooms

For complex rejected/mismatch items, the redesign may introduce a focused route that gathers the document, reason, evidence slot, prior attempts, timeline, and upload resolver in one place.

This should feel like a guided legal-tech case room, not a modal with a file input.

## Visual Components To Build Toward

Future redesign work should prefer reusable product-specific components such as:

- `EvidenceSlotCard`
- `EvidenceSlotGrid`
- `ComplianceCommandCenter`
- `NextActionRail`
- `SubmissionTimeline`
- `ReplacementLineage`
- `ObligationStateBadge`
- `ReviewDecisionPanel`
- `DocumentIntelligencePanel`
- `ReportReadinessPanel`
- `PeriodNavigator`
- `WorkspaceContextHeader`
- `ComplianceMap`
- `ResolutionRoom`
- `RiskQueue`
- `AuditTrailRail`
- `DeadlinePressureBar`
- `DocumentPreviewFrame`
- `EvidenceSlotMatrix`

Do not create these all at once. Let architecture-backed surfaces drive which components are needed.

## Motion

Motion should communicate state, not decoration.

For interaction craft, prefer Motion, external design tools, and upstream
`/impeccable`. Motion should sharpen transitions, tactile states, and premium
microinteractions without weakening CheckWise's compliance clarity.

Use motion for:

- upload received
- validation completed
- status transition
- evidence slot resolved
- timeline update
- AI/confidence reveal
- route transitions between command center, slot detail, and resolution room
- timeline expansion/collapse
- replacement-lineage handoff from old submission to new submission

Do not use motion for:

- ambient backgrounds
- decorative page entrances
- parallax
- spinning icons as the main loading state

Motion should be memorable but disciplined. A status transition can feel crisp and alive; an ambient loop on a dashboard is noise.

## Typography

Use:

- Geist Sans for product UI
- Geist Mono for RFCs, IDs, hashes, periods, and evidence keys
- Open Sans only for marketing/report contexts

The type system should feel operational and premium. Avoid oversized display text inside dense product screens.

## Asset Use

Use `docs/design-system/ASSET_MANIFEST.md` as the canonical asset inventory.

Rules:

- `assets/checkwise-mark.svg` is the preferred product mark.
- Screenshots are visual references only.
- Logo PNG/JPG assets are references or external-facing brand assets.
- Do not make uploaded screenshots part of the runtime UI.

## Redesign Readiness Gate

Before any full visual implementation starts, a Claude Code session must be able to answer:

- Which backend service powers each screen?
- Which evidence-slot state powers each card, row, or badge?
- Which status vocabulary is canonical?
- Which actions mutate state through the workflow service?
- Which replacement lineage is visible?
- Which component primitives already exist?
- Which visual references are source material only?
- Which new routes or layouts improve the workflow?
- Which animations communicate real state transitions?

If these answers are missing, the task is not ready for redesign.

## Definition Of A Strong Redesign

A strong CheckWise redesign is not only beautiful. It is structurally honest.

It should make a user feel:

- "I know exactly what is missing."
- "I know what CheckWise is reviewing."
- "I know why something was rejected."
- "I know what replaces what."
- "I know what must happen next."
- "I trust this product with compliance risk."

If a screen is visually impressive but does not clarify compliance state, it fails this doctrine.
