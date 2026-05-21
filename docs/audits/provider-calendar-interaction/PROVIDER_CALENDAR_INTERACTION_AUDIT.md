# Provider Calendar Interaction Audit

**Date:** 2026-05-21
**Branch:** `main` (uncommitted working tree)
**Scope:** Provider-facing calendar at `/portal/calendar` only. Touches reusable cell primitives and links into the existing submission detail route. No backend changes.

---

## 1. Objective

Convert the provider calendar from a read-only year overview into a useful **provider action hub** where a provider can clearly understand:

1. What requirements they need to complete
2. What documents they have already uploaded
3. What is missing, pending, approved, rejected, or expired
4. What they can click to upload next
5. What they can click to preview an uploaded document

Two pre-existing UI issues blocked this:

- The hover popover was clipped at the right edge of the grid
- The colored cell edges had a competing-border seam that made cells look unfinished

---

## 2. Current calendar architecture

| Layer | Path | Purpose |
|---|---|---|
| Route | [app/portal/calendar/page.tsx](../../../frontend/app/portal/calendar/page.tsx) | Provider calendar grid + slide-in drawer |
| Cell primitives | [components/checkwise/calendar/](../../../frontend/components/checkwise/calendar/) | `MonthCell`, `CellPopover`, `InstitutionRowHeader`, `types` |
| Calendar API | [`lib/api/portal.ts`](../../../frontend/lib/api/portal.ts) — `getCalendar()` | `GET /api/v1/portal/workspaces/{id}/calendar?year=` |
| Backend endpoint | [`backend/app/api/v1/portal.py`](../../../backend/app/api/v1/portal.py) line 1333 | Returns `CalendarPayload` |
| Backend `_calendar_upload_href()` | `backend/app/api/v1/portal.py:378` | Precomputes per-row upload URL with `requirement_code`, `institution`, `period_key`, `load_type`, `v2`, `replaces` |
| **Reused** — Upload route | [app/portal/upload/page.tsx](../../../frontend/app/portal/upload/page.tsx) | Reads query params; locks context; prefills wizard |
| **Reused** — Submission detail | [app/portal/submissions/[submission_id]/page.tsx](../../../frontend/app/portal/submissions/[submission_id]/page.tsx) | Existing rich detail page: status, reasons, filename, history, lineage, retry CTA |
| Status tokens | [`app/globals.css`](../../../frontend/app/globals.css) lines 157-198 | `--doc-{state}-{bg,text,border}` × 8 states |
| Dev mock | [app/dev/calendar-preview/page.tsx](../../../frontend/app/dev/calendar-preview/page.tsx) | Unauthenticated synthetic-data preview, mirrors the real grid |

### Affected routes / components in this change

- `frontend/app/portal/calendar/page.tsx` — drawer action + ya-enviado notice
- `frontend/components/checkwise/calendar/cell-popover.tsx` — full rewrite (portal + collision)
- `frontend/components/checkwise/calendar/month-cell.tsx` — rewrite (clean edges, icon glyph, popover triggerRef)
- `frontend/app/dev/calendar-preview/page.tsx` — inherits popover/cell changes via shared primitives; no edits required this round
- New file: `docs/audits/provider-calendar-interaction/PROVIDER_CALENDAR_INTERACTION_AUDIT.md` (this file)
- New folder: `docs/audits/provider-calendar-interaction/screenshots/`

### Not touched (deliberately out of scope)

- `backend/app/api/v1/portal.py` (parallel session is editing)
- `frontend/components/checkwise/intake-wizard.tsx`
- `frontend/app/portal/upload/page.tsx`
- `frontend/app/portal/submissions/[submission_id]/page.tsx` (reused as-is)
- Admin and client routes
- Dashboard, expediente, reports

---

## 3. Root cause: popover clipping

**Old implementation** rendered the popover as a sibling of the cell button:

```tsx
<div className="absolute left-1/2 top-full z-30 mt-1.5 w-[280px] -translate-x-1/2 …">
```

