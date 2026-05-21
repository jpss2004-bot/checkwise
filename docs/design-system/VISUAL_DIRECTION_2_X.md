# CheckWise 2.x — Visual Direction Lock

Status: **Phase 2 deliverable.** Read after [AUDIT_2_X.md](AUDIT_2_X.md) + [INSPO_MAP.md](INSPO_MAP.md). Operates within the broader [VISUAL_REDESIGN_DOCTRINE.md](VISUAL_REDESIGN_DOCTRINE.md).
Locked: 2026-05-17, on `design/visual-direction-2x` branch.

This doc is the single source of truth for the visual decisions driving Phases 3–5 of the 2.x rework. Where AUDIT_2_X catalogs current state and INSPO_MAP curates external signals, this doc *commits* to a direction. After Phase 2 merges, surfaces that drift from this direction get reverted, not relitigated.

Companions: [peer-references/README.md](../../design-concepts/peer-references/README.md) names the products we're translating from.

## North Star

CheckWise 2.x should feel like a **compliance cockpit operated by a small group of skilled people**: dense where density serves operators, calm where calm serves providers, precise everywhere. The visual register sits between Linear (table density), Mercury (mono metadata and asymmetric admin), Vanta (compliance row patterns), and Stripe Dashboard (document-quality reports).

It is not a friendly consumer SaaS. It is not a fintech-dark cockpit. It is a legal-tech operational system that respects its operators' time.

## Density target — three tiers

`design-taste-frontend` defines `VISUAL_DENSITY` on a 1–10 scale. Lock:

| Tier | Density | Where it applies | What it looks like |
|---|---|---|---|
| **Comfortable** | 4 (existing) | `/`, `/login`, `/activate`, `/portal/entra-a-tu-espacio` | Generous spacing. Headlines breathe. Single primary action per viewport. This is the marketing register. |
| **Operational** | 5 (default product) | `/portal/dashboard`, `/portal/calendar`, `/portal/onboarding`, `/portal/upload`, `/portal/submissions/*` | Provider register. Tight enough to scan, loose enough to not stress users who are stressed about compliance. |
| **Premium-dense** | 7 (admin + reports) | `/admin/*`, `/portal/reports`, `/client/*` | Operator + power-user register. Tables get one extra column. Padding tightens. Mono carries every number, ID, and timestamp. |

Implementation: the existing `[data-density]` token system in [globals.css](../../apps/web/app/globals.css) gets a third value, `dense`, sitting between `comfortable` and `compact`. Phase 5 applies `[data-density="dense"]` to `<html>` for `/admin/*` and `/portal/reports` routes.

## Type scale (locked)

Current: body 14px / 1.6, no explicit display scale.

New explicit scale, mapped to Tailwind utilities + token utilities:

| Token | Rem | Use | Tailwind alias |
|---|---|---|---|
| `--text-eyebrow` | 0.6875 (11px) | Section eyebrow labels (small caps, tracking +0.05em, mono) | `cw-eyebrow` |
| `--text-body-sm` | 0.8125 (13px) | Table cells, metadata, helper text | `text-sm` |
| `--text-body` | 0.875 (14px) | Body paragraphs, default | `text-[14px]` |
| `--text-h3` | 1.0 (16px) | Section headings inside cards/surfaces | `text-base font-semibold` |
| `--text-h2` | 1.25 (20px) | Page subtitles, report section heads | `text-xl font-semibold` |
| `--text-h1` | 1.625 (26px) | Page titles | `text-[26px] font-semibold tracking-tight` |
| `--text-display-sm` | 2.25 (36px) | Hero subtitle, report cover subtitle | `text-4xl font-semibold tracking-tight` |
| `--text-display` | 3.5 (56px) | Hero headline only, report covers may use | `text-[56px] font-bold tracking-tight` |

`impeccable` prescription: hierarchy through scale + weight contrast, ≥1.25 ratio between steps. The above hits ≥1.18 minimum, ≥1.5 for display jumps. Weights stay disciplined: 400 / 500 / 600 / 700 only. No 800/900 except `--text-display`.

