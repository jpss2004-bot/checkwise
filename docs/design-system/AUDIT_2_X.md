# CheckWise 2.x — Pre-Rework Audit

Status: **Phase 1 deliverable.** Read before Phase 2 lock-in.
Captured: 2026-05-17, on `design/audit-2x` branch, V2.0 (`v2.0.0`) baseline.

This audit is the current-state baseline for the 2.x visual rework. It catalogs every reachable surface, what's working, what isn't, and the cross-cutting findings that should drive Phase 2 (Visual Direction Lock).

Companion: [INSPO_MAP.md](INSPO_MAP.md) — the inspo signal extraction.

## Method

- Local dev stack (`bash dev.sh` equivalent: Postgres via docker compose, FastAPI via uvicorn, Next.js dev via preview).
- Logged in as `boss.demo@checkwise.mx` (provider, completed expediente) for `/portal/*`, and `ada@legalshelf.mx` (internal_admin + reviewer) for `/admin/*`.
- Viewport: 1440×900 desktop.
- Public PNGs saved under [`design-concepts/screenshots/public/`](../../design-concepts/screenshots/public/); authenticated surfaces captured inline during this session (not on disk) because saving them requires either replaying the auth flow under headless Chrome or wiring CDP — out of scope for the audit pass.
- 12 of 26 routes captured directly. Remaining routes either share a layout with a captured route (`/admin/[reviewer|calendar|clients|requirements]`, `/portal/submissions/[id]`) or are gated behind a missing seed (`/client/*` — see Findings).

## Surface-by-surface

### Public (4 routes)

| Route | What's strong | What's weak | Next move |
|---|---|---|---|
| `/` | Historical V2.0 asymmetric hero with a detailed "Centro de cumplimiento" preview card. Monospace metadata and navy/teal restraint still carry useful product signals. | The preview is synthetic JSX, not a real product screenshot. It now reads too plain/static for the desired landing page and should not remain the target visual language. | Superseded by `docs/claude/HERO_LANDING_AUDIT.md`: rebuild around real product screenshots/assets, external design tooling, and purposeful Motion. |
| `/login` | Calm centered card. Single email+password input pair. Helper copy positioned correctly above the form. | The card is generic SaaS chrome — would not feel out of place in 100 other products. No marker that this is a compliance product. The placeholder `tu.correo@empresa.com` is the only Spanish hint. | Cosmetic-only: introduce the same monospace metadata strip that lives on `/`, plus a "Powered by Legal Shelf" tighter typographic lockup. Drop the duplicate "Acceso a CheckWise" header — the page already says it. |
| `/admin/login` | Same form as `/login`, which means cross-role parity. | **Visually 1:1 identical to `/login`.** If the system already collapses all auth into a single surface (per `app/login/page.tsx` comment: "CheckWise 1.8 collapsed the old 3-role picker into a single email + password form"), then `/admin/login` exists but is a redundant route. | Verify the route is still reachable from any UI link. If yes, redirect to `/login`. If no, consider deleting it. |
| `/activate?token=demo` | The route is wired; doesn't error. | With an invalid token the page falls back to the **same** login form — no acknowledgement that activation was attempted, no "this invitation token is invalid" message. The README promises a "3-step wizard + role confirmation" that's unreachable without a valid seeded invitation. | Two follow-ups: (a) add an invalid-token state with clear copy; (b) the activate wizard itself needs a real audit pass once a valid token can be seeded. |

### Provider portal (5 routes, all behind `PortalAppShell`)

| Route | What's strong | What's weak | Next move |
|---|---|---|---|
| `/portal/dashboard` | Real signal in the page: workspace identity, KPI strip, status panel. Sidebar nav (PortalAppShell) is the right shape. | Generic KPI tile composition (icon + number + label). Hero "Hola, Servicios" line + tiny subhead reads like consumer SaaS warmth, mismatched with the rest of CheckWise's voice. Banner alert at the top is full-width and visually dominates over the actual compliance state. | Demote the greeting block, promote the compliance gauge to the visual anchor, replace the equal-card KPI strip with a horizontal rhythm of different-weighted signals (gauge → density chart → upcoming action rail). |
| `/portal/calendar` | Real institution × month grid with monospace metadata. Filter tabs render. | Very sparse — most cells are empty placeholders, which makes the grid feel like wireframe even when there's data nearby. | Add a "compactness" toggle, make occupied cells visually heavier (real density), and tie the grid to `/portal/dashboard`'s "what's next" via shared component. |
| `/portal/onboarding` | Banner-and-grid pattern is functional; reviewer-note slot exists. | The requirements are an equal 2×2 card grid (pure cliché per `impeccable` absolute bans — "identical card grids"). Provisional-access banner repeats info that's already in the page header. | Replace the card grid with a vertical list of requirement rows with full borders + status pills, in the spirit of the reviewer queue table. Treat "mandatory" and "optional" as separate sections, not pills. |
| `/portal/reports` | Real route exists with placeholder cards. Status states (`ready` / `generating` / `needs_review` / `blocked` / `unavailable`) are wired. | **This is the weakest surface in the product.** Two static report-type cards stacked at the top, then 4 more in a row beneath — pure "identical card grid" anti-pattern. No actual report content. No print/export mode. The 5 archetypes the README references aren't visually differentiated. | Full Phase 3 rebuild. See Phase 3 plan: report archetypes, real `ReportSection` / `ReportTimeline` / `ReportEvidenceTable` primitives, print-friendly mode. |
| `/portal/upload` | Multi-step wizard is mounted. Real workflow. | Looks like a settings form — fields stacked vertically with weak hierarchy. The wizard step indicator at the top of the page is barely visible. PDF-preview slot is empty until upload. | Apply the dual-pane "metadata + drop zone" pattern (see INSPO_MAP §Cake / Upload modal). Promote the step indicator to a sticky rail. |

