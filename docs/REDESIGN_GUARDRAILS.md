# Redesign Guardrails

What the upcoming CheckWise redesign must respect. Read this
**before** opening any frontend file. Companion to
[PRE_REDESIGN_SYSTEM_MAP.md](_archive/PRE_REDESIGN_SYSTEM_MAP.md) and
[API_CONTRACT_MAP.md](API_CONTRACT_MAP.md).

## 1. Product principle

> CheckWise should feel like a **guided compliance assistant**,
> not a generic compliance database.

Every surface answers two questions for its user:

1. *What is my situation right now?* — current state, semaphore,
   counts, lineage.
2. *What should I do next?* — concrete next action, why it
   matters, where to do it.

A redesign that produces clean tables but doesn't answer either
question regresses the product. Stay opinionated about the
narrative.

## 2. Non-negotiable architecture rules

These are pinned by tests and a redesign that breaks any of them
will fail CI:

1. **PostgreSQL is the source of truth for compliance state.** The
   frontend may not invent a status, a count, a semaphore level,
   or a deadline from local fixtures. Every visible compliance
   field traces to a canonical backend response.
2. **`access_token` never leaves the backend.** The provider
   workspace session token is the tenant guard for uploads;
   surfacing it in any response (admin, client, reviewer) breaks
   Phase 1's contract. Regression-pinned by
   `test_admin_workspaces_response_redacts_access_token` and the
   client-portal redaction test.
3. **`client_admin` sees only their own client(s).** Scope is
   `memberships → organization(kind="client") → client_id`.
   Cross-client → 403. `internal_admin` may inspect but must pass
   `?client_id=` explicitly.
4. **Providers see only their own workspace.** Enforced by
   `current_portal_workspace` and `ProviderWorkspace.owner_user_id`.
5. **Reviewer and admin permissions stay separate.** `reviewer`
   alone cannot reach `/api/v1/admin/*` or `/api/v1/client/*`.
   Both gates are 403.
6. **Replacement lineage is preserved.** `supersedes_submission_id`
   stays the canonical "I replaced this prior" pointer. The
   evidence-slot service walks the chain to pick the "current"
   submission. Don't add a second source of truth for "which
   submission is active for this slot."
7. **Audit logging must remain intact.** Every reviewer decision,
   admin mutation, and submission intake writes to `audit_log`.
   The redesign may rebuild the UI that displays audit rows but
   must not bypass the write path.
8. **AI/OCR cannot auto-approve critical documents.** A future
   OCR phase may pre-validate signals; final approval is always a
   reviewer decision recorded through the workflow state machine.

## 3. UI/UX redesign priorities

In order of importance:

1. **Guide non-technical users.** Provider personas are not
   compliance experts. Lead with the next step, not the regulatory
   citation.
2. **Reduce mistakes.** Make uploading the wrong document hard;
   make uploading the right one one click.
3. **Show progress.** Onboarding gate progress, calendar coverage,
   per-vendor compliance — visible at a glance.
4. **Explain *why* a document is needed.** The catalog
   `why`/`format` fields exist for this; surface them prominently.
5. **Show the next action clearly.** `next_action` for onboarding,
   `suggested_action` for calendar, `suggested_actions[]` on the
   dashboard — these strings are computed against current state.
6. **Use semaphores consistently.** red/yellow/green semantics are
   defined once in the evidence-slot service. Use the same colors
   and the same rules across provider, admin, client surfaces.
7. **Reviewer and admin surfaces stay operational, not
   decorative.** Tables, filters, audit visibility. Don't waste
   real estate on hero animations there.
8. **Client surfaces stay executive and action-oriented.** The
   client buys *visibility into a portfolio*, not document
   management. Headline counts → drill into vendors → drill into
   submissions.

## 4. What the redesign **can** change freely

These are pure presentation concerns; no backend coordination
needed:

