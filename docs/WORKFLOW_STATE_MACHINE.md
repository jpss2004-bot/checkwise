# Submission + Document Workflow State Machine

Single source of truth for how a CheckWise submission moves between
statuses after it has been received.

The workflow service lives at
[`apps/api/app/services/submission_workflow.py`](../apps/api/app/services/submission_workflow.py).
Every reviewer- or legal-driven status transition MUST go through it.
Direct `Submission.status = ...` or `Document.status = ...` writes
outside that service are a bug — they bypass the audit trail.

## Statuses

Canonical values stored in `Submission.status` and `Document.status`.
Defined in [`apps/api/app/constants/statuses.py`](../apps/api/app/constants/statuses.py).

| Code (DB)              | Spanish label              | Category   | Meaning                                          |
|------------------------|---------------------------|------------|--------------------------------------------------|
| `pendiente`            | Pendiente                 | Initial    | Slot exists; no submission yet.                  |
| `recibido`             | Recibido                  | Queue      | Submission received, awaiting prevalidation.     |
| `pendiente_revision`   | Pendiente de revisión     | Queue      | Default intake outcome; reviewer must decide.    |
| `prevalidado`          | Prevalidado               | Queue      | Automatic prevalidations passed; reviewer next.  |
| `posible_mismatch`     | Posible mismatch          | Queue      | Document signals flagged a probable mismatch.    |
| `requiere_aclaracion`  | Requiere aclaración       | Provider   | Reviewer asked for clarification; provider acts. |
| `aprobado`             | Aprobado                  | **Terminal** | Reviewer approved.                             |
| `rechazado`            | Rechazado                 | **Terminal** | Reviewer rejected.                             |
| `excepcion_legal`      | Excepción legal           | **Terminal** | Marked as a legal exception.                   |
| `no_aplica`            | No aplica                 | Other      | Slot does not apply for this provider/period.    |
| `vencido`              | Vencido                   | Other      | Period closed without a valid submission.        |

## Reviewer actions

Defined in `ReviewerAction` in `apps/api/app/constants/statuses.py`.

| Action                  | Maps to status          | Requires reason? |
|-------------------------|------------------------|------------------|
| `approve`               | `aprobado`             | No               |
| `reject`                | `rechazado`            | **Yes**          |
| `request_clarification` | `requiere_aclaracion`  | **Yes**          |
| `mark_exception`        | `excepcion_legal`      | **Yes**          |

Whitespace-only reason is treated as empty (`422`).

## Allowed source statuses for reviewer decisions

A reviewer decision may be applied to submissions in any of these
states. Anything else returns `409 Conflict`.

- `recibido`
- `pendiente_revision`
- `prevalidado`
- `posible_mismatch`
- `requiere_aclaracion` — the ball is normally back in the provider's
  court, but a reviewer can still re-decide if clarification arrived
  out-of-band.

## Transition table

| From → To                        | `approve` | `reject` | `request_clarification` | `mark_exception` |
|---------------------------------|:---------:|:--------:|:-----------------------:|:----------------:|
| `recibido`                       | ✅        | ✅       | ✅                      | ✅               |
| `pendiente_revision`             | ✅        | ✅       | ✅                      | ✅               |
| `prevalidado`                    | ✅        | ✅       | ✅                      | ✅               |
| `posible_mismatch`               | ✅        | ✅       | ✅                      | ✅               |
| `requiere_aclaracion`            | ✅        | ✅       | ✅                      | ✅               |
| `aprobado` *(terminal)*          | 409       | 409      | 409                     | 409              |
| `rechazado` *(terminal)*         | 409       | 409      | 409                     | 409              |
| `excepcion_legal` *(terminal)*   | 409       | 409      | 409                     | 409              |
| `pendiente` / `vencido` / `no_aplica` | 409       | 409      | 409                     | 409              |

Re-deciding a terminal submission is intentionally blocked — a new
attempt must be filed by the provider. This protects the audit record
from accidental double-clicks.

## Side effects per successful transition

