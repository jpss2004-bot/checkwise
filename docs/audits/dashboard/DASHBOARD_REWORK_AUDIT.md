# Provider Dashboard Rework — Audit & Implementation

Session: 2026-05-21
Surface: `/portal/dashboard` (provider portal)
Author: Claude Code session

## Current-state findings

The provider dashboard rendered correctly and was fully backed by
real backend data — but the surface read as a *marketing-style hero
page*, not an operational compliance console. Users could not answer
the four questions an active vendor opens the page to settle:

1. "What is my current compliance status?"
2. "What should I do next?"
3. "What is missing / in review / what did I upload?"
4. "What is coming up?"

The radial gauge, donut, and 12-month calendar teaser each duplicated
data that was already in the metadata strip, the semaphore reason, or
the `/portal/calendar` surface. The "in review" lifecycle bucket was
collapsed into the `attention_today` list with no separate surface,
and there was no surface at all for "recent uploads," forcing
providers to navigate to `/portal/submissions` to see what they had
just sent.

## Data-flow map

| Layer            | File                                                                     |
| ---------------- | ------------------------------------------------------------------------ |
| Page             | `apps/web/app/portal/dashboard/page.tsx`                                 |
| Shell            | `apps/web/components/checkwise/portal/portal-app-shell.tsx`              |
| API client       | `apps/web/lib/api/portal.ts` → `getDashboard()`                          |
| Endpoint         | `apps/api/app/api/v1/portal.py` → `GET /workspaces/{id}/dashboard`       |
| Slot service     | `apps/api/app/services/evidence_slots.py`                                |
| Auth dependency  | `current_portal_workspace` in `apps/api/app/api/v1/portal.py`            |
| Response model   | `DashboardResponse` (pydantic), `DashboardPayload` (TS)                  |

### Backend response shape (post-rework)

```
DashboardResponse
├── workspace_id, persona_type
├── onboarding_summary { total_required, completed, in_review, needs_action, … }
├── document_state_counts { approved, in_review, uploaded, pending, needs_review, rejected, expired, exception }
├── semaphore { level, label, reason, compliance_pct, total_tracked, on_track }
├── suggested_actions[] { id, type, title, body, priority, href, requirement_code, period_key }
├── attention_today[] { id, title, institution, state, due_in_days, href }
├── upcoming_deadlines[] { id, title, institution, period_key, due_month, state, href, due_in_days }
└── recent_uploads[]    ← added in this rework
       { submission_id, requirement_code, requirement_name, institution,
         period_key, status, submitted_at, filename, href }
```

### Data-source verification

- **Real backend, no mocks.** Every field on the dashboard now comes
  from `GET /workspaces/{id}/dashboard`. The legacy demo/mock payload
  documented in `docs/PROVIDER_DASHBOARD_READ_MODEL.md` is gone from
  the runtime path.
- **Suggested actions are real.** `_compute_suggested_actions` walks
  the evidence-slot views, surfacing rejected/needs-correction/mismatch
  as high priority, missing onboarding as medium, expired calendar
  slots as high ("regularize"), and upcoming missing slots (≤14d)
  as low/medium. CTAs route to `/portal/upload` with the right
  `requirement_code` / `period_key` / `replaces` / `v2=1` flags
  pre-encoded.
- **Attention list is real.** `_compute_attention_today` includes
  required rejected / needs-correction / mismatch / expired *plus*
  required missing within 14 days, sorted overdue-first.
- **No state-label drift.** The frontend uses
  `statusToDocumentStateCode` and `SLOT_STATE_TO_DOC_CODE` to map
  backend `RequirementStatus` / `SlotState` values onto the single
  `DocumentStateCode` vocabulary that drives `DocStateBadge`. No
  surface invents a Spanish label inline.

### Gap identified and closed: `recent_uploads`

The backend already exposed every signal needed for an operational
dashboard *except* "what did the provider most recently upload, and
where is each of those submissions in its lifecycle." Adding it was
small and safe:

