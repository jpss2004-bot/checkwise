# Pre-Redesign System Map

Snapshot of every user-facing route in CheckWise as of the end of
Phase 9. The visual/product redesign that follows this phase must
preserve every "must preserve" column and may freely change the
"can redesign" column.

Status legend:

- **canonical** — production-quality, backed by canonical backend
  data, no mock fallback at runtime.
- **preview** — minimal/operational page, real backend data, plain
  table-or-form UI.
- **demo** — runtime depends on a `lib/mock/*` module because the
  backing backend endpoint hasn't shipped yet. Documented; not a
  bug.

Roles use the `MembershipRole` enum
(`internal_admin` / `reviewer` / `client_admin`); the provider
portal is its own auth chain (JWT + httpOnly cookie tied to
`ProviderWorkspace.owner_user_id`).

---

## Provider portal — workspace-scoped JWT + cookie

| Route | Status | Purpose | Backend endpoint(s) | Must preserve | Can redesign |
|---|---|---|---|---|---|
| `/portal/entra-a-tu-espacio` | demo (corrections form is mock) | Post-auth workspace confirmation; "I am at the right tenant" gate | `GET /api/v1/portal/me`; correction form posts to `lib/mock/corrections` until backend endpoint ships | Tenant-locked field rendering; correction-request affordance; redirect to `/portal/onboarding` or `/portal/dashboard` based on `expediente_status` | Layout, copy, locked-field visualisation, correction-form UX |
| `/portal/onboarding` | canonical | Expediente Corporativo gate — providers complete required documents to unlock the dashboard | `GET /api/v1/portal/workspaces/{id}/onboarding`, `POST /api/v1/portal/workspaces/{id}/complete-onboarding` | "Required vs optional" split; `expediente_status === complete` unlocks dashboard; backend-owned `why`/`format`/`next_action`/`reviewer_note` per item; replacement-lineage-aware current submission | Card layout, section grouping, progress visualisation, copy |
| `/portal/dashboard` | canonical | Provider semaphore + suggested actions + attention items + upcoming deadlines | `GET /api/v1/portal/workspaces/{id}/dashboard` | Semaphore semantics (red/yellow/green rules), counts buckets, lineage-aware current submission, `expediente_status` gating via `withOnboardingGate` | All layout, tile design, suggested-action UI, attention visualisation |
| `/portal/calendar` | canonical | Year-grid of recurring obligations | `GET /api/v1/portal/workspaces/{id}/calendar` | Lineage-aware current submission per slot; backend-supplied `required_document`/`deadline_iso`/`suggested_action`/`href` | Grid layout, drawer, status pills, filter chips |
| `/portal/submissions/[submission_id]` | canonical | Single submission detail + correction flow | `GET /api/v1/portal/workspaces/{id}/submissions/{id}` | Replacement lineage strip ("reemplaza" / "reemplazado por"); reupload CTA threading `?replaces=` to the wizard; reviewer notes + status history | Visual hierarchy, reasons card, timeline, traceability footer |
| `/portal/upload` | canonical | 5-step intake wizard | `POST /api/v1/portal/workspaces/{id}/submissions`, `GET /portal/workspaces/{id}/duplicate-check` | Tenant-safe upload (no browser-posted client/vendor identity); `supersedes_submission_id` lineage link; duplicate pre-check; PDF-only validation | Step layout, locked-context display, success/error states |
| `/portal/reports` | demo (`lib/mock/reports`) | Reports preview center | none (mock only) | The 5 report-state vocabulary (`ready`/`generating`/`needs_review`/`blocked`/`unavailable`) when backend pipeline ships | Everything — backend pipeline is the redesign trigger |

---

## Reviewer surface — internal_admin / reviewer JWT

| Route | Status | Purpose | Backend endpoint(s) | Must preserve | Can redesign |
|---|---|---|---|---|---|
| `/admin/reviewer` | preview | Reviewer queue ordered by attention | `GET /api/v1/reviewer/queue` (filters: status, institution) | Tenant-cross visibility (queue is global for internal users); FIFO ordering; submission age display | Filter chips, row layout, priority cues |
| `/admin/reviewer/[submission_id]` | preview | Full reviewer detail + decision form | `GET /api/v1/reviewer/submissions/{id}`, `POST .../decision` | Status mutation goes only through the workflow service; reason required for reject/clarify/exception; replacement-lineage strip (Phase 9); audit trail of decisions | Card composition, decision-form layout, timeline visualisation |
| `/admin/login` | canonical | Staff login → JWT | `POST /api/v1/auth/login` | `must_change_password` → `/activate` redirect; redirect by role | Form layout |

---

## Admin operations — internal_admin only