Every successful call to `apply_reviewer_decision(...)` runs as one
DB transaction. Partial writes are impossible — if any of these
inserts fails, the whole decision rolls back.

1. **`Submission.status`** → new value · `updated_at` refreshed.
2. **`Document.status`** (primary document only) → same new value ·
   `updated_at` refreshed. *Phase 2 closed the prior gap where the
   reviewer endpoint left the document row drifting on its
   intake-time status.*
3. **`DocumentStatusHistory`** row inserted:
   - `from_status` = previous status
   - `to_status` = new status
   - `reason` = trimmed reason (or null for approve)
   - `actor` = `reviewer:<user_id>`
4. **`ValidationEvent`** row inserted:
   - `event_type` = `"reviewer_decision"`
   - `rule_code` = `"reviewer_decision"`
   - `result` = the action code (`approve` / `reject` / …)
   - `severity` = `info` for approve, `warning` otherwise
   - `actor_type` = `"reviewer"`
   - `payload` = `{from_status, to_status, reviewer_user_id}`
5. **`AuditLog`** row inserted *(new in Phase 2)*:
   - `action` = `"submission.reviewer_decision"`
   - `actor_type` = `"reviewer"`
   - `actor_id` = reviewer's user id
   - `before` = `{"status": previous_status}`
   - `after` = `{"status": new_status}`
   - `metadata` = `{reviewer_action, reason, document_id}`

The trail is intentionally redundant. Each surface answers a
different question:

| Need                                       | Look at                  |
|--------------------------------------------|--------------------------|
| Provider-facing timeline                   | `DocumentStatusHistory`  |
| Reviewer-facing event log + automation     | `ValidationEvent`        |
| Cross-entity compliance / audit reports    | `AuditLog`               |

## Error response shape

The workflow service raises `fastapi.HTTPException` directly so the
reviewer router stays a thin shell:

| Cause                                           | HTTP status | Detail                                              |
|-------------------------------------------------|-------------|-----------------------------------------------------|
| Submission already in a terminal status         | `409`       | `Submission already resolved as '<status>'.`        |
| Submission in an unsupported source status      | `409`       | `No se permite una decisión de revisor desde el estado '<status>'.` |
| Unknown DB status (data corruption guard)       | `409`       | `Submission tiene un estado no reconocido (...)`    |
| Action requires a reason and it's empty         | `422`       | `'<action>' requires a 'reason'.`                   |
| Unknown reviewer action                         | `422`       | `Acción de revisor desconocida: '<action>'.`        |

`404` from the router (unknown submission) is raised before the
workflow service runs.

## What's in scope vs. out of scope

In scope for the workflow service today:

- All reviewer decisions (`approve` / `reject` / `request_clarification` /
  `mark_exception`).
- Document status mirroring for the primary document.
- Side-effect fan-out (history, validation events, audit log).
- Terminal-status guard.

Out of scope (left intentionally, see comments in
`submission_workflow.py`):

- **Initial intake.** `finalize_intake_submission(...)` writes the
  first `DocumentStatusHistory` row directly. Centralising "set the
  starting status" through the workflow service would only restate
  what intake already does atomically and risk fragmenting the intake
  transaction. Tracked as future cleanup.
- **Provider-side actions.** The provider's correction flow today
  triggers a new submission rather than mutating the prior one, so
  no transition is required.
- **Time-based transitions** (e.g. `pendiente_revision` → `vencido`
  when a period closes). No scheduled job runs today; when one
  ships, it should call into this service.

## Where it's used

| Caller                                                                      | Notes                                                            |
|----------------------------------------------------------------------------|------------------------------------------------------------------|
| `POST /api/v1/reviewer/submissions/{id}/decision`                          | Thin wrapper; loads the submission, delegates to the workflow.   |
| (future) admin override / batch re-validation / scheduled expiry job       | Must go through `apply_reviewer_decision` or a sibling helper.   |

Direct `submission.status = ...` writes outside this service are a
bug. Code review should reject them.
