# API Contract Map

Every backend endpoint a frontend surface depends on, with the
contract the upcoming redesign teams may rely on. "Stable for
redesign" means: shape + auth + tenant rules are pinned by tests
and won't move during the visual redesign.

Versioning: every endpoint lives under `/api/v1`. No /v2 is
planned for the redesign. If a redesign team needs a contract
extension, it must be additive (new optional field) or a new
endpoint — never a breaking rename.

---

## Auth surface — `/api/v1/auth`

| Method | Path | Role | Tenant rule | Purpose | Stable | Notes |
|---|---|---|---|---|---|---|
| POST | `/auth/login` | none | n/a | Email + password → JWT (+ `must_change_password` flag) | ✅ | Pre-existing; do not break. |
| GET | `/auth/me` | any authenticated | n/a | Hydrated current user (`UserOut` + roles + org_ids) | ✅ | |
| POST | `/auth/set-password` | any authenticated | n/a | First-login password change | ✅ | Clears `must_change_password`. |

---

## Provider portal — `/api/v1/portal/*`

Auth: JWT (`Authorization: Bearer`), or httpOnly session cookie
(`checkwise_portal_session`), or legacy `X-Workspace-Token`. Every
workspace-scoped endpoint validates the JWT user's
`ProviderWorkspace.owner_user_id`.

| Method | Path | Role | Tenant rule | Purpose | Stable | Notes |
|---|---|---|---|---|---|---|
| POST | `/portal/enter` | authenticated provider user | path workspace must be owned by user | Mints httpOnly cookie + returns workspace summary | ✅ | Rotates `access_token` on entry. |
| POST | `/portal/logout` | any | n/a | Clears the cookie | ✅ | |
| GET | `/portal/me` | provider session | own workspace only | Current workspace summary + `expediente_status` | ✅ | Drives every gate. |
| GET | `/portal/workspaces/{id}` | provider session | path workspace must match session | Workspace summary | ✅ | |
| GET | `/portal/workspaces/{id}/onboarding` | provider session | own workspace | Onboarding sections + enriched items (`why`/`format`/`next_action`/`reviewer_note`) | ✅ | Lineage-aware via evidence_slots. |
| GET | `/portal/workspaces/{id}/calendar?year=` | provider session | own workspace | Aggregated calendar grid + enriched items (`required_document`/`deadline_iso`/`suggested_action`/`href`) | ✅ | |
| GET | `/portal/workspaces/{id}/dashboard?year=` | provider session | own workspace | Backend-composed dashboard (semaphore, suggested actions, attention, upcoming, doc counts) | ✅ | Phase 4. |
| GET | `/portal/workspaces/{id}/submissions/{submission_id}` | provider session | own workspace; submission must belong | Submission detail + replacement-lineage pointers | ✅ | |
| POST | `/portal/workspaces/{id}/submissions` | provider session | tenant identity derived from session, not browser | Tenant-safe intake (PDF, validations, audit, optional `supersedes_submission_id`) | ✅ | Phase 1 + Phase 3. |
| POST | `/portal/workspaces/{id}/complete-onboarding` | provider session | own workspace | Idempotent gate-flip to `expediente_status=complete` | ✅ | |
| GET | `/portal/workspaces/{id}/duplicate-check?sha256=` | provider session | own workspace | Wizard's pre-submit duplicate hint | ✅ | |

Deprecated (kept for the importer + dev paths):
`POST /api/v1/submissions` — trusts browser identity. Phase 1
explicitly preserves it; the workspace endpoint above is the
production replacement.

---

## Reviewer queue — `/api/v1/reviewer/*`

Auth: JWT with `reviewer` OR `internal_admin` role.

| Method | Path | Role | Tenant rule | Purpose | Stable | Notes |
|---|---|---|---|---|---|---|
| GET | `/reviewer/queue?status=&institution=&limit=` | reviewer / internal_admin | cross-tenant (queue is global for internal users) | Submissions awaiting a human decision, FIFO | ✅ | |
| GET | `/reviewer/submissions/{id}` | reviewer / internal_admin | cross-tenant read | Full submission detail incl. `supersedes_submission_id` / `superseded_by_submission_id` | ✅ | Same shape as provider detail. |
| POST | `/reviewer/submissions/{id}/decision` | reviewer / internal_admin | cross-tenant write | Routes through `apply_reviewer_decision` workflow service | ✅ | Mutates submission + document + history + validation_event + audit. |

---

## Admin operations — `/api/v1/admin/*`

Auth: JWT with `internal_admin`. Reviewer-only is **403**.

