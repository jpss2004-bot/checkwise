# CheckWise Client Portal — Comprehensive UX/UI/Engineering Audit

**Date:** 2026-06-18
**Scope:** Entire client portal (`apps/web/app/client/**`) — 19 audited areas, 193 adversarially-verified findings, deduplicated and synthesized.
**Benchmark bar:** Vanta, Drata, Rippling, Ramp, Stripe, Linear, Notion, Asana, Monday, Workiva.
**Core objective every recommendation is graded against:** help the cliente corporativo *maintain visibility, reduce risk, ensure compliance, and decide fast* across a portfolio of providers.

> Method note: every finding below was opened against the cited `file:line` in the current code and confirmed, dropped, or re-rated. Severities here reflect the honest post-verification rating (several were demoted from the original pass). Findings that recur across surfaces (truncation, mobile search, deep-link scope loss, status-code jargon, missing pagination) are merged once at the root and cross-referenced.

---

## 1. Executive Summary

The client portal is a mature, multiple-times-redesigned product with a genuinely strong spine: a token-governed design system, a real `<table>`-based compliance matrix with proper ARIA, a working semáforo filter, async intake, and a sophisticated report engine. The 2026-06-17 AA token fix is live and holding (`--text-tertiary` now clears 4.5:1), so most "low-contrast gray" complaints are stale and were dropped.

What remains is a coherent set of **systemic gaps**, not scattered cosmetics. They cluster into five themes:

1. **The dashboard answers "how much" but not "which / what next."** The flagship screen surfaces aggregate red/yellow/red counts but never *names* the at-risk providers, never shows *overdue* (the highest-liability state), buries *rejected/correction* in prose, and offers no *trend*. The single most valuable executive view — "here are your fires, worst-first, click to act" — exists only inside an on-demand report.

2. **Silent truncation across every list and the metadata master.** Vendors (>100), submissions, activity (>200), notifications (>100), and the metadata table (~499 rows) all cap server-side while the UI reports the capped count as the total, with no pager — even though the backend already returns `total`/`has_more`/`offset`. For a compliance/audit product this is a correctness-and-trust failure.

3. **Global search is broken at the front door.** It cannot find a provider by name (only RFC/period/folio), is completely unreachable on phones, floods results with duplicate per-submission rows, truncates at 50 with a dead "showing N" indicator, and has an invisible keyboard focus ring.

4. **Unbounded blocking operations with no escape.** Report generation (list page full-screen overlay; reports preset overlay; vendor-detail spinner) and the custom audit-package POST download have no client-side timeout — the exact "spinner forever" class the team already hotfixed elsewhere.

5. **Navigation context loss + orphaned high-value routes.** Every nav link, the bell, the logo, and BackBar drop the load-bearing `?client_id` scope param, silently switching internal/multi-client users to the wrong tenant. The flagship audit-package builder has no nav entry. Two competing back affordances co-render on detail pages.

Accessibility is mixed: the matrix and many ARIA landmarks are strong, but the mobile nav drawer is not a real dialog (no focus trap/Escape/restore), the semáforo "why is this red" tooltip is keyboard-unreachable, there's no skip link, and page-level fetch errors are unannounced. The design system has two unsynced type-scale sources, a dead `--density-*` token system, undefined `--state-*` tokens forcing hardcoded report hex, and ~97 arbitrary `text-[Npx]` literals.

None of this is catastrophic; the portal works. But against the enterprise-SaaS bar it reads as *85% of the way there* — the remaining 15% is exactly the part that makes a CFO trust the numbers and act in under 60 seconds.

---

## 2. Dashboard Audit (`apps/web/app/client/dashboard/page.tsx`)

The dashboard is the <60s portfolio-health entry point for every persona. It is the highest-leverage screen in the portal and carries the densest concentration of high-severity gaps.

### HIGH — Dashboard never names the at-risk providers; only aggregate counts
- **Severity:** High · **Complexity:** M
- **Business impact:** A Compliance Manager/Legal Director learns "tienes N proveedores en riesgo" but cannot see *which* without leaving for `/client/vendors` and re-filtering. The single most valuable answer — the named list of problem providers — is absent from the most important page.
- **User impact:** The hero headline ("Tienes 3 proveedores en riesgo") is a non-clickable dead end with no drill-in.
- **Root cause:** The `/overview` loop computes `semaphore_level` per workspace (`client.py:1230-1245`) but folds it into scalar counts and discards which vendor is which. `ClientOverview` (`lib/api/client.ts:108-123`) carries no `top_risk_vendors[]`. The page doc-comment (`page.tsx:54-58`) promises a "risk attention list" that was never built.
- **Recommended solution:** Add a "Proveedores en riesgo" attention card. Extend `ClientOverview` with `top_risk_vendors[]` (id, name, level, top_reason) populated inside the existing loop (no extra query). Render name + dominant problem + a `Link` to `/client/vendors/{id}`. Make the hero count a `Link` to `/client/vendors?semaphore_level=red` (the endpoint already accepts that filter — `client.py:1298`).
- **Evidence:** `page.tsx:259-267`, `page.tsx:168-178`, `page.tsx:54-58`, `client.py:1230-1245`, `client.py:1298`, `lib/api/client.ts:108-123`

### HIGH — Overdue / VENCIDO obligations are invisible on the dashboard
- **Severity:** High · **Complexity:** M
- **Business impact:** A lapsed REPSE obligation = active legal/tax exposure — the highest-liability state. The dashboard surfaces "Por vencer (≤14 días)" but has no concept of *already overdue*. A CFO can be fully red on the gauge yet never see "vencido" or a past-due count.
- **User impact:** Past-due items get the same or less visual weight than upcoming ones; the most urgent class is silently folded into the red bucket with no count or label.
- **Root cause:** `_compliance` computes `due_soon` strictly as `0 <= due_in <= 14` (`client.py:341-343`), dropping `due_in < 0` — even though the codebase's own `_calendar_item_risk` recognizes an `overdue`/VENCIDO state (`client.py:1164,1184-1187`). `ClientOverview` has `due_soon_total` but no `overdue_total`.
- **Recommended solution:** Add `overdue_total` to `ClientOverview` (slots required, unresolved, `due_in < 0`). Surface it as a dedicated "Vencidos" KPI with **error** tone at the TOP of the KPI strip, linking to `/client/calendar`. Reflect it first in `summaryDescription`.
- **Evidence:** `client.py:335-343`, `client.py:1164,1184-1187`, `client.py:344-355`, `lib/api/client.ts:108-123`, `page.tsx:347-355`

### HIGH — Rejections / aclaraciones pendientes are buried in prose, not a scannable KPI
- **Severity:** High · **Complexity:** S
- **Business impact:** Rejected docs/pending aclaraciones are the most directly actionable item a client can chase (they force re-submission) and the rule that *defines* the red semáforo (`vendors/page.tsx:521-526`). They appear only inside the gray prose paragraph of the hero, never as a KPI tile or clickable target.
- **User impact:** Scanning the KPI strip, the "rechazos o aclaraciones pendientes" number is only legible if you read the full sentence, and it links nowhere.
- **Root cause:** `ClientKpiStrip` hard-codes 4 rows (`page.tsx:325-356`) — Proveedores / Faltantes / En revisión / Por vencer — and omits `overview.rejected_or_correction_total`; the value lives only in `summaryDescription` (`page.tsx:272-273`). Field exists at `lib/api/client.ts:118`.
- **Recommended solution:** Add a "Rechazos / aclaraciones" KPI row with error tone when >0, linking to `/client/submissions` filtered to rejected/correction. Order the strip most-actionable-first: Vencidos, Rechazos, Faltantes, Por vencer.
- **Evidence:** `page.tsx:325-356`, `page.tsx:272-273`, `lib/api/client.ts:118`

### MEDIUM — Dashboard's most urgent signals are dead text (headline + 2 of 4 KPI rows don't drill down)
- **Severity:** Medium · **Complexity:** S *(merged: "KPI strip risk rows not clickable" + "headline not a Link")*
- **Business impact:** At the moment of highest intent, the headline "Tienes 3 proveedores en riesgo" and the "Faltantes obligatorios" / "En revisión" KPI rows are non-interactive. Reading "you have risk" costs 0 clicks; acting on it costs ~3.
- **User impact:** "Faltantes" and "En revisión" rows still show `hover:bg-surface-hover` (implying interactivity) but render the `ArrowRight` chevron as an empty spacer and lead nowhere; "Proveedores" and "Por vencer" do navigate — an inconsistent affordance.
- **Root cause:** `summaryHeadline()` returns a plain string; in the rows array only Proveedores (`page.tsx:327`) and Por vencer (`page.tsx:348`) carry `href`; the shared `content` div applies hover unconditionally (`page.tsx:376`) while the chevron is conditional (`page.tsx:393-401`).
- **Recommended solution:** Wrap the hero headline in a `Link` to `/client/vendors?level=red` (vendors page parses `?level=` and auto-filters — `vendors/page.tsx:66-68`). Give "Faltantes" → `?level=red` and "En revisión" → `/client/submissions`, so every risk KPI has a consistent drill affordance. If a destination genuinely can't be filtered, drop the hover on non-link rows.
- **Evidence:** `page.tsx:259-267,326-355,376,393-401`; `vendors/page.tsx:66-68`

### MEDIUM — No trend / period-over-period signal anywhere on the live surfaces
- **Severity:** High *(see §13 — kept High there as the executive-benchmark headline)* — listed here as the dashboard manifestation. **Complexity:** M
- **Business impact:** The CFO/Sponsor 60-second question "are we better or worse than last month?" is structurally unanswerable on the live dashboard. A portfolio at 78% looks identical whether it climbed from 60% or fell from 95%.
- **Root cause:** Trend was built only for the report engine (`insights._approval_trend`, `data_fetchers._compute_compliance_history_6mo`). `ClientOverview` has no prior-period fields; the hero gauge/KPI strip render point-in-time only. `StatCard` even exposes an unused `trend` sparkline prop (`stat-card.tsx:139-146`).
- **Recommended solution:** Add a compliance_pct delta-vs-prior-month to `ClientOverview`, render it next to the `RadialGauge`; optionally wire `StatCard`'s `trend` prop into the strip.
- **Evidence:** `lib/api/client.ts:108-123`; `page.tsx:217-257,317-356`; `stat-card.tsx:139-146`; `apps/api/app/services/reports/insights.py:147-164`

### MEDIUM — Whole dashboard blocks on one `Promise.all`; one feed failure blanks the page
- **Severity:** Medium · **Complexity:** M
- **Business impact:** The hero gauge (driven only by `overview`) can't paint until the slowest of four batched calls returns, and a single failed call rejects the whole batch into a page-level error.
- **Root cause:** A single `Promise.all` of overview+submissions+activity+notifications with one shared `.catch` → `setError` (`page.tsx:118-135`); render gate is `!overview ? <DashboardSkeleton/>` after the error check (`page.tsx:155-160`).
- **Recommended solution:** Render hero + KPI strip as soon as `overview` resolves; let each feed own its loading+error (`Promise.allSettled` or independent `useQuery` — react-query is already used in `app/admin/*`). One failure degrades one card.
- **Evidence:** `page.tsx:118-135,155-160,76-89`

### MEDIUM — Headline compliance % has no denominator or target band
- **Severity:** Medium · **Complexity:** M
- **Business impact:** "XX% cumplimiento" is the biggest figure on screen with no denominator (% of what?) and no target marker; the gauge flips tone at hard-coded 85/60 with no SLA context. Vendor *detail* already pairs its gauge with "X de Y obligaciones al día" (`vendors/[vendor_id]/page.tsx:324-326`); the portfolio hero does not.
- **Recommended solution:** Thread a portfolio-level denominator under the hero gauge (mirror the detail pattern) and render the 85% target as a ring tick.
- **Evidence:** `page.tsx:227-234,218-223`; `vendors/[vendor_id]/page.tsx:324-326`

### MEDIUM — Client switcher displays raw 36-char UUIDs instead of company names
- **Severity:** Medium · **Complexity:** M
- **Business impact:** Multi-tenant users (internal admins, holding-company sponsors) get a dropdown of opaque UUIDs; picking the wrong tenant is error-prone and reads as internal-grade UI. Only affects users with >1 visible client (switcher hidden otherwise, `page.tsx:146`).
- **Root cause:** `ClientMe.visible_client_ids` is a bare id list (`lib/api/client.ts:93`) from `_visible_client_ids_for_user` (`client.py:134-155`); `Client.id` is a `String(36)` UUID (`entities.py:51`). Switcher maps each id to `<option>{cid}</option>` (`page.tsx:205-209`).
- **Recommended solution:** Return `visible_clients:[{id,name}]` from `/client/me` and render the name (id as muted suffix/title).
- **Evidence:** `page.tsx:205-209,146-152`; `lib/api/client.ts:93`; `client.py:134-155,501`; `entities.py:51`

