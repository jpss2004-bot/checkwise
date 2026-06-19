# Calendar parity: provider portal vs client portal (2026-06-18)

Analysis of `/portal/calendar` (provider) vs `/client/calendar` (client) to find what
makes the provider calendar feel richer and how to bring the client one up to par.

## Core difference
Same data (recurring REPSE catalog × submissions), opposite roles.

- **Provider** (`apps/web/app/portal/calendar/page.tsx`, `apps/api/.../portal.py:1612`):
  single workspace, **institutions × 12 months**, first-person **action console** — every
  cell is self-describing and self-actionable (backend `suggested_action`, pre-filled upload
  deep-link, anatomy/where/common_errors, v2 `accepts_documents`, uploaded `filename`/`submitted_at`).
  Weakness: **no server-side risk scoring** — all urgency coloring is FE-only.
- **Client** (`apps/web/app/client/calendar/page.tsx`, `apps/api/.../client.py:2239`,
  `apps/api/app/services/calendar_aggregate.py`): whole portfolio, **providers × 12 months**,
  third-person **oversight console** — server-computed `risk_level` (single source of truth
  shared with the admin grid), worst-provider-first, role-correct actions (chase/wait, never
  upload), deep-links into expedientes. Weakness: **thin per-obligation context**.

**"Bring the client to the provider's level" = port the contextual richness (what/why/how/
already-done) re-framed for oversight, while keeping the client's superior risk + portfolio model.**

## Client is already BETTER at
- Server-computed risk as single source of truth (`_calendar_item_risk`, client.py:1156).
- Portfolio risk KPI strip + worst-first provider rollup.
- Role-aware next steps (`nextActionFor`, client-calendar-shared.ts:68) — never "upload".
- Deep-link into expediente w/ focus bucket + returnTo + audit-package shortcut.
- Year picker, fuller URL state (year+vendor+inst+client_id), ErrorState **with retry**.
- O(1)-in-vendor-count query cost.

## Status
**Tiers 1–6 SHIPPED + MERGED TO `main`** (ae66f76 + f7aff86 + 390f36e, FF-pushed to origin/main, code-only/no migration → auto-deploys prod). Tiers 7–8 still open.

## Gaps in the client (ranked roadmap)

1. **Server-owned, oversight-framed `suggested_action`** [HIGH/M]. Move `nextActionFor` logic
   server-side into the aggregate so client+provider next-steps can't drift; mirror
   `_calendar_suggested_action` (portal.py:461) structure, client voice (chase/wait).
   Files: calendar_aggregate.py (CalendarObligation), client.py (ClientCalendarItem + map),
   obligation-block.tsx:85, client-calendar-shared.ts.

2. **Render `anatomy` (already on the wire) + a guidance disclosure** [HIGH/S — cheapest, no BE].
   `aggregate_client_calendar` already returns `anatomy` (calendar_aggregate.py:189); ObligationBlock
   shows only `where_to_obtain` (obligation-block.tsx:72-86). Add a collapsible "Qué debe contener"
   reusing the provider `DocumentGuidanceDisclosure` (expediente-card.tsx:325).

3. **Surface `filename`/`submitted_at` + reviewer note** [HIGH/M]. Resolve filename+date via the
   batched Document lookup the provider uses (portal.py:1648); join `_latest_reviewer_note`
   (portal.py:489, already used in client.py:2539) onto action_required items → render
   "Entregado: <file> · <fecha>" and "Motivo del rechazo". Evidence-backs the chase decision.

4. **Add `common_errors` + `accepts_documents`/`minimum_documents`** [MED/M]. Emit
   `recurring_common_errors` + `recurring_accepted_documents`; render for review ("Errores comunes
   a verificar", "Cualquiera de estos documentos satisface la obligación"). Fixes v2 over-chasing.

5. **Wire provider-name drill (`onSelectRow`) + emit `days_until`/`is_overdue`** [MED/S].
   ComplianceMatrix already supports `onSelectRow` but the page never passes it
   (page.tsx:315-330) — clicking a provider name is dead. Select {vendorId, month:null} = that
   provider's whole-year worklist. Expose day-math from `_calendar_item_risk`.

6. **Hover-preview popover on matrix cells** [MED/M]. Adapt cell-popover.tsx (provider has it) so
   the client scans multi-obligation cells without click+scroll.

7. **Per-month `by_institution` drill + optional `?institution=` server filter** [MED/M].
   `calendar_snapshot.py:104-111` already computes `by_institution {count,worst_risk,delivered}`
   from the same aggregate — surface it on ClientCalendarMonth; institution filter is FE-only today.

8. **First-viewport client next-action rail + fix server `href` affordance** [MED/L]. Adapt the
   unwired NextActionRail/SuggestedActions into "Proveedores a dar seguimiento" ranked by risk_level.
   Also: aggregate emits `href = _calendar_upload_href` (a provider surface the client can't use) —
   the FE ignores it but the contract is wrong; point it at the `/client/vendors/{id}?focus=…#documentos`
   review surface (mirror `_calendar_reupload_href` role-variant pattern, portal.py:3554).

## Note
Provider load-error path has no retry (page.tsx:331); client's does — keep the client's pattern.
The `strip` next-deadline comparison (page.tsx:240-249) uses lexicographic ISO compare, which is
chronologically correct for `YYYY-MM-DD` — NOT a bug.

Source: 6-agent workflow `calendar-provider-vs-client` + first-hand reads, 2026-06-18.