Not captured live but inherits portal pattern:
- `/portal/submissions/[submission_id]` — submission detail. Will need its own polish pass once the dashboard/onboarding pattern is locked.
- `/portal/entra-a-tu-espacio` — workspace confirmation gate. Per `CHECKWISE_1_6.md` already has a deliberate composition (locked tenant fields + editable profile + 4 preview tiles). Audit-by-doc-review: the 4-tile preview is at risk of looking like a 4-card grid (anti-pattern); reframe as a vertical "what's next" rail.

### Admin portal (4 routes, behind top-nav `AdminShell`)

| Route | What's strong | What's weak | Next move |
|---|---|---|---|
| `/admin/dashboard` | Real top-level KPIs and a queue-health gauge. Top-nav shell is the right shape for an internal staff console (sidebar would be wrong — too few sections). | Asymmetric layout (gauge + greeting block on the left, 4 KPIs on the right) but the right side is still an equal-card grid. Empty stat cards (showing "0") feel like wireframe. | Replace equal-card 4-up with mixed density: gauge ring → "needs decision now" prioritized list → small monospace metric strip. Empty zeros should render as "—" with helper hint, not as a number with no signal. |
| `/admin/reviewer` | Real table, real filters, real workflow surface. The cleanest admin surface today. Visually closest to the target (Stripe / Linear) voice. | Filter tabs at the top duplicate the column header logic. The "Decidir" button column is empty when there's no decision yet — should be inline. | Light polish. Promote this layout's table primitive into a shared `<DataTable>` used by `/admin/vendors`, `/admin/clients`, `/admin/audit-log`, and any /client/* roster. |
| `/admin/vendors` | Same `<DataTable>` pattern as reviewer. Tenant column is monospace — correct. | Body rows are very low-density — three short rows of vendor names with one badge each. Compare to inspo "order list" where every row carries 6+ signals. | Add columns: last submission status, days-overdue, primary contact. Inline mini-sparkline column showing 6-month compliance trend. |
| `/admin/audit-log` | Filter row exists. | Empty state is generic ("No events"). This is the Operations / SRE-style surface — should be the densest table in the product, but it's the emptiest. | Seed real audit events for the demo. Add timestamp-first column with monospace, action verb pill, target reference, actor, raw-payload toggle. This surface should feel like the Linear "Activity" view. |

Not captured live but inherits admin pattern:
- `/admin/clients`, `/admin/calendar`, `/admin/requirements`, `/admin/reviewer/[id]` — will all benefit from the same `<DataTable>` consolidation and the same density push.

### Client portal (`/client/*`, 7 routes) — **NOT CAPTURED**

`/client/*` is gated by `client_admin` role membership. The dev seed only creates `ada@legalshelf.mx` (internal_admin + reviewer) and two provider users; no `client_admin` is seeded, so login → `/client/*` is unreachable without modifying the seed.

> **Finding:** the `/client/*` routes shipped in 2.0 cannot be reached by any seeded user in `bash dev.sh` defaults. They build clean in CI but receive zero demo coverage. Two consequences: design drift is invisible until a real client is onboarded, and the new shared dashboard primitives can't be visually QA'd against the client tier.

Action for Phase 2: add a seeded `client_admin` (e.g. `cliente.demo@checkwise.mx`) with a small client portfolio. Then audit-pass `/client/*` before Phase 5 polish.

## Cross-cutting findings

### F1 — Two-shell drift between portal and admin

`PortalAppShell` (left sidebar) and the admin shell (top horizontal nav) carry different paddings, different page-header treatment, and a different sense of "where am I." That's intentional shape-wise (different surfaces, different jobs) but the spacing scale and typographic rhythm aren't shared. A user moving between `/portal/dashboard` and `/admin/reviewer` perceives two products.

**Phase 2 action:** lock a shared spacing token set so both shells inherit the same rhythm. The shells differ in *structure*, not in *texture*.

### F2 — Card-grid reflex everywhere except `/admin/reviewer`

Onboarding, reports, dashboard KPIs, vendors — every non-table surface defaults to "equal cards in a grid." `impeccable` calls this out as an absolute ban: *"Identical card grids — same-sized cards with icon + heading + text, repeated endlessly."* `design-taste-frontend` says the same with different words: *"generic card containers are strictly BANNED. Use logic-grouping via `border-t`, `divide-y`, or purely negative space."*

**Phase 2 action:** add a single rule to the active external design workflow: any new surface that introduces three+ identical cards in a row must justify why a vertical list with full borders isn't a better affordance.

### F3 — `/portal/reports` is the lowest-density, lowest-signal surface

This is the one the user has called out as needing to be "the strongest part possible" of CheckWise. The current state is the opposite: it's the surface with the least content and the most generic chrome. There's no executive layout, no print mode, no traceability narrative, no real exportable artifact. The 5 status states (`ready`/`generating`/`needs_review`/`blocked`/`unavailable`) are wired but invisible — they look like the same card with a slightly different badge.

**Phase 3 action:** treat reports as a separate design problem, not a dashboard variant. See the Phase 3 plan in the 5-phase doc.

### F4 — Three login pages render the same UI

`/login`, `/admin/login`, and `/activate?token=demo` (with invalid token) all render the identical centered email+password card. The login page header comment says CheckWise 1.8 collapsed roles into one surface — but the routes weren't collapsed alongside it. Two of these three pages are now dead UI.

**Phase 2 or housekeeping:** decide whether to redirect `/admin/login` → `/login` and add an invalid-token state to `/activate`, or keep the routes as-is and visually mark them differently. Pick one.

### F5 — Empty-state quality varies wildly

- `/portal/calendar` empty cells: visually identical to occupied cells, just a smaller number. No "nothing here yet" texture.
- `/admin/audit-log` empty: generic "No events" line + spinner-style placeholder. Acceptable but flat.
- `/portal/reports` empty: report cards with placeholder text. Looks the same as a populated report would.

`design-taste-frontend` mandates *"Beautifully composed empty states indicating how to populate data."* CheckWise's voice (calm, precise, Spanish-first) gives a clear path: each empty state should tell the operator *exactly* what to do next, in plain Spanish, with a single primary CTA.

**Phase 5 action:** dedicated empty-states pass during the upstream `/impeccable` final-mile sweep.

### F6 — Density target

Today's product reads at roughly `VISUAL_DENSITY: 4` (per `design-taste-frontend`'s scale). Per Phase 0 decisions, the target is **premium-dense** (Stripe / Linear / Mercury / Ramp territory) — that's `VISUAL_DENSITY: 6–7` in the same scale. Tables get one extra column, KPI strips get one extra signal per tile, default padding tightens by one step (likely `p-6` → `p-5` for body cards, `gap-6` → `gap-5` for grid gaps).

**Phase 2 action:** decide the *exact* tokens that change. Resist density creep by leaving onboarding and the provider dashboard slightly looser than the admin / reports surfaces — providers are stressed compliance users, not power operators.

### F7 — Token coverage on the new 2.0 primitives is correct

Spot-checking the new charts and `StatCard` family, the tone CSS variables (`--text-brand`, `--text-teal`, `--status-success-text`, …) are bound consistently. No raw hex in the surfaces audited. That's the floor — Phase 2 expands the token set, not fights to repair it.

## Anti-patterns observed (cross-checked against `impeccable` absolute bans)

| Ban | Where it shows up | Severity |
|---|---|---|
| Identical card grids | `/portal/onboarding`, `/portal/reports`, KPI strips on every dashboard | High |
| Modal as first thought | (not observed — surfaces use route-level affordances. Good.) | n/a |
| Hero-metric template | `/admin/dashboard` (big number + small label + supporting stats) | Medium |
| Gradient text | (not observed.) | n/a |
| Glassmorphism as default | (not observed.) | n/a |
| Side-stripe borders | (not observed in captured surfaces, but the `Alert` primitive used in banners has a 4px left bar — verify before Phase 2.) | Verify |

## Recommended Phase 2 inputs

When Phase 2 (Visual Direction Lock) opens, carry these forward as the constraints to design within:

1. **Density target: 6–7** for admin + reports; **5** for provider portal; **4** kept for marketing / login.
2. **Banned this round:** any new identical-card grid. Any new modal that could have been a side panel or inline.
3. **Hero anchor superseded:** `/` should no longer be treated as the locked language target. Use the current hero audit and external-design policy for the next landing pass.
4. **Token deltas:** likely additions are a tighter spacing scale (`--space-5: 1.125rem`?) and an explicit monospace metadata utility. Phase 2 decides.
5. **Reports gets the deepest pass** (Phase 3). Marketing + login get the conversion-critical pass (Phase 4). Internal surfaces get the systematic roll-out (Phase 5).
6. **Seed gap:** add `cliente.demo@checkwise.mx` (client_admin) to `dev_seed.py` before Phase 5 so `/client/*` can be audited and demoed.

## Status

Phase 1 complete. Audit-pass ground truth is captured; Phase 2 has its constraints. No code changes landed in this phase — only this doc and `INSPO_MAP.md`.
