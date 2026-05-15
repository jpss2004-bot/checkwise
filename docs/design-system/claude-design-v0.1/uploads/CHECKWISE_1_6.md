# CheckWise 1.6 — Implementation note

Companion to [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md), [ONBOARDING_V1.md](ONBOARDING_V1.md), and [CHECKWISE_1_5.md](CHECKWISE_1_5.md). Documents the workspace-confirmation step, security hardening, routing logic, and reports state additions that landed in CheckWise 1.6.

## Goals

Add the post-auth workspace-confirmation step (`/portal/entra-a-tu-espacio`), harden tenant isolation and protected-field handling, refine the post-login routing helper, and grow the reports surface with `blocked` + `unavailable` states. Don't break anything from 1.5.

## Route map

| Route | Before 1.6 | After 1.6 |
|---|---|---|
| `/` | Marketing landing; if session existed, sent to `/portal/onboarding` | Marketing landing; **session → `/portal/entra-a-tu-espacio`** |
| `/login` | Role selector; success → `/portal/onboarding` | Role selector; **success → `/portal/entra-a-tu-espacio`** |
| `/activate?token=…` | Identity step success → `/portal/onboarding` | Identity step success → **`/portal/entra-a-tu-espacio`** |
| `/portal/entra-a-tu-espacio` | did not exist | **New** — workspace confirmation gate |
| `/portal/onboarding` | unchanged | Adds "Reportar inconsistencia" link on rejected/needs_review/expired cards |
| `/portal/dashboard` | Semaphore + summary | Adds `WorkspaceIdentityCard` with locked fields + correction CTA |
| `/portal/reports` | 4 reports, 4 statuses | Adds **blocked** + **unavailable** states; new seed report + tenant scope note |
| `/portal/calendar` | unchanged | unchanged |

## Post-auth routing flow

```
Login submitted / Activation success / Returning session
          │
          ▼
decidePostLoginRoute(requirements, workspace_id)
          │
   ┌──────┴──────────────────────────────────────────┐
   │ workspace not yet confirmed?                    │
   │  YES → /portal/entra-a-tu-espacio               │
   │        (banner: needs_workspace_confirmation)   │
   └──────┬──────────────────────────────────────────┘
          │ user confirms via "Entrar a mi espacio"
          ▼
   decideWorkspaceAccess(workspace, alreadyConfirmed=true, …)
          │
   ┌──────┼──────────────────────────────────────────────────┐
   │ blocked       → AccessDecisionBanner (no redirect)      │
   │ mandatory     → /portal/onboarding                      │
   │ in_review     → /portal/dashboard + ProvisionalAccessBanner │
   │ all approved  → /portal/dashboard                       │
   └──────────────────────────────────────────────────────────┘
```

## "Entra a tu espacio" purpose

Not a loading screen. A **secure workspace confirmation step**. Lives between auth-success and the rest of the portal. Users see:

- **Tenant identity** — role, RFC, razón social, workspace id (locked, via `ProtectedFieldNotice`)
- **Editable profile** — first name, last name, phone, job title, contact preference (free to edit)
- **Next-step preview** — 4 tiles previewing what's coming
- **Primary CTA** — "Entrar a mi espacio" persists the profile + flips `workspace_confirmed_at`, then redirects via `decideWorkspaceAccess`
- **Secondary CTA / scroll target** — "Reportar información incorrecta" anchors to the inline `CorrectionRequestForm`

## Editable vs protected fields

Source: `lib/workspace/types.ts`.

### `EditableProfileFields` — user can update inline

| Field | Notes |
|---|---|
| `first_name` | Free edit |
| `last_name` | Free edit |
| `phone` | Optional, free edit |
| `job_title` | Optional, free edit |
| `contact_preference` | `email` / `whatsapp` / `both` |

### `ProtectedWorkspaceFields` — locked, correction-request only

| Field | Why locked |
|---|---|
| `workspace_id` | Tenant primitive — backend-issued, never editable |
| `tenant_id` | Same |
| `client_id` / `provider_id` | Mapping owned by admin |
| `role` | From invitation; changing requires admin review |
| `rfc` | Legal identity |
| `email` | Invitation anchor |
| `company_legal_name` | Legal identity |
| `email_domain` | Mismatch surface |

Any attempt to change a protected field opens the `CorrectionRequestForm`. The form sets `requires_admin_review: true` and stores a `ProfileCorrectionRequest` for backend review.

## Tenant isolation rules

- `localStorage` is convenience only — **never authority**. Any protected value must be re-fetched from a backend route the user is authenticated against.
- File hash (SHA-256) is for integrity / deduplication — **not authorization**.
- `decideWorkspaceAccess` returns `blocked` when:
  - Invitation expired / revoked / used
  - Token-hinted company domain doesn't match the email domain (generic domains skip this check)
  - Role dispute / unknown workspace
- Reports never let the client choose `company_id` — backend resolves from the authenticated session.

Every relevant block carries a `TODO[security-backend]` comment.

## New types (`lib/workspace/types.ts`)