### MEDIUM — Bare `<select>` ClientSwitcher suppresses the focus ring (keyboard focus invisible)
- **Severity:** Medium · **Complexity:** S
- **Business impact:** WCAG 2.4.7. Keyboard tenant-switch loses focus visibility. (Note: the shared `Select` primitive is NOT affected — it has `focus-visible:ring-2` at `select.tsx:17`, only lacks offset.)
- **Root cause:** `ClientSwitcher` `<select>` applies `focus:outline-none` with no replacement ring (`page.tsx:203`).
- **Recommended solution:** Remove `focus:outline-none`, add the tokened ring (`focus-visible:ring-2 ring-[color:var(--border-focus)]/40 ring-offset-2`).
- **Evidence:** `page.tsx:200-204`; `components/ui/select.tsx:9-22`

### LOW — Distribution card triple-encodes one 3-number split (donut + rows + StackedBars)
- **Severity:** Low · **Complexity:** S
- **Business impact:** `SemaphoreDistribution` renders a Donut, a SemaphoreRow list (count+%), AND a StackedBars of the identical green/yellow/red segments — three encodings of one vector, crowding out the missing at-risk list. The vendors page already removed an equivalent redundant StackedBars (de-dup comment at `vendors/page.tsx:233-236`).
- **Recommended solution:** Drop the StackedBars (`page.tsx:470-476`); reclaim the space for the at-risk providers list. Optionally make each `SemaphoreRow` a `Link` to `/client/vendors?semaphore_level={tone}`.
- **Evidence:** `page.tsx:453-477,226-234`

### LOW — KPI values render `0` as an em-dash, hiding the all-clear state
- **Severity:** Low · **Complexity:** S
- **Business impact:** `{row.value === 0 ? '—' : row.value}` (`page.tsx:391`) erases "zero problems (good)" vs "no data." A clean portfolio looks like missing data; screen readers announce a bare dash.
- **Recommended solution:** Show literal `0` for count KPIs; reserve the em-dash for genuinely null values (these counts are never null).
- **Evidence:** `page.tsx:391`

### LOW — `Accesos rápidos` duplicates the top nav and omits Reportes + Auditoría
- **Severity:** Low · **Complexity:** S
- **Business impact:** QuickLinks lists 5 destinations all already in the persistent nav, consuming prime real estate while omitting Reportes and the audit-package builder (two high-intent destinations).
- **Recommended solution:** Replace redundant entries with outcome-oriented shortcuts: a one-click executive report, `/client/auditoria`, and a pre-filtered `/client/vendors?level=red`.
- **Evidence:** `page.tsx:662-689`; `_shell.tsx:81-90`

### LOW — Several recency captions use ad-hoc 10px text + "hace segs" colloquialism
- **Severity:** Low · **Complexity:** S
- **Business impact:** Recency captions render at `font-mono text-[10px] text-tertiary` (below the 11px eyebrow token); `timeAgo` emits "hace segs" — terse/dev-flavored. (Contrast claim is stale: gray-450 ≈ 5:1 passes AA; this is polish, not a11y.)
- **Recommended solution:** Standardize to the 11px eyebrow token; replace "hace segs" with "hace un momento"/"ahora"; add an absolute-datetime tooltip for auditors.
- **Evidence:** `page.tsx:567,636,752,780`; `globals.css:117,318`

---

## 3. Navigation Audit (`apps/web/app/client/_shell.tsx`, `back-bar.tsx`, `user-menu.tsx`, `search-bar.tsx`)

> The shell/nav was audited twice (in the "Consent gate + Shell" scope and the "Navigation/IA & Routing" scope). The two passes describe the same root issues; merged here.

### HIGH — Nav, bell, logo, BackBar and search all drop `?client_id` — internal/multi-client users lose tenant scope on first click
- **Severity:** High · **Complexity:** M *(merged across both scopes; this is the strongest nav finding)*
- **Business impact:** Internal compliance staff (whose `default_client_id` is null) and any `client_admin` with >1 visible client silently jump to the *wrong* tenant's data the instant they click any nav item, the bell, the logo, or run a search. For a compliance product this is a trust-breaking data-context error with zero on-screen signal.
- **User impact:** An internal_admin viewing Tenant A clicks "Proveedores" → empty/own-scope page; a multi-client admin is bounced to their default client on every nav click. `useUrlClientId` is documented as the ONLY scoping mechanism (`use-url-client-id.ts:8-22`).
- **Root cause:** The shell reads scope (`urlClientId`, `_shell.tsx:113`) but every NAV href is a static literal (`_shell.tsx:81-90`, mapped at `:334-336`/`:379-381`), the bell `Link` is `/client/notifications` (`:287`), the logo `Link` is `/client/dashboard` (`:277`), `SearchBar` `resultsHref='/client/buscar'` (`:285`), and BackBar `homeHref='/client/dashboard'` (`:404`). The five scope-blind destination pages (submissions, notifications, metadata, activity, reports) never even call `useUrlClientId`, so they cannot honor it. Per-page builders (`vendors`/`calendar`/`dashboard`) *do* preserve it — proving the pattern is load-bearing and inconsistently applied.
- **Recommended solution:** Add a `withClientId(href)` helper (sibling to `lib/navigation/return-to.ts`; none exists today) that appends `?client_id` when set; apply to the NAV map, bell, logo, SearchBar `resultsHref`, and BackBar `homeHref`. Make the five scope-blind pages read `useUrlClientId` and pass `{ client_id }` into their list calls. Add a test asserting nav links preserve the param.
- **Evidence:** `_shell.tsx:81-90,113,277,285,287,334-336,379-381,404`; `use-url-client-id.ts:8-22`; `vendors/page.tsx:70-80`; `calendar/page.tsx:86`; `dashboard/page.tsx:102`; scope-blind: `submissions/page.tsx:77,98`, `notifications/page.tsx:138`, `metadata/page.tsx:32`, `activity/page.tsx:46`, `reports/page.tsx`

### HIGH — Global search is completely unreachable on phones (<640px)
- **Severity:** High · **Complexity:** S *(merged: "Consent/Shell" + "Nav/IA" + the Search-scope mobile finding)*
- **Business impact:** On the device most used for the "health in <60s" check, search simply does not exist. The component docstring asserting the drawer exposes it is provably false.
- **User impact:** Below 640px the header `SearchBar` is `hidden sm:flex` (`search-bar.tsx:45`) and the hamburger drawer renders only the 8 NAV items (`_shell.tsx:374`) — none is `/buscar`. Grep confirms `/client/buscar` appears only in the hidden SearchBar and the page itself.
- **Root cause:** `/client/buscar` is never added to the NAV array; the docstring (`search-bar.tsx:16-19`) wrongly claims drawer reachability.
- **Recommended solution:** Add a "Buscar" entry (MagnifyingGlass, `/client/buscar`) to the NAV array, OR render a full-width SearchBar at the top of the mobile drawer. Fix the false docstring.
- **Evidence:** `search-bar.tsx:45,16-19`; `_shell.tsx:81-90,374`

### MEDIUM — Mobile nav drawer is `role="dialog"` but has no focus trap, Escape handler, or focus restoration
- **Severity:** Medium · **Complexity:** M *(merged across Consent/Shell + Accessibility scopes)*
- **Business impact:** The drawer is the ONLY navigation below 1024px, so keyboard/SR users on tablets/phones cannot navigate reliably — a flaggable craft gap in any enterprise a11y RFP. (Not a hard keyboard *trap*: it remains operable via Tab/backdrop/toggle; the defects are missing Escape, focus-trap, and focus-return.)
- **Root cause:** Hand-rolled `<div role="dialog">` (`_shell.tsx:357-401`) with only a backdrop-click close; no open-state focus management. The project ships Radix Dialog (`components/ui/dialog.tsx`) and vaul Drawer (`components/ui/drawer.tsx`), both unused here; `user-menu.tsx:79-96` already has the Escape pattern.
- **Recommended solution:** Re-implement with Radix Dialog/vaul, or add Escape close + initial focus + focus-return + focus trap + `inert` on the page behind.
- **Evidence:** `_shell.tsx:357-401,310-322,159-161`; `user-menu.tsx:79-96`

### MEDIUM — Notification preferences unreachable from nav and the bell; no `/client/configuracion` hub
- **Severity:** Medium · **Complexity:** S *(merged across Notifications, Profile, and Nav/IA scopes)*
- **Business impact:** The portal's only settings surface is reachable only via a "Preferencias" button on the notifications inbox. No parent "Configuración", no breadcrumb, no Settings nav item; the bell links to the feed, and UserMenu's only destination is `/client/onboarding`.
- **Root cause:** `/client/configuracion/notificaciones` is linked only from `notifications/page.tsx:223-228`; `_shell.tsx:306-307` points profile to onboarding; `user-menu.tsx:149-165` has a single profile link; `app/client/configuracion` has no index route (so the bare segment 404s). The panel doc-comment still says "Hosted on /portal/perfil" (`notification-preferences-panel.tsx:14`).
- **Recommended solution:** Add a "Preferencias de notificaciones" row to UserMenu and/or a `/client/configuracion` index. Fix the stale comment.
- **Evidence:** `notifications/page.tsx:223-228`; `_shell.tsx:306-307`; `user-menu.tsx:149-165`; `notification-preferences-panel.tsx:14`

### MEDIUM — Two competing back affordances co-render on detail pages
- **Severity:** Medium · **Complexity:** M
- **Business impact:** Vendor detail and audit pages render their own contextual "Volver" AND the shell's global BackBar, with *different* targets (`router.back()` vs a deterministic href), so the same intent yields different destinations.
- **Root cause:** BackBar renders globally except `hiddenOn=['/client/onboarding']` (`_shell.tsx:403-406`), intentionally coexisting with page-level back links (`back-bar.tsx:11-15`); pages add their own (`vendors/[vendor_id]/page.tsx:250-252`, `auditoria/page.tsx:335-341`).
- **Recommended solution:** Pick one model. Extend `hiddenOn` with the detail routes (let the deterministic per-page back win), or replace BackBar with breadcrumbs.
- **Evidence:** `_shell.tsx:403-406`; `back-bar.tsx:11-15`; `vendors/[vendor_id]/page.tsx:250-252`; `auditoria/page.tsx:335-341`

### MEDIUM — No skip-to-content link
- **Severity:** Medium · **Complexity:** S *(merged across Shell + Accessibility scopes)*
- **Business impact:** WCAG 2.4.1 (Bypass Blocks, Level A). Every keyboard/SR user tabs past logo, search, bell, profile, and 8 nav chips on every route.
- **Root cause:** `<main>` (`_shell.tsx:408`) has no id; no skip link is the first focusable element. Grep across `app/` and `components/` finds none.
- **Recommended solution:** Add a visually-hidden-until-focused skip link as the first child before `<header>`; add `id` + `tabIndex={-1}` to `<main>`.
- **Evidence:** `_shell.tsx:408`; grep (empty)

