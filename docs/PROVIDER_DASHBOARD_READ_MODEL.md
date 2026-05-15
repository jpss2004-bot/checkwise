# Provider Dashboard Read Model

Phase 4 made the provider portal's read path canonical. Onboarding,
calendar, submission detail and the new dashboard endpoint all
consume the same evidence-slot service introduced in Phase 3, so a
single source of truth answers "what is the current state of every
obligation slot?" for every provider-facing surface.

This document complements [EVIDENCE_SLOTS.md](EVIDENCE_SLOTS.md) and
[WORKFLOW_STATE_MACHINE.md](WORKFLOW_STATE_MACHINE.md).

## What changed

* `GET /api/v1/portal/workspaces/{id}/onboarding` and
  `GET /api/v1/portal/workspaces/{id}/calendar` now go through
  `build_workspace_onboarding_slots(...)` /
  `build_workspace_calendar_slots(...)`. The legacy fuzzy
  `_match_submission` helper was deleted along with `_normalize` and
  the unused `unicodedata` import.
* The provider's submission detail endpoint
  `GET /api/v1/portal/workspaces/{id}/submissions/{submission_id}`
  carries two new fields: `supersedes_submission_id` and
  `superseded_by_submission_id`. The reviewer detail endpoint
  mirrors them.
* New endpoint:
  `GET /api/v1/portal/workspaces/{id}/dashboard`. Tenant-guarded by
  `current_portal_workspace`; composes onboarding + calendar slots
  into the dashboard payload.
* Frontend `/portal/dashboard` consumes the new endpoint at runtime.
  Mock dashboard data is no longer used at runtime — the file
  remains for now as a static example only.

## Replacement-aware current state

The slot service walks the supersession lineage chain to pick the
"current" submission for each slot. Onboarding, calendar, and
dashboard are all built on this: a rejected submission that has been
replaced never wins over its replacement. See
[EVIDENCE_SLOTS.md §Selecting the current submission](EVIDENCE_SLOTS.md#selecting-the-current-submission).

## Dashboard payload contract

```jsonc
GET /api/v1/portal/workspaces/{workspace_id}/dashboard

{
  "workspace_id": "uuid",
  "persona_type": "moral" | "fisica",
  "onboarding_summary": {
    "total_required": 0,
    "completed": 0,
    "in_review": 0,
    "needs_action": 0,
    "optional_pending": 0,
    "completion_pct": 0,
    "is_gate_satisfied": false
  },
  "document_state_counts": {
    "approved": 0, "in_review": 0, "uploaded": 0, "pending": 0,
    "needs_review": 0, "rejected": 0, "expired": 0, "exception": 0
  },
  "semaphore": {
    "level": "green" | "yellow" | "red",
    "label": "Verde · al día",
    "reason": "Todas tus obligaciones obligatorias están aprobadas.",
    "compliance_pct": 0,
    "total_tracked": 0,
    "on_track": 0
  },
  "suggested_actions": [
    {
      "id": "act-…",
      "type": "complete_onboarding" | "reupload" | "verify_mismatch" | "clarify" | "upcoming",
      "title": "…",
      "body": "…",
      "priority": "low" | "medium" | "high",
      "href": "/portal/upload?…",
      "requirement_code": "…" | null,
      "period_key": "…" | null
    }
  ],
  "attention_today": [
    {
      "id": "att-…",
      "title": "…",
      "institution": "sat" | "imss" | "infonavit" | "stps_repse" | "interno_cliente",
      "state": "rejected" | "needs_correction" | "possible_mismatch" | "missing" | "in_review" | "uploaded" | "expired" | …,
      "due_in_days": -3 | 0 | 12 | null,
      "href": "/portal/upload?…"
    }
  ],
  "upcoming_deadlines": [
    {
      "id": "due-…",
      "title": "…",
      "institution": "…",
      "period_key": "2026-M05" | null,
      "due_month": 5,
      "state": "missing" | "in_review" | …,
      "href": "/portal/upload?…"
    }
  ]
}
```

### Semaphore rules

| Condition                                                  | Level    |
|------------------------------------------------------------|----------|
| Any required slot in `rejected`/`needs_correction`/`possible_mismatch` | red    |
| No blocking slot, but any required `missing`/`uploaded`/`in_review`/`expired` | yellow |
| Every required slot is `approved`/`exception`/`not_applicable` | green  |

`compliance_pct = round(on_track / total_tracked * 100)` where
`on_track` counts required slots in the resolved set
(`approved`/`exception`/`not_applicable`).

### Suggested actions

Computed read-only, ≤5 items, ordered by:

1. Blocking required slots (`rejected` → reupload, `needs_correction`
   → clarify, `possible_mismatch` → verify) — all `priority=high`.
2. Missing required onboarding slots — `priority=medium`,
   `type=complete_onboarding`.
3. Calendar slots due within 14 days that are still `missing` —
   `priority=medium` if ≤5 days, `priority=low` otherwise,
   `type=upcoming`.

`href` is a pre-built `/portal/upload?…` URL. For blocking slots
with an existing submission the URL also carries `replaces=<id>` so
the intake wizard POSTs `supersedes_submission_id` and the backend
creates the lineage link automatically.

### Attention today

Surfaces every required slot that's blocking or due within 14 days.
Sorted by `due_in_days` ascending (overdue first; nulls last). Capped
at 10 items.

### Upcoming deadlines

Top 5 unfilled (non-resolved) calendar slots ordered by
`due_in_days`. Used by the right-rail card on the dashboard.

## Submission detail lineage fields

Both `/portal/workspaces/{id}/submissions/{id}` and
`/reviewer/submissions/{id}` now return:

```ts
supersedes_submission_id:   string | null
superseded_by_submission_id: string | null
```

The provider UI renders a "Reemplaza intento anterior" / "Reemplazado
por intento más reciente" strip on `/portal/submissions/[id]`.

## What is intentionally not implemented yet

The dashboard surface intentionally skips features that need to land
in their own focused phases:

- **Persisted suggested actions.** Today every action is computed
  read-only per request. There's no `suggested_actions` table, no
  dismiss state, no per-action cooldown. Persistence + dismissals are
  a future phase.
- **Notifications.** No email / WhatsApp / push fire from the
  dashboard suggestions. They're advisory text only.
- **Reports.** No PDF/Excel generation is wired. The dashboard hints
  at deadlines but does not produce client-facing artefacts.
- **Client dashboard.** Cross-vendor aggregations for `client_admin`
  users are out of scope for the provider read model. They will be
  built on the same slot service in a later phase.
- **Scheduled expiry.** A background runner (Redis + RQ or Celery)
  that flips `pendiente_revision` / `recibido` to `vencido` once a
  period closes is still on the roadmap, not implemented. The
  dashboard renders `vencido` correctly when it appears, but never
  produces it on its own.
- **OCR / AI extraction.** Document signals remain deterministic.

## Where it's consumed today

| Surface                                                      | Endpoint                                                    |
|--------------------------------------------------------------|-------------------------------------------------------------|
| `/portal/dashboard` (provider)                               | `GET /api/v1/portal/workspaces/{id}/dashboard`              |
| `/portal/onboarding` (provider)                              | `GET /api/v1/portal/workspaces/{id}/onboarding`             |
| `/portal/calendar` (provider)                                | `GET /api/v1/portal/workspaces/{id}/calendar`               |
| `/portal/submissions/[id]` (provider)                        | `GET /api/v1/portal/workspaces/{id}/submissions/{id}`       |
| `/admin/reviewer/[submission_id]` (LegalShelf staff)         | `GET /api/v1/reviewer/submissions/{id}`                     |