```ts
WorkspaceContext            // { protected, editable, invitation_hints, confirmed_at_iso }
ProtectedWorkspaceFields    // workspace_id, tenant_id, client_id, provider_id,
                            //   role, rfc, email, company_legal_name, email_domain
EditableProfileFields       // first_name, last_name, phone, job_title, contact_preference
WorkspaceAccessOutcome      // discriminated union: allow / allow_provisional /
                            //   redirect_onboarding / needs_confirmation / blocked
ProfileCorrectionRequest    // id, workspace_id, field, current_value, proposed_value,
                            //   reason, message?, requires_admin_review, created_at_iso
PROTECTED_FIELD_LABEL       // Map<keyof ProtectedWorkspaceFields, string>
EDITABLE_FIELD_LABEL        // Map<keyof EditableProfileFields, string>
```

## Components added

| Component | Purpose |
|---|---|
| `ProtectedFieldNotice` | Read-only display of a tenant-locked field with lock icon + helper |
| `WorkspaceIdentityCard` | Tenant identity summary used on `/portal/entra-a-tu-espacio` + `/portal/dashboard` |
| `CorrectionRequestForm` | Submit a `ProfileCorrectionRequest`; marks protected-field changes as `requires_admin_review` |
| `AccessDecisionBanner` | Renders the right banner copy for any `WorkspaceAccessOutcome` |

All four live under `components/checkwise/workspace/`.

## Mock modules

| Module | Purpose | Backend target |
|---|---|---|
| `lib/mock/corrections.ts` | Submit / save / list local corrections + editable-profile patches | `POST /api/v1/workspace/corrections` + audit log |
| `lib/workspace/resolver.ts` | Build `WorkspaceContext` + compute `WorkspaceAccessOutcome` | `GET /api/v1/portal/workspace` |
| `lib/mock/reports.ts` | Adds `blocked` + `unavailable` states + 5th seed report | Existing reports endpoints (1.5) |

Routing helper extension lives in `lib/routing/post-login.ts` — adds `needs_workspace_confirmation` banner and the `workspace_id` parameter.

## Reports foundation enhancements

- **New states**: `blocked` (data integrity issue — can't generate), `unavailable` (period not yet closed)
- **5th seed report** that exercises the `blocked` state
- **Tenant scope note** added to the page: "Aislamiento por tenant. Cada reporte sólo incluye datos del workspace autenticado. Nunca seleccionamos clientes o proveedores por ID en el frontend — la backend valida ownership antes de generar un PDF."

## Backend integration TODOs

Find them all with: `rg 'TODO\[(backend-integration|security-backend)\]' frontend/lib`.

Priority order for V1.6 → V1.7:

1. **`GET /api/v1/portal/workspace`** — returns the full `WorkspaceContext` derived from the authenticated session
2. **`POST /api/v1/workspace/corrections`** — persists the correction request + emits notification to admin reviewers + writes audit log
3. **`workspace_membership.workspace_confirmed_at`** — replaces the `checkwise.workspace.confirmed.v1` localStorage check
4. **Token expiry + single-use enforcement** server-side (currently only mock validates)
5. **Domain + RFC mismatch checks** server-side (frontend checks are UX-only)
6. **Reports generation pipeline** (from 1.5, unchanged)

## What still depends on real auth / session / backend

- The portal session is still a localStorage workspace token (`lib/session/portal.ts`).
- `buildWorkspaceContext` synthesizes the snapshot from the session + the locally-stored `demo` invitation. Production must derive every protected field from the authenticated session.
- `decideWorkspaceAccess` returns `blocked` only for the mock-detectable conditions (token expired locally, slug-based domain mismatch). Real validation must happen server-side.
- `submitCorrection` persists into localStorage. No notification, no audit log, no admin queue. All blocked behind `TODO[backend-integration]`.

## What's fully working in the browser

- `/portal/entra-a-tu-espacio` renders the identity card with locked fields, the editable profile form, the next-step preview, and the inline correction request form
- Confirmation persists `confirmed_at` per workspace_id and routes to the right destination via `decideWorkspaceAccess`
- Dashboard now shows the `WorkspaceIdentityCard` between the locked/provisional banner and the semaphore
- Onboarding cards in `rejected` / `needs_review` / `expired` states show the "Reportar inconsistencia" link
- Reports page shows the new "Aislamiento por tenant" note + a `blocked` example
- `tsc` clean, `next lint` clean, `next build` clean (15 routes)
- Browser smoke: zero console errors on every touched route

## Suggested follow-ups

1. **Real auth + workspace API** — biggest lift. Until then every "this is locked" claim is UX-only.
2. **Audit log surface** — the corrections list (`listCorrections`) needs an admin view.
3. **Mismatched-period reports** — when the user's `requirements` snapshot shows blocking items, the `provider_expediente` report should auto-flip to `blocked`.
4. **Wizard split** — still 1,268 LOC.
5. **i18n** — copy is hardcoded Spanish; the existing structure makes a `dict` extraction easy.
6. **Frontend tests** — `decideWorkspaceAccess` and `decidePostLoginRoute` are pure functions and deserve unit tests.
