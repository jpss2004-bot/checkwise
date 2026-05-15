# Provider Portal — Canonical Reads

Phase 5 closes the provider portal's "frontend mocks → canonical
backend data" migration that began in Phase 4. The provider pages
`/portal/dashboard`, `/portal/onboarding`, and `/portal/calendar` now
consume the same evidence-slot service end to end — no adapter, no
mock padding, no fuzzy name matching.

Companion to
[EVIDENCE_SLOTS.md](EVIDENCE_SLOTS.md),
[WORKFLOW_STATE_MACHINE.md](WORKFLOW_STATE_MACHINE.md),
and [PROVIDER_DASHBOARD_READ_MODEL.md](PROVIDER_DASHBOARD_READ_MODEL.md).

## What changed in Phase 5

* `frontend/app/portal/onboarding/page.tsx` consumes the backend
  onboarding response directly. The legacy
  `adaptOnboardingToRequirements` + `MOCK_EXPEDIENTE` enrichment is
  gone.
* `frontend/app/portal/calendar/page.tsx` consumes the backend
  calendar response directly. `adaptCalendarToEvents` +
  `MOCK_CALENDAR_2026` removed.
* `frontend/lib/api/portal-adapters.ts` and
  `frontend/lib/mock/calendar.ts` deleted (no remaining consumers).
* `frontend/lib/mock/expediente.ts` **survives** — still referenced by
  `lib/workspace/resolver.ts` and `lib/routing/post-login.ts`. Both
  are out of scope for Phase 5; see "Remaining mock dependencies"
  below.
* `OnboardingRequirement` and `RecurringRequirement` dataclasses gain
  optional UX fields (`why`, `format`, `required_document`,
  `due_day`).
* Two endpoints return enriched payloads.

## Backend enrichment contract

### `GET /api/v1/portal/workspaces/{workspace_id}/onboarding`

Each item in `sections[i].items[j]` now carries:

| Field            | Source                                                          | Notes                                       |
|------------------|------------------------------------------------------------------|---------------------------------------------|
| `why`            | `OnboardingRequirement.why` or `compliance_catalog.onboarding_why` default | Static catalog copy.                         |
| `format`         | `OnboardingRequirement.format` or institution default            | Static catalog copy.                         |
| `next_action`    | `_onboarding_next_action(status, required)` (state-driven)       | Computed from the slot's current submission status. Lineage-aware (uses the leaf submission). |
| `reviewer_note`  | Latest reviewer `ValidationEvent.message` on the current submission, or `null` | Surfaces the reviewer's rejection / clarification reason without a new column. |

The existing fields (`code`, `name`, `institution`, `required`,
`note`, `status`, `submission_id`, `submitted_at`, `filename`) are
preserved.

### `GET /api/v1/portal/workspaces/{workspace_id}/calendar`

Each item in `months[i].institutions[j].items[k]` now carries:

| Field                | Source                                              | Notes                                                              |
|---------------------|-----------------------------------------------------|--------------------------------------------------------------------|
| `required_document` | `RecurringRequirement.required_document` or `name`  | Static catalog copy.                                               |
| `due_month`         | `RecurringRequirement.due_month`                    | The month the doc is due (1–12).                                   |
| `deadline_iso`      | `(year, due_month, due_day)` → ISO date              | Day-17 cutoff for monthly / bimestral / cuatrimestral. SAT annual carries `due_day=30` in the catalog. |
| `suggested_action`  | `_calendar_suggested_action(status)` (state-driven)  | Computed from the slot's current submission status.                |
| `href`              | `_calendar_upload_href(...)`                         | Canonical `/portal/upload?…` URL the frontend can render verbatim. |

Existing fields (`code`, `name`, `frequency`, `period_label`,
`period_key`, `status`, `submission_id`) preserved.

## Replacement-aware current state

The lineage rule from Phase 3 still controls which submission is
"current." Phase 5 wires the enriched fields against that same
current submission:

- `reviewer_note` reads the latest reviewer event on the leaf
  submission — not on a superseded prior.
- `next_action` and `suggested_action` reflect the leaf's status. A
  rejected prior that has been replaced no longer drives the copy.

A regression test (`test_onboarding_lineage_still_drives_current_state_after_phase5`)
pins the contract.

## Computed-action rules

`next_action` for onboarding cards (per slot status):

| Status              | Copy                                                                          |
|---------------------|-------------------------------------------------------------------------------|
| `pendiente` (or missing) | "Sube este documento para destrabar tu expediente inicial." (required) / "Si tu actividad lo requiere, sube el documento." (optional) |
| `recibido`          | "Recibimos tu documento. Va a la cola de revisión."                            |
| `pendiente_revision`/`prevalidado` | "Tu documento está en revisión humana…"                          |
| `aprobado`          | "Listo. Lo revisaremos por vigencia el próximo periodo."                       |
| `rechazado`         | "Revisa la nota del revisor y sube una versión corregida."                     |
| `requiere_aclaracion` | "Responde la observación o sube una versión corregida."                      |
| `posible_mismatch`  | "Verifica el archivo y vuelve a subir si fue equivocado."                      |
| `vencido`           | "El documento venció. Sube la versión vigente."                                |
| `excepcion_legal`   | "Aprobado bajo excepción legal. Sin acción adicional."                         |
| `no_aplica`         | "Este requisito no aplica para tu caso. Sin acción."                           |

`suggested_action` for calendar items follows the same status →
copy mapping but uses calendar-flavoured phrasing (see
`_calendar_suggested_action` in `app/api/v1/portal.py`).