- Added `DashboardRecentUpload` pydantic model.
- Added `_compute_recent_uploads` (reads the same submissions table
  the slot resolver consumes; pulls 5 most recent by `created_at`).
- Added `recent_uploads` to `DashboardResponse`.
- Added test `test_dashboard_recent_uploads_returns_latest_submissions`
  covering empty + populated + status fidelity + ISO timestamp parse.
- Tenant-safe: the new helper filters by `client_id + vendor_id`
  from the already-resolved `ProviderWorkspace`. No new auth surface.

## UX problems with the previous dashboard

1. **Too many large stacked sections.** PageHeader + metadata strip +
   semaphore hero (gauge + stacked bars) + suggested-action rail +
   "Tu expediente inicial" + (attention grid + document-state donut)
   + (calendar teaser + upcoming) made the first viewport 1.5–2
   screens tall before any operational data was visible.
2. **The semaphore hero (148px radial gauge) dominated the page**
   while restating data already in the metadata strip
   (`compliance_pct`, `on_track / total_tracked`).
3. **`DocumentStateOverview` donut** restated the stacked bars in the
   semaphore hero. Donuts on operational surfaces look decorative
   because they don't show "what should I click."
4. **`ExpedienteSummaryCard`** was only relevant during the initial
   onboarding flow; for returning providers it was noise.
5. **`CalendarTeaser`** drew 12 month chips with the current month
   highlighted and pointed at `/portal/calendar`. It carried no
   operational state — pure marketing-style filler.
6. **NextActionRail used horizontal-scroll cards** at equal weight,
   diluting the primary "next action." There was no clear single
   thing to do.
7. **No "in review" or "recent uploads" surface.** The provider had
   to navigate away to confirm what they just uploaded or check
   queue status.
8. **State-label drift in copy.** "Por atender" (strip), "Necesitan
   acción" (donut legend), "Necesita tu atención" (attention grid
   title), "Requieren tu atención" (state group). Same lifecycle,
   four phrasings.
9. **Mobile: long full-width decorative cards consumed entire
   viewports** before the user reached anything actionable.

## Proposed dashboard information architecture

A single 1-screen operational layout, top-to-bottom on mobile,
2-column on `lg+`:

```
PageHeader  (eyebrow, vendor, "Subir documento" CTA)
MetadataStrip  (RFC · Persona · Cumplimiento % · Por atender · En revisión · Aprobados · Próximo)
StatusBanner  (1 thin row — semaphore tone + label + reason + compact %)
[ LockedDashboardBanner | ProvisionalAccessBanner ]   ← only when applicable

┌─ LEFT (lg:col-span-2) ─────────────────┐  ┌─ RIGHT ─────────────────┐
│ PrimaryActionPanel                     │  │ UpcomingDeadlinesPanel │
│   • 1 dominant action card             │  │   compact list, sorted │
│   • 2–3 secondary action rows          │  │   by due_in_days       │
│                                        │  │                        │
│ OperationalQueues (2×2)                │  │ ComplianceLedger        │
│   Por atender  │  Vence pronto         │  │   compact state counts │
│   En revisión │  Cargas recientes      │  │   (replaces donut)     │
└────────────────────────────────────────┘  └────────────────────────┘
```

Every section answers at least one of the doctrine's questions
(`docs/design-system/VISUAL_REDESIGN_DOCTRINE.md` §"Audit criteria"):
*what is missing, what is risky, who owns the next action, what is
due, what changed*.

## Backend-contract findings

- Existing payload already covered: status, compliance %, missing,
  needs-action, upcoming. **No gap.**
- New `recent_uploads` field added (small, additive, tenant-safe).
  No breaking changes to existing consumers.
- All existing tests for shape and lineage continue to pass.

## Changes implemented

### Backend

