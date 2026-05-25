# CheckWise 2.0 — Implementation note

Companion to [CHECKWISE_1_5.md](CHECKWISE_1_5.md), [CHECKWISE_1_6.md](CHECKWISE_1_6.md), and [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md). Documents the frontend redesign pass that lifts CheckWise from operational V1.6 surfaces into a unified compliance-cockpit visual language across vendor, client, and admin portals.

## Goals

Consolidate the three portals (vendor / client / admin) onto one design language and one component spine. Replace per-page dashboard tiles with shared primitives, swap top-bar navigation for a real sidebar shell on the vendor portal, centralize post-login routing, and bridge mock data to real backend payloads through an adapter layer — all without touching any backend contracts.

The hero on `/` was already shipped as the "CheckWise 2.0 launch hero" (commit `badde42`). 2.0 extends that work *inward* into the product surfaces.

## What's new at a glance

| Layer | Before 2.0 | After 2.0 |
|---|---|---|
| Vendor portal chrome | `ProviderContextBar` (top-only) | `PortalAppShell` (sidebar + slim top bar) |
| Dashboard primitives | `Tile` redefined 3× across surfaces | Single `StatCard` / `Surface` / `EmptyState` family |
| Charts | None — only text + badges | Inline-SVG chart primitives bound to design tokens |
| Post-login routing | Decision logic inline across `/login`, `/activate` | `lib/routing/post-login.ts` single source of truth |
| Backend ↔ UI shape | Pages still consumed `lib/mock/*` directly | `lib/api/portal-adapters.ts` bridges real payloads + UX enrichments |

## Surfaces redesigned

20 routes, ~3,700 lines added / ~1,300 removed.

### Vendor portal (`/portal/*`)

| Route | What changed |
|---|---|
| `/portal/dashboard` | Sidebar shell, `StatCard` grid, `RadialGauge` for completeness, `Donut` for institution mix, `StackedBars` for monthly trend |
| `/portal/calendar` | Minor — adopts shared `Surface` chrome |
| `/portal/onboarding` | Minor — adopts shared `Surface` chrome |
| `/portal/reports` | Minor — adopts shared `Surface` chrome |
| `/portal/upload` | Minor — adopts shared `Surface` chrome |
| `/portal/submissions/[submission_id]` | Minor — adopts shared `Surface` chrome |

### Admin portal (`/admin/*`)

| Route | What changed |
|---|---|
| `/admin/_shell` | Description + actions slots; full nav rework |
| `/admin/dashboard` | Top-level KPIs via `StatCard`, reviewer queue tile, gauge for queue health |
| `/admin/audit-log` | Filterable timeline, surface-aware empty state |
| `/admin/calendar` | Multi-tenant institution view |
| `/admin/clients` | Roster table with risk badges |
| `/admin/requirements` | Catalog viewer with frequency + period axis |
| `/admin/vendors` | Vendor roster with status mix donut |

### Client portal (`/client/*`)

| Route | What changed |
|---|---|
| `/client/_shell` | Sidebar + top-bar, parity with portal/admin |
| `/client/dashboard` | Portfolio-wide KPIs, vendor-status donut, attention list |
| `/client/activity` | Filterable activity feed |
| `/client/calendar` | Read-only institution × month grid |
| `/client/submissions` | Cross-vendor submissions index |
| `/client/vendors` | Vendor roster with risk surface |
| `/client/vendors/[vendor_id]` | Per-vendor compliance view |

## New primitives

### `components/checkwise/dashboard/stat-card.tsx`

Shared dashboard atom family. Replaces three drifted `Tile` implementations.

- `<StatCard tone={...} icon={...} label value delta trend chart hint cta />`
- `<Surface tone padding shadow border>...</Surface>` — the canonical card chrome.
- `<EmptyState icon title body action>` — the canonical zero-state surface.

Tones are bound to semantic CSS tokens: `neutral`, `brand`, `teal`, `success`, `warning`, `error`, `info`. No raw hex anywhere in the component layer.

### `components/checkwise/charts/index.tsx`

Inline-SVG chart primitives. Zero external dependencies — every chart is a small functional component rendered into SVG and tone-bound to `globals.css` variables.