### MEDIUM — BackBar visibility relies on `window.history.length`, making global back non-deterministic
- **Severity:** Medium · **Complexity:** S
- **Business impact:** The bar *hides* on a freshly-opened deep link (where it's most useful) and `router.back()` can navigate *out* of CheckWise after an external referrer. The portal's deep links are shared in notifications/emails.
- **Root cause:** Gates on `history.length > 1` (`back-bar.tsx:51-59`) and uses `router.back()` (`:69`); `safeReturnTo` parent resolution exists (`return-to.ts:31-56`) but is unused by BackBar.
- **Recommended solution:** Drive global back from a deterministic parent/`returnTo` href, falling back to `homeHref`. Resolves the dual-back ambiguity too.
- **Evidence:** `back-bar.tsx:51-59,61,69`; `return-to.ts:31-56`

### LOW — Two nav landmarks share the identical accessible name "Portal cliente"
- **Severity:** Low · **Complexity:** S
- **Root cause:** Both `<nav>` carry `aria-label='Portal cliente'` (`_shell.tsx:326`, `:370`). Mitigated: desktop nav is `lg`-hidden, drawer only mounts when open.
- **Recommended solution:** Differentiate labels ("Navegación principal" / "Menú de navegación") or drop the drawer nav's (its dialog parent already has `aria-label='Menú cliente'`).
- **Evidence:** `_shell.tsx:325-326,369-370`

### LOW — Standalone routes light up no active nav item
- **Severity:** Low · **Complexity:** M
- **Root cause:** Active state = `pathname === item.href || startsWith(href+'/')` (`_shell.tsx:330-331,375-376`); `/client/auditoria`, `/client/buscar`, `/client/onboarding`, `/client/configuracion/notificaciones` share no NAV prefix. (Mitigated: each renders its own H1 + eyebrow + BackBar, so orientation isn't lost.)
- **Recommended solution:** Add a route→section map so child routes resolve to a parent nav item.
- **Evidence:** `_shell.tsx:330-331,375-376`

### LOW — No breadcrumbs; deep routes rely on a single history-based back
- **Severity:** Low · **Complexity:** M
- **Root cause:** No breadcrumb primitive (`lib/navigation/` has only `return-to.ts`); orientation leans on BackBar + per-page "Volver". The portal is shallow (mostly list→detail), so marginal value is low.
- **Recommended solution:** Optional lightweight breadcrumb slot for detail/child routes (Proveedores › {vendorName}).
- **Evidence:** `back-bar.tsx:65-80`; `vendors/[vendor_id]/page.tsx:250-252`

### LOW — Horizontal nav uses `overflow-x-auto` with 8 chips and no scroll affordance
- **Severity:** Low · **Complexity:** M
- **Root cause:** `overflow-x-auto` (`_shell.tsx:327`), `shrink-0` chips (`:339`), no fade/active-into-view; whether chips clip between 1024–1180px is plausible but unmeasured.
- **Recommended solution:** Measure real cutoff; allow `flex-wrap` at intermediate widths or add an edge fade + `scrollIntoView` for the active chip.
- **Evidence:** `_shell.tsx:325-353`

### LOW — Flat 8-item nav weights low-frequency surfaces equal to the executive core
- **Severity:** Low · **Complexity:** M
- **Root cause:** Single flat NAV array, no tiers (`_shell.tsx:81-90`); Metadata (a power-user export) is a peer of Resumen; Reportes sits 7th, far from the decision loop. (Subjective: 8 flat items is within the comfortable range — the one concrete win is moving Reportes up.)
- **Recommended solution:** Light grouping or, minimally, move Reportes next to the decision loop. Validate against analytics first.
- **Evidence:** `_shell.tsx:81-90`

---

## 4. Provider Management Audit (Vendors list + Vendor detail)

### Provider Portfolio list (`apps/web/app/client/vendors/page.tsx`)

#### HIGH — No sorting; the portfolio cannot be ranked by risk (the #1 job of this screen)
- **Severity:** High · **Complexity:** M
- **Business impact:** A Compliance Manager/CFO with 40+ providers cannot click a column header to bring the worst providers / lowest % / most missing docs to the top. The semáforo pill filter (`page.tsx:257-275`) mitigates by isolating red, but within any set there's no ordering, and default order is workspace `created_at desc` — a brand-new green provider can sit above a long-standing red one.
- **Root cause:** Shared `DataTable` is documented "no sorting, no pagination" (`data-table.tsx:44`); `_scoped_workspaces` orders by `created_at.desc()` (`client.py:222`); `client_vendors` (`client.py:1292-1302`) has no sort param. The worst-first `_SEMAPHORE_SORT_ORDER` (`client.py:1153`) is applied only to the calendar agenda.
- **Recommended solution:** Default-sort returned rows worst-first (red→yellow→green, then ascending compliance_pct, then descending missing+rejected) before passing to `DataTable`; better, add sortable column headers via a `sortKey` on `DataTableColumn`. Eventually move server-side.
- **Evidence:** `data-table.tsx:44`; `vendors/page.tsx:280-291,257-275`; `client.py:217-224,1292-1302,1153`

#### HIGH — Portfolios over 100 providers silently truncate — missing rows, wrong count, no pagination
- **Severity:** High · **Complexity:** M *(instance of the portal-wide truncation theme — see §8/§12)*
- **Business impact:** An enterprise client with >100 providers sees only 100 with zero indication. Risk in 101+ is invisible; the "Proveedores" KPI and per-bucket sums under-report because they're derived from `rows.length`, not the API `total`.
- **Root cause:** `listClientVendors` sends only search+semaphore (`page.tsx:88-95`), never `limit`/`offset`; backend defaults `limit=100` and *does* return `total`+`has_more` (`client.py:1300,1389-1394`), but the FE ignores `total` and `ClientVendorListResponse` doesn't even declare `has_more` (`client.ts:154-158`). Strip values/sums read `rows` (`page.tsx:224,290,123-134`).
- **Recommended solution:** Short term, pass `limit=500` (backend max) and surface the true `total` ("Mostrando 100 de N"). Proper fix: add `has_more`+`offset` to the FE type/signature and wire offset pagination/infinite scroll.
- **Evidence:** `vendors/page.tsx:88-95,224,290,123-134`; `client.ts:508-514,154-158`; `client.py:1300-1301,1389-1394`

#### HIGH — "Reporte" generation throws a full-screen blocking overlay that freezes the whole portfolio
- **Severity:** High · **Complexity:** S
- **Business impact:** Generating a per-provider report (multi-second inline AI op) renders a `fixed inset-0 z-50` overlay blocking the whole page and disables *every* row's buttons; no cancel. The portfolio is held hostage by a single-row action.
- **Root cause:** `onGenerateReport` sets `generatingVendorId` → full-viewport overlay (`page.tsx:176-191`) + `disabled={generatingVendorId !== null}` across all rows (`:468`); awaited inline with no abort. A per-row spinner already exists (`:472-476`), making the overlay redundant.
- **Recommended solution:** Scope the loading state to the originating row (keep the per-row spinner; drop the overlay or make it an inline non-blocking banner). Only disable the one row. Add a client-side timeout (see Reports finding).
- **Evidence:** `vendors/page.tsx:176-191,468,472-476`

#### MEDIUM — "Próx. a vencer ≤14d" column and "Renovación" pill use different deadline windows (14d vs 30d)
- **Severity:** Medium · **Complexity:** S
- **Business impact:** A row can show a "CSF · en 25d" renewal pill while its "≤14d" cell reads "—", forcing a click-through to reconcile and eroding trust.
- **Root cause:** `due_soon` = 0–14 days over calendar slots (`client.py:341-342`); `_next_renewal_for_workspace` = 30-day window over onboarding requirements (`client.py:246-253,272`). Two functions, two windows, side-by-side with no explanation. (They measure genuinely different things — entregas vs expediente renewals.)
- **Recommended solution:** Keep them distinct but add a "Renovación" header tooltip explaining the two horizons, and/or centralize the window constants.
- **Evidence:** `vendors/page.tsx:421`; `client.py:341-342,246-253,272`

#### MEDIUM — 8+ column table has no responsive treatment below the `lg` drawer breakpoint
- **Severity:** Medium · **Complexity:** L *(see also §12 — paired with the metadata/submissions table responsiveness)*
- **Business impact:** A Sponsor on a phone gets a 10-column table that only horizontal-scrolls; semáforo + actions can't be seen together. The calendar matrix proves a mobile accordion pattern exists, unused here.
- **Root cause:** Single `overflow-auto` wrapper (`table.tsx:28-38`) + fixed px column widths (`vendors/page.tsx:344-491`), no responsive collapse.
- **Recommended solution:** Stacked card variant for `<md` (Proveedor + semáforo + % headline, buckets as key-value, actions as footer), or hide low-priority numeric columns below `md`. Implement as a `DataTable` `mobileCard` mode.
- **Evidence:** `table.tsx:28-38`; `vendors/page.tsx:344-491`

#### MEDIUM — Compliance % bars all share the generic accessible name "Progreso"
- **Severity:** Medium · **Complexity:** S
- **Business impact:** Every row's bar announces "Progreso, 73 por ciento" with no provider identity on the progressbar itself. (Value IS announced via `aria-valuenow`+`showValue`, and the row's first cell is the vendor name, so context isn't lost — a quality degradation, not a blocker.)
- **Root cause:** `<Progress value showValue tone>` with no `label` (`vendors/page.tsx:367-385`); `progress.tsx:57` defaults `aria-label` to "Progreso".
- **Recommended solution:** Pass `label={`Cumplimiento de ${row.vendor_name}`}` or add a separate `ariaLabel` prop.
- **Evidence:** `vendors/page.tsx:367-385`; `progress.tsx:55-57`

#### MEDIUM — "Novedades" unread counts capped at a separate 200-item fetch
- **Severity:** Medium · **Complexity:** M
- **Business impact:** Per-vendor unread counts beyond the first 200 notifications silently read 0, making "who has unresolved observations" unreliable on the busiest portfolios.
- **Root cause:** `refresh()` fetches `listClientNotifications({unread_only, limit:200})` and tallies client-side (`page.tsx:94-100`); no per-vendor aggregate.
- **Recommended solution:** Move the unread-per-vendor count to the server as part of the vendor row payload (`unread_count` on `ClientVendorRow`, same pass as `client.py:1344-1367`), eliminating the second fetch.
- **Evidence:** `vendors/page.tsx:94-100,446-455`

#### LOW — KPI strip is read-only (clicking "En riesgo: 3" doesn't filter)
- **Severity:** Low · **Complexity:** M — `MetadataStrip` renders non-interactive spans (`metadata-strip.tsx:53-66`); the working semáforo filter is separate (`vendors/page.tsx:257-275`). Make risk-bearing strip items call `setLevel`.
#### LOW — Renewal pill abbreviation is a brittle 4-name `.replace()` chain
- **Severity:** Low · **Complexity:** S — `vendors/page.tsx:552-556`; full name preserved in `title` (`:565`). Source a `short_label` from the requirement catalog. (Largely latent: today's emitted set is the 4 hardcoded names.)
#### LOW — Four near-identical numeric columns dilute the scan; "Pendientes" alone is a non-drill cell
- **Severity:** Low · **Complexity:** M — `vendors/page.tsx:386-431,297-336`. Tier the columns by severity (Rechazados→error, Faltantes→warning, Pendientes→muted) or consolidate into one "Pendientes de atención" with a breakdown popover.

### Provider Detail (`apps/web/app/client/vendors/[vendor_id]/page.tsx`)

#### HIGH — Recommended "next corrective action" cards are dead ends
- **Severity:** High · **Complexity:** M
- **Business impact:** The core job (investigate a problem provider, know the next step) is incomplete: "Acción sugerida: Alta" cannot be clicked to act or jump to the obligation, slowing the <60s loop.
- **Root cause:** `SuggestedActionsCard` (`page.tsx:675-734`) and `AttentionTodayCard` (`page.tsx:738-787`) render plain non-interactive `<li>`. Backend hrefs exist but target the *provider's* `/portal/upload` (`portal.py:3638-3642,3859`), correctly dropped client-side. The adjacent `DocumentActionItemsCard` DOES open docs via `submission_id`, so the affordance exists; suggested/attention rows carry `requirement_code`/`period_key` (`client.ts:201-202`) but expose no self-anchor.
- **Recommended solution:** Link high-priority rows to `?focus=<requirement_code>#documentos` (the `FOCUS_KINDS`/`focusKey` machinery exists at `page.tsx:527-545`), and/or open the doc when `submission_id` resolves. At minimum make them keyboard-focusable links.
- **Evidence:** `page.tsx:694-728,750-782,158-170,527-545`; `portal.py:3638-3642,3859`; `client.ts:201-202`

#### HIGH — Raw machine tokens shown to executives (`a.type`, `n.result`, `contract.status`)
- **Severity:** High · **Complexity:** S
- **Business impact:** A CFO/Legal Director sees "verify_mismatch", "complete_onboarding", "prevalidado", "recibido", "approve" on an executive-Spanish page that already ships a localization layer.
- **Root cause:** Three spots bypass existing localizers: `contract.status` raw (`page.tsx:476`, source `client.py:1550`), suggested-action `a.type` raw (`:716-717`, source `portal.py:3628-3706`), reviewer `n.result` raw (`:888`, source `submission_workflow.py:398`). `statusLabel`/`statusVariant` (`statuses.ts:127,160`) and the `ReviewerAction` map (`statuses.ts:40-47`) exist and are unused for these.
- **Recommended solution:** `<Badge variant={statusVariant(contract.status)}>{statusLabel(contract.status)}</Badge>`; a Spanish category-label map for `a.type`; route `n.result` through a reviewer-action label.
- **Evidence:** `page.tsx:476,716-717,888`; `client.py:1550`; `portal.py:3628-3706`; `submission_workflow.py:398`; `statuses.ts:40-47,127,160`

#### MEDIUM — Hard load failures styled as soft amber warnings, no retry, no 404 distinction
- **Severity:** Medium · **Complexity:** M
- **Business impact:** Any fetch error replaces the page with a small `--status-warning-*` banner, only the raw thrown message, no "Reintentar", same copy for a true 404/403 as a transient blip. (A back path technically exists via the shell action.)
- **Root cause:** Error branch uses warning tokens for error outcomes (`page.tsx:258-261`); `ClientApiError` carries `.status` (`client.ts:25-31,68,701`) but the catch discards it.
- **Recommended solution:** Use `--status-error-*` + "Reintentar" + "Volver a proveedores"; distinguish 404/403 via `ClientApiError.status`.
- **Evidence:** `page.tsx:258-261,139-152`; `client.ts:25-31,68,701`

#### MEDIUM — "Atención inmediata" / "Documentos por atender" / "Próximos vencimientos" overlap with no cross-reference
- **Severity:** Medium · **Complexity:** M
- **Business impact:** "What needs attention" is split across three independently-computed lists with overlapping items (expired/due_soon appear in multiple) and no dedup/badge/scope subhead, slowing triage.
- **Root cause:** Three backend arrays each render standalone (`page.tsx:271,274,278`); `AttentionTodayCard` has no `description` (`:740`); `attention_today` (`portal.py:3834-3882`) structurally overlaps `document_action_items` and `upcoming_deadlines`.
- **Recommended solution:** Merge `attention_today` into "Documentos por atender" as a pinned "urgente" band, OR add a one-line scope descriptor to `AttentionTodayCard` and visually link overlapping rows.
- **Evidence:** `page.tsx:271,274,278,514-515,740`; `portal.py:3841-3882`

#### MEDIUM — Hero stacked bar has no text equivalent for the segments
- **Severity:** Medium · **Complexity:** S *(part of the chart-a11y theme — see §10)*
- **Business impact:** The hero expediente breakdown is a `role="img"` bar labeled only "Distribución" with the legend suppressed; AT users get the headline % and X/Y ratio but not the approved/in-review/needs-correction/missing split.
- **Root cause:** `ExpedienteMicroBar` passes `showLegend={false}` (`page.tsx:355-365`); `StackedBars` hard-codes `aria-label="Distribución"` with counts only in the suppressed legend (`charts/index.tsx:428-429,450-467`).
- **Recommended solution:** Compose a dynamic `aria-label` enumerating segments+counts, or render a visually-hidden value list.
- **Evidence:** `page.tsx:355-365`; `charts/index.tsx:416-429,444`

#### LOW — Header crowds four equal-weight actions
- **Severity:** Low · **Complexity:** S — Generar reporte (default) + 3 outline (incl. Volver) in a flat `flex-wrap` (`page.tsx:195-254`, `_shell.tsx:431`). Collapse the two downloads into a "Descargar" dropdown. (Primary IS distinguished via `variant=default`.)
#### LOW — "Documentos por estado" donut is a static metric with no drill-down
- **Severity:** Low · **Complexity:** S — `page.tsx:791-829`. Add a "Ver documentos" Surface action and/or make legend rows set `?focus`. (Counts come from `document_state_counts`, distinct from action-item kinds → needs a state→kind map.)
#### LOW — Reviewer-note timestamps use a different (local-TZ, long) date format than the rest of the page
- **Severity:** Low · **Complexity:** S — `page.tsx:888` (`toLocaleString` no options) vs curated `formatDeadline` (`:517-525`, UTC) vs contracts (`:461-465`, curated local). Use one shared curated formatter.
#### LOW — Deep-link focus only targets the documents card
- **Severity:** Low · **Complexity:** M — `page.tsx:158-170` hardcodes `getElementById("documentos")`; contract/notes/deadline deep-links unsupported. (No existing link is broken; speculative future routing.) Generalize focus targeting with stable ids per card.

---

## 5. Reports & Audit Package Audit

### Reports (`reports/page.tsx`, `reports-list-view.tsx`, `story-view.tsx`, `report-editor.tsx`, report blocks)

#### HIGH — One-click report generation has no client-side timeout; the full-screen overlay can spin forever
- **Severity:** High · **Complexity:** S
- **Business impact:** A CFO clicking a preset on a slow/cold backend (the slowest report op: hybrid AI + deterministic) sees a `fixed inset-0 z-50` overlay with no error and no escape — the exact "spinner forever" class already hotfixed for report *reads*, now on the buyer's marquee action.
- **Root cause:** `createReportFromPreset()` calls `fetchJson()` with NO `timeoutMs` (`reports.ts:475-493`), unlike `getReport`/`createVersion` which pass it; the `AbortController` (`reports.ts:63-66`) only arms when `timeoutMs` is set. The overlay is gated only on `creating` (`reports-list-view.tsx:373-393`), and `onUsePreset` clears `creating` only in the catch (`:255-276`).
- **Recommended solution:** Pass a generous explicit `GENERATE_TIMEOUT_MS` (~90s, above the ~120s LLM cap — tune carefully; the unbounded choice was deliberate for AI POSTs, comment at `reports.ts:31-34`) so a hang rejects into the existing 408 handler. Optionally add a Cancel affordance.
- **Evidence:** `reports.ts:475-493,246-251,287-298,31-34,63-66`; `reports-list-view.tsx:373-393,255-276`

#### MEDIUM — Read-only client viewer still ships the entire editor export/share bundle
- **Severity:** Medium · **Complexity:** S
- **Business impact:** Slower first paint of the buyer's most-scrutinized artifact. The codebase explicitly code-split these chunks out of the viewer; that investment is nullified for 100% of client report views.
- **Root cause:** `report-editor.tsx` `dynamic()`-imports ExportButton/PreviewPdfButton/ShareDialog (`:59-79`, with a comment naming the read-only viewer bundle), but `story-view.tsx` imports those same three *statically* (`:9-13`), and the client route forces `readOnly` → StoryView.
- **Recommended solution:** Convert the three imports in `story-view.tsx` to `next/dynamic { ssr:false }` mirroring the editor; the closing-CTA section that uses them (`:193-199`) is below the fold.
- **Evidence:** `story-view.tsx:9-13`; `report-editor.tsx:55-79`

#### MEDIUM — Report block status colors resolve to hardcoded hex via undefined `--state-*` tokens
- **Severity:** Medium · **Complexity:** M *(merged with the Design-System "report semaphore detached from tokens" finding — §11)*
- **Business impact:** The report compliance semaphore is the highest-stakes visual (what a Legal Director reads for exposure). 5 blocks reference `var(--state-red,#dc2626)` / `--state-yellow,#d97706` / `--state-green,#16a34a` (+ orange/-fg/-border, `--surface-muted`, `--surface`) — NONE defined in `globals.css` — so the inline hex *always* renders, off-brand from the portal's `--status-*` reds/greens, and immune to theming/dark mode.
- **Root cause:** `report-verdict.tsx:40-42,99-100`; `key-findings.tsx:56-58`; `compliance-state.tsx:113-115`; `prioritized-actions.tsx:102-104`; `upcoming-deadlines.tsx:139-148`. `attention-list.tsx:127` was already migrated off these (comment confirms they "were never defined") — a half-finished cleanup.
- **Recommended solution:** Finish the migration: either define `--state-*`/`--surface-muted` mapped to existing primitives, or rewrite onto `--status-error/warning/success-*` (red→error, yellow→warning, green→success, orange→`--doc-expired-*`). Delete the hex fallbacks so a missing token fails loudly.
- **Evidence:** the 5 blocks above; `globals.css:158-168`; `attention-list.tsx:127`

#### MEDIUM — StoryView opening claims issues are "ya está siendo gestionada por nuestro equipo"
- **Severity:** Medium · **Complexity:** S
- **Business impact:** The paying client is responsible for maintaining compliance, yet the client_facing report opens asserting blanket managed-service coverage of every observation — frequently untrue (many actions need the client to push providers), discourages the monitoring the portal exists to drive, and muddies remediation ownership on an auditor-facing document.
- **Root cause:** `FRAMING_BY_AUDIENCE.client_facing.opening` (`story-view.tsx:244-248`) is static copy. The `vendor_facing` copy (`:256-260`) is more careful ("ya está al día o en revisión interna").
- **Recommended solution:** Rewrite the opening to orient to risk + decision ("…las observaciones marcadas indican dónde concentrar el seguimiento…"); scope any managed-service claim precisely to in_review states.
- **Evidence:** `story-view.tsx:243-254`

#### MEDIUM — Reports table is `overflow-hidden` (not `overflow-x-auto`) — clips on mobile
- **Severity:** Medium · **Complexity:** S
- **Business impact:** On narrow viewports the 5-column table is wrapped in `overflow-hidden` with `min-w-full`, so the wide "Actualizado" cell and the "Abrir" column clip off-screen rather than scroll. The sibling `vendor-risk-matrix.tsx:190` correctly uses `overflow-x-auto`.
- **Recommended solution:** Change the wrapper to `overflow-x-auto`; compact the timestamp on `<sm`.
- **Evidence:** `reports-list-view.tsx:577-578,979-982`; `vendor-risk-matrix.tsx:190`

#### LOW — Client preset gallery is a generic 2-up card grid with identical CTAs
- **Severity:** Low · **Complexity:** M — uniform `PresetCard` (`reports-list-view.tsx:751-811`) in `grid sm:grid-cols-2` (`:502`); add distinct icons + a "responde: …" scope chip. (Note: `featured={i===0}` is *correct* — the client route pins the executive summary first, `reports/page.tsx:12-17` — so the "arbitrary badge" sub-claim is wrong.)
#### LOW — `Audiencia` column is dead noise for clients (single audience) yet occupies a column
- **Severity:** Low · **Complexity:** S — filter is correctly hidden but the `<th>`/`<td>` render unconditionally (`reports-list-view.tsx:582,970-972`). Add a `showAudienceColumn` prop, pass false from the client page.
#### LOW — Two competing back affordances in the client report viewer
- **Severity:** Low · **Complexity:** S *(same root as §4/§3 dual-back)* — StoryView "Volver a reportes" (`story-view.tsx:102-108`) + the shell BackBar (not in `hiddenOn`, `_shell.tsx:403-406`). Pick one.
#### LOW — Block-level empty/error copy reads as author-time placeholders in the read-only viewer
- **Severity:** Low · **Complexity:** M — `prioritized-actions.tsx:134-142` shows "Cargando…" for null data; `vendor-risk-matrix.tsx:161-178` shows "se llenará automáticamente" for empty rows. Thread the read-only signal into empty states.
#### LOW — No empty-state for a zero-provider client; portfolio presets still generate hollow reports
- **Severity:** Low · **Complexity:** S — `reports-list-view.tsx:284-297,848-849`. Show an inline "agrega proveedores" notice linking `/client/vendors`.
#### LOW — Per-vendor report return strands the user on the reports list, not the vendor
- **Severity:** Medium→Low *(workflow)* · **Complexity:** M — generate paths push `/client/reports/{id}` with no `returnTo` (`vendors/[vendor_id]/page.tsx:116-130`, `vendors/page.tsx:138-158`); client report route hardcodes `backHref='/client/reports'` (`reports/[id]/page.tsx:18-26`). Thread `returnTo`; `safeReturnTo`/`withReturnTo` already exist.

### Audit Package builder (`apps/web/app/client/auditoria/page.tsx` + backend)

#### HIGH — Custom-selection POST download has no timeout — "Preparando…" can spin forever
- **Severity:** High · **Complexity:** S
- **Business impact:** A stalled large-ZIP/Chromium-manifest stream during a live inspection leaves an infinite "Preparando…" spinner with no recovery — the exact failure the GET path was already hardened against. This is the page's whole purpose.
- **Root cause:** `downloadAuthenticatedFile` (GET path) wraps fetch in an `AbortController` + `DOWNLOAD_TIMEOUT_MS=120s` (`download.ts:25,64-83`); `downloadClientAuditPackageZipPost` (used the moment the user touches the tree picker, `page.tsx:285`) calls `fetch()` with no signal/timeout (`client.ts:1013-1052`).
- **Recommended solution:** Add the same AbortController + 120s timeout + friendly-error to the POST helper; route both through one shared `fetchFileWithAuth`.
- **Evidence:** `client.ts:1013-1052`; `download.ts:25,64-83`

#### HIGH — Auditoría is an orphan route, absent from primary nav
- **Severity:** High *(Nav scope)* / Medium *(IA scope, given the prominent Proveedores banner)* — see §3 cross-reference. **Complexity:** S
- **Business impact:** Assembling an inspector-ready ZIP is a headline value prop and a time-critical task, but it has no nav entry — discoverable only via a banner on Proveedores (`vendors/page.tsx:197-220`) and a calendar obligation block (`obligation-block.tsx:95-100`).
- **Recommended solution:** Add `{ href:'/client/auditoria', label:'Auditoría', icon: Package }` to NAV; keep the banner as a secondary prompt.
- **Evidence:** `_shell.tsx:81-90`; `vendors/page.tsx:197-220`; `obligation-block.tsx:95-100`

#### MEDIUM — Download button disables silently — no reason for empty-selection / no `title`/`aria-describedby`
- **Severity:** Medium · **Complexity:** S — `downloadDisabled` aggregates 6 conditions (`page.tsx:263-269`); only the two cap reasons print under the button (`:656-670`); the empty-selection case (after "Limpiar") leaves a disabled "Descargar 0 documentos" with no helper and no `title`. Compute a single `disabledReason`, render it for `selectionCount===0`, and pass it as `title`/`aria-describedby`.
#### MEDIUM — Rate-limit (429) gets no tailored UX
- **Severity:** Medium · **Complexity:** S — both ZIP endpoints enforce 10/min, 60/hr (`client.py:3453,2027`; `rate_limit.py:412-416`); `onDownloadClick` catch only reads `err.message` (`page.tsx:296-301`) though `.status` is available. Special-case 429 with a cooldown message.
#### MEDIUM — No period-range validation — inverted/mixed-granularity range silently yields empty
- **Severity:** Medium · **Complexity:** M — two independent PeriodPickers, no comparison (`page.tsx:363-381`); inverted range matches nothing under interval-overlap semantics (`period_range.py:35-55`) and surfaces only as generic 0-results. Add a derived `start>end` warning; consider auto-syncing granularity.
#### MEDIUM — Two count surfaces (Resumen `file_count` vs button `selectionCount`) can disagree
- **Severity:** Medium · **Complexity:** M — `page.tsx:519-524` vs `:650-651`; diverge the instant the user deselects, with no copy stating which ships. Make Resumen selection-aware ("X de Y seleccionados").
#### MEDIUM — Tree leaf shows raw status codes (e.g. `pendiente_revision`)
- **Severity:** Medium · **Complexity:** S — `page.tsx:946` renders raw `doc.status` in an outline Badge; `statusLabel`/`statusVariant` (`statuses.ts:127,160`) unused. Contradicts the CW-03 canonical-label pass.
#### MEDIUM — Initial loads use text placeholders instead of skeletons
- **Severity:** Medium · **Complexity:** S *(design-system rule)* — `page.tsx:508-511,600-603`; `components/ui/skeleton.tsx` exists and is used on 7+ sibling pages; `DESIGN_SYSTEM.md:962`.
#### MEDIUM — Long-export has no progress/size/time signal — only "Preparando…"
- **Severity:** Medium · **Complexity:** M — near-cap (200 files) triggers a synchronous headless-Chromium INDICE.pdf render (`client.py:3495-3526`, `audit_package_manifest.py:75-103`); `selectionBytes` is computed but unused near the button (`page.tsx:252-259,640-651`). Show count + bytes + "Generando índice y comprimiendo…".
#### LOW — Every filter Surface uses the same decorative Sparkle icon (teal, reserved for Wise)
- **Severity:** Low · **Complexity:** S — `page.tsx:363,402,430,465`; rendered teal (`stat-card.tsx:268-273`). Give each a semantic Phosphor glyph; reserve Sparkle for AI.
#### LOW — No way to preview the INDICE.pdf / package layout before download
- **Severity:** Low · **Complexity:** M — promised in prose (`page.tsx:351-358,626-630`), backend-only manifest (`audit_package_manifest.py:62-103`). Frame the tree as "the exact INDICE.pdf contents"; optional HTML manifest preview.
#### LOW — Tree picker renders the full result set unvirtualized
- **Severity:** Low · **Complexity:** M — `page.tsx:771-841`, per-branch `every`/`some` recompute each render; bounded by `MAX_FILES=200` (`audit_package.py:58`) and collapsed-by-default periods (`page.tsx:818`). Memoize per-branch selection off a precomputed index.
#### LOW — API exposes `requirement_codes` filtering but no document-type UI control
- **Severity:** Low · **Complexity:** M — `client.ts:890,918-920` support it; `page.tsx:170-177` never sets it; only place `requirement_name` appears is the leaf label (`:942`). Add a "Tipo de documento" multi-select.

---

## 6. UX Findings (cross-surface, deduped)

Findings whose primary lens is *interaction/usability*. Severities and evidence repeat the canonical entry; grouped here for the UX reviewer.

| Severity | Finding | Surface | Evidence |
|---|---|---|---|
| HIGH | Full-screen blocking overlay freezes portfolio during report gen | Vendors list | `vendors/page.tsx:176-191,468` |
| HIGH | Submissions rows not actionable — can't open the document or drill down | Submissions | `submissions/page.tsx:228-240,313-335`; `client.py:2113`; `client.ts:737-759` |
| MEDIUM | Hard load failures styled as soft warnings, no retry / no 404 distinction | Vendor detail | `vendors/[vendor_id]/page.tsx:258-261` |
| MEDIUM | Audit download disables silently; no empty-selection reason | Auditoría | `auditoria/page.tsx:263-269,633-670` |
| MEDIUM | No "Limpiar filtros" affordance; filter state not in URL | Submissions | `submissions/page.tsx:65-71,188-194,236-237` |
| MEDIUM | Filtered-to-zero search renders a blank table body (no "no results") | Metadata | `metadata/page.tsx:135-189,101-108` |
| LOW | Calendar selection silently resets to default when filters change | Calendar | `calendar/page.tsx:213-223,150-155` |
| LOW | "Resueltas" tab conflates resolved with any read item | Notifications | `notifications/page.tsx:116-120,13-17` |
| LOW | No mark-as-unread / dismiss / per-row read affordance separate from title | Notifications | `notifications/page.tsx:189-206,443-507` |
| LOW | Block-level retry/error states absent in the read-only viewer | Reports | `prioritized-actions.tsx:134-142`; `vendor-risk-matrix.tsx:161-178` |
| LOW | Category chips hidden when only one category present (disappearing affordance) | Notifications | `notifications/page.tsx:254` |

**Detail on the two HIGH items unique to this lens:**

### HIGH — Submissions rows are a dead end (no document open, no drill-down)
- **Business impact:** Entregas is the system of record for "what did this provider deliver", yet a Legal Director/auditor cannot open the file from here to verify it. They must leave to the vendor expediente and re-find the document.
- **Root cause:** `DataTable` supports `onRowClick` (`data-table.tsx:70,90,223-225,256-265`) but `page.tsx:228-240` passes none; the file column renders the filename as inert `<p>` (`:313-335`). The `GET .../document` route exists (`client.py:2113`) and `clientSubmissionDocumentUrl`/`fetchClientSubmissionDocumentBlob` (`client.ts:737-759`) are *already used* on vendor detail (`vendors/[vendor_id]/page.tsx:410,430,597`).
- **Recommended solution:** Make the filename a button calling `fetchClientSubmissionDocumentBlob(row.submission_id)`; optionally wire `onRowClick` → `/client/vendors/{vendor_id}?focus=…#documentos`.

---

## 7. UI / Visual Findings

| Severity | Finding | Evidence |
|---|---|---|
| HIGH | Report semaphore colors render hardcoded hex via undefined `--state-*` tokens *(see §5/§11)* | `compliance-state.tsx:113-115`; `report-verdict.tsx:40-42` |
| LOW | Header crowds four equal-weight actions (vendor detail) | `vendors/[vendor_id]/page.tsx:195-254` |
| LOW | All audit filter Surfaces use the same decorative Sparkle icon in reserved teal | `auditoria/page.tsx:363,402,430,465` |
| LOW | Activity: rejection events use a generic `FileText` icon (color-only differentiation) | `activity/page.tsx:180-189` |
| LOW | Report masthead uses `text-white/70` `/95` instead of solid inverse-text tokens *(token adoption, NOT AA — ~7:1 passes)* | `report-masthead.tsx:61,76`; `globals.css:126-127` |
| LOW | Phone-verification chip uses raw `emerald-*` outside the token system | `phone-verification-flow.tsx:131,134` |
| LOW | Metadata strip "Archivo: metadata.xlsx" is a decorative non-metric in reserved teal; search in a redundant titled card | `metadata/page.tsx:115,119-126`; `metadata-strip.tsx:28-32` |
| LOW | Dashboard recency captions use ad-hoc 10px + "hace segs" | `dashboard/page.tsx:567,636,752,780` |

### LOW — Activity rejection icon is color-only (`FileText` for both upload and reject)
- **Business impact:** Iconography is the fastest pre-attentive cue; mapping rejections to the same `FileText` glyph as uploads (only color differs) weakens the one signal that flags risk and fails shape-redundancy for color-blind users (WCAG 1.4.1).
- **Recommended solution:** Use a distinct negative glyph (`XCircle`/`WarningCircle`) for rejections; keep `CheckCircle` for approvals, `FileText` for neutral uploads.
- **Evidence:** `activity/page.tsx:180-184,185-189`

---

## 8. Routing Findings

### HIGH — `?client_id` inspection scope is dropped by every nav link, the bell, and search *(canonical entry in §3)*
- Same root issue as the §3 nav finding, viewed through the routing lens: the five destination pages (submissions/notifications/metadata/activity/reports) never read `useUrlClientId` and pass no `client_id`, so they cannot honor the scope even if it were passed. `_shell.tsx:81-90,285,286-301`; grep of `useUrlClientId`.

### HIGH — Notification / deep-link query params (`?vendor_id`, `?status`) are ignored on Submissions
- **Severity:** High · **Complexity:** M
- **Business impact:** The core "alert → act" loop is broken at the destination. Notifications link to `/client/submissions?vendor_id=…` expecting a pre-filtered view; the user lands on the full unfiltered list and must re-filter by hand.
- **Root cause:** The page imports only `useEffect`/`useState` (`page.tsx:3`), seeds filters from a hardcoded object (`:65-71`), and the load effect ignores the URL (`:112-115`). The backend deliberately emits these links (`client_notifications.py:88,158,203,256`) and the UI renders them as `<Link href={action_url}>` (`notifications/page.tsx:465-467`).
- **Recommended solution:** Read `useSearchParams` on mount to seed filters; write active filters back to the URL on Aplicar (matches the URL-persist pattern on calendar/vendors).
- **Evidence:** `submissions/page.tsx:3,65-71,112-115`; `client_notifications.py:88,158,203,256`; `notifications/page.tsx:465-467`

### MEDIUM — Global search rows discard the matched document and dump on a generic vendor page
- **Severity:** Medium · **Complexity:** S *(merged with the Workflow "search returns only vendor pages" finding)*
- **Business impact:** Searching a period/folio to locate one document drops the user on the provider expediente where they must re-find it — the query's precision is discarded on click.
- **Root cause:** `buildHref` hardcodes `/client/vendors/${hit.vendor_id}` (`buscar/page.tsx:37-40`), ignoring `requirement_name`/`period_key`/`status`. The vendor page supports `?focus=…#documentos` (`vendors/[vendor_id]/page.tsx:158-170`) but the focus matcher keys on `requirement_code`, which the `SearchHit` does NOT carry (only `requirement_name`, `search.ts:25`).
- **Recommended solution:** Surface `requirement_code` on the hit, then build `?focus={requirement_code}#documentos`. Interim: append `#documentos` (or a period focus) so the row at least scrolls to the docs section.
- **Evidence:** `buscar/page.tsx:37-40`; `search.ts:14-30`; `vendors/[vendor_id]/page.tsx:154-170,543`

### LOW — Deep-link focus only targets the documents card (vendor detail) *(see §4)*
### LOW — Standalone routes light up no active nav item *(see §3)*

---

## 9. Workflow Findings

### CRITICAL — Global search cannot find a provider by name (only RFC / period / folio)
- **Severity:** Critical · **Complexity:** M
- **Business impact:** The portal's entire value prop is monitoring a PORTFOLIO OF PROVIDERS. Every persona instinctively types a provider's *name* into search; they get zero results and conclude the provider isn't in the system or the product is broken. This is the single highest-frequency failed query, and name search is table-stakes for the Vanta/Linear bar.
- **Root cause:** `search_service.detect_query_type` returns only rfc/period/folio (`search_service.py:61-77`); the three predicate branches (`:166-182`) contain no `Vendor.name`/`Client.name` `ILIKE`. The accent-insensitive `f_unaccent` helper (migration 0052, `text_search.py` `accent_ci_contains`) is wired into the entity-LIST search (`client.py:1313`), NOT this omnibox path.
- **Recommended solution:** Add an accent-insensitive `Vendor.name`/`Client.name` predicate to the folio/fallback branch via `accent_ci_contains`. Add a `name` value to `QueryType`/`SearchMatchType`; update the omnibox placeholder/description to include "nombre de proveedor"; de-duplicate to one row per vendor when matched by name (see grouping finding).
- **Evidence:** `search_service.py:61-77,152-182`; `search-bar.tsx:23`; `buscar/page.tsx:23`; `text_search.py`; `entities.py:97`

### HIGH — Risk is shown everywhere but never RANKED into an actionable worklist from the executive entry point
- **Severity:** High · **Complexity:** M *(the dashboard's missing at-risk list + the unsorted vendor list, viewed as one workflow gap)*
- **Business impact:** To find the riskiest providers and act, an exec must leave the dashboard, open `/client/vendors`, manually filter to red (the list isn't worst-first by default), then drill in. The "here are your fires, click to act" view exists only inside a generated report.
- **Root cause:** The most actionable dashboard panel is QuickLinks (generic nav, `dashboard/page.tsx:662-718`); `client_vendors()` returns `created_at desc` order (`client.py:217-224,1369-1391`); the worst-first `_SEMAPHORE_SORT_ORDER` (`client.py:1153`) is used only on the calendar agenda; worst-first ranking otherwise exists only in the report layer (`compliance-overview.tsx:186-226`).
- **Recommended solution:** Add a "Requieren tu atención" ranked panel (top 3–5 red/yellow, worst-first, primary issue + deep-link) and default-sort `client_vendors()` by semaphore.
- **Evidence:** `dashboard/page.tsx:662-718`; `client.py:217-224,1153,1369-1391`; `compliance-overview.tsx:186-226`

### HIGH — Submissions: no real pagination — table hard-capped, older entregas unreachable
- **Severity:** High · **Complexity:** M *(truncation theme)* — backend supports `offset`/`total`/`has_more` (`client.py:2406,2449-2452,2553`); FE never uses them (`submissions/page.tsx:65-91`; `client.ts:371-377,584-599` omit `has_more`/`offset`). The "Mostrar N" control only raises the cap. Add a real pager + "Mostrando 1–100 de {total}".

### HIGH — Submissions: "En revisión" status filter returns only ~⅓ of in-review entregas
- **Severity:** High · **Complexity:** M — three raw statuses (`recibido`, `pendiente_revision`, `prevalidado`) all display as "En revisión" (`statuses.ts:77-79`), but the dropdown offers only `pendiente_revision` and the backend matches exactly (`client.py:2426-2427`), silently dropping `recibido`/`prevalidado`. Make the filter operate on the collapsed label set (`status=en_revision` → `IN (…)`). `submissions/page.tsx:30-44`.

### HIGH — Activity / Submissions / Notifications truncate at a hardcoded cap with no pagination *(truncation theme)*
- **Severity:** High (activity, submissions) / Medium (notifications) · **Complexity:** M
- Activity: `listClientActivity({ limit:200 })` once, reads only `data.items`, header uses `rows.length` (`activity/page.tsx:46,86`); type omits `has_more` (`client.ts:391-396`); backend paginates (`client.py:2580-2581,2730-2737`). An audit trail that can't show history beyond 200 is not defensible evidence.
- Notifications: `{ limit:100 }` once, `all: rows.length`, `total` ignored (`notifications/page.tsx:138,521`; `client.ts:431-440`) — and the preferences copy positions the bell as the "respaldo formal de auditoría" (`notification-preferences-panel.tsx:178-182,334-338`).

### HIGH — Raw English `actor_type` + dotted action codes shown verbatim in the Activity audit trail
- **Severity:** High · **Complexity:** S
- **Business impact:** The audit trail is the evidence surface a Compliance Manager/Legal Director uses. Showing "supplier", "reviewer", "system", "submission.uploaded", "reviewer.decision", "metadata.ready" reads as a leaked internal field, not a product.
- **Root cause:** `activity/page.tsx:130` renders raw `actor_type`; `:131-133` renders raw `action` in `font-mono`. Backend emits an exhaustive, enumerable vocabulary (`client.py:2670-2719`). The admin audit log already adopted ES labels.
- **Recommended solution:** Add `ACTOR_LABELS_ES`/`ACTION_LABELS_ES` maps (or `lib/activity-labels.ts`); render the ES label as a quiet category chip; drop the redundant raw mono code. Lock with a vitest mirroring `doc-state-labels.test.ts`.
- **Evidence:** `activity/page.tsx:130,131-133`; `client.py:2670-2671,2694-2712,2719`

### MEDIUM — Metadata download failures are swallowed silently (no catch)
- **Severity:** Medium · **Complexity:** S — `downloadWorkbook` is try/finally with no catch (`metadata/page.tsx:64-80`); `downloadClientMetadata` throws on 401/timeout/non-OK (`client.ts:672-703`). The vendor-detail sibling does it right (`vendors/[vendor_id]/page.tsx:100-114`). Add a catch → inline alert + `aria-live`.

### MEDIUM — No calendar-level export/share (a core exec/audit deliverable)
- **Severity:** Medium · **Complexity:** M — only per-obligation "Empaquetar" deep-links exist (`obligation-block.tsx:46-47,95-100`); no CSV/PDF/print of the matrix or selected month (`calendar/page.tsx:261-280,310-331,353-464`). Add an "Exportar" action reusing the auditoría/ZIP plumbing.

### MEDIUM — Activity / Reports / Submissions findings don't deep-link to the offending document
- **Severity:** Medium · **Complexity:** M *(merged: report findings + activity event deep-links)* — report client_facing findings render non-interactive (`story-view.tsx:171-176`); activity rows link only the vendor name and the type lacks a per-event document key (`activity/page.tsx:134-140`; `client.ts:379-389`). Link findings/events to `/client/vendors/{id}?focus=<requirement_code>#documentos` where resolvable; interim, default the vendor link to `#documentos`.

### LOW — `terms_accepted:false` re-sent on every returning-visit save
- **Severity:** Low · **Complexity:** S — `onboarding/page.tsx:63,114,283`; the backend only ACTS on a truthy value (`client.py:1084-1106`), so it's audit-metadata noise (`:1126`), NOT a consent-integrity bug. Conditionally spread `terms_accepted` only when `isFirstTime`.

### LOW — Submit button lives outside its `<form>` — Enter-to-submit broken (onboarding)
- **Severity:** Medium→Low *(workflow)* · **Complexity:** S — `<form>` closes at `onboarding/page.tsx:281`; the save button is a `type='button'` sibling at `:332-343` with a synthetic-event cast. Move the action row inside the form, make it `type='submit'`.

### LOW — Client RFC is read-only with only a WhatsApp escape hatch
- **Severity:** Low · **Complexity:** M — `onboarding/page.tsx:190-215`; deliberate admin-managed design, but the off-platform handoff is the weak point. Add an in-product "Solicitar corrección" path.

### LOW — Metadata-only events surface in the client audit trail as noise
- **Severity:** Low · **Complexity:** S — `_CLIENT_VISIBLE_EVENTS` includes `metadata_table_exported` (`client.py:2565-2572,2701-2706`). Down-rank or filter by default.

---

## 10. Accessibility Findings

> Net posture: genuinely strong in places (matrix `<table>` with `scope` headers + per-cell `aria-label`; labeled landmarks; `aria-busy` skeletons). The `--text-tertiary` AA fix is live, so most contrast complaints are stale and were dropped. The real gaps are interaction-pattern and announcement defects.

### HIGH — Page-level fetch errors announce nothing to screen readers (no `role="alert"`)
- **Severity:** High · **Complexity:** S
- **Business impact:** When a portfolio view silently fails, an AT user waits on a page that never populates. Dashboard renders a bare styled `<div>` (`dashboard/page.tsx:155-158`) and vendor-detail a bare `<p>` (`vendors/[vendor_id]/page.tsx:258-261`); grep finds zero `role="alert"` under `app/client/`. Shared `ErrorState` has `role="alert"` (`state-surfaces.tsx:164`) and is unused.
- **Recommended solution:** Route page errors through `ErrorState`, or add `role="alert"` to the inline containers.

### HIGH — Mobile nav drawer is not a real dialog (no focus trap/Escape/restore) *(canonical in §3)*

### HIGH — Semáforo "why is this red" tooltip is keyboard/SR-unreachable
- **Severity:** High · **Complexity:** S
- **Business impact:** The plain-language reason a provider is red/yellow/green — the core "where is the risk" answer — is unreachable for keyboard/AT users; they get the color and one-word label but never the justification.
- **Root cause:** `SemaphorePill` wraps a static `<span>` (cursor-help) in a Radix Tooltip (`vendors/page.tsx:528-541`); Radix opens on focus only for a *focusable* trigger, and a `<span>` has no tab stop (verified: `@radix-ui/react-tooltip@1.2.8` dist never makes a non-focusable child tabbable). The explanatory copy (`SEMAPHORE_EXPLANATION`, `:521-526`) is portaled, mounted only on open, with no parallel accessible name.
- **Recommended solution:** Add `aria-label={SEMAPHORE_EXPLANATION[level]}` to the pill and make the trigger focusable (`tabIndex={0}` or a `<button>`). Apply anywhere a Tooltip wraps a bare span.
- **Evidence:** `vendors/page.tsx:521-541`; `tooltip.tsx:80-81`

### HIGH — Search result rows have an invisible keyboard focus (focus ring removed, no replacement)
- **Severity:** High · **Complexity:** S
- **Business impact:** WCAG 2.4.7 failure on a core navigational surface; a procurement-a11y blocker. The result `<Link>` sets `focus-visible:outline-none` with no replacement; the only emphasis is `group-hover:underline` (mouse only).
- **Recommended solution:** Add `focus-visible:ring-2 ring-[color:var(--border-focus)] ring-offset-2` to the Link and `group-focus-visible:underline` to the name.
- **Evidence:** `search-results.tsx:162,165`

### MEDIUM — Heading hierarchy skips h2 portal-wide (h1 → h3); key panel titles are non-heading `<p>`
- **Severity:** Medium · **Complexity:** M *(merged: dashboard "no h2" + portal-wide "h1→h3 skip")*
- **Business impact:** AT users navigate dense compliance pages by heading; the broken outline slows jumping to "Documentos por atender" / "Distribución".
- **Root cause:** Shell title is `<h1>` (`_shell.tsx:420`); every `Surface` panel hardcodes `<h3>` (`stat-card.tsx:266`) with no `<h2>` between; `StatGroup` uses `<h2>` (`stat-card.tsx:205`) but isn't used on the dashboard; the dashboard hero headline is a `<p>` (`dashboard/page.tsx:241`); the calendar `SelectionDetail` title is a `<p>` above `<h3>` children (`calendar/page.tsx:409,428`).
- **Recommended solution:** Add an `as`/`headingLevel` prop to `Surface` defaulting top-level panels to `h2`; promote the hero headline and `SelectionDetail` title to headings.
- **Evidence:** `_shell.tsx:420`; `stat-card.tsx:205,266`; `dashboard/page.tsx:241`; `calendar/page.tsx:409,428`

### MEDIUM — Notifications tab strip is a partial ARIA tab pattern (no `tabpanel`/`aria-controls`/roving tabindex/arrow keys)
- **Severity:** Medium · **Complexity:** M *(merged across Notifications + Accessibility scopes)* — `notifications/page.tsx:293-331` declares `role=tablist/tab/aria-selected` on plain buttons; the `<ol>` (`:264`) has no `tabpanel` role; no `aria-controls`, no roving tabindex, no Arrow handlers. Tabs ARE operable via Tab+Enter (native buttons), so degraded-not-broken. Adopt Radix Tabs (`components/ui/tabs.tsx`) or downgrade to `aria-pressed` filter buttons.

### MEDIUM — Mark-as-read actions give no screen-reader confirmation (no live region)
- **Severity:** Medium · **Complexity:** S — `markOne`/`markAll` only `setRows` (`notifications/page.tsx:189-206`); no polite live region announces the result (WCAG 4.1.3). Add a visually-hidden `aria-live="polite"` status.

### MEDIUM — Compliance gauge and donut are `aria-hidden` with no role/aria-label
- **Severity:** Medium · **Complexity:** S — `RadialGauge`/`Donut` SVGs are `aria-hidden` (`charts/index.tsx:98,177`); `MiniBars`/`StackedBars` correctly use `role=img`+`aria-label` (`:361-362,428-429`). Mitigated on the dashboard: the gauge % renders as real text (`:124-127`) and the donut segments are enumerated in the adjacent `SemaphoreRow` list (`dashboard/page.tsx:462-469`). Add `role="img"`+`aria-label` for consistency.

### MEDIUM — Hero stacked bar / chart primitives carry only a generic "Distribución" aria-label *(see §4)*
- The clearest value-less gap is vendor-detail `ExpedienteMicroBar` (`vendors/[vendor_id]/page.tsx:365`, shows only "X / Y"). Compose segment+count aria-labels in `StackedBars`/`MiniBars` (`charts/index.tsx:429,361`) when `showLegend` is false.

### MEDIUM — Skip-to-content missing *(canonical in §3)*

### MEDIUM — Bare `<select>` ClientSwitcher suppresses the focus ring *(canonical in §2)*

### MEDIUM — Tab control half-implemented on notifications *(same as the ARIA-tab finding above; the original "Notifications tab" finding from the Notifications scope is merged here)*

### LOW — Compliance matrix `<table>` lacks a `<caption>`/accessible name + arrow-key navigation
- **Severity:** Low · **Complexity:** M — `compliance-matrix.tsx:94` has no caption/aria-label (only the per-cell aria-label at `:291`); cells are individual `<button>`s (`:287-308`) in linear tab order. Add a visually-hidden `<caption>`; consider roving tabindex. (Cells are reachable + well-labeled, so not a blocker.)

### LOW — Calendar empty grid cells / current-month emphasis are color-only
- **Severity:** Low · **Complexity:** S — empty cells are `aria-hidden` divs (`compliance-matrix.tsx:269-282`); current-month header is `text-brand` vs `text-tertiary` color-only (`:127-136`). Add a visually-hidden "mes actual" marker. (Otherwise the strongest a11y surface.)

### LOW — Compliance heatmap legend is desktop-only; mobile grid has no color key
- **Severity:** Low · **Complexity:** S — legend `<ul>` inside the `lg:block` wrapper (`compliance-matrix.tsx:93,181-196`); mobile block (`:200`) has none. Mitigated: expanded accordion rows print `RISK_LABEL` text (`:397`). Move the legend to a shared footer.

### LOW — Critical event detail (timestamp + action code) rendered at hardcoded 10px (below the 11px floor)
- **Severity:** Low · **Complexity:** S — `activity/page.tsx:122,131` (`text-[10px]`), `:119` (`text-[13px]`); below `--text-eyebrow` 11px (`globals.css:318`). (Contrast is fine — `--text-tertiary` is AA-safe.) Bump to the eyebrow/caption token.

---

## 11. Design System Findings

### HIGH — Named type scale is effectively unused; ~97 arbitrary `text-[Npx]` literals + generic `text-sm/xs` replace it
- **Severity:** High · **Complexity:** L
- **Business impact:** Six competing small-text sizes (10/11/12/13px arbitrary + `text-xs`=12 + `text-sm`=14) with no rule erode the visual rhythm an enterprise tool needs. Captions, metadata, helper text blur together.
- **Root cause:** The DS scale tokens (`text-h1/h2/h3/body/body-sm/caption/label/helper`) appear ZERO times in client pages; arbitrary px literals carry the portal. Grep `app/client`: `text-[10px]`×35, `[11px]`×27, `[12px]`×19, `[13px]`×13 (97 total); `text-sm`×42, `text-xs`×30; named scale = 0.
- **Recommended solution:** Single-source the scale (next finding), map the four small literals onto two named steps (`body-sm`=13px, `caption`=11px), codify a rule, and sweep. Promote the 10px usages (below the 11px floor).
- **Evidence:** `_shell.tsx:281,420,425`; grep counts.

### HIGH — Report semaphore colors are detached from the design system (undefined `--state-*` → hardcoded hex) *(canonical in §5)*
- The strongest DS finding: 5 report blocks render off-token reds/greens that always fall through to inline hex; `attention-list.tsx` already migrated off them. See §5 for the full entry.

### MEDIUM — Two conflicting type-scale sources of truth (`globals.css --text-*` vs `tailwind.config text-*`)
- **Severity:** Medium · **Complexity:** M
- **Business impact:** A latent maintenance trap: `var(--text-h1)`=26px vs `text-h1`=22px, display 56 vs 36, etc. — they disagree on every step. (Latent today: neither set is used for client headings, which hardcode pixels.)
- **Root cause:** `globals.css:323` vs `tailwind.config.ts:106-110`, authored independently. `borderRadius`/`boxShadow` in the same config DO reference CSS vars, so the single-sourcing pattern exists.
- **Recommended solution:** Make `tailwind.config` `fontSize` entries reference the CSS vars; reconcile to the *documented* values (`DESIGN_SYSTEM.md:425-437` sides with the tailwind 22px set, NOT the globals 26px).
- **Evidence:** `globals.css:323`; `tailwind.config.ts:106-110`; `DESIGN_SYSTEM.md:425-437`

### MEDIUM — The `--density-*` token system the shell opts into is dead code
- **Severity:** Medium · **Complexity:** M — `_shell.tsx:269` sets `data-density='dense'`; `globals.css:296-304` defines the tier; grep `var(--density-` across `app/`+`components/` = 0 consumers. Wire the core primitives (Surface padding, control heights, section gap) to the tokens, or delete the system.

### MEDIUM — Two card primitives (`Surface` vs `ui/Card`) define incompatible radius/shadow/title
- **Severity:** Medium · **Complexity:** M — `Surface` (`stat-card.tsx:256,266`): `rounded-lg`/`shadow-xs`/uppercase 13px header; `ui/Card` (`card.tsx:9,22`): `rounded-md`/`shadow-soft`(=`shadow-sm`)/non-uppercase 18px title. Client portal uses only `Surface` (latent), but `ui/Card` sets the wrong precedent. Converge on the `Surface` spec; document the single card radius.

### MEDIUM — Top-level page section gap is hardcoded inconsistently (`space-y-4/5/6/7`)
- **Severity:** Medium · **Complexity:** M — `_shell.tsx:411` (5), dashboard (7), vendors/calendar/auditoria (6), submissions/metadata (5), none reference `--density-section-gap`. Standardize to one value applied once in the shell wrapper.

### MEDIUM — Three conflicting page-title (H1) treatments; none use the H1 token
- **Severity:** Medium · **Complexity:** S — shell `text-[26px]` (`_shell.tsx:420`), `PageHeader` `text-3xl sm:text-4xl` (`page-header.tsx:54`), standalone pages `text-2xl`. Route every title through one reconciled `--text-h1`.

### MEDIUM — Card radius is unsystematic (`rounded-md`×31, `rounded-lg`×22, `rounded-xl`×3, `rounded-sm`×3)
- **Severity:** Medium · **Complexity:** M — no radius-by-elevation rule; `vendors/[vendor_id]/page.tsx:304,885,906` mixes three in one file. Codify a rule (cards=`lg`, nested=`md`, pills=`full`, chips=`sm`) and sweep.

### MEDIUM — The "eyebrow" label is hand-rolled ~20× with three recipes instead of `.cw-eyebrow`
- **Severity:** Medium · **Complexity:** M — `.cw-eyebrow` (`globals.css:402-409`) used only 7× in client; 20 hand-rolled `text-[10px] uppercase` eyebrows; divergent teal/`0.18em` recipe at `_shell.tsx:281`, `page-header.tsx:49`. `_shell.tsx` itself uses both recipes. Replace with `.cw-eyebrow` (or an `<Eyebrow>` component).

### MEDIUM — Initial loads use text/spinner instead of skeletons (auditoría, metadata, onboarding) *(design-system rule, also in §5/§12)*
- `auditoria/page.tsx:508-511,600-603`; `metadata/page.tsx` (text loading); `onboarding/page.tsx:176-181`; `notification-preferences-panel.tsx:137-143`. `DESIGN_SYSTEM.md:962` mandates skeletons. Replace with shape-matched skeletons.

### LOW — Loading skeletons use `rounded-xl` while the real cards use `rounded-lg`
- **Severity:** Low · **Complexity:** S — `dashboard/page.tsx:225`(lg) vs `:799`(xl); `vendors/[vendor_id]/page.tsx:304`(lg) vs `:906`(xl) → visible corner "pop" on load. Match the skeleton radius (or reuse the real Surface shell).

### LOW — Calendar re-implements the KPI/stat card by hand instead of the shared `StatCard`
- **Severity:** Medium→Low *(consistency)* · **Complexity:** S — local `KpiTile` (`calendar/page.tsx:528-546`) diverges from `StatCard` (`stat-card.tsx`) on label style/padding/icon. Replace with `StatCard` (add a prop if a variant is missing).

### LOW — Report masthead / phone-verification / metadata strip use off-token colors *(see §7)*

### LOW — Shared `Select` primitive hardcodes `bg-white` / Tailwind tokens instead of semantic CSS vars
- **Severity:** Low · **Complexity:** S — `select.tsx:9-12` (`bg-white`, `border-input`, `ring-ring`) vs surrounding `var(--surface-*)`. Cross-surface change — migrate to semantic tokens.

---

## 12. Performance Findings

> Cross-cutting root cause: **no shared fetch cache** (`request-cache.ts` `dedupeRead` is wired to only `/me` + bell summary), so every navigation re-runs full waterfalls. Several findings below are facets of this.

### HIGH — Metadata table renders the entire master unvirtualized, with no pagination or mobile treatment
- **Severity:** High · **Complexity:** M
- **Business impact:** The documentary system of record (600+ rows on the flagship tenant, unbounded across a portfolio) mounts every row as raw `<tr>`, pinning the main thread on load; each keystroke re-filters the full array and re-renders synchronously. This is the genuinely unbounded case (grows with document count, not provider count).
- **Root cause:** Bespoke `<table>` + `documents.map` (`metadata/page.tsx:135-189`), not `VirtualTableBody`/`DataTable`; `getClientMetadata` returns the whole set with no `limit`/`offset` (`client.ts:662-666`; `client.py:2957-2983`). Also: server slices the XLSX preview to 500 rows with no `total` emitted and drops the header row → ~499-doc ceiling, silently (see truncation theme).
- **Recommended solution:** Wrap the `<tbody>` in `VirtualTableBody` (virtualizes >60 rows), or route through `DataTable`. Return `total_documents`+`truncated` from the backend; show "Mostrando N de TOTAL" + a notice pointing to the Excel.
- **Evidence:** `metadata/page.tsx:135-189,46-62`; `client.ts:662-666`; `client.py:2957-2983,2970,3066-3068`; `client_metadata.py:145`

### HIGH — One-click report / audit-package operations have no client-side timeout *(canonical in §5)*
- Report preset generation (`reports.ts:475`), vendors-list overlay, and the audit POST download (`client.ts:1013-1052`) can all spin forever.

### HIGH — No trend signal on live surfaces *(canonical in §13/§2)*

### MEDIUM — Lists render `items.length` and never surface the API `total` (no paging beyond the first capped slice) *(truncation theme — submissions/vendors/activity/notifications)*
- **Severity:** Medium · **Complexity:** L
- Every response type carries `total` and the endpoints accept `offset` (`client.py:1300-1301,2405,2580`), but the FE functions don't expose `offset` and the pages render `items.length` (`submissions/page.tsx:198-199,238`; `vendors/page.tsx:222-231,290`; `activity/page.tsx:46,86`; `client.ts:154-158/371-377/391-396/431-440`). (Note: the dashboard gauge uses a *separate* `/overview` aggregate, so portfolio-health numbers are not truncated — the harm is operators not paging past the first 100–200 rows.)
- **Recommended solution:** Surface "Mostrando N de TOTAL" everywhere; add `offset` to the FE signatures; wire real paging.

### MEDIUM — No shared fetch cache; every navigation re-runs waterfalls and refetches identity/lists
- **Severity:** Medium · **Complexity:** M — `request-cache.ts` `dedupeRead` is applied only to `getClientMe` (30s) and the bell summary (15s); all list/overview reads bypass it. The vendors roster is fetched uncached by 3 pages (`vendors`/`submissions`/`calendar`). Extend `dedupeRead` (params-keyed TTL) to the roster/overview/calendar, or adopt react-query for client reads.
- **Evidence:** `request-cache.ts:1-22`; `client.ts:482-486,508-516,616-625`; `vendors/page.tsx:89`, `submissions/page.tsx:98`, `calendar/page.tsx:100`

### MEDIUM — Dashboard fetch waterfall (identity must resolve before overview/lists fire)
- **Severity:** Medium · **Complexity:** M — `getClientMe` then a separate effect (deps `[clientId, me]`) fires the batch (`dashboard/page.tsx:91-111,113-139`); the shell also calls `/me` (coalesced). For the no-`?client_id` default case, fire the portfolio reads in parallel with identity, or pass the shell's `/me` down via context.

### MEDIUM — Vendors list refetches a 200-row notification pull on every search query
- **Severity:** Medium · **Complexity:** S — `refresh()` bundles the roster query and a `limit:200` unread-notifications pull into one `useCallback` keyed on `[urlClientId, debouncedSearch, level]` (`vendors/page.tsx:83-109`), so the search-independent notification fetch re-fires per query. Split it into its own scope-keyed effect.

### MEDIUM — Submissions page-size change refetches with the STALE limit (closure-over-state race)
- **Severity:** Medium · **Complexity:** S *(also a Workflow bug)* — `setFilters(next)` then `window.setTimeout(refresh,0)` where `refresh` closes over the pre-update `filters.limit` (`submissions/page.tsx:205-213,73-83`). First change fetches the old limit. Drive `refresh` from a `useEffect` keyed on `filters.limit`, or pass the new limit explicitly.

### MEDIUM — The two widest tables (metadata 1100px, submissions ~8 cols) have no responsive/mobile treatment *(merged with §4 vendors-table responsiveness)*
- **Severity:** Medium · **Complexity:** M — metadata locked to `min-w-[1100px]` with no card fallback (`metadata/page.tsx:138-139`); submissions has 8 fixed-width columns, no collapse (`submissions/page.tsx:246-347`); `DataTable` has no card mode. The calendar matrix proves the mobile pattern exists. Add a `DataTable` priority/card-collapse mode + a metadata mobile card layout.

### LOW — Notifications and Activity lists render every row unvirtualized
- **Severity:** Low · **Complexity:** M — hand-rolled card/timeline maps (`notifications/page.tsx:264-272`, `activity/page.tsx:88-99`), bypassing `VirtualTableBody` (which is `<tbody>`-only). Hard-capped server-side, so DOM is bounded (a few hundred light nodes) — `React.memo` the rows; longer-term a generic `VirtualList`.

### LOW — Compliance matrix renders the full providers×12 grid with no row windowing
- **Severity:** Low · **Complexity:** M — `compliance-matrix.tsx:147-177,200-211`; empty cells render cheap `aria-hidden` divs (not buttons, `:269-282`), so worst-case is bounded by provider count. Window rows once counts grow large.

### LOW — Calendar flattens and re-scans the year's obligations client-side on filter/selection
- **Severity:** Low · **Complexity:** M — `calendar/page.tsx:150-252`; all derivations are `useMemo`'d with correct deps so cost is bounded (selecting a cell only recomputes `selectionItems`). Optionally push the institution filter server-side.

### LOW — Initial metadata GET has no client-side timeout/abort
- **Severity:** Low · **Complexity:** S — `metadata/page.tsx:29-43` (cancellation but no AbortController/timeout); error EmptyState has no "Reintentar" (`:95-98`). Mirror the download `DOWNLOAD_TIMEOUT_MS` pattern + add retry.

### LOW — Calendar year input is unclamped/undebounced (fires per keystroke, can send NaN/out-of-range)
- **Severity:** Medium→Low *(perf)* · **Complexity:** S — `calendar/page.tsx:276` (`onChange={(e)=>setYear(Number(e.target.value))}`); fetch effect keyed on `year`; `parseCalendarYear` clamp (`lib/calendar-year.ts:28-34`) only runs at mount. Route input through the guard or use prev/next steppers (range is only 2021–2030).

### LOW — Generic `RouteSkeleton` mismatches every client page layout (CLS)
- **Severity:** Low · **Complexity:** S — `app/client/loading.tsx` renders `RouteSkeleton` (`max-w-6xl`, 3-col stat grid, `route-skeleton.tsx:16-18`) while the shell content is `max-w-7xl` (`_shell.tsx:411`). Align the container, or per-route `loading.tsx` reusing each page's skeleton.

### LOW — Calendar blocks the whole view on the heavier payload instead of progressive reveal
- **Severity:** Low · **Complexity:** S — render gates on `!data` (`calendar/page.tsx:288-289`) even when the cheap vendor-filter list (`:98-110`) has resolved. Render the filter bar/strip first with a localized matrix skeleton.

### LOW — Tree picker / submissions stale-closure / others *(see Workflow + per-page sections)*

---

## 13. Executive User Audit

How the portal serves each persona's core question — *What is wrong? Where is the risk? What needs attention? What next?* — answered against the current code.

### CFO — "Compliance risk at a glance, in <60s"
- **Strength:** The hero RadialGauge gives an instant portfolio %.
- **Gaps (all confirmed):** No **trend** — "are we better or worse than last month?" is unanswerable on the live dashboard (HIGH, §2/§9). The % has no **denominator or target band** (MEDIUM). **Overdue** (highest-liability) is invisible (HIGH). **Rejected/correction** (the red-driving bucket) is buried in prose (HIGH). The richest exec material is gated behind manual report generation (MEDIUM, §13-benchmark). Verdict: the CFO gets a number, not a direction or a denominator.

### Legal Director — "Legal exposure"
- **Gaps:** The audit trail (Activity) leaks raw English tokens and dotted action codes (HIGH, §9) and truncates at 200 with no pagination (HIGH) — not defensible as evidence. Report blocks render off-brand status hex (MEDIUM). The client_facing report opens claiming everything "ya está siendo gestionada por nuestro equipo" — muddies remediation ownership on an auditor document (MEDIUM). The audit-package builder (the literal "hand the inspector a ZIP" tool) is an orphan route (HIGH/MEDIUM) and its custom download can hang forever (HIGH).

### Procurement Manager — "Provider performance"
- **Gaps:** The portfolio **cannot be ranked by risk** — no sorting (HIGH, §4). Portfolios >100 providers silently truncate (HIGH). Generating one provider's report freezes the whole list (HIGH). Submissions can't be paged past the cap and rows can't open the document (HIGH×2, §6/§9). Provider name search returns nothing (CRITICAL, §9).

### Compliance Manager — "Find & resolve issues fast"
- **Gaps:** The dashboard never names the at-risk providers (HIGH) and there's no ranked attention worklist outside a report (HIGH). Notification deep-links land on an unfiltered Submissions table (HIGH, §8). The "En revisión" filter silently hides ⅔ of in-review docs (HIGH). The semáforo "why is this red" reason is keyboard/SR-unreachable (HIGH a11y). Three overlapping "what needs attention" lists on vendor detail fragment triage (MEDIUM).

### Executive Sponsor — "Portfolio health in <60s"
- **Gaps:** On a phone, **search is completely unreachable** (HIGH) and the densest screens horizontal-scroll (MEDIUM). The dashboard answers "how much" but not "which/what next" or "trend" (HIGH×2). The compliance % is a bare vanity number (MEDIUM). Verdict: a desktop Sponsor gets a passable 60-second read; a mobile Sponsor does not.

---

## 14. Enterprise Benchmark (vs Vanta / Drata / Rippling / Ramp / Stripe / Linear / Notion / Workiva)

| Capability | Benchmark expectation | CheckWise client portal | Gap |
|---|---|---|---|
| **Risk worklist** | Ranked "needs attention", click-to-act (Vanta/Drata) | Counts + donut; ranking only inside a report | HIGH |
| **Trend / momentum** | Up/down deltas, sparklines on the dashboard | None on live surfaces; trend only in reports | HIGH |
| **Search** | Instant name/fuzzy search, everywhere incl. mobile (Linear/Stripe) | RFC/period/folio only, no name match, unreachable on mobile, no focus ring | CRITICAL/HIGH |
| **Pagination / data integrity** | "Showing X of N", infinite scroll, never silent truncation | Silent caps on every list + metadata; `total`/`offset` ignored | HIGH |
| **Loading states** | Shape-matched skeletons, no infinite spinners | Mixed: some skeletons, some text/spinners; report/download ops can hang | MED |
| **Scheduled digests** | Recurring auto exec summaries (Vanta/Workiva) | Reports are manual, on-demand only | MED |
| **Accessibility** | WCAG AA, real dialogs, skip links, focus visible | Strong matrix; but no skip link, fake dialog drawer, unreachable tooltip, invisible search focus | HIGH |
| **Design-system rigor** | Single token source, no hardcoded hex (Stripe/Notion) | Two type-scale sources, dead `--density-*`, undefined `--state-*` → report hex, ~97 px literals | MED |
| **Localization polish** | No machine tokens in the UI | Raw status/action/actor codes leak on detail, activity, audit-package | HIGH |
| **Navigation scope integrity** | Context (tenant) survives navigation | `?client_id` dropped by nav/bell/logo/search → wrong tenant | HIGH |
| **Export/share** | One-click export of any view (Drata) | Per-obligation only; no calendar/report-list export | MED |

**Honest read:** CheckWise clears the bar on data model depth, the compliance matrix, and async intake. It falls short on the *connective tissue* the benchmark products are famous for — ranked worklists, trend, instant universal search, never-lie pagination, and bulletproof loading/timeout states. These are the differences between "a capable compliance tool" and "a tool an executive trusts to act on in 60 seconds."

---

## 15. Prioritized Implementation Roadmap

Ordered by (business + user impact) ÷ complexity, and by how directly each unblocks *understand risk → reduce risk → ensure compliance → decide fast*. Dependencies noted.

### Phase 0 — Stop the bleeding (CRITICAL + cheap HIGH; days)
*Theme: correctness, trust, and the front door.*
1. **Provider name search** (CRITICAL, M) — add `accent_ci_contains` name predicate to `search_service.py`; add `name` to `QueryType`/`SearchMatchType`; update placeholder. *Highest-frequency failed query.*
2. **Report/audit-package timeouts** (HIGH, S) — `GENERATE_TIMEOUT_MS` on `createReportFromPreset`; AbortController on the audit POST download. *Kills the "spinner forever" class on the buyer's marquee actions.* No deps.
3. **Search keyboard focus ring + mobile reachability** (HIGH, S) — replace `focus-visible:outline-none`; add `/client/buscar` to NAV. No deps.
4. **Notification deep-link params honored on Submissions** (HIGH, M) — read `useSearchParams` to seed filters. *Repairs the alert→act loop.*
5. **Page-level error `role="alert"`** (HIGH, S) — route through `ErrorState`. No deps.

### Phase 1 — Make the dashboard decision-grade (HIGH; ~1–2 weeks)
*Theme: the <60s executive answer. Depends on small `ClientOverview` extensions.*
6. **Name the at-risk providers + ranked attention worklist** (HIGH, M) — `top_risk_vendors[]` on `ClientOverview`; default-sort `client_vendors()` worst-first; "Requieren tu atención" card; make the headline a `Link`. *Single highest-leverage UX change.*
7. **Surface Overdue + Rejected as top KPI tiles** (HIGH, S+M) — add `overdue_total`; promote `rejected_or_correction_total`; reorder strip most-actionable-first; make all risk KPIs drill.
8. **Compliance trend delta** (HIGH, M) — reuse the report engine's 6-month history; render a delta + sparkline (`StatCard.trend` exists). *Depends on #6's overview work.*
9. **Vendor list risk sorting** (HIGH, M) — sortable headers / default worst-first. *Pairs with #6's backend sort.*

### Phase 2 — Truth in data + open the dead ends (HIGH; ~2 weeks)
*Theme: never silently truncate; let users act from where they are.*
10. **Pagination across lists + metadata** (HIGH, L) — surface `total`/`has_more`; add `offset` to FE signatures; "Mostrando N de TOTAL"; metadata `total_documents`/`truncated` + virtualize the table. *Backend already supports it; one shared pattern.*
11. **"En revisión" filter expands to all 3 raw states** (HIGH, M) — collapsed label → `status IN (…)`.
12. **Open documents from Submissions + actionable suggested/attention cards** (HIGH, M×2) — wire the existing blob-view helper + `?focus` deep-links.
13. **Localize raw tokens** (HIGH, S) — ES label maps for Activity actor/action, vendor-detail `a.type`/`n.result`/`contract.status`; vitest lock.
14. **Scope-preserving navigation** (HIGH, M) — `withClientId` helper on nav/bell/logo/search/BackBar; make scope-blind pages read `useUrlClientId`.

### Phase 3 — Enterprise polish & accessibility (MED; ~2–3 weeks)
*Theme: clear the procurement-a11y and design-system bars.*
15. **Real mobile nav dialog** (MED, M) — Radix Dialog/vaul; focus trap + Escape + restore.
16. **Skip link, semáforo tooltip a11y, heading hierarchy, mark-read live region, ARIA tabs** (MED, S–M each).
17. **Design-system reconciliation** (MED, M each) — single type-scale source; finish `--state-*`/report-color migration; wire or delete `--density-*`; converge card radius; replace hand-rolled eyebrows; skeletons-not-text.
18. **Responsive tables** (MED, M) — `DataTable` card/priority mode; metadata mobile cards; vendors mobile stack.
19. **Auditoría in nav; dual-back reconciliation; settings hub in UserMenu** (MED, S each).
20. **Read viewer bundle split + StoryView copy fix + reports table overflow** (MED, S each).

### Phase 4 — Differentiation (MED/LOW; backlog)
*Theme: match the benchmark's connective tissue.*
21. **Scheduled exec digest** (MED, L) — auto-regenerate `client-monthly-executive` on a cadence.
22. **Calendar/report export & share** (MED, M).
23. **Trend on the radar for thin tenants, period-range validation, count-surface reconciliation** (MED, S–M).
24. **Remaining LOW polish** — em-dash-for-zero, redundant distribution chart, recency captions, icon semantics, off-token colors, year-input clamp, RouteSkeleton geometry, virtualize notification/activity lists, no-results states, filter "Limpiar" + URL persistence.

**Dependency summary:** Phase 1 #6–#8 all extend `ClientOverview` (do the type/endpoint change once). Phase 2 #10 establishes the pagination pattern reused everywhere. The `?focus`/deep-link plumbing (#12, search routing) and the localization maps (#13) are reused by Activity, Reports, and Search. Phase 3 #17 (design system) should land before any large net-new UI to avoid re-introducing drift.