- `apps/api/app/api/v1/portal.py`
  - Added `DashboardRecentUpload` pydantic model.
  - Added `_compute_recent_uploads` helper.
  - Added `_recent_upload_href` helper (links to `/portal/submissions/{id}`).
  - Added `recent_uploads` field to `DashboardResponse`.
  - Wired the field through the endpoint return.

- `apps/api/tests/test_portal_dashboard.py`
  - Extended `test_dashboard_returns_expected_payload_shape` to assert
    `recent_uploads` is present and a list.
  - Added `test_dashboard_recent_uploads_returns_latest_submissions`
    covering empty workspace + populated workspace + status fidelity.

### Frontend

- `apps/web/lib/api/portal.ts`
  - Added `DashboardRecentUpload` TS type.
  - Added `recent_uploads?` to `DashboardPayload` (optional so older
    payloads stay forward-compatible).

- `apps/web/app/portal/dashboard/page.tsx` — full rewrite
  - Removed the giant `SemaphoreHero` (148px radial gauge + stacked bars).
  - Removed `DocumentStateOverview` donut.
  - Removed `CalendarTeaser` (12-month decorative strip).
  - Removed `ExpedienteSummaryCard` (only the locked-gate / provisional
    banners survive, since they're real onboarding-state signals).
  - Removed the `cw-metadata-strip` ad-hoc markup and switched to the
    shared `MetadataStrip` primitive from `apps/web/components/ui/`
    (single source of truth across the app).
  - Added `StatusBanner` — thin colored-bar + icon + reason + inline
    `%` and `on_track/total_tracked`. Replaces the dominant gauge.
  - Added `PrimaryActionPanel` — single dominant action card +
    compact secondary list (replaces the horizontal-scroll equal-weight
    rail). CTAs use specific verbs: "Corregir carga", "Responder
    observación", "Verificar documento", "Regularizar", "Subir
    documento".
  - Added `OperationalQueues` — 2×2 grid of `QueuePanel` rows:
    *Por atender* (rejected / needs_correction / possible_mismatch /
    expired), *Vence pronto* (missing within 14d), *En revisión*
    (uploaded / in_review), *Cargas recientes* (last 5 submissions).
    Each row links straight into its slot or submission detail.
  - Added `UpcomingDeadlinesPanel` sidebar with urgency-tinted day
    pills (red ≤3d, amber ≤7d, neutral otherwise).
  - Added `ComplianceLedger` sidebar — compact state-count list using
    `DocStateBadge` for visual consistency (replaces the donut).
  - Consolidated state-label vocabulary: every surface uses
    `DocStateBadge` (which reads `DOC_STATE_LABELS` from a single map),
    so a state is named the same way every time it appears.

## Verification

- `npx tsc --noEmit` in `apps/web` → passes.
- `pytest tests/test_portal_dashboard.py` in `apps/api` → 15 passed.
- Browser preview verification was deferred — see "Remaining
  follow-ups" below.

## Remaining follow-ups

- **Browser preview not run in this session** — the harness flagged
  the absence of a running preview server. A follow-up pass should
  spin one up (`preview_start`) and capture desktop + mobile
  screenshots of the new layout against a populated and an empty
  workspace.
- **`/portal/submissions` list view** — the new "Cargas recientes"
  panel links rows to `/portal/submissions/{id}`; that detail route
  exists, but the "Ver todo" header link points at `/portal/submissions`
  (a list surface). Confirm or implement that list view if it isn't
  already in place.
- **Recent uploads pagination** — backend caps at 5 (intentional). If
  product later wants a deep "all my uploads" view, it should live
  on `/portal/submissions`, not the dashboard.
- **Onboarding view of the same surface** — when a provider is
  pre-onboarding (`gateBlocked`), the dashboard now shows the locked
  banner *and* the queues. The queues will be mostly empty in that
  state; consider whether the queues should be hidden until the gate
  flips, or whether the empty-state copy is sufficient (current
  implementation: empty-state copy).
