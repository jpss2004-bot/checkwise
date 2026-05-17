---
description: Project-local design-taste guard for CheckWise. Activate when judging or rewriting any visual decision in the frontend so it stays grounded in CheckWise's compliance/legal-tech voice and the tokens defined in frontend/app/globals.css and docs/DESIGN_SYSTEM.md.
---

# CheckWise Taste

Use this skill before approving any UI change. It is the local override
of the global `taste-skill`: stricter, narrower, and tuned to one
product — CheckWise — instead of generic web aesthetic.

The product is a Mexican REPSE compliance SaaS. Reviewers, internal
operators and legal counsel are the primary audience. Tone is closer
to **Stripe / Linear / Mercury / Ramp** than to consumer SaaS. If a
proposed change makes the screen feel more like a marketing site or
consumer dashboard, it fails this skill.

## Source of truth

Every taste call must reconcile against the existing artefacts before
suggesting alternatives:

- `docs/DESIGN_SYSTEM.md` — tokens, brand foundation, anti-patterns,
  reference products. Read sections 1, 2, 3.1, 3.3, 4 before any
  visual judgement.
- `frontend/app/globals.css` — the canonical token vocabulary
  (`--brand-navy`, `--brand-teal`, `--surface-*`, `--text-*`,
  `--status-*`, `--doc-*`). Do not invent new tokens; map proposed
  values to existing ones.
- `frontend/components/checkwise/**` — existing component shapes
  (`expediente-card`, `provider-context-bar`, `WorkspaceIdentityCard`,
  the intake-wizard step pattern). Match them; do not parallel-invent.

If a component or token does not exist for the use case, prefer
extending the design system over forking a one-off.

## What this skill enforces

| Dimension | Rule |
|---|---|
| Voice | Executive, calm, traceable. Not cheerful, not playful, not edgy. |
| Color | Brand navy and teal carry meaning. Status colors come from `--status-*`. Document states come from `--doc-*` (8 distinct values). Never use a status color for decoration. |
| Type | Open Sans display + Inter body + JetBrains Mono for codes/IDs. No fourth typeface. |
| Spacing | 4px / 8px scale. No magic spacing. |
| Density | Lean closer to Linear than to Notion. White space serves hierarchy, not breathing for its own sake. |
| Hierarchy | Each section answers at least one of: what is missing, what is risky, what is due, who owns it, what changed, what is the next action. |
| Motion | Only when it communicates state change. No ambient loops. No purely decorative parallax. |
| Imagery | Brand mark + Phosphor icons (duotone for hero, bold for inline). No stock photography. No emoji as UI. |
| Empty states | Always tell the user what to do next. Empty must never look like loading. |

## Reject on sight

- Three-column equal-grid hero on an operational screen.
- Status badge using a non-status color.
- Two competing primary buttons in the same view.
- Mixed border radii within one component.
- Card shadows that do not map to `--shadow-*` tokens.
- Capitalised section labels for anything other than the existing
  font-mono uppercase tracking-wide convention.
- "Coming soon" stickers on shipped surfaces — either build it or
  remove the entry point.
- Decorative gradients, glow effects, or animated backgrounds that
  imply consumer SaaS.
- Loading spinners without an accompanying skeleton in the same slot.
- Internal vocabulary in user copy: TODO, mock, hardcoded, temporary,
  fake. Use plain Spanish.

## How to deliver a taste pass

When reviewing or proposing a UI change, structure the answer:

1. **What this is supposed to communicate** — one sentence.
2. **What the current state communicates instead** — concrete, not
   adjective soup.
3. **Specific token / component swaps** — reference globals.css
   variables and existing components by file path.
4. **What to remove** — call out anything that competes with the
   primary intent.
5. **One-screen verification** — describe the dominant visual after
   the change, not a list of features.

Do not produce a moodboard. Do not propose a redesign. Do not invent
a new colour. Bound the change to the smallest unit that solves the
clarity problem.
