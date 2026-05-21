# CheckWise Hero Landing Audit

Captured: 2026-05-20

## Current state

The public landing page lives in `apps/web/app/page.tsx`.

The hero is a hand-built JSX cockpit:

- `MarketingNav`
- `Hero`
- `BackgroundOrnaments`
- `HeroCockpit`
- `HeroTrustStrip`
- `ProductPreview`
- `Features`
- `HowItWorks`
- `LegalShelfBlock`
- `RequestInformation`

The current hero does not use real product images. It renders a synthetic
dashboard preview from arrays such as `COCKPIT_SLOTS` and
`COCKPIT_TIMELINE`. That makes the page feel internally consistent in code but
visually less believable as a product landing page.

Runtime public images are limited mostly to logos and brand collateral:

- `apps/web/public/brand/checkwise-brand-sheet.png`
- `apps/web/public/brand/checkwise-impi.jpg`
- `apps/web/public/brand/checkwise-mark.png`
- `apps/web/public/brand/checkwise-square.jpg`
- `apps/web/public/brand/checkwise-wordmark.png`
- `apps/web/public/checkwise-logo.png`
- `apps/web/public/checkwise-whatsapp-qr.png`

Real product screenshots exist outside the runtime public folder:

- `docs/audit-screenshots/2026-05-18-system-audit/*.png`
- `design-concepts/screenshots/public/*.png`
- `demo_assets/screenshots/*.png`

Search did not find `CheckWise 1.71` or `1.71` in the current frontend landing
source. If that text appears in the browser, it is likely coming from a stale
deployed build, cache, an older branch, or an asset not represented in the
current checked tree.

## Why it feels weak

- **The proof object is not real.** The right-side cockpit is detailed, but it
  is still an invented illustration. The user cannot see what the actual system
  looks like.
- **The composition is static.** Motion is CSS-only (`cw-fade-up`,
  `cw-pulse-soft`, `cw-scan`) and does not create a memorable product reveal.
- **The hero is still locked to the old local design doctrine.** The page has
  comments and structure from the old "CheckWise 2.0 launch hero" pass.
- **The first viewport has too much abstract explanation.** The headline,
  metadata rail, preview lattice, trust strip, and fine print all compete
  before the user sees a real surface.
- **The asset strategy is incomplete.** The repo has screenshots, but no
  curated `apps/web/public/marketing/` product-image set for the landing page.

## Design direction for the next pass

Use CheckWise docs as product constraints, but do not reuse the old local hero
skill as visual direction.

The next hero should:

- show real CheckWise product screenshots or screenshot composites;
- use a stronger first-viewport product signal than a synthetic preview card;
- create depth with layered product imagery, not decorative blobs;
- replace static CSS entrances with purposeful Motion for React animation;
- update stale version/copy references wherever they appear in runtime;
- preserve the core REPSE promise in Spanish;
- keep the CTAs simple: contact/demo and login;
- make the next section visible below the hero on desktop and mobile.

## Recommended implementation stack

Use:

- UI UX Pro Max for critique and visual direction once installed;
- 21st.dev / Magic MCP for component discovery once configured;
- Motion for React (`motion`, imported from `motion/react`) for hero animation;
- `/gpt-taste`, `/design-taste-frontend`, `/high-end-visual-design`,
  `/redesign-existing-projects`, and `/impeccable` for external skill passes;
- `/checkwise-frontend` for implementation discipline;
- `/checkwise-qa-release` after the patch.

Do not use these as visual direction for the new hero:

- `/hero-redesign`
- `/taste`
- `/impeccable-ui`
- `/emil-kowalski-design`
- `/checkwise-ui-designer`
- `/checkwise-visual-redesign`
- `/checkwise-redesign-prep`

## Concrete patch sequence

1. Create `apps/web/public/marketing/` and copy or regenerate curated real
   product screenshots from the audit/demo screenshot sets.
2. Add Motion for React to `apps/web/package.json`.
3. Split the landing page into focused components instead of keeping the whole
   marketing surface inside `apps/web/app/page.tsx`.
4. Replace `HeroCockpit` with a real screenshot-based product stage.
5. Add a controlled animated reveal: screenshot stack, active document state,
   report preview, and reviewer action moving through the system.
6. Rework `ProductPreview` so it supports the hero instead of repeating fake
   miniature UI.
7. Run frontend typecheck, lint, build, and screenshot QA at desktop and mobile
   widths.

## Files to inspect before patching

- `apps/web/app/page.tsx`
- `apps/web/app/globals.css`
- `apps/web/package.json`
- `apps/web/public/`
- `apps/web/components/checkwise/brand-logo.tsx`
- `apps/web/components/ui/button.tsx`
- `apps/web/components/ui/badge.tsx`
- `docs/audit-screenshots/2026-05-18-system-audit/`
- `design-concepts/screenshots/public/`
- `demo_assets/screenshots/`