| Method | Path | Role | Tenant rule | Purpose | Stable | Notes |
|---|---|---|---|---|---|---|
| GET | `/admin/overview` | internal_admin | n/a | Operational counters | ✅ | |
| GET/POST/PATCH | `/admin/clients[/{id}]` | internal_admin | n/a | Client CRUD-minus-delete | ✅ | Audits on mutate. |
| GET/POST/PATCH | `/admin/vendors[/{id}]` | internal_admin | enforces client existence + unique (client_id, rfc) | Vendor CRUD-minus-delete | ✅ | Audits on mutate. |
| GET/PATCH | `/admin/workspaces[/{id}]` | internal_admin | n/a | Workspace read + minimal patch; `access_token` redacted | ✅ | Audits on mutate. |
| GET/POST/PATCH | `/admin/requirements[/{id}]` | internal_admin | n/a | Catalog management; initial RequirementVersion optional | ✅ | Audits on mutate. |
| GET | `/admin/periods?year=&period_type=` | internal_admin | n/a | Period roster | ✅ | Read-only. |
| GET | `/admin/calendar?year=&persona_type=` | internal_admin | n/a | Aggregated catalog snapshot | ✅ | Read-only. |
| GET | `/admin/audit-log?…&limit=` | internal_admin | n/a | Filtered audit-log explorer | ✅ | Newest-first, hard cap 200. |

Mutations always write `AuditLog` with
`actor_type="internal_admin"`, `actor_id=user.id`, `before`,
`after`, `metadata.source="admin_operations"`.

---

## Client portal — `/api/v1/client/*`

Auth: JWT with `client_admin` OR `internal_admin`. Reviewer-only
and provider users are **403**. Every endpoint resolves scope via
`memberships → organization(kind=client) → client_id`. Read-only.

| Method | Path | Role | Tenant rule | Purpose | Stable | Notes |
|---|---|---|---|---|---|---|
| GET | `/client/me` | client_admin / internal_admin | n/a | Identity + visible client ids + default | ✅ | |
| GET | `/client/overview?client_id=&year=` | client_admin / internal_admin | client_admin locked to own clients; internal_admin must pass `client_id` if no client_admin membership exists | Counters + per-semaphore-level counts | ✅ | |
| GET | `/client/vendors?...` | client_admin / internal_admin | scoped to resolved client; access_token redacted | Per-vendor row with semaphore + counts | ✅ | |
| GET | `/client/vendors/{id}` | client_admin / internal_admin | vendor must belong to scoped client (404 otherwise) | Full vendor dashboard (lineage-aware) | ✅ | |
| GET | `/client/calendar?year=` | client_admin / internal_admin | scoped | Aggregated month grid | ✅ | Day-17 / day-30 deadline heuristic. |
| GET | `/client/submissions?...` | client_admin / internal_admin | scoped; foreign vendor_id → 404 | Filtered submission list with reviewer note + lineage | ✅ | |
| GET | `/client/activity?limit=` | client_admin / internal_admin | scoped | Sanitised feed (uploads + reviewer decisions only) | ✅ | Excludes admin audit rows. |

---

## Metadata / dev surfaces

| Method | Path | Auth | Purpose | Stable |
|---|---|---|---|---|
| GET | `/health` | none | Liveness probe | ✅ |
| GET | `/api/v1/health` | none | Versioned liveness | ✅ |
| GET | `/api/v1/health/db` | none | DB reachable probe | ✅ |
| GET | `/api/v1/catalogs` | none | Frontend catalog mirror | ✅ |
| GET | `/api/v1/compliance/*` | none | Compliance catalog reads (legacy) | ⚠️ Used by `/portal/upload` wizard catalog. Keep stable until wizard adopts a workspace-scoped catalog. |
| POST | `/api/v1/metadata-dry-run/pdf` | none | n8n / sample-PDF dry-run | ⚠️ Dev/integration tool. Not consumed by the product UI. |

---

## Known limitations

- **No `/client/submissions/{id}/download`** — signed file URLs
  aren't a thing yet. Phase 8 documents this as deferred.
- **No `/admin/users` / membership editor** — admins still manage
  memberships through the DB.
- **No `POST /api/v1/workspace/corrections`** — the
  `/portal/entra-a-tu-espacio` correction form still writes to
  `lib/mock/corrections.ts`.
- **No reports / notifications / OCR / scheduled-expiry
  endpoints** — out of phase scope.

These limitations do not block the redesign; they should appear
as "future endpoint" placeholders in the new UI where
appropriate.