This placed the popover inside the cell's wrapper, which lived inside a `<td>` inside a `<table>` inside `<section className="overflow-x-auto">`. Combined with `left-1/2 -translate-x-1/2`:

1. **Stacking** — `z-30` competed with the portal app shell's sticky top bar (also `z-30`)
2. **Clipping** — late months (OCT/NOV/DEC) pushed the centered popover past the right viewport edge with no collision logic
3. **Containment** — the `overflow-x-auto` section technically allowed scroll, but the popover was constrained to its `<td>` parent's stacking context
4. **No flip** — vertically, no fallback when the cell sat near the bottom of the viewport

**Fix.** Rewrote [cell-popover.tsx](../../../frontend/components/checkwise/calendar/cell-popover.tsx) to:

- Render via `createPortal(..., document.body)` so the popover escapes all parent stacking contexts and overflow clips
- Position with `position: fixed` using `getBoundingClientRect()` of the cell button
- Horizontally shift to fit the viewport with an 8px margin on both edges
- Vertically prefer below; flip above if there's no room below
- Use `zIndex: 50` to layer above the sticky header (`z-30`) and below the modal drawer overlay (`z-50` dialog territory)
- Re-position on `scroll` (with `capture: true`) and `resize`
- Share `onEnter` / `onLeave` callbacks with `MonthCell` so the cursor can move from cell to popover without the popover closing (120ms close delay, cancelled on enter)

**Numeric verification (live):**

| Cell | Cell rect | Popover rect | Viewport | Overflow? |
|---|---|---|---|---|
| MAY (centered) | x≈462, w≈63 | x=384, w=300 | 1440 | No |
| DEC (right edge) | x≈1230, w≈63 | x=1132, w=300 → ends at 1432 | 1440 | No (8px margin to edge) |

---

## 4. Root cause: bad cell edges

**Old cell composition:**

```
+— button (border: SEGMENT_BORDER[dominant], i.e., doc-state-colored) ——+
|  [ SegmentBar: bg + border-b border-subtle ]                          |
|  count (mono)                                                         |
+———————————————————————————————————————————+
```

Two problems:

1. **Competing borders.** The button border was colored per state, AND the segment bar had `border-b border-subtle` beneath it. Where the bar ended and the cell body began, two 1px strokes met at slightly different colors → a perceived seam.
2. **State color carried twice.** The segment bar already showed composition; the button border duplicated the same signal less precisely.
3. **No glyph in cell.** State was conveyed by color alone in the cell body (WCAG 1.4.1 risk for color-blind users).

**Fix.** Rewrote [month-cell.tsx](../../../frontend/components/checkwise/calendar/month-cell.tsx):

- **Neutralized cell border** to `--border-subtle` so it reads as structural, not status-bearing. Hover transitions to `--border-default`.
- **Removed the `border-b` seam** under the segment bar — the bar now flows into the cell body without a 1px gray line.
- **Bumped segment bar** to `h-2 lg:h-2.5` so the composition signal is legible on larger screens.
- **Added phosphor icon glyph** of the dominant state next to the count. Single-state cells now read as "✓ 4" or "⌛ 3" instead of "4" with only color to disambiguate. Multi-state cells additionally show a tiny `2↕` indicator to flag mixed composition.
- **Background uses `--surface-raised`** for the resting state; past-month cells get `opacity-50 grayscale-25%`; urgent past keeps full color with an outer rejected-tone ring.

**Status accessibility:**

- The aria-label of each cell button now carries the full state list when there are multiple obligations: `"4 obligaciones en mayo; aprobado, en revisión, pendiente. Toca para ver detalle."`
- The popover items each have a colored dot + `title={DOC_STATE_LABELS[event.state]}` for sighted hover hints and screen-reader announcement.

---

## 5. New interaction model

### Cell click

| What's in the cell | Click target |
|---|---|
| Any cell with ≥1 obligation | Opens the drawer at `events[0]` |
| (Multi-obligation cells) | Hover/focus to open the popover, then click a specific obligation to open the drawer at that one |

### Drawer action button — state-contextual

The drawer's primary action now depends on `event.state` × whether `event.submission_id` is present:

| State | Has submission_id? | Label | Route | Tone |
|---|---|---|---|---|
| `approved` | yes | "Ver documento aprobado" | `/portal/submissions/[id]` | outline |
| `in_review` / `uploaded` | yes | "Ver envío" | `/portal/submissions/[id]` | outline |
| `rejected` | yes | "Revisar rechazo y corregir" | `/portal/submissions/[id]` | primary |
| `needs_review` | yes | "Revisar y corregir" | `/portal/submissions/[id]` | primary |
| `expired` | (either) | "Subir documento actualizado" | `event.href` (upload) | primary |
| `pending` / `empty` | (no) | "Subir documento" | `event.href` (upload) | primary |
| any without submission_id | no | upload-style routes apply | `event.href` | primary |

Implemented at [`page.tsx:drawerAction()`](../../../frontend/app/portal/calendar/page.tsx) below the EventDrawer. The button uses `<Link href={action.href}>` so navigation respects Next.js prefetch and middleware.

### "Ya enviaste un documento" notice

When `event.submission_id` is set, the drawer shows a small advisory line above the action:

> _"Ya enviaste un documento para este requisito. Toca abajo para revisarlo."_

This makes the difference between "this requirement needs you to upload something" and "this requirement already has a submission you can preview" visible immediately, without forcing the user to interpret the state color.

---

## 6. Calendar-to-upload flow

The calendar does NOT re-implement upload routing. The backend's `_calendar_upload_href()` (line 378 in `portal.py`) already precomputes the canonical upload URL per row with all context baked in:

- `requirement_code` — canonical obligation code
- `institution` — SAT / IMSS / INFONAVIT / STPS_REPSE
- `period_key` — backend-canonical period (e.g., `2026-M05`, `2026-Q2`)
- `period_label` — human label
- `load_type`
- `v2=1` when the row carries `accepts_documents` alternatives (Session 3)
- `replaces=<submission_id>` when re-uploading after rejection (Phase 3 lineage)

The calendar drawer's action button consumes `event.href` for upload flows (`pending`, `empty`, `expired`). The upload route ([app/portal/upload/page.tsx](../../../frontend/app/portal/upload/page.tsx)) reads these params, locks context, and prefills the wizard with the matching requirement and (for v2 rows) the alternatives picker.

No upload-route changes were required — the contract was already there.

---

## 7. Uploaded-document preview flow

**No new route created.** The existing [/portal/submissions/[submission_id]](../../../frontend/app/portal/submissions/[submission_id]/page.tsx) page is the reusable preview surface and already carries:

- Status hero + reasons
- Document filename, upload date
- Reviewer comment when rejected
- Validation summary
- Mismatch warnings
- Submission history + status timeline
- Lineage to previous attempts
- Retry CTA when status is actionable

The calendar drawer now links to it whenever `event.submission_id` is populated. This page is also available for future reuse from reports, dashboard, and history — no additional wiring required, just the calendar link added in this round.

Rationale for reuse: the brief explicitly says "Before creating a new route, inspect whether an existing submission detail page already exists. If it exists, improve/reuse it instead of duplicating." The existing page satisfies all the user-facing requirements; duplicating it would have added maintenance cost and divergence risk.

---

## 8. Plain-language UX audit

All user-facing strings in the touched files use plain Spanish:

| Surface | Copy |
|---|---|
| Filter chips | `Todas`, `SAT`, `IMSS`, `INFONAVIT`, `STPS / REPSE` |
| Page title | `Tu año de cumplimiento de un vistazo` |
| Page description | `Cada celda muestra las obligaciones de ese mes; pasa el cursor para ver el detalle o toca para abrir la siguiente acción.` |
| Popover header | `{Mes} · N obligaciones` |
| Popover overflow | `+ N más en esta celda` |
| Filtered empty | `No hay obligaciones para {Institución}.` + `Quitar filtro` |
| Drawer "ya enviado" | `Ya enviaste un documento para este requisito. Toca abajo para revisarlo.` |
| Drawer actions | See table in §5 — all human Spanish phrases |
| Legend | Reused `DocStateBadge` labels: `Aprobado`, `En revisión`, `Enviado`, `Pendiente`, `Necesita revisión`, `Rechazado`, `Vencido`, `Sin cargar` |

