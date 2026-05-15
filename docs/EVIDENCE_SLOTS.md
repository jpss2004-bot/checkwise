# Evidence Slots & Replacement Lineage

CheckWise tracks regulatory compliance one **evidence slot** at a time.
This doc explains what a slot is, how submissions are linked through
replacement lineage, and how the canonical "current submission" is
selected.

## What is an evidence slot?

A slot is the logical seat an obligation occupies for one provider in
one period. It is identified by the tuple:

```
(client_id, vendor_id, requirement_code, period_key)
```

- `client_id` / `vendor_id` come from the authenticated
  `ProviderWorkspace`.
- `requirement_code` is the canonical regulatory requirement (e.g.
  `REC-INFONAVIT-2026-B1`).
- `period_key` is the canonical period the document covers
  (e.g. `2026-B1` for bimestre 1 of 2026, `2025-M12` for December 2025
  filed in early 2026).

Onboarding (Expediente Corporativo) slots use the same shape but with
a synthetic period_key (e.g. `onb-repse-2026`) since onboarding rows
are one-off rather than recurring.

### Legacy fallback

Submissions that pre-date the Reconciliation Patch may not carry
canonical keys. For those rows, the slot service falls back to the
plain FKs:

```
(client_id, vendor_id, requirement_id, period_id)
```

The fallback is used only when canonical keys are absent on the
stored row. New intake (V1.4+) always populates the canonical pair.

## Replacement lineage

When a provider re-uploads a document for the same slot (after a
rejection, request for clarification, possible mismatch, or expiry)
they MAY explicitly link the new submission to the prior one. The
backend records the link on the new row:

```python
new_submission.supersedes_submission_id = prior_submission.id
```

This is a self-FK on `submissions` (migration
`0008_submission_supersedes.py`). The column is nullable — most rows
never supersede anything.

### Rules

- **Explicit only.** No auto-linking. If the upload form does not
  include `supersedes_submission_id`, the new row stands alone.
- **Tenancy.** The prior submission MUST belong to the same
  workspace's `client_id` + `vendor_id`. A cross-tenant reference
  returns `404` (we never confirm cross-tenant existence).
- **Eligibility.** The prior submission MUST be in one of:
  - `rechazado`
  - `requiere_aclaracion`
  - `posible_mismatch`
  - `vencido`

  Anything else (still-in-review, already approved, exception, etc.)
  returns `409`.
- **Slot match.** When both submissions carry canonical keys, both
  `requirement_code` and `period_key` MUST match. A mismatch returns
  `409`. Legacy rows without canonical keys skip the slot check.

### Side effects of a successful replacement

When `POST /api/v1/portal/workspaces/{workspace_id}/submissions`
includes a valid `supersedes_submission_id`, the back end writes:

1. `submissions.supersedes_submission_id` on the new row (FK).
2. `ValidationEvent` on the new submission:
   - `event_type = "submission_replacement_linked"`
   - `actor_type = "supplier"`
   - `payload = {previous_submission_id, previous_status}`
3. `ValidationEvent` on the prior submission:
   - `event_type = "submission_replaced"`
   - `actor_type = "system"`
   - `payload = {new_submission_id, previous_status}`
4. The standard `AuditLog action="submission.created"` row carries an
   extra `metadata.supersedes_submission_id` and an
   `after.supersedes_submission_id`.
5. A dedicated lineage `AuditLog` row:
   - `action = "submission.replacement_linked"`
   - `metadata = {previous_submission_id, new_submission_id, requirement_code, period_key, workspace_id, previous_status}`

The prior submission's `status` is **not** changed by the
replacement. It keeps its rejected/clarification/mismatch state for
the audit timeline; the slot's "current submission" simply moves
forward via lineage.

## Selecting the current submission

`current_submission_for_slot(db, *, client_id, vendor_id,
requirement_code, period_key, requirement_id=None, period_id=None)`
returns the leaf of the supersession chain — i.e. the latest
submission that **no other submission supersedes**.