Body line length cap: **65ch**. Enforced via `.cw-prose` utility (Phase 2 adds it).

**Fonts (already locked, no change):** Geist for UI, Geist Mono for technical metadata. Phosphor icons exclusively. No emoji in product UI.

## Color strategy — Restrained

Per `impeccable`'s four-step commitment axis (Restrained / Committed / Full palette / Drenched):

CheckWise is **Restrained**: tinted neutrals + one accent ≤10% surface coverage.

- **Navy** (`--navy-800` = `#013557`) is structure, authority, nav, primary action.
- **Teal** (`--teal-500` = `#09c1b0`) is intelligence, "Wise" moments, AI/extraction signals. **Cap teal at ~10% of any surface.** It loses meaning when overused.
- **Cool gray** is the texture neutral — every gray tinted toward navy (`gray-900` actually sits at `222 24% 16%`, not pure neutral). Already correct in globals.css.
- **Status colors** (green/amber/red/blue/orange) are reserved for compliance state. **Never decorative.**

Phase 2 absolute bans, codified from `impeccable` + `design-taste-frontend`:

1. **No gradients.** Not on buttons, not on cards, not on text. The hero may keep its grid-pattern ornament because that's texture, not gradient.
2. **No glassmorphism.** `backdrop-blur` only used inside the right-rail detail panel where layering is functionally meaningful.
3. **No purple, no lila, no neon.** Period. (`design-taste-frontend`'s "Lila ban".)
4. **No new hex.** Anything that would need a new hex value gets a new token in `globals.css` first.
5. **No `#000` or `#fff`.** Every neutral tints toward navy. Already correct in primitive scales.

## Layout doctrine

### The big rules

1. **Asymmetric over symmetric.** Equal grids are banned across `/portal/dashboard`, `/admin/dashboard`, `/client/dashboard`. Use the Mercury/Ramp composition: large primary widget + 2-3 differently-weighted secondaries.
2. **Vertical lists over card grids** for *anything* where the items represent compliance state. The pattern is: full top/bottom borders, no left/right border, status pill, mono metadata, optional inline trend. Examples: `/portal/onboarding` requirement rows (replaces the 2×2 card grid), `/portal/reports` report list (replaces the static card cluster).
3. **`<DataTable>` as a primitive.** Promoted from `/admin/reviewer` to a shared component used by every roster surface in the product. Standard column shape: status (left, icon-only or pill) → primary identifier (left, may be mono) → 2–4 medium-weight signal columns → trailing metadata (right, mono).
4. **Right-rail detail panels** for any flow where detail-while-keeping-context is the right affordance (per Mercury). Reserved for `/admin/reviewer/[id]`, `/portal/submissions/[id]`, future correction-request detail. **Modals are banned as a default** — only for blocking confirmations (per `impeccable`).
5. **Page header = title + description + actions slot**, in that left-to-right order, with the title at `--text-h1` and the description capped at one short line. Spacing follows Tier-density rules. The existing `AdminShell` already has slots — extend to `PortalAppShell` for parity.

### What "rhythm" means

`impeccable`: *"Vary spacing for rhythm. Same padding everywhere is monotony."* Translated:

- Card padding varies by content weight, not by surface. A KPI tile is `p-5`, a report section is `p-8`, a table row is `py-3 px-4`.
- Section gaps between unrelated content blocks: `gap-12` (loose). Inside a related cluster: `gap-6`. Inside a row of tiles: `gap-4`.
- Border-only dividers (`border-t border-[color:var(--border-subtle)]`) replace card chrome wherever the content is already grouped by context.

## Motion doctrine

The existing motion system in [globals.css](../../apps/web/app/globals.css) is good. Phase 2 codifies how to use it:

| Use case | Class / curve | Duration |
|---|---|---|
| Page enter (any route) | `cw-fade-up` + `cw-stagger` | 320–480ms cascading |
| Inline state change (badge, status pill, button hover) | `transition-all` + `--ease-enter` | 150–250ms |
| Right-rail panel open | translate-x + opacity, `--ease-enter` | 280ms |
| Skeleton shimmer | existing `shimmer` keyframe | continuous |
| Success / completion celebration | `cw-success-ring` + `cw-draw-check` | one-shot, ~700ms |
| Hover lift on interactive cards | existing `cw-hover-lift` | 220ms |

**Bans (`impeccable` + `design-taste-frontend`):**

- No bounce / elastic curves. `--ease-bounce` is reserved for success microinteractions only.
- No animating CSS layout properties (top/left/width/height). Only `transform` and `opacity`.
- No animating on scroll without ScrollTrigger. No `addEventListener("scroll")` directly.
- No motion that hides or delays required compliance information (`DESIGN.md` rule).

`prefers-reduced-motion: reduce` continues to disable everything decorative. Already correct in globals.css.

## Shadow / elevation

The existing 5-step shadow scale (`--shadow-xs` → `--shadow-xl`) is correct. Phase 2 codifies usage:

- **`--shadow-xs`**: KPI tiles, list rows (the floor of "this is a surface").
- **`--shadow-sm`**: cards that contain a primary signal (e.g., gauge widget, status panel).
- **`--shadow-md`**: dropdowns, popovers, hover states on interactive cards.
- **`--shadow-lg`**: right-rail detail panel.
- **`--shadow-xl`**: modal scrim only. **Modals banned by default; this token exists for the few blocking confirmations.**

All shadows already tint toward navy (`rgba(1, 53, 87, ...)`), correct.

## Icon discipline

Phosphor icons exclusively, weight rules:

- **`weight="regular"`** for default icon usage (the 80% case).
- **`weight="bold"`** for active states, primary CTAs, and the leading icon on a status pill.
- **`weight="fill"`** reserved for filled success/check moments and brand logo lockups.
- Stroke width: do not set explicitly. Phosphor handles it.

## Status pill system (locked)

We have all the tokens. Phase 2 commits to one rendering:

```tsx
<span className="
  inline-flex items-center gap-1.5
  px-2 py-0.5
  rounded-full
  text-[12px] font-medium
  bg-[color:var(--doc-{state}-bg)]
  text-[color:var(--doc-{state}-text)]
">
  <Icon weight="bold" className="h-3 w-3" />
  {label}
</span>
```

Notes:
- **No border by default.** The token triplet stays, but the border is opt-in (used only when a pill sits on a same-tint background).
- The pill carries an icon **only** when the status name alone is ambiguous (e.g., `requiere_aclaracion` benefits from a question icon; `aprobado` does not need a check).
- Label text is the canonical Spanish from `apps/web/lib/constants/statuses.ts`. No improvisation.

This finalizes Linear's "tint, no border" pattern translated to our tokens.

## Metadata strip — new pattern

Every page header, every detail surface, every right-rail panel uses the same metadata strip composition:

```
LABEL_MONO_CAPS   value         LABEL_MONO_CAPS   value         LABEL_MONO_CAPS   value
```

- Labels: `cw-eyebrow` utility (added in Phase 2 — small caps, tracked, mono, `--text-tertiary`).
- Values: mono, `--text-primary`, may include status pill.
- Separator: 24px gap, no bullet.
- Wraps to next line at breakpoint, never to a vertical list.

This was the visual signature of the V2.0 hero ("CENTRO DE CUMPLIMIENTO · MAYO 2026 · 3 acciones pendientes"). Treat it as historical context, not as the locked landing-page target.

## Anti-patterns — codified ban list

Lifted from `impeccable` + `design-taste-frontend` + DESIGN.md, locked here for the `taste` skill to enforce:

| Pattern | Why banned |
|---|---|
| **Identical card grids** (3+ same-size cards in a row, each with icon + heading + text) | `impeccable` absolute ban. AUDIT F2 confirmed everywhere. |
| **Hero-metric template** (big number + small label + supporting stats + accent) | SaaS cliché. Replace with asymmetric composition. |
| **Nested cards** (card inside a card) | `impeccable` absolute ban. |
| **Side-stripe borders** (`border-left` ≥ 2px as decorative accent) | `impeccable` absolute ban. Existing `<Alert>` left-bar must be verified. |
| **Gradient text** (`background-clip: text`) | `impeccable` absolute ban. |
| **Glassmorphism as default** | `impeccable` absolute ban. Only on right-rail. |
| **Modal as first thought** | Use right-rail or inline expansion. |
| **Em dashes (—) in copy** | `impeccable` ban. Use commas, colons, periods, or parentheses. |
| **Emoji in product UI** | `DESIGN.md` + `design-taste-frontend`. Phosphor icons only. |
| **Inter font for "premium" headlines** | `design-taste-frontend` ANTI-SLOP. We use Geist; this just reinforces. |
| **Centered hero/H1** | `design-taste-frontend` ANTI-CENTER-BIAS. Asymmetric only. |
| **Purple / lila / neon accents** | `design-taste-frontend` LILA BAN. |
| **Static HTML pasted from design previews** | `DESIGN.md` ban. |
| **Fake metrics, random gradients, low-contrast gray dashboards** | `DESIGN.md` ban. |

## Token deltas — this phase

Minimal, additive, no breaking change. See diff in [globals.css](../../apps/web/app/globals.css).

1. **New density tier:** `[data-density="dense"]` between comfortable and compact.
2. **Type scale tokens:** `--text-eyebrow` through `--text-display` exposed as CSS custom properties + matching utility classes (`.cw-eyebrow`, `.cw-display`, `.cw-display-sm`, `.cw-prose`).
3. **Metadata strip utility:** `.cw-metadata-strip` — the canonical horizontal label/value layout.

No primitive scale changes. No semantic token changes. No status / doc / confidence changes. Phase 2 is **purely additive**.

## Anchor spike: `/portal/dashboard`

Phase 2 ships one surface rewritten against this direction, as proof:

- Replace the equal 4-up KPI grid with an asymmetric composition: one anchor widget (compliance gauge with center number + ring) + 2 medium tiles (next-action rail + status mix donut) + 1 small mono metadata strip.
- Replace the full-width banner with a metadata strip in the page header.
- Demote the "Hola, [vendor]" greeting block; promote workspace identity to mono metadata strip.
- Tighten padding by one step (Operational tier → density 5).

The spike is **`/portal/dashboard` only**. Phase 5 rolls the direction across the remaining 19 routes. If we discover the direction is wrong, we revert the spike and Phase 2 reopens — far cheaper than discovering it after Phase 5.

## What this doc does NOT do

- Does not redesign any surface other than `/portal/dashboard` (the spike).
- Does not touch backend.
- Does not introduce new colors or new primitive tokens.
- Does not address the `/client/*` seed gap (Phase 5).
- Does not address motion choreography beyond codifying existing utilities.
- Does not address the reports archetypes (Phase 3) or the marketing register (Phase 4).

## Verification gates for Phases 3–5

When subsequent phases land surfaces, they pass the gate by:

1. **Token contract.** No raw hex anywhere in the new surface. No new color tokens added without a written justification.
2. **Ban list check.** None of the codified anti-patterns above.
3. **Density tier.** The surface declares its density tier and applies the corresponding `[data-density]` attribute.
4. **Status pill rendering.** Every status pill follows the locked component shape.
5. **Metadata strip usage.** Page header uses the metadata strip pattern.
6. **`taste` skill review.** The skill explicitly evaluates the surface against this direction before merge.

Phase-2 PR is itself the first surface that has to pass these gates — the anchor spike on `/portal/dashboard`.

## Status

Phase 2 locked. Phase 3 (Reports) opens after this PR merges.
