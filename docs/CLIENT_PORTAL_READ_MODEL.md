# Client Portal Read Model

Phase 8 — client-facing monitoring surface. Read-only. Built on
the canonical evidence-slot service and the provider dashboard
helpers, so every red/yellow/green decision matches what the
provider sees.

Companion to
[EVIDENCE_SLOTS.md](EVIDENCE_SLOTS.md),
[WORKFLOW_STATE_MACHINE.md](WORKFLOW_STATE_MACHINE.md),
[PROVIDER_DASHBOARD_READ_MODEL.md](PROVIDER_DASHBOARD_READ_MODEL.md),
[PROVIDER_PORTAL_CANONICAL_READS.md](PROVIDER_PORTAL_CANONICAL_READS.md),
and [ADMIN_OPERATIONS_CORE.md](ADMIN_OPERATIONS_CORE.md).

## Endpoints

All endpoints live under `prefix=/client` and are gated by
`require_any_role(CLIENT_ADMIN, INTERNAL_ADMIN)`.

| Method | Path                                          | Purpose                                                       |
|--------|-----------------------------------------------|---------------------------------------------------------------|
| GET    | `/api/v1/client/me`                           | Identity + visible client ids + `default_client_id`.          |
| GET    | `/api/v1/client/overview`                     | Operational counters + per-semaphore-level breakdown.         |
| GET    | `/api/v1/client/vendors`                      | One row per workspace with semaphore + counts.                |
| GET    | `/api/v1/client/vendors/{vendor_id}`          | Full dashboard for one vendor (lineage-aware).                |
| GET    | `/api/v1/client/calendar?year=`               | Aggregated month grid across the client's workspaces.         |
| GET    | `/api/v1/client/submissions`                  | Filtered list with reviewer note + replacement lineage.       |
| GET    | `/api/v1/client/activity`                     | Sanitised activity feed (uploads + reviewer decisions only).  |

Read-only. No client endpoint mutates a submission or any other
provider-owned record. The reviewer queue, provider portal, and
admin router are unchanged.

## Permission model

| Caller | Outcome |
|---|---|
| Unauthenticated | **401** (via `get_current_user`) |
| Reviewer-only / provider / no role | **403** |
| `client_admin` | Scoped to clients reachable through their memberships |
| `internal_admin` | Full read access; must pass `?client_id=<uuid>` when no client_admin membership exists |
| `client_admin` requesting another client's id | **403** |
| `client_admin` requesting a non-existent client | **404** |

`internal_admin` is allowed because LegalShelf staff routinely need
to debug a client's view without minting a fake client account.
They cannot mutate anything from `/client` either — staff
mutations still go through `/admin`.

## Client isolation

Scope is resolved by walking
`memberships -> organization (kind="client") -> client_id`. The
helper `_visible_client_ids_for_user(db, user_id)` returns the
ids the user can see; `_resolve_client_id(db, current, requested)`
picks the active scope:

```
requested provided?
  yes ─ exists?  ── no  → 404
         ─ yes  ── internal_admin?  → allow
                   ─ in visible list? ─ yes  → allow
                                       ─ no   → 403
requested not provided?
  visible list non-empty?  → first entry (deterministic)
                           internal_admin & empty visible → 400 (be explicit)
                           neither → 403
```

Every downstream endpoint runs this guard first. Cross-client
vendor / submission ids return **403** (or **404** when the row
plain does not exist) — never confirms tenancy by error code.

`ProviderWorkspace.access_token` is **never** returned by any
client endpoint. A regression test pins the contract.

## Semaphore rules (matches provider dashboard)

| Condition                                                  | `semaphore_level` |
|------------------------------------------------------------|-------------------|
| Any required slot in `rejected` / `needs_correction` / `possible_mismatch` | `red`   |
| No blocking slot, but any required `missing` / `uploaded` / `in_review` / `expired` | `yellow` |
| Every required slot resolved (`approved` / `exception` / `not_applicable`) | `green`  |

`compliance_pct = round(on_track / total_tracked * 100)` where
`on_track` counts required slots in the resolved set. Overview
endpoint reports `green_count`/`yellow_count`/`red_count`; vendor
list reports per-vendor levels.

## Calendar / deadline heuristic

Same convention as the provider calendar: day-17 cutoff for
monthly / bimestral / cuatrimestral slots, day-30 for the SAT
annual override (the catalog row carries `due_day=30`). The
`deadline_iso` field is computed as
`(year, due_month, due_day) → "YYYY-MM-DD"`.

Each calendar month carries:

- `vendors_total` — distinct vendors with an obligation in that
  month
- `due_total` — total obligation rows for the month across all
  vendors
- `approved_total` / `pending_total` / `rejected_or_correction_total`
  / `missing_total` — coarse status buckets
- `due_soon_total` — non-resolved obligations whose deadline is in
  the next 14 days
- `items[]` — one row per (vendor × catalog item) with status +
  href into the upload wizard

January carryover (e.g. `2025-M12` filed in 2026-01) is preserved
because the slot service uses canonical `period_key`.

## Activity feed sanitisation

`GET /client/activity` returns at most `limit` events (default
50, hard cap 200) composed from two safe sources:

1. **Uploads** — `submissions.created_at` for any submission tied
   to a vendor in the client's scope. Action label
   `submission.uploaded`.
2. **Visible validation events** — `validation_events` where
   `event_type IN { "reviewer_decision", "submission_replacement_linked", "submission_replaced" }`.
   Action labels `reviewer.decision` / `submission.replacement_linked`
   / `submission.replaced`.

The feed deliberately **excludes**:

- Internal admin audit metadata (`admin.client.*`, etc.).
- Noisy intake telemetry (`upload_started`, `pdf_inspected`, etc.).
- File hashes and storage keys.
- Provider workspace access tokens.

A regression test (`test_client_activity_returns_sanitised_events`)
asserts admin actions never appear in the feed.

## What the client can see now

- Operational counters + semaphore breakdown across the client's
  portfolio.
- Per-vendor compliance row with semaphore, counts, last activity.
- Per-vendor dashboard (onboarding summary, document counts,
  semaphore, suggested actions, attention items, upcoming
  deadlines, recent submissions, recent reviewer notes).
- Aggregated calendar month grid.
- Filtered submission list with reviewer note + replacement
  lineage (`supersedes_submission_id` / `superseded_by_submission_id`).
- Sanitised activity feed of uploads + reviewer decisions.

## Intentionally not implemented yet

- Report / PDF generation (no `/client/reports` endpoint).
- Exports (CSV / Excel).
- Client-side comments or actions on a submission.
- Notification delivery (email / WhatsApp).
- Signed file downloads (no `/client/submissions/{id}/download`).
- Advanced client user management (membership grants live in
  `/admin` and require an internal_admin).
- Full RBAC editor.
- 2FA / session-policy enforcement.
- AI / OCR metadata extraction.
- Google Sheets sync.
- Scheduled expiry jobs.
- Multi-version requirement editor.

Each is tracked as a follow-up phase and can adopt the same scope
+ permission scaffolding without contract changes.

## Where it lives

| Backend                                                                | Frontend                                                             |
|------------------------------------------------------------------------|----------------------------------------------------------------------|
| [backend/app/api/v1/client.py](../backend/app/api/v1/client.py)        | [frontend/lib/api/client.ts](../frontend/lib/api/client.ts)          |
| [backend/tests/test_client_portal.py](../backend/tests/test_client_portal.py) | [frontend/app/client/_shell.tsx](../frontend/app/client/_shell.tsx) + the 6 new pages under `frontend/app/client/{dashboard,vendors,vendors/[vendor_id],calendar,submissions,activity}/` |
