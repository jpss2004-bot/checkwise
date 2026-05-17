# CheckWise 2.x — Inspo Signal Map

Status: **Phase 1 deliverable.** Read alongside [AUDIT_2_X.md](AUDIT_2_X.md).
Captured: 2026-05-17.

The 16 Pinterest screenshots in [`design-concepts/inspo-screenshots/`](../../design-concepts/inspo-screenshots/) span dashboards, mobile fintech, marketing landings, onboarding wizards, file managers, and upload flows. None of them are a target — CheckWise is a Mexican REPSE compliance product whose visual register is closer to Stripe / Linear / Mercury / Ramp than to any of these. The job of this doc is to extract the **signals** worth pulling forward and the **anti-references** worth marking out, so Phase 2 (Visual Direction Lock) starts from a curated list, not a Pinterest board.

13 of 16 inspos were read in detail this session; the remaining 3 follow the same families and don't change the conclusions.

## How to read this

Each signal is tagged with one of:

- **ADOPT** — Pull this composition or pattern forward as-is. Already compatible with CheckWise's tokens and voice.
- **TRANSLATE** — The underlying idea is valuable, but the execution (palette, font, density) needs to be re-skinned into CheckWise's tokens before it lands.
- **REJECT** — Fails the `taste` guardrail (consumer-SaaS warmth, AI-purple/blue gradients, decorative glassmorphism, hero-metric template, gradient text, identical card grids, etc.). Do not pull forward at any altitude. The screenshot stays in the folder as a *what-not-to-do* anchor.

The `taste` skill specifically vetoes anything that *"makes the screen feel more like a marketing site or consumer dashboard."* That's the recurring filter applied below.

## Signal Catalog

### From dashboard inspos

**Compositional signals**

| Signal | Tag | Where to land it in CheckWise |
|---|---|---|
| Asymmetric grid: large primary widget + 3-4 differently-weighted secondary tiles (vs. equal 4-up KPI strip) | **ADOPT** | `/portal/dashboard`, `/admin/dashboard`. Replaces the current equal-card grids. |
| Gauge-with-center-number as the **anchor** signal on a dashboard | **TRANSLATE** | We already have `<RadialGauge>` from V2.0. Promote it to dashboard-level anchor (compliance %, queue health, vendor risk) instead of being one of N tiles. Re-skin away from the warm-pastel inspo palette — keep navy/teal. |
| Donut chart with category legend below + center percentage | **TRANSLATE** | Use for "submissions by status" on `/portal/dashboard` and "queue by reason" on `/admin/reviewer`. Strip the colored legend pills — render as monospace key/value pairs aligned to the donut. |
| Inline sparkline inside a KPI tile (mini-chart, no axes) | **ADOPT** | Already shipped as `<Sparkline>` in V2.0. Phase 2 standardizes when to use it (only when 7+ data points exist and the trend is signal, not decoration). |
| Stacked / 100% bar showing proportion across categories | **ADOPT** | Use on `/admin/vendors` row-level: a compact stacked bar showing per-vendor compliance state distribution. |

**Layout signals**

| Signal | Tag | Notes |
|---|---|---|
| Sidebar nav with grouped sections, badge counters, hover hint text | **ADOPT** | Already shipped as `PortalAppShell`. Phase 2 extends the same nav primitive to admin (currently top-nav) for narrower viewports while keeping top-nav default. |
| Top filter strip → table → row-level inline actions | **ADOPT** | Already shipped on `/admin/reviewer`. Promote to shared `<DataTable>` for vendors, clients, audit-log. |
| Full-bleed "today / next-action" rail above the dashboard fold | **TRANSLATE** | Inspos pitch this as a marketing banner. CheckWise version: a single horizontal rail with the next 1-2 compliance actions, plain-language Spanish, no decoration. |

**Anti-references (REJECT)**

- Warm pastel KPI cards (mint, lavender, peach). CheckWise's voice is precise legal-tech, not friendly consumer.
- Multi-bright KPI tiles (purple gradient + blue gradient + green gradient stacked). The "Lila ban" from `design-taste-frontend` applies.
- Card-inside-card-inside-card layouts. `impeccable` explicitly bans nested cards.
- "Welcome back, Barbara! 👋" greeting strip with emoji and animation. CheckWise's tone is professional, Spanish-first; the dashboard greeting is "Hola, [vendor]" without emoji, and even that may be too warm — Phase 2 decides.

### From mobile / fintech inspos

| Signal | Tag | Notes |
|---|---|---|
| Big numerical headline + ±% chip with arrow icon | **TRANSLATE** | Use on `/portal/dashboard` for "documents approved this month" KPI. Drop the arrow icon if the same signal lives in a Sparkline below. |
| Doughnut chart with percentage labels in a vertical key | **ADOPT** | Already have `<Donut>`. Use the inspo's key layout (vertical key right of donut, monospace percentages). |
| Multi-screen mobile mockup showing one user flow as a horizontal scroll | **REJECT** | Marketing pattern, not product. |

**Anti-references (REJECT)**

- Bright fintech green / bright fintech navy as the dominant palette. CheckWise is restrained.
- Phone mockup as a hero device. CheckWise is desktop-first (operators on monitors, compliance officers on laptops).

### From marketing / landing inspos