## Deadline rules

Convention used across the calendar:

- Monthly, bimestral, cuatrimestral slots → day 17 of the due month.
  Matches the legacy frontend adapter exactly so behavior is
  preserved.
- SAT annual slot → day 30 of April (catalog override via
  `due_day=30`).
- The deadline is the month the **upload** is due, not the period
  the document covers. The covered period is in `period_key` (which
  also encodes January carryover by pointing to the prior year, e.g.
  `2025-M12` for a doc filed in January 2026).

## Demo fallback policy

**None.** The provider portal pages no longer fall back to mock data
under any flag — including `NEXT_PUBLIC_DEMO_MODE=true`. The empty
states render normally if the backend returns zero items or fails:

- Onboarding: an "expediente está vacío" alert when zero requirements
  apply to the workspace; a "no pudimos cargar" alert on fetch error.
- Calendar: an inline error notice on fetch failure; the existing
  per-cell empty styling on a slot with no submission.

If a future demo surface needs synthetic data, it should call its own
fixtures path explicitly — not silently shadow the canonical reads.

## Remaining mock dependencies

`frontend/lib/mock/expediente.ts` was **deleted in Phase 6**. The
`MOCK_EXPEDIENTE` fallback chain it powered was traced to two helpers
(`decideWorkspaceAccess` in `lib/workspace/resolver.ts` and
`decidePostLoginRoute` in `lib/routing/post-login.ts`) that **had
zero callers** in product code — they were dead V1.6 routing
infrastructure that never got wired in. Both helpers and the
related `AccessDecisionBanner` component were removed:

| Deleted in Phase 6                                            | Reason                                                                |
|---------------------------------------------------------------|-----------------------------------------------------------------------|
| `frontend/lib/routing/post-login.ts`                          | `decidePostLoginRoute` had no callers — routing happens inline in `/login`. |
| `frontend/lib/routing/` (directory)                           | Empty after the file removal.                                          |
| `frontend/lib/mock/expediente.ts`                             | No remaining importers after the two helpers were removed.             |
| `frontend/components/checkwise/workspace/access-decision-banner.tsx` | Orphan component, no importers.                                        |
| `frontend/lib/workspace/resolver.ts::decideWorkspaceAccess`   | No callers; deleted along with its `slugMatches` + `GENERIC_DOMAINS` helpers. |
| `frontend/lib/workspace/types.ts::WorkspaceAccessOutcome`     | Only consumer was the deleted banner.                                  |

`buildWorkspaceContext` (the workspace-identity snapshot used by
`/portal/dashboard` and `/portal/entra-a-tu-espacio`) is preserved
unchanged — it does not depend on mock expediente data.

## Provider routing — single source of truth

After Phase 6 the provider portal reads every routing-relevant
field from canonical backend responses. No frontend helper
synthesises routing decisions from mock state.

| Surface                                | Source of truth                                                              |
|----------------------------------------|------------------------------------------------------------------------------|
| `/login` redirect                      | Auth login response (`must_change_password`, `roles`).                       |
| `/activate` post-success redirect      | `POST /portal/enter` response (`expediente_status`).                          |
| `/portal/entra-a-tu-espacio` redirect  | `session.expediente_status` (from `GET /portal/me`).                          |
| `withOnboardingGate`                   | `session.expediente_status === "complete"` (backend derives it).              |
| Dashboard widgets                      | `GET /portal/workspaces/{id}/dashboard` (Phase 4).                            |
| Onboarding cards                       | `GET /portal/workspaces/{id}/onboarding` (Phase 5).                           |
| Calendar grid + drawer                 | `GET /portal/workspaces/{id}/calendar` (Phase 5).                             |

`lib/workspace/resolver.ts::buildWorkspaceContext` is still a
client-side synthesiser that wraps the `PortalSession` (and an
optional activation-time invitation) into the `WorkspaceContext`
shape consumed by the workspace-identity card. The `TODO[backend-
integration]` marker on it now points at a future
`GET /api/v1/portal/workspace` endpoint that would let the function
disappear entirely.

## Future work intentionally not in this phase

- **Admin-managed requirement copy.** The new `why`/`format`/
  `required_document` fields are static catalog data. A future admin
  surface should let LegalShelf staff edit per-requirement copy
  without code changes.
- **Persisted suggested actions.** Today every action string is
  computed read-only per request. No `suggested_actions` table, no
  dismiss state, no per-action cooldown.
- **Notification delivery.** No email/WhatsApp/push fires from the
  enriched copy.
- **Reports.** The report-generation pipeline is still stubbed.
- **Client portal.** Cross-vendor aggregations for `client_admin`
  users are out of scope.
- **AI / OCR metadata extraction.** Document signals remain
  deterministic.
- **Scheduled expiry.** `pendiente_revision` → `vencido` on period
  close still requires a background runner that isn't implemented.

## Where the new fields are consumed today

| Surface                                                                | Endpoint                                                       |
|------------------------------------------------------------------------|----------------------------------------------------------------|
| `/portal/onboarding`                                                   | `GET /api/v1/portal/workspaces/{id}/onboarding`                |
| `/portal/calendar`                                                     | `GET /api/v1/portal/workspaces/{id}/calendar`                  |
| `/portal/dashboard`                                                    | `GET /api/v1/portal/workspaces/{id}/dashboard` (Phase 4)       |
| `ExpedienteCard` component                                             | Renders the four onboarding enrichment fields.                 |
| Calendar drawer + grid                                                 | Renders the four calendar enrichment fields.                   |