Algorithm:

1. Pull every submission matching the slot keys (canonical first,
   legacy fallback when canonical pair is absent).
2. Drop any candidate whose id appears as another candidate's
   `supersedes_submission_id`.
3. Sort the remaining (leaf) candidates by `created_at` descending.
4. Return the first.

When two leaves exist (parallel re-uploads without lineage links — an
unusual but legal scenario), the more recent wins.

## Slot states

The slot's coarse compliance state is derived from the current
submission's `DocumentStatus`. Future surfaces (dashboards, reports,
notifications) should branch on `SlotState`, not on raw status codes:

| `DocumentStatus`        | → `SlotState`              |
|------------------------|----------------------------|
| (no submission)         | `missing`                  |
| `recibido`              | `uploaded`                 |
| `pendiente_revision`    | `in_review`                |
| `prevalidado`           | `in_review`                |
| `posible_mismatch`      | `possible_mismatch`        |
| `aprobado`              | `approved`                 |
| `rechazado`             | `rejected`                 |
| `requiere_aclaracion`   | `needs_correction`         |
| `excepcion_legal`       | `exception`                |
| `vencido`               | `expired`                  |
| `no_aplica`             | `not_applicable`           |

## Service API (read-only)

`backend/app/services/evidence_slots.py` exposes:

```python
SlotState                          # enum (10 states)
SlotKey                            # frozen dataclass — slot identity
SlotView                           # frozen dataclass — slot + state

classify_slot_state(status) -> SlotState
current_submission_for_slot(...) -> Submission | None
build_workspace_onboarding_slots(db, workspace) -> list[SlotView]
build_workspace_calendar_slots(db, workspace, year) -> list[SlotView]
```

The service is **pure read**. It never writes to the DB and never
emits notifications. The existing portal read endpoints
(`/portal/workspaces/{id}/onboarding`, `/portal/workspaces/{id}/calendar`)
still use their original `_match_submission` logic; they will adopt
the slot service when new surfaces (dashboards, reports) need it. The
behavior is compatible — `_match_submission` already picks the latest
matching submission by `created_at`, which matches the leaf rule for
linear lineage chains.

## How this feeds future work

- **Dashboards.** A "compliance semaphore" tile counts slots per
  `SlotState`. Today the frontend mocks this; future work calls
  `build_workspace_calendar_slots` and groups by state.
- **Reports.** A monthly client-facing PDF iterates the slot views for
  every vendor in the client's portfolio.
- **Notifications.** A scheduled job (future, not in this phase) walks
  slots filtered by `SlotState.NEEDS_CORRECTION` or
  `SlotState.REJECTED` to nudge providers.
- **Client portal.** Out-of-tenant aggregations across vendors all use
  the same slot abstraction.

## Intentionally not implemented yet

- **Scheduled expiry.** `pendiente_revision` / `recibido` flipping to
  `vencido` when the period closes. Needs a background runner
  (Redis + RQ or Celery) — out of scope for Phase 3.
- **Notification dispatch.** No email / WhatsApp / in-app
  notifications fire from the slot service.
- **Dashboard mock replacement.** The provider dashboard widgets
  (`lib/mock/dashboard.ts`) still serve fixtures. Replacing them is a
  separate phase.
- **Report generation.** No PDF/Excel pipeline is wired.
- **OCR / AI extraction.** Document signals remain deterministic for
  now.

## Where it's used today

| Caller                                                    | Notes                                                                   |
|----------------------------------------------------------|-------------------------------------------------------------------------|
| `POST /api/v1/portal/workspaces/{id}/submissions`        | Accepts optional `supersedes_submission_id`; validates and persists.    |
| `app.services.submission_service.finalize_intake_submission` | Writes the replacement audit trail when invoked with a prior submission. |
| `app.services.evidence_slots`                            | Read-only slot views — adopted by future dashboards / reports.          |

Direct writes to `submissions.supersedes_submission_id` outside
`finalize_intake_submission` are a bug. Code review should reject
them.
