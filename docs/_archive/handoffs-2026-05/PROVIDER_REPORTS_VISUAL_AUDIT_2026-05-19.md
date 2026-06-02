# Provider Reports — Visual Audit (Why It Reads Wireframe)

> **Date:** 2026-05-19
> **Subject:** /portal/reports list, /portal/reports/[id] editor, /portal/reports/[id]/print, and the 10 block components.
> **Method:** Reviewed 3 prod screenshots ([25-portal-reports.png](audit-screenshots/2026-05-18-system-audit/25-portal-reports.png), [26-portal-report-print.png](audit-screenshots/2026-05-18-system-audit/26-portal-report-print.png), [19-reports-editor.png](executive-evidence/screenshots/19-reports-editor.png)) against the source. Cross-referenced with [block-header.tsx](../apps/web/components/checkwise/reports/block-header.tsx), [kpi-strip.tsx](../apps/web/components/checkwise/reports/blocks/kpi-strip.tsx), [reports-list-view.tsx](../apps/web/components/checkwise/reports/reports-list-view.tsx), and the print page.
> **Verdict:** the "wireframe feel" comes from **5 specific code patterns** repeated across surfaces. One of them is dominant — fix it first and the perceived polish jump is significant.

---

## TL;DR — the dominant offender

**Every report block renders a "block-type label" eyebrow (`TEXTO`, `TIRA DE KPIS`, `DIVISOR`, `RESUMEN EJECUTIVO`, …) above its content. In the editor that's an authoring aid. In the print view and in any read-only view it leaks as dev scaffolding.**

The print screenshot makes it obvious: half of what the eye sees on the page is type labels, not content.

- **Single line of code drives it:** [block-header.tsx:59](../apps/web/components/checkwise/reports/block-header.tsx)
  ```tsx
  <span className="cw-eyebrow">{label}</span>
  ```
- **No `print:hidden`, no read-only branch.** The whole `<BlockHeader>` is rendered for every block, with the type label always visible.
- **Why it persisted:** a prior pass (I-06 in the 2026-05-18 audit) hid the raw machine code (`text`, `kpi_strip`) in read-only views but only the *secondary* span. The primary human label was missed.

**Fix:** hide the entire BlockHeader chrome when `editable === false`, and add `print:hidden` to the cw-eyebrow label in editor mode so the print pipeline (which uses Canvas in read-only mode anyway) double-fences against it. 2 lines of change. **Biggest visual-polish jump per character of edit in this audit.**

---

## Findings, ranked by impact

### F1 — Block-type labels dominate the print view ⚠️ HIGHEST IMPACT

**What you see:** `Aa TEXTO`, `TIRA DE KPIS`, `— DIVISOR` headers above every block on the printable page. Reads as a wireframe / outline, not a finished compliance document.

**Source:** [block-header.tsx:59](../apps/web/components/checkwise/reports/block-header.tsx) renders `<span className="cw-eyebrow">{label}</span>` unconditionally. The whole `<BlockHeader>` component is mounted by Canvas for every block in both editable and read-only modes; only the action buttons (lock, delete, regenerate) are gated on `editable`.

**Where it leaks:**
- /portal/reports/[id]/print (worst — should be invisible chrome)
- /portal/reports/[id] read-only state (e.g. when canvas is locked or status === "shared")
- HTML email / signed-share rendering (if ever wired)

**Minimum-viable fix (~5 lines, one file):**

In [block-header.tsx](../apps/web/components/checkwise/reports/block-header.tsx):

1. **Skip the whole component when not editable** — wrap the `return` with `if (!editable) return null;` and let blocks render without any chrome on top. Tradeoff: read-only viewers also lose the icon. Most blocks already render their own title inside (Executive Summary's h2, KPI strip's labels, etc.), so the icon is decorative.

   **OR**

2. **Keep the icon but drop the label + border** in read-only mode:
   ```tsx
   if (!editable) {
     return null; // or render just <IconComponent /> if you want a glyph
   }
   ```

3. **In editor mode, mark the label as `print:hidden`** as belt-and-braces:
   ```tsx
   <span className="cw-eyebrow print:hidden">{label}</span>
   ```

Recommendation: **option 1 — return null when not editable.** Cleanest, biggest visual jump. The blocks already carry their own titles inside.

---

### F2 — KPI rows read as plain text, not data viz

**What you see:** the Compliance Pulse strip on /portal/reports renders metrics as `CUMPLIMIENTO 78%  EN RIESGO 1  VENCIDOS 0  PRÓXIMO EN 12d` — small uppercase eyebrow labels with monospace numbers, on a thin top/bottom-bordered strip. No color, no chart, no hierarchy.

**Source:** [kpi-strip.tsx:113-127](../apps/web/components/checkwise/reports/blocks/kpi-strip.tsx) uses the `cw-metadata-strip` pattern — a row of label/value pairs. The pattern is intentional (V2.x called out "identical card grids" as anti-patterns and replaced them with metadata strips), but the result is too flat for a compliance dashboard's headline numbers.

