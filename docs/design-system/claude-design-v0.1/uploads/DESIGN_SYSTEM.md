# CheckWise Design System v1.0

**Status:** Foundation spec — pre-implementation  
**Scope:** Frontend token architecture, visual language, component inventory, pattern library  
**Product:** REPSE compliance SaaS — Mexican enterprise legal-tech

---

## Table of Contents

1. [Product + UX Philosophy](#1-product--ux-philosophy)
2. [Brand Foundation](#2-brand-foundation)
3. [Design Token Architecture](#3-design-token-architecture)
   - [3.1 Color System](#31-color-system)
   - [3.2 Spacing Scale](#32-spacing-scale)
   - [3.3 Typography System](#33-typography-system)
   - [3.4 Elevation + Shadow System](#34-elevation--shadow-system)
   - [3.5 Border Radius System](#35-border-radius-system)
   - [3.6 Motion Philosophy](#36-motion-philosophy)
4. [Visual Language](#4-visual-language)
5. [Component Architecture](#5-component-architecture)
6. [Pattern Library](#6-pattern-library)
7. [Responsive System](#7-responsive-system)
8. [Current Audit — Issues + Fixes](#8-current-audit--issues--fixes)
9. [Implementation Plan](#9-implementation-plan)

---

## 1. Product + UX Philosophy

### What CheckWise Is

CheckWise is an enterprise compliance operations platform for REPSE (Registro de Prestadoras de Servicios Especializados u Obras Especializadas) workflows in Mexico. It manages 28+ document types across calendar periods, tracks compliance for multiple clients and providers, and routes document submissions through human-verified review.

The platform serves two primary actors:
- **Providers** — companies submitting compliance documents monthly
- **Operators** — CheckWise / Legal Shelf staff reviewing, validating, and approving submissions

### UX Principles (in priority order)

1. **Guided, not overwhelming.** Non-technical providers must never feel lost. Every screen has one primary action, clear context, and a visible next step.
2. **Trust through transparency.** Compliance failures cost money and licenses. The UI must communicate status clearly, signal errors early, and never hide uncertainty.
3. **Calm precision.** Dense regulatory data must feel organized, not chaotic. Information hierarchy, spacing, and color signal importance — not decoration.
4. **Progressive disclosure.** Show only what's needed now. Complexity is revealed step by step, not dumped upfront.
5. **Reliable feedback.** Every action has an immediate response. Loading states, error messages, and success confirmations are never missing.

### Reference Products

| Product | What to borrow |
|---------|---------------|
| Stripe | Clarity at every step, form validation, error messages |
| Linear | Spacing discipline, type hierarchy, dense data that breathes |
| Ramp | Enterprise data tables, status communication, trust signals |
| Notion | Progressive disclosure, calm base palette, hierarchy without noise |
| Mercury | Clean modal flows, document-centric UX, financial-grade reliability feel |

### Anti-patterns to avoid

- Generic bootstrap-style cards everywhere (3-column equal grid)
- Overly cheerful consumer UI (this is a compliance product, not a wellness app)
- Developer-looking interfaces (raw JSON, exposed IDs, technical labels)
- Loading spinners without skeleton layouts (causes CLS and feels unstable)
- Error messages that don't explain the next action
- Unlabeled icon buttons
- Centered hero layouts when content is operational

---

## 2. Brand Foundation

### Official Brand Colors (from brand guide)

The current implementation (`globals.css`) diverges from the official brand palette. The design system realigns to the registered brand.

| Token | Name | Hex | HSL | Usage |
|-------|------|-----|-----|-------|
| `--brand-navy` | Navy Primary | `#013557` | `204 98% 17%` | Nav, primary buttons, brand text |
| `--brand-teal` | Teal Accent | `#09c1b0` | `175 91% 40%` | Active states, highlights, icons |
| `--brand-navy-mid` | Navy Secondary | `#02558a` | `204 96% 28%` | Hover state on navy |
| `--brand-blue-gray` | Blue-Gray | `#4b90a4` | `196 37% 47%` | Supporting brand elements |

> **Note:** The current `--primary: 174 72% 28%` (`#1B6B59`) is a dark forest teal — not the brand color. The official navy `#013557` should be the primary interactive color.

### Typography (Brand)

The brand guide specifies **Open Sans** for marketing/print. The product UI uses **Geist** — a technical, high-quality sans-serif built for software interfaces (used by Vercel). This is the standard for premium SaaS products.

- **Product UI:** Geist (heading and body)
- **Monospace / data:** Geist Mono (document codes, hashes, IDs, metadata values)
- **Marketing / external:** Open Sans (kept for brand consistency in reports, PDFs)

### Logo Usage Rules

- Use `CW sin fondo.png` mark (navy + teal stacked layers) in the product UI nav
- The mark is geometric with layered rectangles forming a "W" — suggests organization, depth, structure
- Minimum safe area: 8px on all sides
- Never recolor the mark; use approved navy + teal only
- "Powered by Legal Shelf" endorsement appears on external-facing screens (provider portal) only

---

## 3. Design Token Architecture

The system uses a **3-layer token architecture**:

```
Primitive Tokens  →  raw values (hex, px, ms)
Semantic Tokens   →  meaning-based (--surface-page, --text-primary)
Component Tokens  →  component-specific (--btn-height, --input-border)
```

This ensures global palette changes propagate automatically, and components stay decoupled from raw values.

---

### 3.1 Color System

#### Primitive Palette — Navy Scale

Derived from brand primary `#013557`:

```css
--navy-50:  204 100% 97%;   /* #F0F7FF — hover tints, tag backgrounds */
--navy-100: 204  90% 92%;   /* #D9EEFF */
--navy-200: 204  85% 82%;   /* #AACFED */
--navy-300: 204  80% 68%;   /* #6AAFD9 */
--navy-400: 204  78% 52%;   /* #2D8CC5 */
--navy-500: 204  93% 38%;   /* #0470A8 — mid-blue, info states */
--navy-600: 204  96% 28%;   /* #025487 — hover on primary */
--navy-700: 204  97% 21%;   /* #024069 */
--navy-800: 204  98% 17%;   /* #013557 — brand primary */
--navy-900: 204  99% 12%;   /* #012440 */
--navy-950: 204 100%  8%;   /* #01162A */
```

#### Primitive Palette — Teal Scale

Derived from brand accent `#09c1b0`:

```css
--teal-50:  175  90% 96%;   /* #EBFBFA */
--teal-100: 175  88% 88%;   /* #C2F4EF */
--teal-200: 175  86% 74%;   /* #7DEAD9 */
--teal-300: 175  88% 60%;   /* #3DD9CC */
--teal-400: 175  89% 50%;   /* #0ECFBE */
--teal-500: 175  91% 40%;   /* #09C1B0 — brand teal */
--teal-600: 175  91% 34%;   /* #07A396 */
--teal-700: 175  92% 27%;   /* #058178 */
--teal-800: 175  92% 20%;   /* #046059 */
--teal-900: 175  93% 14%;   /* #03423D */
```

#### Primitive Palette — Neutral/Gray Scale

```css
--gray-25:  210  20% 99%;   /* #FDFEFF — almost white */
--gray-50:  210  20% 98%;   /* #F7F9FB — page background (keep existing) */
--gray-100: 210  18% 94%;   /* #EEF1F6 */
--gray-200: 214  18% 88%;   /* #DDE2EC */
--gray-300: 214  16% 76%;   /* #B8C0D0 */
--gray-400: 215  14% 60%;   /* #8D98AE */
--gray-500: 215  14% 42%;   /* #5F6E87 — muted-foreground (keep existing) */
--gray-600: 215  16% 34%;   /* #4A5670 */
--gray-700: 215  18% 26%;   /* #374157 */
--gray-800: 220  20% 20%;   /* #2A3245 */
--gray-900: 222  24% 16%;   /* #202D42 */
--gray-950: 222  28% 13%;   /* #1B2638 — foreground (keep existing) */
```

#### Primitive Palette — Status Colors

```css
/* Success */
--green-50:  142  76% 95%;
--green-100: 142  70% 85%;
--green-500: 142  76% 36%;   /* #199641 */
--green-700: 142  80% 26%;

/* Warning */
--amber-50:   38  90% 95%;
--amber-100:  38  85% 85%;
--amber-500:  38  92% 50%;   /* #EDA415 */
--amber-700:  38  90% 36%;

/* Error */
--red-50:   0  90% 96%;
--red-100:  0  80% 88%;
--red-500:  0  72% 45%;    /* #D81C1C — keep existing */
--red-700:  0  76% 34%;

/* Info */
--blue-50:  214  80% 96%;
--blue-100: 214  70% 88%;
--blue-500: 214  89% 52%;   /* #2570E8 */
--blue-700: 214  89% 38%;
```

#### Semantic Token Layer

This is what components consume. Map primitives to meaning:

```css
:root {
  /* ── Surfaces ─────────────────────────────────────── */
  --surface-page:       hsl(var(--gray-50));     /* body background */
  --surface-raised:     hsl(0 0% 100%);          /* cards, panels */
  --surface-overlay:    hsl(0 0% 100%);          /* modals, dropdowns */
  --surface-sunken:     hsl(var(--gray-100));    /* inputs, code, readonly */
  --surface-hover:      hsl(var(--gray-50));     /* row hovers */
  --surface-selected:   hsl(var(--navy-50));     /* selected rows */
  --surface-brand:      hsl(var(--navy-800));    /* primary brand bg */
  --surface-brand-muted:hsl(var(--navy-50));     /* subtle brand tint */
  --surface-teal-muted: hsl(var(--teal-50));     /* subtle teal tint */

  /* ── Text ─────────────────────────────────────────── */
  --text-primary:    hsl(var(--gray-950));  /* main content */
  --text-secondary:  hsl(var(--gray-500));  /* supporting info */
  --text-tertiary:   hsl(var(--gray-400));  /* placeholders, hints */
  --text-disabled:   hsl(var(--gray-300));  /* disabled elements */
  --text-inverse:    hsl(0 0% 100%);        /* text on dark bg */
  --text-link:       hsl(var(--navy-700));  /* anchors, interactive text */
  --text-brand:      hsl(var(--navy-800));  /* brand emphasis */
  --text-teal:       hsl(var(--teal-600));  /* teal-colored labels */

  /* ── Borders ──────────────────────────────────────── */
  --border-subtle:   hsl(var(--gray-100));  /* very subtle dividers */
  --border-default:  hsl(var(--gray-200));  /* standard element borders */
  --border-strong:   hsl(var(--gray-300));  /* emphasized borders */
  --border-focus:    hsl(var(--navy-500));  /* focus rings */
  --border-brand:    hsl(var(--navy-800));  /* brand-colored borders */
  --border-error:    hsl(var(--red-500));   /* error state */
  --border-success:  hsl(var(--green-500)); /* success state */

  /* ── Interactive ──────────────────────────────────── */
  --interactive-primary:        hsl(var(--navy-800));
  --interactive-primary-hover:  hsl(var(--navy-700));
  --interactive-primary-active: hsl(var(--navy-900));
  --interactive-secondary:      hsl(var(--teal-500));
  --interactive-secondary-hover:hsl(var(--teal-600));
  --interactive-ghost-hover:    hsl(var(--gray-100));
  --interactive-destructive:    hsl(var(--red-500));

  /* ── Status ───────────────────────────────────────── */
  --status-success-text: hsl(var(--green-700));
  --status-success-bg:   hsl(var(--green-50));
  --status-success-border:hsl(var(--green-100));

  --status-warning-text: hsl(var(--amber-700));
  --status-warning-bg:   hsl(var(--amber-50));
  --status-warning-border:hsl(var(--amber-100));

  --status-error-text:   hsl(var(--red-700));
  --status-error-bg:     hsl(var(--red-50));
  --status-error-border: hsl(var(--red-100));

  --status-info-text:    hsl(var(--blue-700));
  --status-info-bg:      hsl(var(--blue-50));
  --status-info-border:  hsl(var(--blue-100));

  /* ── Document States (REPSE-specific) ──────────────── */
  --doc-empty-text:         hsl(var(--gray-400));
  --doc-empty-bg:           hsl(var(--gray-50));

  --doc-pending-text:       hsl(var(--amber-700));
  --doc-pending-bg:         hsl(var(--amber-50));
  --doc-pending-border:     hsl(var(--amber-100));

  --doc-uploaded-text:      hsl(var(--blue-700));
  --doc-uploaded-bg:        hsl(var(--blue-50));
  --doc-uploaded-border:    hsl(var(--blue-100));

  --doc-in-review-text:     hsl(var(--navy-700));
  --doc-in-review-bg:       hsl(var(--navy-50));
  --doc-in-review-border:   hsl(var(--navy-100));

  --doc-approved-text:      hsl(var(--green-700));
  --doc-approved-bg:        hsl(var(--green-50));
  --doc-approved-border:    hsl(var(--green-100));

  --doc-rejected-text:      hsl(var(--red-700));
  --doc-rejected-bg:        hsl(var(--red-50));
  --doc-rejected-border:    hsl(var(--red-100));

  --doc-expired-text:       hsl(30 80% 38%);
  --doc-expired-bg:         hsl(30 80% 96%);
  --doc-expired-border:     hsl(30 70% 85%);

  --doc-needs-review-text:  hsl(var(--amber-700));
  --doc-needs-review-bg:    hsl(var(--amber-50));

  /* ── AI/OCR Confidence States ─────────────────────── */
  --confidence-high-text:   hsl(var(--green-700));   /* ≥95% */
  --confidence-high-bg:     hsl(var(--green-50));
  --confidence-high-border: hsl(var(--green-100));

  --confidence-medium-text: hsl(var(--amber-700));   /* 70–94% */
  --confidence-medium-bg:   hsl(var(--amber-50));
  --confidence-medium-border:hsl(var(--amber-100));

  --confidence-low-text:    hsl(24 91% 38%);         /* 50–69% */
  --confidence-low-bg:      hsl(24 91% 96%);
  --confidence-low-border:  hsl(24 80% 85%);

  --confidence-none-text:   hsl(var(--gray-500));    /* <50% / not extracted */
  --confidence-none-bg:     hsl(var(--gray-100));
  --confidence-none-border: hsl(var(--gray-200));
}
```

#### Semantic → Tailwind Config Bridge

Update `tailwind.config.ts` colors section to consume semantic tokens:

```ts
colors: {
  border: "var(--border-default)",
  input: "var(--surface-sunken)",
  ring: "var(--border-focus)",
  background: "var(--surface-page)",
  foreground: "var(--text-primary)",

  primary: {
    DEFAULT: "var(--interactive-primary)",
    foreground: "var(--text-inverse)",
    hover: "var(--interactive-primary-hover)",
  },
  secondary: {
    DEFAULT: "var(--interactive-secondary)",
    foreground: "var(--text-inverse)",
  },
  muted: {
    DEFAULT: "var(--surface-sunken)",
    foreground: "var(--text-secondary)",
  },
  accent: {
    DEFAULT: "var(--surface-brand-muted)",
    foreground: "var(--text-brand)",
  },
  destructive: {
    DEFAULT: "var(--interactive-destructive)",
    foreground: "var(--text-inverse)",
  },
  success: {
    DEFAULT: "var(--status-success-text)",
    bg: "var(--status-success-bg)",
    border: "var(--status-success-border)",
  },
  warning: {
    DEFAULT: "var(--status-warning-text)",
    bg: "var(--status-warning-bg)",
    border: "var(--status-warning-border)",
  },
}
```

---

### 3.2 Spacing Scale

Base unit: **4px**. All spacing tokens are multiples of 4px. Tailwind's default scale maps directly — no overrides needed. Named breakpoints for semantic clarity:

| Name | Value | Tailwind | Usage |
|------|-------|----------|-------|
| `space-0.5` | 2px | `p-0.5` | Icon inner padding |
| `space-1` | 4px | `p-1` | Tight gaps, inline elements |
| `space-2` | 8px | `p-2` | Badge padding, icon button padding |
| `space-3` | 12px | `p-3` | Input padding (horizontal), tight card padding |
| `space-4` | 16px | `p-4` | Standard card padding, form field gap |
| `space-5` | 20px | `p-5` | Comfortable section padding |
| `space-6` | 24px | `p-6` | Card padding (standard) |
| `space-8` | 32px | `p-8` | Large card padding, dialog padding |
| `space-10` | 40px | `p-10` | Section padding (desktop) |
| `space-12` | 48px | `p-12` | Page-level section gap |
| `space-16` | 64px | `p-16` | Hero section padding |
| `space-20` | 80px | `p-20` | Large feature section gap |

**Component spacing rules:**
- Form field vertical gap: `gap-4` (16px)
- Label-to-input gap: `gap-1.5` (6px)
- Input-to-helper gap: `gap-1` (4px)
- Card padding: `p-6` (24px) desktop, `p-4` (16px) mobile
- Section divider gap: `space-y-8` (32px)
- Page max-width container: `max-w-7xl mx-auto px-5`
- Portal content wrapper: `max-w-3xl` for single-column flows, `max-w-7xl` for dashboards

---

### 3.3 Typography System

#### Font Installation

```bash
# Install Geist from npm (Next.js optimized)
npm install geist
```

Wire in `app/layout.tsx`:

```tsx
import { GeistSans } from 'geist/font/sans';
import { GeistMono } from 'geist/font/mono';

export default function RootLayout({ children }) {
  return (
    <html lang="es" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
```

Update `globals.css`:

```css
body {
  font-family: var(--font-geist-sans), 'Arial', sans-serif;
  /* mono available as var(--font-geist-mono) */
}
```

#### Type Scale

| Role | Size | Weight | Line-height | Tracking | Usage |
|------|------|--------|-------------|---------|-------|
| `display` | 36px / `text-4xl` | 700 | 1.0 | `tracking-tighter` | Landing hero only |
| `display-sm` | 28px / `text-3xl` | 700 | 1.1 | `tracking-tight` | Metric numbers in dashboard |
| `heading-1` | 22px / `text-2xl` | 600 | 1.2 | `tracking-tight` | Page titles |
| `heading-2` | 18px / `text-xl` | 600 | 1.25 | `tracking-tight` | Section headers, card titles |
| `heading-3` | 15px / `text-[15px]` | 600 | 1.3 | normal | Subsection labels |
| `heading-4` | 13px / `text-[13px]` | 600 | 1.4 | `tracking-wide` uppercase | Table headers, category labels |
| `body` | 14px / `text-sm` | 400 | 1.6 | normal | Primary UI text |
| `body-sm` | 13px / `text-[13px]` | 400 | 1.6 | normal | Secondary content |
| `body-xs` | 12px / `text-xs` | 400 | 1.5 | normal | Metadata, timestamps |
| `label` | 13px / `text-[13px]` | 500 | 1.4 | normal | Form labels |
| `helper` | 12px / `text-xs` | 400 | 1.5 | normal | Helper text, hints |
| `caption` | 11px / `text-[11px]` | 400 | 1.5 | `tracking-wide` | Eyebrow text, captions |
| `mono` | 13px / `text-[13px]` | 400 | 1.5 | normal | Document codes, IDs, hashes |

**Rules:**
- Serif fonts are banned in the product UI
- `font-mono` (Geist Mono) for all RFC codes, document hashes, IDs, technical data
- Heading hierarchy: never skip levels (`h1` → `h2`, not `h1` → `h4`)
- Color contrast: all body text must meet WCAG AA (4.5:1) minimum
- Avoid pure black (`#000000`) — use `--text-primary` (`--gray-950`) which is off-black

---

### 3.4 Elevation + Shadow System

Elevation communicates z-axis hierarchy. Tint shadows toward the background's hue (blue-gray) for a cohesive, non-generic feel.

```ts
// tailwind.config.ts — boxShadow extension
boxShadow: {
  /* Level 0 — flat, no elevation */
  none: 'none',

  /* Level 1 — micro hover elevation */
  xs: '0 1px 2px rgba(1, 53, 87, 0.06)',

  /* Level 2 — card / raised surface */
  sm: '0 2px 8px rgba(1, 53, 87, 0.08), 0 1px 2px rgba(1, 53, 87, 0.04)',

  /* Level 3 — floating elements (dropdowns, popovers) */
  md: '0 4px 16px rgba(1, 53, 87, 0.10), 0 2px 4px rgba(1, 53, 87, 0.06)',

  /* Level 4 — modals, dialogs */
  lg: '0 12px 40px rgba(1, 53, 87, 0.12), 0 4px 12px rgba(1, 53, 87, 0.08)',

  /* Level 5 — toasts, drawer panels */
  xl: '0 24px 64px rgba(1, 53, 87, 0.14), 0 8px 20px rgba(1, 53, 87, 0.08)',

  /* Legacy alias — keep for backward compat, maps to sm */
  soft: '0 2px 8px rgba(1, 53, 87, 0.08), 0 1px 2px rgba(1, 53, 87, 0.04)',
}
```

**Usage rules:**
- `shadow-none` — flat content sections, page backgrounds
- `shadow-xs` — subtle hover state on rows
- `shadow-sm` — cards, panels, raised containers
- `shadow-md` — dropdowns, command palette, date pickers
- `shadow-lg` — modals, dialogs, drawers
- `shadow-xl` — toast notifications
- Never use `shadow-2xl` or generic Tailwind shadows (they use wrong hue)
- No outer glow effects, no `box-shadow` color glows

---

### 3.5 Border Radius System

```ts
// tailwind.config.ts — borderRadius extension
borderRadius: {
  none: '0',
  sharp: '4px',    /* table cells, inline tags, code blocks */
  sm: '6px',       /* inputs, small buttons, tight elements */
  DEFAULT: '8px',  /* standard — cards, buttons, dropdowns */
  md: '10px',      /* panels, dialog containers */
  lg: '12px',      /* large cards, feature blocks */
  xl: '16px',      /* section containers, onboarding panels */
  '2xl': '20px',   /* hero elements (landing only) */
  full: '9999px',  /* pills — status badges, chips */
}
```

**Rules:**
- Inputs: `rounded-sm` (6px) — matches button height parity
- Buttons: `rounded` (8px) default — `rounded-full` only for icon-only pill buttons
- Cards: `rounded-lg` (12px) — consistent throughout portal
- Dialogs: `rounded-xl` (16px)
- Status badges: `rounded-full` (pill)
- Avatars: `rounded-full`
- Table cells: `rounded-none`

---

### 3.6 Motion Philosophy

**Principle:** Motion communicates state change. It is never decorative in a compliance product.

**Rules:**
1. Never animate layout properties (`width`, `height`, `top`, `left`) — only `transform` and `opacity`
2. No autoplay animations on data-heavy screens (compliance calendar, document lists)
3. Overlays (modals, drawers) use spring physics — they feel physical, not digital
4. Loading states use shimmer (not spinner) on skeleton shapes
5. Success states get a brief, non-intrusive confirmation micro-animation
6. Page transitions: simple fade + subtle translate-up (150ms)
7. No parallax, no scroll-triggered reveals on functional portal pages

#### Easing Functions

```css
:root {
  --ease-enter:    cubic-bezier(0.16, 1, 0.3, 1);   /* spring-like entry */
  --ease-exit:     cubic-bezier(0.4, 0, 1, 1);       /* quick exit */
  --ease-standard: cubic-bezier(0.4, 0, 0.2, 1);    /* general transition */
  --ease-bounce:   cubic-bezier(0.34, 1.56, 0.64, 1); /* success confirmation */
}
```

#### Duration Scale

```css
:root {
  --duration-instant:  80ms;   /* hover effects, color changes */
  --duration-fast:    150ms;   /* micro-interactions, icon swaps */
  --duration-standard:250ms;   /* component transitions */
  --duration-slow:    350ms;   /* layout shifts, panel slides */
  --duration-enter:   400ms;   /* page-level entrances */
}
```

#### Framer Motion Defaults

```ts
// shared motion config for portal
export const motionConfig = {
  fadeIn: {
    initial: { opacity: 0, y: 4 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.25, ease: [0.16, 1, 0.3, 1] },
  },
  slideUp: {
    initial: { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.35, ease: [0.16, 1, 0.3, 1] },
  },
  spring: {
    type: 'spring',
    stiffness: 300,
    damping: 28,
  },
  stagger: {
    animate: { transition: { staggerChildren: 0.06 } },
  },
};
```

---

## 4. Visual Language

### Tone + Personality

CheckWise is **calm, precise, and trustworthy**. The visual language communicates operational reliability — the same feeling as a well-designed banking interface or legal document management system.

| Axis | Position |
|------|----------|
| Warm ←→ Cool | Neutral-cool (navy + gray base) |
| Simple ←→ Complex | Simple structure, complex data |
| Playful ←→ Serious | Serious with moments of warmth |
| Sparse ←→ Dense | Sparse chrome, dense when necessary |
| Static ←→ Animated | Mostly static, purposeful micro-motion |

### Color Usage in Context

- **Navy** appears in: primary buttons, active nav items, brand headers, document type codes
- **Teal** appears in: active status highlights, progress indicators, AI/OCR confidence (high), success teal tones
- **Gray** appears in: 90% of the interface — surfaces, borders, body text
- **Status colors** appear only in: badges, alerts, inline validation, document state labels
- **Never** use status colors for decoration

### Iconography

Use `@phosphor-icons/react` exclusively. Check if installed before using.

```bash
npm install @phosphor-icons/react
```

**Icon sizing rules:**
- Inline (body text): `h-4 w-4` (16px)
- Button icons: `h-4 w-4` (16px)
- Section icons: `h-5 w-5` (20px)
- Feature/card icons: `h-6 w-6` (24px)
- Empty state icons: `h-10 w-10` (40px)

**Weight:** Use `weight="regular"` as default. `weight="bold"` for emphasis. Never mix weights in a single component.

**Phosphor icons to use by category:**

| Category | Icons |
|----------|-------|
| Documents | `FilePdf`, `FileDoc`, `Files`, `FolderOpen`, `Upload` |
| Compliance | `ShieldCheck`, `Scales`, `Certificate`, `Gavel`, `Stamp` |
| Status | `CheckCircle`, `WarningCircle`, `XCircle`, `Clock`, `HourglassHigh` |
| Navigation | `ArrowLeft`, `ArrowRight`, `CaretDown`, `X`, `DotsThree` |
| Data | `Calendar`, `Table`, `ChartBar`, `TrendUp` |
| AI/OCR | `Sparkle`, `Robot`, `Eye`, `MagnifyingGlass` |
| User | `User`, `Building`, `IdentificationCard`, `Briefcase` |

---

## 5. Component Architecture

### Layer Diagram

```
Pages
  └── Templates (portal layout, onboarding layout)
        └── Compositions (compliance-calendar, intake-wizard, document-list)
              └── Primitives (Button, Badge, Input, Field, Card...)
                    └── Tokens (CSS variables)
```

### Primitive Inventory

#### Currently Exists (7)

| Component | Status | Issues |
|-----------|--------|--------|
| `Button` | Good — CVA, 4 variants | Add `size` prop variants; add loading state |
| `Card` | Good — composed divs | Add `CardFooter`; add `variant` (elevated, flush) |
| `Badge` | Broken — hardcoded colors | Replace amber/red hardcoding with semantic tokens |
| `Input` | Incomplete | No error state styling, no prefix/suffix slots |
| `Label` | Good | Add `required` indicator support |
| `Select` | HTML native | Replace with Radix Select for custom styling |
| `Textarea` | Good | Add resize control, character count |

#### Must Add (Priority Order)

| Component | Priority | Reason |
|-----------|----------|--------|
| `Field` | P0 | Compose Label + Input + Helper + Error into one unit |
| `Skeleton` | P0 | Replace all `Loader2` spinners on data screens |
| `Alert` | P0 | Replace ad-hoc error div patterns (3 different ones exist) |
| `Spinner` | P0 | Single spinner component (currently duplicated) |
| `Dialog` | P1 | Needed for confirmations, previews |
| `Toast` | P1 | Sonner integration — replaces manual success states |
| `Tabs` | P1 | Dashboard and document type filtering |
| `Progress` | P1 | Upload progress, onboarding completion |
| `Checkbox` | P1 | Requirement checklists |
| `Table` | P1 | Compliance period list, document history |
| `Tooltip` | P2 | Help text, status explanations |
| `Dropdown` | P2 | Period selector, action menus |
| `Drawer` | P2 | Document detail panel, mobile navigation |

### Composition Inventory

#### Currently Exists

| Composition | Lines | Issues |
|------------|-------|--------|
| `IntakeWizard` | 702 | Monolith — extract step components |
| `ComplianceCalendar` | ~300 | Good structure, fix month-button CVA |
| `ProviderAccessForm` | ~150 | Good, add Zod validation |
| `ProviderContextBar` | ~80 | Good, refine visual design |
| `OnboardingChecklist` | ~200 | Good structure |
| `ValidationSummary` | ~100 | Centralize `ValidationSignal` type |
| `DocumentSubmissionForm` | ~150 | Good |
| `SupportCard` | ~40 | Good |
| `RequirementStatusBadge` | ~50 | Fix: hardcoded variant map |

#### Must Add (REPSE-specific)

| Composition | Purpose |
|-------------|---------|
| `DocumentCard` | Single document with status, deadline, actions |
| `RequirementRow` | Table row for a compliance requirement |
| `PeriodSelector` | Month/year picker for compliance periods |
| `UploadDropzone` | Drag-and-drop upload with progress |
| `ConfidenceBadge` | AI/OCR confidence indicator |
| `MetadataReviewPanel` | Show extracted fields with confidence |
| `ComplianceScoreBar` | Overall compliance % for a period |
| `TimelineStep` | Single step in a multi-step flow |
| `EmptyDocumentSlot` | Placeholder for a missing required document |
| `ReviewFlagCard` | Flag/note from human reviewer |

### Auth Guard Pattern

Replace the 4-copy session check with a single pattern:

```tsx
// lib/with-portal-session.tsx
'use client';
export function withPortalSession<T extends { session: PortalSession }>(
  Component: React.ComponentType<T>
) {
  return function GuardedComponent(props: Omit<T, 'session'>) {
    const router = useRouter();
    const [session, setSession] = useState<PortalSession | null>(null);

    useEffect(() => {
      const s = readPortalSession();
      if (!s) { router.replace('/'); return; }
      setSession(s);
    }, [router]);

    if (!session) return null;
    return <Component {...(props as T)} session={session} />;
  };
}
```

### Type Centralization

Move all shared types to `lib/types.ts`:

```ts
// Types currently duplicated across 3+ files:
export type ValidationSignal = 'valid' | 'warning' | 'error' | 'pending';
export type RequirementStatus = 'pending' | 'uploaded' | 'in_review' | 'approved' | 'rejected' | 'expired';
export type ConfidenceLevel = 'high' | 'medium' | 'low' | 'none';
export type DocumentGroup = 'expediente_inicial' | 'cumplimiento_repse';
```

---

## 6. Pattern Library

### 6.1 Onboarding Patterns

CheckWise onboarding is the first impression for providers. It must feel guided and safe.

#### Multi-step Wizard Rules

- Maximum 5 steps per wizard
- Progress indicator always visible at top (step dots or numbered steps)
- Current step label shown below progress
- Each step has: title, subtitle (context), content, primary action, secondary action (back)
- Never show all fields at once — reveal only the current step's fields
- Validation runs on blur (per field) and on "Next" attempt
- Error messages appear inline below the failing field within 150ms
- "Back" never loses data
- Final step: confirmation summary with all entered data before submission

#### Step Indicator Component Spec

```
[1] ─── [2] ─── [3] ─── [4] ─── [5]
 ●         ○       ○       ○       ○
Contexto
```

- Completed: filled navy circle with checkmark
- Active: filled navy circle with step number
- Upcoming: empty circle with gray border
- Connector line: gray when incomplete, navy when passed

#### Onboarding Checklist Rules

- Each requirement shows: icon, name, status badge, optional description
- Status badges: `Pendiente` (amber), `Enviado` (blue), `Aprobado` (green), `Rechazado` (red)
- Completed items are visually de-emphasized (opacity reduced, moved to bottom)
- Count: "3 de 8 completados" shown prominently in section header
- Never show a generic empty state — show the first pending item as a call-to-action

---

### 6.2 Dashboard + Calendar Patterns

#### Compliance Calendar Rules

The calendar is the operational heart of the portal. It must communicate:
- Which months have pending submissions
- Status of each month's requirements
- Deadlines (upcoming vs. overdue)
- Quick action to go to a specific period

**Month cell states:**
- `complete`: green tint, checkmark — all requirements for this month are approved
- `partial`: amber tint, partial progress indicator — some submitted, some pending
- `pending`: gray/muted — not yet started (future months)
- `overdue`: red tint, warning icon — past deadline with missing required docs
- `current`: subtle navy ring — current calendar month

**Layout:** 4-column grid on desktop (3 months per quarter), 2-column on mobile. Each cell shows: month name, year, status badge, count of approved/total requirements.

#### Dashboard Summary Bar Spec

A horizontal band above the calendar showing:
- Provider name + RFC
- Period (year)
- Overall compliance % with a progress bar
- Count: "X de Y meses con expediente completo"
- Quick action: "Ver periodo actual"

---

### 6.3 Document Upload Flow

#### Upload Dropzone States

| State | Visual | Description |
|-------|--------|-------------|
| `idle` | Dashed border, gray text, upload icon | Waiting for interaction |
| `hover` | Navy dashed border, navy text | File dragged over zone |
| `uploading` | Progress bar inside zone, filename shown | Upload in progress |
| `success` | Green border, checkmark, filename + size | Upload complete |
| `error` | Red border, error message below | Upload failed |

**Rules:**
- Only accept: PDF (`application/pdf`)
- Max file size: 10MB (configurable)
- Show filename and size after upload, not just "uploaded"
- Single file per upload slot (one slot per document type)
- Error messages are specific: "El archivo excede 10 MB" not "Error al subir"

#### Upload Progress Pattern

```
[filename.pdf]  [2.3 MB]
████████████░░  68%
Subiendo... 2s restantes
```

---

### 6.4 Validation States

All form fields follow this exact structure:

```
[Label] *required
[Input field]
[Helper text — always in markup, shown when relevant]
[Error message — only on error, replaces helper]
```

CSS classes for each state:

**Default:** `border-border bg-background`
**Focus:** `border-border-focus ring-2 ring-border-focus/20`
**Success:** `border-border-success bg-status-success-bg/20`
**Error:** `border-border-error bg-status-error-bg/30`
**Disabled:** `border-border bg-surface-sunken text-text-disabled cursor-not-allowed`

**Inline error pattern:**
```tsx
{error && (
  <p className="flex items-center gap-1.5 text-xs text-status-error-text" role="alert">
    <WarningCircle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" weight="fill" />
    {error}
  </p>
)}
```

**Helper text pattern:**
```tsx
{!error && helper && (
  <p className="text-xs text-text-tertiary">{helper}</p>
)}
```

---

### 6.5 AI/OCR Confidence States

For the upcoming AI/OCR metadata extraction (v0.5 roadmap), the UI needs to communicate how confident the system is about each extracted field.

#### Confidence Badge Component Spec

```
┌─────────────────────────────────────────────────┐
│ [Sparkle] RFC del Proveedor                     │
│ LOGIS870412AB3                                  │
│ [ALTA] Extraído automáticamente (97%)           │
└─────────────────────────────────────────────────┘
```

**Visual states:**

| Confidence | Label | Color | Icon | Action |
|-----------|-------|-------|------|--------|
| ≥95% | Alta confianza | Green | `Sparkle` (filled) | Auto-fill, confirm |
| 70–94% | Confianza media | Amber | `Sparkle` | Review suggested value |
| 50–69% | Baja confianza | Orange | `WarningCircle` | Human input required |
| <50% / none | Sin extracción | Gray | `Question` | Manual entry required |

**Rules:**
- All AI-extracted values show the confidence badge
- `Alta confianza` fields are pre-filled but still editable
- `Baja confianza` fields show the suggestion greyed out with a warning; user must confirm
- `Sin extracción` fields are blank — standard input
- Never approve a document with unreviewed `media` or `baja` confidence fields
- The review UI shows a count: "3 campos requieren revisión"

#### Metadata Review Panel Layout

```
CAMPOS EXTRAÍDOS AUTOMÁTICAMENTE
──────────────────────────────────
RFC del proveedor          [Alta] LOGIS870412AB3
Fecha del documento        [Alta] 15 de marzo de 2026
Periodo reportado          [Media] Marzo 2026  ← needs review
Número de empleados        [Baja]  142          ← warning
Firma del representante    [—]    Pendiente manual
──────────────────────────────────
2 campos requieren confirmación
[Revisar campos] →
```

---

### 6.6 Empty States

Every list, table, and calendar view must have a defined empty state.

**Empty state anatomy:**
```
[Icon — 40px, --text-tertiary]
[Title — heading-3]
[Description — body, max-w-xs, centered, --text-secondary]
[Primary action button — optional]
```

**Templates by context:**

| Context | Icon | Title | Description | Action |
|---------|------|-------|-------------|--------|
| No documents uploaded | `FolderOpen` | Sin documentos | Aún no has enviado documentos para este periodo | Subir primer documento |
| No requirements found | `Scales` | Sin requisitos | No hay requisitos registrados para este periodo | — |
| Calendar with no data | `Calendar` | Calendario vacío | Completa el expediente inicial para activar el calendario | Ir a expediente |
| Search with no results | `MagnifyingGlass` | Sin resultados | No encontramos documentos con esa búsqueda | — |
| Provider not found | `Building` | Proveedor no encontrado | No existe un proveedor con esa clave de acceso | — |

---

### 6.7 Loading States

**Rule:** Every data-fetching screen uses skeleton loaders, not spinners, for initial loads. Spinners are reserved for inline actions (button submitting, uploading).

#### Skeleton Component Spec

```tsx
// Base skeleton shimmer
function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "animate-pulse rounded bg-gray-200/80",
        "relative overflow-hidden",
        "after:absolute after:inset-0",
        "after:bg-gradient-to-r after:from-transparent after:via-white/40 after:to-transparent",
        "after:animate-[shimmer_1.5s_infinite]",
        className
      )}
    />
  );
}
```

**Keyframes for shimmer:**
```css
@keyframes shimmer {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}
```

**Skeleton layouts by screen:**

| Screen | Skeleton pattern |
|--------|-----------------|
| Dashboard | Summary bar (1 wide), calendar grid (12 cells) |
| Onboarding checklist | 6 rows of `[circle] [wide bar] [narrow badge]` |
| Document list | 4 rows of `[square] [2 lines] [badge]` |
| Provider access form | Single centered card with 2 fields + button |

---

### 6.8 Error States

**Three types of errors, three distinct patterns:**

#### 1. Inline field validation error
```tsx
<p className="flex items-center gap-1.5 text-xs text-red-600" role="alert">
  <WarningCircle className="h-3.5 w-3.5 shrink-0" weight="fill" />
  Este campo es obligatorio
</p>
```

#### 2. Alert banner (page-level, recoverable)
```tsx
<Alert variant="error">
  <WarningCircle className="h-4 w-4" />
  <AlertTitle>No fue posible cargar el calendario</AlertTitle>
  <AlertDescription>
    Revisa tu conexión e intenta de nuevo.
    <button onClick={retry}>Reintentar</button>
  </AlertDescription>
</Alert>
```

#### 3. Full-screen error (session expired, fatal error)
```tsx
<ErrorScreen
  title="Sesión expirada"
  description="Ingresa de nuevo con tu clave de acceso."
  action={{ label: "Ingresar", href: "/" }}
/>
```

**Rules:**
- Never show raw API error strings to users
- Every error must suggest a next action
- Error messages in Spanish, clear language, no technical jargon
- `role="alert"` on all error containers for screen reader support
- Log technical errors to console, show user-friendly version in UI

---

## 7. Responsive System

### Breakpoints

```ts
// No changes to Tailwind defaults — they're correct
screens: {
  sm:  '640px',   // Large phones
  md:  '768px',   // Tablets, small laptops
  lg:  '1024px',  // Standard desktop
  xl:  '1280px',  // Wide desktop
  '2xl':'1536px', // Ultrawide (rarely needed)
}
```

### Layout Rules

**Page container:**
```tsx
<main className="mx-auto max-w-7xl px-4 sm:px-5 lg:px-6">
```

**Breakpoint-by-breakpoint behavior:**

| Screen | Nav | Content | Calendar | Form |
|--------|-----|---------|----------|------|
| Mobile (< md) | Top bar, no sidebar | Full-width, stacked | 2-col grid | Full-width fields |
| Tablet (md–lg) | Top bar | max-w-3xl centered | 3-col grid | max-w-lg form |
| Desktop (≥ lg) | Fixed top bar | max-w-7xl | 4-col grid (quarterly) | max-w-2xl form |

**Anti-patterns:**
- Never use `h-screen` — use `min-h-[100dvh]` (iOS Safari safe)
- Never use `w-[calc(33%-1rem)]` — use `grid-cols-3 gap-4`
- All asymmetric layouts must collapse to single-column on mobile
- Horizontal scroll is never acceptable on mobile

---

## 8. Current Audit — Issues + Fixes

### Critical (fix immediately)

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | `globals.css` | Font: Arial (not brand) | Install Geist, wire into layout |
| 2 | `globals.css` | `--primary` is `#1B6B59` (wrong brand color) | Replace with `#013557` navy |
| 3 | `components/ui/badge.tsx` | Hardcoded `amber-*` and `red-*` Tailwind classes | Use semantic CSS token vars |
| 4 | `portal/dashboard/page.tsx` | `Loader2 animate-spin` on data load | Replace with `CalendarSkeleton` component |
| 5 | `portal/onboarding/page.tsx` | Same `Loader2` pattern | Same fix |
| 6 | All 4 portal pages | Session check duplicated | Use `withPortalSession` HOC |
| 7 | `components/checkwise/portal/requirement-status-badge.tsx` | Static `STATUS_VARIANT` map won't scale | Token-based status map from `lib/types.ts` |

### High (fix before V1.3)

| # | File | Issue | Fix |
|---|------|-------|-----|
| 8 | `components/checkwise/intake-wizard.tsx` | 702-line monolith | Extract: `ContextStep`, `RequirementStep`, `ReviewStep` |
| 9 | 3 files | `ValidationSignal` type duplicated | Centralize to `lib/types.ts` |
| 10 | `components/ui/select.tsx` | HTML native select (no custom styling) | Replace with Radix Select |
| 11 | All pages | Error div: 3 different patterns | Use single `<Alert>` component |
| 12 | `app/portal/upload/page.tsx` | `useSearchParams()` without validation | Sanitize before prefill |
| 13 | `lib/portal-session.ts` | Session in localStorage, plain text | Migrate to httpOnly cookies (V2) |

### Medium (design debt)

| # | File | Issue | Fix |
|---|------|-------|-----|
| 14 | `app/page.tsx` | 3-column equal card grid at bottom | 2-column zig-zag or horizontal layout |
| 15 | Entire portal | No `lg:` or `xl:` breakpoints used | Add responsive breakpoints to calendar, forms |
| 16 | `components/checkwise/portal/compliance-calendar.tsx` | Month button ternary styling not CVA | Extract `MonthButton` with CVA variants |
| 17 | All forms | No Zod validation | Add Zod schema per form |
| 18 | `app/portal/*/page.tsx` | No empty states defined | Add empty state for each list/data view |

---

## 9. Implementation Plan

### Phase 1 — Token Foundation (Week 1)

Estimated: 4–6 hours. Zero UX change risk. Pure under-the-hood.

1. [ ] `npm install geist @phosphor-icons/react`
2. [ ] Wire `GeistSans` + `GeistMono` in `app/layout.tsx`
3. [ ] Rewrite `globals.css` — add primitive token layer, update semantic tokens, align brand colors
4. [ ] Update `tailwind.config.ts` — new shadow scale, radius scale, semantic color bridge
5. [ ] Fix `Badge` component — replace hardcoded Tailwind with semantic token CSS vars
6. [ ] Create `lib/types.ts` — consolidate `ValidationSignal`, `RequirementStatus`, `ConfidenceLevel`
7. [ ] Create `withPortalSession` HOC — remove 4x session check duplication

**Validation:** Run existing pages, verify colors render correctly, no visual regression on production code.

### Phase 2 — Missing Primitives (Week 2)

Estimated: 8–12 hours. Establishes the component library.

1. [ ] `Field` — Label + Input + Helper + Error composed primitive
2. [ ] `Skeleton` — with shimmer animation, sized variants
3. [ ] `Alert` — variants: info, success, warning, error + title + description + action
4. [ ] `Progress` — determinate + indeterminate variants
5. [ ] `Spinner` — inline button spinner (replaces all `Loader2 animate-spin`)
6. [ ] `Checkbox` — Radix-based, with label integration
7. [ ] `Select` — Radix-based, replacing HTML native select
8. [ ] `Tabs` — Radix-based with content panel

**Validation:** Create stories or standalone test pages for each primitive.

### Phase 3 — Loading + Error Patterns (Week 2–3)

Estimated: 4–6 hours. High user-perceived quality impact.

1. [ ] `CalendarSkeleton` — replace `Loader2` in dashboard
2. [ ] `ChecklistSkeleton` — replace `Loader2` in onboarding
3. [ ] `ErrorScreen` — replace ad-hoc error divs across all pages
4. [ ] Empty states — add to every data view (calendar, document list, checklist)

### Phase 4 — Compositions Refactor (Week 3–4)

Estimated: 10–16 hours. Maintainability + scalability.

1. [ ] Extract `IntakeWizard` steps into `ContextStep`, `RequirementGroupStep`, `ReviewStep`
2. [ ] Extract `MonthButton` from `ComplianceCalendar` with CVA variants
3. [ ] Add Zod validation to `ProviderAccessForm`
4. [ ] Add Zod validation to `DocumentSubmissionForm`
5. [ ] Create `RequirementStatusBadge` v2 using token-based status map
6. [ ] Add `PeriodSelector` composition

### Phase 5 — AI/OCR Readiness (Before V0.5 backend)

Estimated: 6–8 hours. Future-proofs the frontend for AI extraction phase.

1. [ ] `ConfidenceBadge` component (high/medium/low/none states)
2. [ ] `MetadataReviewPanel` composition
3. [ ] `MetadataFieldRow` — field name + extracted value + confidence + edit action
4. [ ] `ReviewFlagCard` — reviewer notes, flags, and rejection reasons
5. [ ] Add AI confidence CSS tokens to `globals.css` (already specced above)

---

## Appendix A — globals.css (complete rewrite)

The final `globals.css` after Phase 1 implementation:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

/* ── Primitive Tokens ────────────────────────────────── */
:root {
  /* Navy */
  --navy-50:   204 100%  97%;
  --navy-100:  204  90%  92%;
  --navy-200:  204  85%  82%;
  --navy-300:  204  80%  68%;
  --navy-400:  204  78%  52%;
  --navy-500:  204  93%  38%;
  --navy-600:  204  96%  28%;
  --navy-700:  204  97%  21%;
  --navy-800:  204  98%  17%;
  --navy-900:  204  99%  12%;
  --navy-950:  204 100%   8%;

  /* Teal */
  --teal-50:   175  90%  96%;
  --teal-100:  175  88%  88%;
  --teal-200:  175  86%  74%;
  --teal-300:  175  88%  60%;
  --teal-400:  175  89%  50%;
  --teal-500:  175  91%  40%;
  --teal-600:  175  91%  34%;
  --teal-700:  175  92%  27%;
  --teal-800:  175  92%  20%;
  --teal-900:  175  93%  14%;

  /* Gray */
  --gray-25:   210  20%  99%;
  --gray-50:   210  20%  98%;
  --gray-100:  210  18%  94%;
  --gray-200:  214  18%  88%;
  --gray-300:  214  16%  76%;
  --gray-400:  215  14%  60%;
  --gray-500:  215  14%  42%;
  --gray-600:  215  16%  34%;
  --gray-700:  215  18%  26%;
  --gray-800:  220  20%  20%;
  --gray-900:  222  24%  16%;
  --gray-950:  222  28%  13%;

  /* Status */
  --green-50:  142  76%  95%;
  --green-100: 142  70%  85%;
  --green-500: 142  76%  36%;
  --green-700: 142  80%  26%;

  --amber-50:   38  90%  95%;
  --amber-100:  38  85%  85%;
  --amber-500:  38  92%  50%;
  --amber-700:  38  90%  36%;

  --red-50:    0  90%  96%;
  --red-100:   0  80%  88%;
  --red-500:   0  72%  45%;
  --red-700:   0  76%  34%;

  --blue-50:   214  80%  96%;
  --blue-100:  214  70%  88%;
  --blue-500:  214  89%  52%;
  --blue-700:  214  89%  38%;
}

/* ── Semantic Tokens ─────────────────────────────────── */
:root {
  /* Surfaces */
  --background:           var(--gray-50);
  --surface-page:         hsl(var(--gray-50));
  --surface-raised:       hsl(0 0% 100%);
  --surface-sunken:       hsl(var(--gray-100));
  --surface-hover:        hsl(var(--gray-50));
  --surface-selected:     hsl(var(--navy-50));
  --surface-brand:        hsl(var(--navy-800));
  --surface-brand-muted:  hsl(var(--navy-50));
  --surface-teal-muted:   hsl(var(--teal-50));

  /* Text */
  --foreground:           var(--gray-950);
  --text-primary:         hsl(var(--gray-950));
  --text-secondary:       hsl(var(--gray-500));
  --text-tertiary:        hsl(var(--gray-400));
  --text-disabled:        hsl(var(--gray-300));
  --text-inverse:         hsl(0 0% 100%);
  --text-link:            hsl(var(--navy-700));
  --text-brand:           hsl(var(--navy-800));

  /* Borders */
  --border:               var(--gray-200);
  --border-subtle:        hsl(var(--gray-100));
  --border-default:       hsl(var(--gray-200));
  --border-strong:        hsl(var(--gray-300));
  --border-focus:         hsl(var(--navy-500));
  --border-brand:         hsl(var(--navy-800));
  --border-error:         hsl(var(--red-500));
  --border-success:       hsl(var(--green-500));

  /* Interactive */
  --primary:                    var(--navy-800);
  --primary-foreground:         0 0% 100%;
  --ring:                       var(--navy-500);
  --input:                      var(--gray-100);
  --interactive-primary:        hsl(var(--navy-800));
  --interactive-primary-hover:  hsl(var(--navy-700));
  --interactive-primary-active: hsl(var(--navy-900));
  --interactive-secondary:      hsl(var(--teal-500));
  --interactive-ghost-hover:    hsl(var(--gray-100));
  --interactive-destructive:    hsl(var(--red-500));

  /* Components */
  --secondary:            var(--teal-500);
  --secondary-foreground: 0 0% 100%;
  --muted:                var(--gray-100);
  --muted-foreground:     var(--gray-500);
  --accent:               var(--navy-50);
  --accent-foreground:    var(--navy-800);
  --destructive:          var(--red-500);
  --destructive-foreground: 0 0% 100%;

  /* Status */
  --status-success-text:  hsl(var(--green-700));
  --status-success-bg:    hsl(var(--green-50));
  --status-success-border:hsl(var(--green-100));
  --status-warning-text:  hsl(var(--amber-700));
  --status-warning-bg:    hsl(var(--amber-50));
  --status-warning-border:hsl(var(--amber-100));
  --status-error-text:    hsl(var(--red-700));
  --status-error-bg:      hsl(var(--red-50));
  --status-error-border:  hsl(var(--red-100));
  --status-info-text:     hsl(var(--blue-700));
  --status-info-bg:       hsl(var(--blue-50));
  --status-info-border:   hsl(var(--blue-100));

  /* Document states */
  --doc-pending-text:     hsl(var(--amber-700));
  --doc-pending-bg:       hsl(var(--amber-50));
  --doc-uploaded-text:    hsl(var(--blue-700));
  --doc-uploaded-bg:      hsl(var(--blue-50));
  --doc-in-review-text:   hsl(var(--navy-700));
  --doc-in-review-bg:     hsl(var(--navy-50));
  --doc-approved-text:    hsl(var(--green-700));
  --doc-approved-bg:      hsl(var(--green-50));
  --doc-rejected-text:    hsl(var(--red-700));
  --doc-rejected-bg:      hsl(var(--red-50));
  --doc-expired-text:     hsl(30 80% 38%);
  --doc-expired-bg:       hsl(30 80% 96%);

  /* AI confidence */
  --confidence-high-text:   hsl(var(--green-700));
  --confidence-high-bg:     hsl(var(--green-50));
  --confidence-medium-text: hsl(var(--amber-700));
  --confidence-medium-bg:   hsl(var(--amber-50));
  --confidence-low-text:    hsl(24 91% 38%);
  --confidence-low-bg:      hsl(24 91% 96%);
  --confidence-none-text:   hsl(var(--gray-500));
  --confidence-none-bg:     hsl(var(--gray-100));
}

/* ── Animation ───────────────────────────────────────── */
@keyframes shimmer {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

@keyframes fade-in {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ── Global Reset ────────────────────────────────────── */
* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--surface-page);
  color: var(--text-primary);
  font-family: var(--font-geist-sans), 'Arial', sans-serif;
  font-size: 14px;
  line-height: 1.6;
  letter-spacing: 0;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

button, input, select, textarea {
  font: inherit;
}

/* ── Mono Utility ────────────────────────────────────── */
.font-mono, code, pre {
  font-family: var(--font-geist-mono), 'Courier New', monospace;
}
```

---

## Appendix B — tailwind.config.ts (complete rewrite)

```ts
import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-geist-sans)", "Arial", "sans-serif"],
        mono: ["var(--font-geist-mono)", "Courier New", "monospace"],
      },
      colors: {
        border: "hsl(var(--border-default, var(--gray-200)))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
      },
      borderRadius: {
        none: "0",
        sharp: "4px",
        sm: "6px",
        DEFAULT: "8px",
        md: "10px",
        lg: "12px",
        xl: "16px",
        "2xl": "20px",
        full: "9999px",
      },
      boxShadow: {
        none: "none",
        xs: "0 1px 2px rgba(1, 53, 87, 0.06)",
        sm: "0 2px 8px rgba(1, 53, 87, 0.08), 0 1px 2px rgba(1, 53, 87, 0.04)",
        DEFAULT: "0 2px 8px rgba(1, 53, 87, 0.08), 0 1px 2px rgba(1, 53, 87, 0.04)",
        md: "0 4px 16px rgba(1, 53, 87, 0.10), 0 2px 4px rgba(1, 53, 87, 0.06)",
        lg: "0 12px 40px rgba(1, 53, 87, 0.12), 0 4px 12px rgba(1, 53, 87, 0.08)",
        xl: "0 24px 64px rgba(1, 53, 87, 0.14), 0 8px 20px rgba(1, 53, 87, 0.08)",
        soft: "0 2px 8px rgba(1, 53, 87, 0.08), 0 1px 2px rgba(1, 53, 87, 0.04)",
      },
      animation: {
        shimmer: "shimmer 1.5s infinite",
        "fade-in": "fade-in 0.25s ease-out",
      },
      transitionTimingFunction: {
        enter: "cubic-bezier(0.16, 1, 0.3, 1)",
        exit: "cubic-bezier(0.4, 0, 1, 1)",
        spring: "cubic-bezier(0.34, 1.56, 0.64, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
```

---

*Last updated: 2026-05-14 — CheckWise Design System v1.0*