**No exposed jargon** in the touched files: no `submission_id`, no `hash`, no `OCR`, no `parser`, no `rule_code`, no `workspace`, no `pipeline`. Internal IDs (e.g., `event.id`, `event.submission_id`) are used only as routing keys, never as primary labels.

---

## 9. Full page audit checklist

| Item | Status | Notes |
|---|---|---|
| Page title | ✅ | Spanish, descriptive |
| Instructions / subtitle | ✅ | Updated to mention hover + click |
| Legend | ✅ | All 8 states, reused `DocStateBadge` |
| Filter chips | ✅ | URL-persisted (`?inst=`), single-select |
| Month navigation | n/a | Year is current-year only; no year picker (out of scope) |
| Current month state | ✅ | Navy column label, per-cell ring, `aria-current` |
| Requirement preview (cells without submission_id) | ✅ | Drawer routes to upload via `event.href` |
| Uploaded document preview (cells with submission_id) | ✅ | Drawer routes to `/portal/submissions/[id]` |
| Empty state (workspace has 0 obligations) | ✅ | Existing branch in page.tsx preserved |
| Filtered empty state | ✅ | "No hay obligaciones para X" + Quitar filtro |
| Loading state | ✅ | Skeletons in header + grid area |
| Error state | ✅ | Inline retry copy, last-loaded grid stays visible |
| Mobile layout | ✅ | Sticky institution column + horizontal month scroll |
| Tablet layout | ✅ | All 12 months fit without scroll |
| Desktop / laptop | ✅ | Fills viewport up to 1536px; breathes beyond |
| Hover state | ✅ | Subtle lift, border darken, popover open |
| Focus state | ✅ | 2px focus ring, popover opens via focus too |
| Click state | ✅ | Opens drawer |
| Keyboard accessibility | Partial | Tab through cells works, Enter opens drawer. No custom shortcuts (user explicitly chose pointer-first in shape phase). |
| Broken links | ✅ | All destinations are existing routes (`/portal/dashboard`, `/portal/submissions/[id]`, `/portal/upload?...`) |
| Route guards | ✅ | `withOnboardingGate` preserved on real page |
| Console errors | ✅ | Verified via preview MCP — only React DevTools install hint, no errors/warnings |
| Hydration errors | ✅ | Verified — page renders without React mismatch warnings |

---

## 10. Files changed

```
M  frontend/app/portal/calendar/page.tsx
M  frontend/components/checkwise/calendar/cell-popover.tsx
M  frontend/components/checkwise/calendar/month-cell.tsx
A  frontend/components/checkwise/calendar/institution-row-header.tsx
A  frontend/components/checkwise/calendar/types.ts
A  frontend/app/dev/calendar-preview/page.tsx
A  docs/audits/provider-calendar-interaction/PROVIDER_CALENDAR_INTERACTION_AUDIT.md
A  docs/audits/provider-calendar-interaction/screenshots/
```

`institution-row-header.tsx`, `types.ts`, and `dev/calendar-preview/page.tsx` were created during earlier rounds of this same redesign effort. They are listed here as part of the calendar primitives now in scope.

---

## 11. Screenshots

Saved under [`docs/audits/provider-calendar-interaction/screenshots/`](./screenshots/):

| Filename | What it shows | Format |
|---|---|---|
| `calendar-overview-after.png` | Desktop 1440×900, full grid | DOM-only (headless Chrome) |
| `calendar-overview-monitor.png` | Big monitor 1680×980, container caps at 2xl with breathing room | DOM-only |
| `calendar-tablet.png` | Tablet 1024×820, all 12 months fit | DOM-only |
| `calendar-mobile.png` | Mobile 390×844, sticky institution column | DOM-only |

