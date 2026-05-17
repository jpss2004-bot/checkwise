---
description: Project-local UI craftsmanship pass for CheckWise. Activate when a frontend surface needs to be tightened, polished, or hardened against demo-day scrutiny — covers spacing audits, state coverage, accessibility, focus order, error surfaces, empty states, responsive collapse, and the small details that separate a real product from a wireframe.
---

# CheckWise Impeccable UI

Local override of the global `impeccable` skill. Same intent — make
the surface look and feel finished — but bound to CheckWise's
constraints, vocabulary, and component library so the output stays
consistent with what already ships.

## When to invoke

- Before a demo that's going to a stakeholder.
- When a surface looks "fine" but reads as unfinished on second look.
- When state coverage is incomplete (loading without skeleton, error
  without action, empty without guidance).
- When responsive collapse breaks (mobile sidebar, dense tables on
  narrow viewports).
- When accessibility has gone unaudited (focus order, keyboard reach,
  contrast ratios, screen-reader copy).
- After a feature lands but before it's added to the boss-demo flow.

Do **not** invoke for greenfield design or restructuring an entire
flow — that belongs to `taste` (judgement) or `hero-redesign`
(landing surface). This skill polishes what already exists.

## Audit checklist

Walk these in order. Fix only what fails.

### 1. Hierarchy
- One unmistakable primary action per view. Secondary actions are
  visually muted (`variant="outline"` or `variant="ghost"`).
- The page header answers "what am I doing here" in ≤ 8 words.
- The first viewport contains the most important data + the next action.

### 2. State coverage
- **Loading** — skeleton in the exact slot of the eventual content.
  No bare spinner mid-page.
- **Empty** — explains why empty + what to do next. Never a sad face
  alone.
- **Error** — quotes the error in human language + offers a recovery
  action (retry, edit, contact). Reference: `Alert` variants.
- **Success** — confirmed action + what comes next, not just a
  checkmark.
- **Stale / partial** — when data is from a fallback (offline, cache),
  surface a non-blocking warning Alert, do not silently mislead.

### 3. Tokens
- Background: only from `--surface-*`.
- Text: only from `--text-*`.
- Status badges: `--status-*` for system feedback, `--doc-*` for
  document lifecycle.
- Borders: prefer `--border-default`, escalate to `--border-strong`
  only on focus / selection.
- Shadows: `--shadow-xs`, `--shadow-sm`, `--shadow-md`. No raw rgba.

### 4. Type
- One H1 per page. Subheads use semantic h2/h3.
- `font-mono` only for IDs, codes, hashes, period keys.
- The "tag" pattern is uppercase tracking-wide font-mono 10–11 px.
  Do not bold or recolor it.

### 5. Spacing
- 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 px. Reject anything in between.
- Card internal padding: 24 (`p-6`). Section gap: 32 (`space-y-8`).
- Between label and input: 8 (`gap-2`). Between fields: 16 (`gap-4`).

### 6. Forms
- Every field has a `<Label>` + helper text or placeholder.
- Validation errors render in `Field error="…"` slot, not as
  free-floating text.
- Required fields marked with `*`, not "(required)".
- Disabled state explains why if non-obvious.
- Long labels wrap; never truncate the meaning.

### 7. Tables and lists
- Sticky table header at ≥ 8 rows.
- Each row has one obvious primary action; secondary in an overflow
  menu, not a row of 5 buttons.
- Empty cell = `—`, never blank.

### 8. Responsive
- Test ≤ 360 px, 768 px, 1280 px.
- The header navigation collapses below 768 px (use the existing
  `ProviderContextBar` mobile pattern).
- Cards reflow from grid to stack — never overflow horizontally.

### 9. Accessibility
- All interactive elements reachable by Tab in visual order.
- Focus ring: the existing `:focus-visible` ring, never `outline:none`
  without replacement.
- Icons that are alone in a button get an `aria-label`.
- Color is never the only signal — pair status colors with an icon or
  text.
- Contrast: text on background ≥ 4.5:1 for body, 3:1 for large.

### 10. Copy
- Spanish, plain. Avoid jargon.
- Active voice. Direct address ("Sube tu documento", not "El
  documento debe ser subido").
- Never the words: TODO, mock, hardcoded, temporary, fake, demo
  (unless surfacing an actual demo PDF).
- Error messages name the failure + the next step in one sentence.

## Output shape

When asked to apply this skill, produce a list of fixes — not an
essay. Format:

```
File: <path>
- <one-line fix>  →  <token / component to use>
- <one-line fix>  →  <token / component to use>
```

Followed by the smallest set of code edits that implement the list.
Verify with `npm run typecheck && npm run build` before declaring
done. If a real backend session is required to see the change, say so
explicitly instead of claiming local verification.

## Out of scope

- Adding new dependencies (no new icon set, no new motion library).
- Changing brand colors or typography choices.
- Replacing existing components with new ones unless the existing one
  is structurally broken — extend, don't fork.