| Signal | Tag | Notes |
|---|---|---|
| Centered headline → dashboard preview card embedded immediately below the fold | **ADOPT** | Already shipped on `/` (the V2.0 hero). The "Centro de cumplimiento" preview card is exactly this pattern, executed correctly. |
| Asymmetric headline layout (large headline left, supporting visual right, no center bias) | **ADOPT** | Already on `/`. Phase 4 extends the asymmetric register to `/login` and `/activate` without copying the layout literally. |
| Feature-spotlight dual-column (text + supporting screenshot or illustration) | **TRANSLATE** | Use on a future `/about` or `/security` marketing surface. Not currently in scope for 2.x. |
| Curated FAQ list with collapsible rows | **TRANSLATE** | Could land on a future Public security or compliance-documentation page. Not in scope for 2.x. |

**Anti-references (REJECT)**

- Orange/purple horizontal gradient backgrounds. AI-slop signature.
- "Designed to help you do more with less stress" generic SaaS copy. CheckWise voice is direct next-action language.
- Emoji-in-headline patterns ("Turn your 🛍️ Shoppers into Subscribers").
- Hero-with-phone-mockup-tilted-30°. Consumer-mobile signature.
- Multi-card "All in one place" benefit grids. Identical-card ban.

### From upload / file-manager inspos

| Signal | Tag | Where to land |
|---|---|---|
| Dual-pane upload: drop zone left, file list with per-file progress + status right | **TRANSLATE** | `/portal/upload` wizard step that handles the actual file. Re-skin to use CheckWise's status pills (`Esperando revisión`, `Posible inconsistencia`, …). |
| File list with file icon + name + size + status pill + actions | **ADOPT** | Use for `/portal/onboarding` requirement rows (replaces the 2×2 card grid). |
| Folder-grid landing for a document workspace | **REJECT** | CheckWise's evidence model is requirement-driven, not folder-driven. Folders are a worse mental model for compliance — keep the existing requirement-slot pattern. |

**Anti-references (REJECT)**

- Dashed-border drop zones with cute illustrations (the spaceship / cloud upload mascots).
- Emoji file-type icons.

### From onboarding inspos

| Signal | Tag | Where to land |
|---|---|---|
| "What brings you here?" — 3 simple option cards stacked vertically | **TRANSLATE** | Possible pattern for future `/onboarding/role` if CheckWise ever introduces self-serve role selection. **Not in 2.x scope.** Today, role is always determined by the invitation, never picked by the user. |
| "Tell us about you" — 5 vertical option rows with icon + label | **TRANSLATE** | Same — held for future onboarding work. |

**Anti-references (REJECT)**

- Cartoon mascot illustrations (the Viking-helmet emoji in the inspo). CheckWise's voice does not permit mascots.

### From auth inspos

| Signal | Tag | Notes |
|---|---|---|
| Single calm centered card with email-only first input + bold primary CTA | **ADOPT (already done)** | `/login` already executes this. The Phase 2 refinement is to make the surface read as CheckWise — not as a generic centered-card auth screen. See AUDIT §Public Routes. |
| "OR Sign in with Google" social OAuth row | **REJECT (out of scope)** | CheckWise is invitation-only and tenant-scoped. Adding social OAuth would change the auth model. Not in 2.x. |

## Phase 2 inputs derived from this map

1. **Hero language is locked.** The V2.0 `/` page is the visual anchor. Every signal in this map gets translated into the same register before it lands.
2. **Dashboard composition** changes shape:
   - Anchor signal (gauge or large-format chart) replaces the equal-card 4-up.
   - KPI strip becomes a varied-rhythm row (large, medium, medium, small) with sparklines where the trend is real signal.
   - Greeting strip shrinks or disappears.
3. **Reports gets the deepest re-conception** in Phase 3. The inspo signals worth pulling: dual-column report archetypes, executive-summary headline → drill-down sections, status-aware row patterns for evidence tables.
4. **Tables become a primitive.** The `/admin/reviewer` table pattern shipped in 2.0 deserves promotion to a shared `<DataTable>` used everywhere a roster is rendered.
5. **Upload UI** swaps the wizard's pure-form layout for the dual-pane (drop zone + file list) pattern, re-skinned to CheckWise tokens.
6. **All identical-card grids are deleted.** Replaced with vertical lists with full borders (compliance reads better as a stack than as a tiling).

## What the inspos did NOT tell us

The Pinterest set is biased toward consumer SaaS, fintech apps, and marketing landings. It under-represents the registers most relevant to CheckWise:

- **Legal-tech operator consoles** (Westlaw, LexisNexis, Clio — all denser, more terminal-flavored than what's in the folder).
- **Compliance / audit-trail interfaces** (Vanta, Drata, Secureframe — closer to CheckWise's actual peer set, none in the folder).
- **Government / institutional document portals** (SAT's own portal, IMSS's portal — the *actual* surfaces CheckWise replaces).

Phase 2 should add at minimum one Vanta-like dashboard reference and one Mercury/Ramp-density admin reference before locking the direction. If the user wants me to source those, I can — but I'll only do it inside Phase 2 (Visual Direction Lock), not as part of this Phase 1 audit.

## Status

Phase 1 complete. The inspo board is now a *curated* reference, not a raw mood board.
