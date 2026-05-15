# CheckWise Design Asset Manifest

Last verified: 2026-05-15

## Canonical Asset Source

Use this folder as the canonical design asset source for future frontend redesign work:

`docs/design-system/claude-design-v0.1/`

The older `design-concepts/` folder contains the same logo and inspiration images with slightly different filename punctuation. Keep it as historical source material, but prefer the `docs/design-system/claude-design-v0.1/` copies when writing prompts, implementation plans, or component specs.

## Brand Assets

| File | Dimensions | Recommended Use |
|---|---:|---|
| `assets/checkwise-mark.svg` | SVG | Preferred product mark for app UI, favicon candidates, small icon contexts |
| `uploads/CW sin fondo.png` | 600x337 | Product logo/mark reference with transparent-style presentation |
| `uploads/CheckWise Fon Blanco.jpg` | 500x500 | Logo on white background reference |
| `uploads/CheckWise IMPI.jpg` | 500x500 | Registered/brand reference, not a primary UI asset |
| `uploads/CheckWise Powered by Legal Shelf.png` | 1920x1080 | External/provider-facing endorsement reference |
| `uploads/HTML CheckWise.png` | 1920x1080 | Brand/HTML preview reference |

## Inspiration Screenshots

These files are visual references only. Do not copy them into the product UI. Use them to infer spacing, density, hierarchy, and pattern direction.

| File | Dimensions |
|---|---:|
| `uploads/Screenshot 2026-05-14 at 12.15.38 PM.png` | 1262x898 |
| `uploads/Screenshot 2026-05-14 at 12.15.48 PM.png` | 1720x1160 |
| `uploads/Screenshot 2026-05-14 at 12.16.12 PM.png` | 714x1114 |
| `uploads/Screenshot 2026-05-14 at 12.16.25 PM.png` | 1304x982 |
| `uploads/Screenshot 2026-05-14 at 12.16.51 PM.png` | 528x1242 |
| `uploads/Screenshot 2026-05-14 at 12.20.29 PM.png` | 616x1220 |
| `uploads/Screenshot 2026-05-14 at 12.20.43 PM.png` | 582x1266 |
| `uploads/Screenshot 2026-05-14 at 12.21.10 PM.png` | 528x1242 |
| `uploads/Screenshot 2026-05-14 at 12.21.19 PM.png` | 1240x806 |
| `uploads/Screenshot 2026-05-14 at 12.25.01 PM.png` | 516x744 |
| `uploads/Screenshot 2026-05-14 at 12.25.14 PM.png` | 488x640 |
| `uploads/Screenshot 2026-05-14 at 12.25.24 PM.png` | 1150x630 |
| `uploads/Screenshot 2026-05-14 at 12.26.05 PM.png` | 1154x514 |
| `uploads/Screenshot 2026-05-14 at 12.26.13 PM.png` | 506x578 |
| `uploads/Screenshot 2026-05-14 at 12.28.18 PM.png` | 752x614 |
| `uploads/f0709d587d46c1ae2b92072d4ffeb657.jpg` | 1199x1616 |

## Design Docs In Package

| File | Role |
|---|---|
| `AUDIT.md` | Verified package inventory and implementation caution notes |
| `uploads/DESIGN_SYSTEM.md` | Long-form product/design-system spec exported with Claude Design |
| `uploads/CHECKWISE_1_5.md` | Product workflow/context reference |
| `uploads/CHECKWISE_1_6.md` | Product workflow/context reference |
| `v0.2/README.md` | Phase 1 patch guidance from Claude Design export |
| `v0.2/INSTALL.md` | Installation/wiring guidance from Claude Design export |
| `v0.2/globals.css` | Token reference, not a drop-in replacement |
| `v0.2/tailwind.config.ts` | Tailwind reference, not a drop-in replacement |

## Missing Source Files

The HTML preview references these files, but they were not present in the export:

- `tokens.css`
- `base.css`
- `primitives.css`
- `patterns.css`
- `icons.jsx`
- `foundations.jsx`
- `primitives.jsx`
- `pattern-dashboard.jsx`
- `pattern-upload-ocr.jsx`
- `pattern-onboarding-responsive.jsx`
- `app.jsx`

If these files are later recovered, add them under `docs/design-system/claude-design-v0.1/` and update `AUDIT.md` plus this manifest.