| Component | Purpose |
|---|---|
| `<RadialGauge value max label tone />` | Circular progress (completeness, queue health) |
| `<Donut segments size />` | Multi-segment proportions (status mix) |
| `<Sparkline points tone />` | Trend line inside `StatCard` |
| `<MiniBars data tone />` | Small column chart, animated on mount |
| `<StackedBars segments />` | Horizontal stacked bar |
| `<TrendArrow delta />` | Up/down delta indicator |

Recharts and similar libraries were deliberately ruled out — payload + animation cost was disproportionate to the small dashboard widgets the product actually needs.

### `components/checkwise/portal/portal-app-shell.tsx`

Sidebar-driven shell for the vendor portal. Replaces `ProviderContextBar`. Carries the brand mark, primary nav with active states, workspace context bar at the top, mobile collapsing drawer.

### `lib/routing/post-login.ts`

Single source of truth for the post-auth routing decision. Returns `{ route, banner }` from the expediente snapshot. Used by `/login`, `/activate`, and the future returning-session flow.

Routes: `/portal/entra-a-tu-espacio` · `/portal/onboarding` · `/portal/dashboard`.
Banners: `none` · `provisional_access` · `expediente_blocked` · `needs_workspace_confirmation`.

### `lib/api/portal-adapters.ts`

Adapters that map real backend payloads onto the UI-friendly shapes the V1.5/1.6 pages were built against. Bridges the gap until the backend endpoints emit the enriched shape directly.

> **TODO[backend-integration]** — when `/portal/workspaces/{id}/onboarding` returns the enriched onboarding fields (P1-1 in `CHECKWISE_1_6.md`), drop this adapter and consume the API directly.

### `lib/mock/{calendar,expediente}.ts`

UX-curated mock data, extracted from inline page state so it stays in one place. Same role as the existing mocks under `lib/mock/*`; backend integration will collapse these.

## Token contract

All new primitives consume the semantic CSS variables defined in [`apps/web/app/globals.css`](../apps/web/app/globals.css). No raw hex, no Tailwind palette imports, no inline gradients. This keeps 2.0 cleanly within the "Visual Source Of Truth" rules in [`DESIGN.md`](../DESIGN.md).

Banned in this pass and preserved going forward:

- Static HTML pasted from design previews.
- Recharts / d3 / heavy chart libraries for small dashboard widgets.
- New per-surface `Tile` components.
- Hex colors anywhere outside `globals.css`.

## Removed

- `apps/web/components/checkwise/workspace/access-decision-banner.tsx` — orphan referencing the `WorkspaceAccessOutcome` type that was deliberately deleted in Phase 6. No consumers. Routing now reads `session.expediente_status` straight from the backend at every post-auth surface.

## Verification

Run before the merge that lands 2.0:

```bash
# Frontend
cd frontend
node_modules/.bin/tsc --noEmit          # → clean
node_modules/.bin/next lint --quiet     # → clean
node_modules/.bin/next build            # → all 20 routes compile

# Backend (unchanged by 2.0; sanity)
cd backend
.venv/bin/ruff check .                  # → clean
.venv/bin/pytest -q                     # → 269 passed
```

Last verified: 2026-05-17 (`release/2.0` branch, pre-merge).

## What 2.0 does NOT do

- **No backend changes.** Every endpoint, schema, and migration is untouched.
- **Does not finish mock-to-real wiring.** The integration TODOs in `CHECKWISE_1_6.md` carry forward into 2.x. `portal-adapters.ts` is the planned bridge.
- **Does not rework auth.** Token flow, RBAC, and workspace confirmation logic are unchanged.
- **Does not add new product features.** Surfaces redesigned are surfaces that already exist.

## Carry-forward to 2.1+

- Backend-integration TODOs from `CHECKWISE_1_6.md` (drop `portal-adapters.ts` once endpoints carry enriched onboarding fields).
- Real-data wiring for admin + client dashboards (today they consume `lib/mock/*`).
- Provider portal token migration — `X-Workspace-Token` → JWT (still a roadmap item).
- S3-compatible storage path before any production-style deploy.