- Layout, grid, card composition, spacing, padding.
- Typography, weights, line heights.
- Color tokens, palette, dark mode.
- Component structure (buttons, badges, modals).
- Navigation grouping + visual hierarchy.
- Empty states, loading skeletons, error states.
- Animations, transitions, micro-interactions.
- Iconography (`@phosphor-icons/react` is in place — keep one
  family).
- Copy refinement (without changing meaning of
  `next_action`/`suggested_action`/`why` since those are
  backend-owned).
- Mobile responsive breakpoints.

## 5. What the redesign **cannot** change without backend coordination

Each item below needs a backend phase before the UI can change
its shape:

- **Route auth assumptions.** Changing who can hit
  `/admin/reviewer` requires updating `require_any_role`
  dependencies.
- **Endpoint contracts.** Renaming a field or removing one needs
  a new endpoint version + frontend cutover.
- **Tenant isolation rules.** Anything that would let a client
  see another client's data, a provider see another provider's,
  or a reviewer/admin see hidden fields, is a backend ticket
  first.
- **Upload semantics.** Tenant-safe uploads derive identity from
  the authenticated workspace, not from form fields. The redesign
  may not reintroduce browser-posted `client_name`/`vendor_name`/
  `vendor_rfc` as authoritative.
- **Evidence-slot logic.** Which submission is "current" for a
  slot is decided by lineage in
  `app/services/evidence_slots.py`. Don't compute it in the
  frontend.
- **Validation state machine.** Status transitions go through
  `app/services/submission_workflow.py::apply_reviewer_decision`.
  No direct `submission.status = …` mutations from any new code.
- **Lineage semantics.** `supersedes_submission_id` is the
  canonical "I replaced X" pointer.
  `superseded_by_submission_id` is computed at read time. The
  redesign can render these differently but cannot redefine them.
- **Audit logging.** Action codes (`admin.client.created`,
  `submission.reviewer_decision`, `submission.replacement_linked`,
  …) are stable identifiers. UI may render them differently but
  shouldn't fork them.

## 6. Demo dependencies the redesign should make obvious

Some surfaces still run on `lib/mock/*` because the backing
endpoint hasn't shipped. These are documented in
[PRE_REDESIGN_SYSTEM_MAP.md](_archive/PRE_REDESIGN_SYSTEM_MAP.md). The
redesign should label them visibly as previews ("Próximamente",
"Vista preliminar", etc.) so a stakeholder doesn't mistake the
demo for production:

- `/portal/reports` — backed by `lib/mock/reports.ts`.
- `/portal/entra-a-tu-espacio` correction-request form — backed
  by `lib/mock/corrections.ts`.
- `/activate?token=…` flow — backed by `lib/mock/invitations.ts`
  for the demo invitation.

A redesigned product that hides the preview status of these
surfaces is a regression.

## 7. Implementation notes for the redesign team

- Frontend tests don't exist in this repo. Use
  `node_modules/.bin/tsc --noEmit` + `next build` as the contract
  check.
- Backend tests are the only safety net for cross-surface invariants;
  do NOT break them.
- `next lint` is deprecated but still passes. Acceptable.
- The `lib/api/*` modules (`admin.ts`, `client.ts`, `portal.ts`,
  `reviewer.ts`, `auth.ts`) are the typed boundary between
  frontend and backend. Add a new helper rather than reaching
  into `fetch` directly.
- `readAdminSession()` is the staff JWT helper — reused by admin,
  reviewer, and client surfaces. Provider portal uses its own
  cookie-based path (`fetchCurrentSession()`).

## 8. Process for a redesign that needs to break a guardrail

1. Open a backend ticket that describes the change (new
   endpoint, additive field, audit-action rename, etc.).
2. Land the backend change with tests.
3. Update [API_CONTRACT_MAP.md](API_CONTRACT_MAP.md).
4. Then ship the redesigned frontend that consumes it.

Never the other way around. Frontends inferring data from
locally-computed mocks is the original sin this repo has been
explicitly cleaning up across phases 5–8.
