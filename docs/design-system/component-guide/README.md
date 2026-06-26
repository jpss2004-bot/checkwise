# CheckWise · Component Guide

A visual design-system & component reference for CheckWise, generated from the **live codebase** (not an idealized spec). Every color swatch and component sample uses the real production token values copied verbatim from `apps/web/app/globals.css`.

## Files

- **`index.html`** — interactive guide. Open in any browser. Click a color swatch to copy its token. Loads Geist / Geist Mono / Schibsted Grotesk from Google Fonts (falls back to system fonts offline).
- **`CheckWise-Design-System.pdf`** — 23-page print/share version.
- **`assets/`** — the official brand PNGs (also live in `apps/web/public/brand/`).

## What it covers

Brand & logo · full color system (primitive → semantic → component tokens) · typography · spacing & density tiers · radius · elevation · **the 136 Phosphor icons actually used in the app** · components as labeled state-grids (buttons, badges, form controls, feedback, containers) · the REPSE document-state & AI-confidence vocabulary · domain components · the four navigation shells · the marketing subsystem · and an appendix with a source-file map and mobile-translation notes.

## Regenerating the PDF

The PDF is rendered from `index.html` with headless Chrome. From an ASCII path (the repo path's spaces/em-dash break `file://` URLs, so copy out first):

```sh
cp -R . /tmp/cw-ds-guide
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --no-pdf-header-footer --virtual-time-budget=14000 \
  --print-to-pdf=/tmp/cw-ds-guide/CheckWise-Design-System.pdf \
  "file:///tmp/cw-ds-guide/index.html"
cp /tmp/cw-ds-guide/CheckWise-Design-System.pdf ./CheckWise-Design-System.pdf
```

## Source of truth & drift

Values are taken from the **shipped code**, which is canonical. The older narrative spec `docs/DESIGN_SYSTEM.md` (v1.0, 2026-05-14) has drifted in places — e.g. it lists `expired`=orange, `in_review`=navy, `pending`=amber, and a 4-variant button, whereas production now has `expired`=red, `in_review`=blue, `pending`=gray, and 6 button variants. When in doubt, `globals.css` + `components/ui/*` win.

_Generated 2026-06-26._