| Route | Status | Purpose | Backend endpoint(s) | Must preserve | Can redesign |
|---|---|---|---|---|---|
| `/admin` | preview | Admin home + role-aware tile grid | `GET /api/v1/auth/me` (implicit via session) | Role-gated tile visibility | Tile design |
| `/admin/dashboard` | preview | Operational counters | `GET /api/v1/admin/overview` | Counter accuracy; internal_admin-only access | Tile layout |
| `/admin/clients` | preview | Client list + create/edit form | `GET/POST/PATCH /api/v1/admin/clients[/{id}]` | Mutations write `admin.client.*` audit rows; status toggle (no delete) | Form/table layout |
| `/admin/vendors` | preview | Vendor list + create/edit form | `GET/POST/PATCH /api/v1/admin/vendors[/{id}]` | Vendor must belong to existing client (404 otherwise); unique (client_id, rfc); status toggle (no delete); audit on mutate | Form/table layout |
| `/admin/requirements` | preview | Catalog list + create/edit | `GET/POST/PATCH /api/v1/admin/requirements[/{id}]` | RequirementVersion 1 created when version fields supplied; audit on mutate; do not break `compliance_catalog.py` | Layout, copy |
| `/admin/calendar` | preview | Period roster + recurring catalog summary | `GET /api/v1/admin/periods`, `GET /api/v1/admin/calendar` | Read-only; matches `compliance_catalog` shape | Layout |
| `/admin/audit-log` | preview | Filtered audit-log explorer | `GET /api/v1/admin/audit-log` | Newest-first; AND filters; limit cap 200; internal_admin-only | Filter form, row layout |

`ProviderWorkspace.access_token` is **never** returned by any admin
endpoint. Regression-pinned by `test_admin_workspaces_response_redacts_access_token`.

---

## Client portal — client_admin / internal_admin (read-only)

| Route | Status | Purpose | Backend endpoint(s) | Must preserve | Can redesign |
|---|---|---|---|---|---|
| `/client` | preview | Redirects to `/client/dashboard` | none | Redirect semantics | (nothing to redesign) |
| `/client/dashboard` | preview | Operational counters + semaphore breakdown | `GET /api/v1/client/me`, `GET /api/v1/client/overview` | Scope resolution (client_admin → own client; internal_admin → must pick `client_id`); red/yellow/green semantics identical to provider | Tile layout |
| `/client/vendors` | preview | Per-vendor table with semaphore + filters | `GET /api/v1/client/vendors` | No `access_token` exposure; semaphore semantics identical to provider; tenant scoping | Filter chips, row layout |
| `/client/vendors/[vendor_id]` | preview | Per-vendor dashboard (onboarding/doc counts/semaphore/actions/attention/recent submissions/reviewer notes) | `GET /api/v1/client/vendors/{id}` | Cross-client → 404; replacement-lineage-aware recent submissions; reviewer notes; no access_token | Card composition |
| `/client/calendar` | preview | Aggregated month grid across the client's portfolio | `GET /api/v1/client/calendar?year=` | Day-17 / day-30 deadline heuristic; tenant scope; lineage-aware current submission | Grid layout |
| `/client/submissions` | preview | Filtered submission list with reviewer note + lineage | `GET /api/v1/client/submissions` | Replacement-lineage fields; reviewer note from latest reviewer-decision event; tenant scope; vendor_id validated before filter | Table layout, filter form |
| `/client/activity` | preview | Sanitised activity feed | `GET /api/v1/client/activity` | Only `submission.uploaded`, `reviewer.decision`, `submission.replacement_linked`, `submission.replaced`; admin audit metadata excluded; tenant scope | Timeline/list layout |

---

## Cross-surface compile and route check

Frontend `next build` produces 29 routes total. All seven client
routes, ten admin routes, six provider routes, and the home /
login / activate routes are statically prerendered (except the two
dynamic `[submission_id]` routes). Confirmed in the Phase 8 build
output and re-verified in Phase 9 final gauntlet.

---

## Demo runtime dependencies (intentionally retained)

These `lib/mock/*` modules survive because the corresponding
backend endpoint or workflow has not yet been built. They are NOT
hidden — each is gated by a clearly demo-only page and named:

| Mock module | Powers | Future canonical replacement |
|---|---|---|
| `lib/mock/reports.ts` | `/portal/reports` (5 states + fixture list) | Phase 10 reports pipeline |
| `lib/mock/corrections.ts` | Correction-request form on `/portal/entra-a-tu-espacio` | `POST /api/v1/workspace/corrections` (deferred) |
| `lib/mock/invitations.ts` | `/activate?token=…` flow + `Invitation` type used by `buildWorkspaceContext` | Real backend invitation flow (deferred) |
| `lib/mock/activation.ts` | Activation transition (`writePortalSession` shim) | Real `/portal/access`-equivalent endpoint that mints the cookie at activation time |
| `lib/mock/dashboard.ts` | `DashboardSemaphore`/`SemaphoreTone` types only on `/portal/dashboard` | Type can move to `lib/api/portal.ts` once redesign decides on the semaphore prop shape |
| `lib/mock/contact-requests.ts` | Marketing contact form on `/` | Real `/api/v1/marketing/contact` endpoint (deferred) |

Removed in earlier phases (no longer in the tree):
`lib/api/portal-adapters.ts`, `lib/mock/calendar.ts`,
`lib/mock/expediente.ts`, `lib/routing/post-login.ts`,
`components/checkwise/workspace/access-decision-banner.tsx`,
`lib/workspace/resolver.ts::decideWorkspaceAccess`.