**Where it leaks:**
- /portal/reports CompliancePulseStrip
- /portal/dashboard MetadataStrip
- kpi_strip block in any report

**Why it feels generic:**
- All metrics get equal visual weight. A 78% compliance score competes with a "PRÓXIMO EN 12d" duration for attention.
- The eyebrow + value pattern reads as a list, not a dashboard.
- No color anchoring — green for safe, amber for at-risk, red for blocked. The numbers are all monospace neutral.

**Minimum-viable fix (~30 lines, mostly in kpi-strip.tsx):**

Promote the **leading metric** visually:
- Primary: 2× font size, primary color, optional trend arrow next to it.
- Secondary metrics: keep current label/value pattern but smaller.
- Add semantic color hints to values based on metric_key (e.g. compliance_pct ≥ 80 = green, 60–79 = amber, < 60 = red; overdue_count > 0 = red).

This is one block, doesn't touch layout. Same data, much sharper reading.

---

### F3 — `SIN SELLO DE ACTUALIZACIÓN` banner clutters the print view

**What you see:** below the KPI strip in the print screenshot, a small all-caps "SIN SELLO DE ACTUALIZACIÓN" badge. Reads as a developer note ("no fetched_at present in data payload"), not a thing a reader of the report cares about.

**Source:** [freshness-label.tsx](../apps/web/components/checkwise/reports/freshness-label.tsx) renders this fallback when `data.fetched_at` is missing. Useful in the editor — tells the author the block hasn't been hydrated yet. Useless in print.

**Minimum-viable fix:** in the FreshnessLabel component, when `editable === false` AND `fetched_at == null`, **render nothing**. The "Datos al [date]" line is valuable when there's a date; the "no seal" warning is not valuable to a reader.

```tsx
// inside FreshnessLabel, top of return
if (!fetchedAt && !showInEditor) return null;
```

