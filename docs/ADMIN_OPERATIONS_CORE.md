# Admin Operations Core

Phase 7 — internal control plane so CheckWise can be operated from
the app instead of directly from the database. Scoped to
LegalShelf-internal staff (`internal_admin` role); reviewers and
provider users are intentionally out of scope.

Companion to
[WORKFLOW_STATE_MACHINE.md](WORKFLOW_STATE_MACHINE.md),
[EVIDENCE_SLOTS.md](EVIDENCE_SLOTS.md),
[PROVIDER_DASHBOARD_READ_MODEL.md](PROVIDER_DASHBOARD_READ_MODEL.md),
and [PROVIDER_PORTAL_CANONICAL_READS.md](PROVIDER_PORTAL_CANONICAL_READS.md).

## Endpoints

All endpoints live under `prefix=/admin` and are gated on the
`internal_admin` role via
`require_role(MembershipRole.INTERNAL_ADMIN)`.

| Method | Path                                                    | Purpose                                  |
|--------|---------------------------------------------------------|------------------------------------------|
| GET    | `/api/v1/admin/overview`                                | Operational counters (clients, vendors, workspaces, reviews, audit). |
| GET    | `/api/v1/admin/clients`                                 | List clients.                            |
| GET    | `/api/v1/admin/clients/{client_id}`                     | Read one client.                         |
| POST   | `/api/v1/admin/clients`                                 | Create client.                           |
| PATCH  | `/api/v1/admin/clients/{client_id}`                     | Update client (partial).                 |
| GET    | `/api/v1/admin/vendors`                                 | List vendors (filter by `client_id`).    |
| GET    | `/api/v1/admin/vendors/{vendor_id}`                     | Read one vendor.                         |
| POST   | `/api/v1/admin/vendors`                                 | Create vendor; rejects missing client.   |
| PATCH  | `/api/v1/admin/vendors/{vendor_id}`                     | Update vendor (partial).                 |
| GET    | `/api/v1/admin/workspaces`                              | List provider workspaces (no token).     |
| GET    | `/api/v1/admin/workspaces/{workspace_id}`               | Read one workspace (no token).           |
| PATCH  | `/api/v1/admin/workspaces/{workspace_id}`               | Update status / owner / display fields.  |
| GET    | `/api/v1/admin/requirements`                            | List requirements (filters).             |
| GET    | `/api/v1/admin/requirements/{requirement_id}`           | Read one requirement (with current version). |
| POST   | `/api/v1/admin/requirements`                            | Create requirement (+ optional version 1).|
| PATCH  | `/api/v1/admin/requirements/{requirement_id}`           | Update requirement fields.               |
| GET    | `/api/v1/admin/periods`                                 | List Period rows (filter by year / type).|
| GET    | `/api/v1/admin/calendar?year=…`                         | Aggregated recurring catalog snapshot.   |
| GET    | `/api/v1/admin/audit-log`                               | Filtered audit-log explorer.             |

Provider portal endpoints, reviewer queue, evidence-slot service,
and submission workflow are unchanged.

## Permission model

- `internal_admin` → full access to every endpoint in this router.
- `reviewer` (only) → **403** on every admin endpoint. Reviewers
  keep their access to `/api/v1/reviewer/*` and `/admin/reviewer/*`.
- `client_admin` / no role → **403** on every admin endpoint.
- Unauthenticated → **401** (via `get_current_user`).

Frontend: every admin operations page calls
`readAdminSession()` and redirects to `/admin/login` if no session
or to `/admin` if the role is not `internal_admin`. Reviewer-only
users still see the reviewer tile on `/admin` but no admin
operations links.

## Audit behavior

Every mutation routes through `_audit_admin(...)` in
`app/api/v1/admin.py`, which calls the shared `add_audit_event`
helper with:

```python
actor_type   = "internal_admin"
actor_id     = current.user.id
action       = "admin.<entity>.<verb>"  # admin.client.created, etc.
entity_type  = "client" | "vendor" | "provider_workspace" | "requirement"
entity_id    = row.id
before       = <previous serialisation, or None on create>
after        = <new serialisation>
metadata     = {"source": "admin_operations", ...}
```

Actions emitted:

| Action                            | When                              |
|-----------------------------------|-----------------------------------|
| `admin.client.created`            | `POST /admin/clients`             |
| `admin.client.updated`            | `PATCH /admin/clients/{id}`       |
| `admin.vendor.created`            | `POST /admin/vendors`             |
| `admin.vendor.updated`            | `PATCH /admin/vendors/{id}`       |
| `admin.workspace.updated`         | `PATCH /admin/workspaces/{id}`    |
| `admin.requirement.created`       | `POST /admin/requirements`        |
| `admin.requirement.updated`       | `PATCH /admin/requirements/{id}`  |

Read endpoints do not write to `audit_log`. Use the audit-log
explorer (`GET /admin/audit-log?actor_type=internal_admin`) to
reconstruct any operator's session of changes.

## Workspace `access_token` is never returned

Phase 1 made tenant-safe uploads possible by tying the workspace
session token to the provider's identity. Surfacing that token in
an admin response would defeat the guard. Every admin workspace
serializer strips it explicitly; a regression test
(`test_admin_workspaces_response_redacts_access_token`) pins the
contract.

## What admins can manage today

- Clients: name, RFC, responsible person, status.
- Vendors: same identity fields per client + REPSE id + contact.
  Hard-coded to belong to an existing client. Status toggle.
- Provider workspaces: status, owner user, display name, filial
  name. Status toggle.
- Requirements: code, name, institution, load type, frequency, risk
  level, active flag. New requirements may seed an initial version
  1 with legal basis / human-review / required flags.
- Periods: read-only listing (filter by year / period type).
- Calendar: read-only aggregated catalog snapshot per persona type.
- Audit log: filter by actor / action / entity / date / limit.

## Intentionally not implemented yet

- Full RBAC permission editor (membership CRUD, role grants).
- 2FA / session-policy enforcement.
- Notification center (no email / WhatsApp).
- Integration monitor (Render / Vercel / Postgres health probes).
- Client portal (out-of-tenant `client_admin` view).
- Report generation pipeline.
- AI / OCR metadata extraction.
- Bulk import / Google Sheets export.
- Scheduled expiry jobs.
- Period creation / holiday adjustment.
- Multi-version requirement editor (only initial version 1 on
  create today).

Each is tracked as a follow-up phase and can adopt the same admin
audit + permission scaffolding.

## Where new code lives

| Backend                                                         | Frontend                                                       |
|-----------------------------------------------------------------|-----------------------------------------------------------------|
| [apps/api/app/api/v1/admin.py](../apps/api/app/api/v1/admin.py)   | [apps/web/lib/api/admin.ts](../apps/web/lib/api/admin.ts)       |
| [apps/api/tests/test_admin.py](../apps/api/tests/test_admin.py)   | [apps/web/app/admin/_shell.tsx](../apps/web/app/admin/_shell.tsx) and the six new pages under `apps/web/app/admin/{dashboard,clients,vendors,requirements,calendar,audit-log}/` |