**Note on screenshot fidelity.** Tailwind v4 + Next.js dev mode + Chrome `--headless=new --screenshot` flag has a known interaction where CSS chunks load too late for the one-shot capture. The saved PNGs render the DOM structure (counts, layout, icon glyphs, semantic table) but without Tailwind utility classes fully applied. Styled visuals were verified live:

1. **Through this conversation's preview MCP screenshots** (visible inline in the chat history at the messages immediately following each code change)
2. **Numeric DOM-inspect verification** for layout correctness: popover position, cell bounding boxes, computed styles (e.g., `opacity: 0.5; filter: grayscale(0.25)` on past cells, `--surface-raised` background on cells, `--border-subtle` on cell borders)

To regenerate styled screenshots locally:

```bash
cd CheckWise/frontend
npm run dev     # in one terminal
# in another, open http://localhost:3000/dev/calendar-preview
# Use macOS Cmd+Shift+4 or Chrome DevTools "Capture node screenshot"
```

---

## 12. Verification commands

Run from `CheckWise/frontend/`:

```bash
npx tsc --noEmit                  # PASS — no type errors
npm run lint                      # PASS — eslint clean
npm run build                     # PASS — production build OK
```

**Build output (relevant routes):**

```
○ /dev/calendar-preview                12.7 kB         130 kB
○ /portal/calendar                     7.93 kB         188 kB
ƒ /portal/submissions/[submission_id]   8.7 kB         193 kB
○ /portal/upload                       21.2 kB         188 kB
```

Backend was not touched — no backend tests need re-running for this audit.

---

## 13. Known limitations / follow-ups

1. **Drawer doesn't show filename / upload date in the calendar context.** `CalendarItem` doesn't carry these — they live on `SubmissionDetail`. The drawer surfaces a "Ya enviaste un documento" notice and routes to the full detail page where filename, date, reviewer comment, and validation summary all appear. A follow-up could fetch a lightweight submission summary on drawer open for one-tap previews, but that adds an N+1 fetch cost.
2. **Year switcher** — not implemented. The page currently shows only the current year.
3. **Keyboard shortcuts** — not implemented (user picked pointer-first in shape phase).
4. **Custom popover does not yet support touch press-and-hold** on mobile. The cell-click path opens the drawer, which is the primary mobile interaction. The popover is desktop-hover-first.
5. **Dev mock route** at `/dev/calendar-preview` is left in the tree per user request for ongoing visual QA. Should be removed before public deploy or hidden behind an env flag.
6. **The submission-detail route's incoming-from-calendar context isn't visually called out** — coming from the calendar lands you on the same submission detail page anyone would see. A breadcrumb or `?from=calendar` UX hint could improve return-navigation but is out of scope for this round.

---

## 14. Recommended follow-up routes for the submission detail page

The submission detail page at `/portal/submissions/[submission_id]` is the canonical "uploaded document preview" surface and should be reused (not duplicated) from:

| Surface | Trigger | Linked from? |
|---|---|---|
| Calendar drawer | `submission_id` present | **Yes — new in this round** |
| Dashboard "Atención" list | Each actionable item | Recommended (verify current behavior) |
| Reports | Each cited submission | Recommended |
| Submission history view | All historical submissions | Recommended (likely already linked) |
| Notifications / activity feed | New review event | Recommended for future |

---

## 15. Recommendation

The implementation is **reviewable as-is**. All scope is delivered:

- Popover clipping fixed (portal + collision)
- Cell visual seams fixed (neutralized border, no `border-b`, larger segment bar)
- Color-only signal supplemented with state icon glyph
- Drawer action becomes state-contextual
- "Ya enviado" notice added
- Submission detail route reused (no new duplicate page)
- Upload flow already wired via existing `event.href`
- Audit doc + screenshots saved

**Do not commit yet** — the user explicitly requested review before commit.

Suggested commit boundary if approved:

```
git add frontend/app/portal/calendar/page.tsx \
        frontend/app/dev/calendar-preview/page.tsx \
        frontend/components/checkwise/calendar/ \
        docs/audits/provider-calendar-interaction/
git commit -m "..."
```

A multi-paragraph commit message in the repo's direct-to-main style is recommended.