(Or just early-return when there's no fetchedAt period — the editor can show the "Actualizar" button via a separate component.)

---

### F4 — Preset cards on the list page are equal-weight and undifferentiated

**What you see:** 3 cards under "Plantillas" — "Mi estado de cumplimiento" / "Documentos faltantes" / "Rechazos recientes" — same size, same icon style, same `[Usar plantilla]` button. The user has no signal about which is the recommended starting point. Reads as a checkbox list of options, not a curated entry point.

**Source:** [reports-list-view.tsx:248-260](../apps/web/components/checkwise/reports/reports-list-view.tsx) maps presets to identical cards.

**Why it matters for Jorge's test:** he doesn't know that `provider-current-state` is the only one that produces meaningful data on a fresh workspace. Visual hierarchy could nudge him there without you having to brief him.

**Minimum-viable fix (~15 lines):**
- Mark one preset as "recommended" (config flag on ReportPreset).
- Render the recommended one larger, with primary-color border, and a "Empieza aquí" eyebrow.
- Demote the other two to secondary visual weight (smaller, neutral border).

OR — minimum-er fix: just add a "✨ Recomendado" pill on the first preset in the list. One badge, big effect on entry-point clarity.

---

### F5 — Cover-page metadata seal is too prominent

**What you see:** in the print screenshot, just under the title "Riesgo del portafolio · Q2 2026", a row of metadata: `AUDIENCIA Para el cliente · ESTADO Activo · VERSIÓN v1 · GENERADO 18 de mayo de 2026 a las 6:57 p.m.` followed by a separate badge `🕐 GENERADO EL 18 DE MAYO DE 2026 A LAS 6:57 P.M.`. The badge **duplicates** the inline metadata line above it, and is rendered in a bordered all-caps box that draws attention away from the report's actual content.

**Source:** [app/portal/reports/[id]/print/page.tsx](../apps/web/app/portal/reports/[id]/print/page.tsx) — the cover-page section composes title + subtitle + metadata-strip + a separate `fetched_at`-derived seal.

**Minimum-viable fix:** remove the duplicate seal badge. The metadata-strip already shows the generated timestamp. If the freshness anchor matters, fold it into the existing metadata row instead of a separate boxed badge.

---

### F6 — Editor block-action chrome is visible but visually busy

**What you see:** in the editor screenshot (19-reports-editor.png), every block has a chrome row with: drag handle (on hover), icon, type-label, raw type code in mono, then on the right side icons for explain / regenerate / lock / delete. With 4+ blocks in a report, this is a lot of repeated chrome.

**Source:** [block-header.tsx:48-130](../apps/web/components/checkwise/reports/block-header.tsx).

**Why it feels generic:** action buttons sit on hover-reveal but the chrome row itself is always visible. The block becomes a "card with a header" instead of a piece of content.

**Minimum-viable fix:** keep the actions on hover, but only show the **icon + label** when the block is selected/hovered; otherwise render minimal chrome (just a thin focus line on hover). This makes the canvas feel like a document, not a forms editor.

Lower-effort alternative: remove the raw type-code monospace span (`{type}` next to the label) entirely. The icon + Spanish label is enough authoring context.

```tsx
// in editor branch, around line 60-64 — delete this whole conditional span:
{editable && (
  <span className="cw-print-meta-code font-mono text-[10px] ...">
    {type}
  </span>
)}
```

---

### F7 — `Pulse de cumplimiento` strip uses 4-up grid (V2.x anti-pattern resurfacing)

**What you see:** the top of /portal/reports renders 4 equal-width cards (ESTADO GENERAL · ATENCIÓN REQUERIDA · PRÓXIMOS VENCIMIENTOS · ACCIONES PRIORITARIAS). Each is a bordered box of equal weight.

**Note:** [docs/CHECKWISE_2_0.md](_archive/CHECKWISE_2_0.md) explicitly called out and removed F2 "identical-card grids" elsewhere ("All F2 identical-card grids killed (`/admin/dashboard` 4-up, `/client/dashboard` 4-up, `/portal/onboarding` 2×2)"). The CompliancePulseStrip on `/portal/reports` is the same anti-pattern that survived the V2.1 sweep.

**Source:** the strip component shipped in P1.6 (commit `464b2ba`).

**Minimum-viable fix:** asymmetric layout — a wide-left primary card (semaphore + compliance %) plus a stack of 2-3 secondary cards on the right. Or one full-width hero card for the headline metric, with a horizontal row of secondaries below.

---

### F8 — Divider blocks render their label in `cw-eyebrow` style (small, all-caps, tracked)

**What you see:** in the print screenshot, `DETALLE POR PROVEEDOR` appears centered between two horizontal lines — but in tiny all-caps eyebrow style, almost as small as the type-label leak from F1.

**Source:** [divider.tsx:31](../apps/web/components/checkwise/reports/blocks/divider.tsx) — the optional label is rendered with `className="cw-eyebrow ..."` so it gets the eyebrow treatment.

**Why it's wrong:** a section divider with a label is essentially a section heading. Sections in a printed report should feel like H2-level demarcations, not eyebrow labels.

**Minimum-viable fix:** when the divider has a label, render it as a small section heading (e.g. larger size, sentence case or capitalized, primary text color) rather than eyebrow chrome.

---

## Summary table

| ID | Surface | Severity | One-line fix | LoC |
|---|---|---|---|---|
| F1 | Print + read-only | ⚠️ Highest | `if (!editable) return null;` in BlockHeader; add `print:hidden` to label | ~5 |
| F2 | KPI strip everywhere | High | Promote first metric + add semantic color on values | ~30 |
| F3 | Print view | High | Hide "SIN SELLO DE ACTUALIZACIÓN" in read-only mode | ~3 |
| F4 | List page | Medium | Mark recommended preset with "✨ Recomendado" pill OR make it larger | ~15 |
| F5 | Print cover | Medium | Remove duplicate "GENERADO EL …" badge | ~5 |
| F6 | Editor | Medium | Drop raw type-code monospace span next to label | ~5 |
| F7 | List page strip | Medium | Asymmetric layout, kill the 4-up grid | ~40 |
| F8 | Print dividers | Low | Render dividers' optional labels as section headings | ~10 |

Total estimated change to land all 8: ~115 lines across ~6 files. None require new dependencies. None restructure layout. None touch the data layer.

---

## Recommended fix order (high impact first)

1. **F1** (kill block-type labels in read-only/print) — single-line change with the biggest visible delta. Print view stops reading like a wireframe.
2. **F3** (kill `SIN SELLO DE ACTUALIZACIÓN` in print) — pairs naturally with F1; finishes cleaning print.
3. **F5** (remove duplicate cover seal) — finishes the print-view polish.
4. **F6** (drop raw type code in editor header) — tightens the editor.
5. **F2** (promote primary KPI + semantic color) — adds character to numerical surfaces.
6. **F4** (highlight recommended preset) — improves Jorge's first-click clarity.
7. **F7** (break the Compliance Pulse 4-up grid) — bigger structural touch; do last.
8. **F8** (divider labels → section headings) — small finishing fix.

If we only had 15 minutes before Jorge's test: do F1, F3, F5 — print view alone gains the most.

If we had 1 hour: F1 + F3 + F5 + F6 + F2.

---

## What this audit does NOT recommend

- No new dependencies (no chart library, no design-system overhaul).
- No layout restructure beyond F7's asymmetric grid.
- No copy changes beyond F5's seal removal.
- No color-token redefinition; the existing `--status-*` and `--text-*` tokens are sufficient for F2's semantic coloring.
- No backend changes. The data shape stays identical.

Each fix is reversible (revert the file). None touches user-test readiness.
