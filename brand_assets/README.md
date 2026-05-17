# `brand_assets/` — Canonical CheckWise brand assets

Source-of-truth logo files for the CheckWise product. This is the only
folder agents should treat as authoritative for CheckWise marks.

## Contents

- `Logos CW/`
  - `CW sin fondo.png` — primary mark, transparent background
  - `CheckWise Fon Blanco.jpg` — primary mark on white
  - `CheckWise IMPI.jpg` — IMPI registration variant
  - `CheckWise Powered by Legal Shelf.png` — co-brand lockup
  - `HTML CheckWise.png` — favicon / HTML embed variant

## What this is *not*

- **Not** the Legal Shelf parent-brand identity. That lives at
  `../../brand-identity/` (one level outside the repo), which holds the
  Legal Shelf identity PDF, HTML guide, and research/QA renders.
- **Not** the design-exploration folder. That lives at `../design-concepts/`
  and holds inspiration screenshots only (no logos).
- **Not** a screenshot store. Product screenshots used by the demo
  guide live at `../demo_assets/screenshots/`.

## When to reach into other folders

| Need                                           | Look in                                  |
| ---------------------------------------------- | ---------------------------------------- |
| CheckWise logo for app / marketing UI          | `brand_assets/Logos CW/` *(here)*        |
| Legal Shelf parent brand colors / typography   | `../../brand-identity/`                  |
| Visual inspiration / mood references           | `../design-concepts/inspo-screenshots/`  |
| Demo screenshots used in PDF / marketing       | `../demo_assets/screenshots/`            |
| Runtime design tokens / Tailwind config        | `../frontend/app/globals.css`            |
