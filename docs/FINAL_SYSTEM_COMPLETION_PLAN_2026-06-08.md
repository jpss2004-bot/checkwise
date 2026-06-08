# CheckWise final system completion plan - 2026-06-08

Purpose: define the path from the current hardened, presentation-ready CheckWise workspace to a final production-complete system.

Current status: CheckWise is ready to present as a hardened pilot-ready platform. It is not yet "final-final" production complete because several product and operations tracks still need to be closed before broad client/vendor rollout.

## 1. Current readiness

### Cleared for presentation

- Core product flow exists across provider, reviewer, admin, and client surfaces.
- Tenant-aware auth and RBAC are in place for admin, reviewer, and client routes.
- Provider portal, onboarding, upload, reviewer decisions, client visibility, reports, Wise client assistant, audit packages, and notification foundations are present.
- The broader workspace has been indexed and cleaned non-destructively.
- Deprecated/prototyping API routes now default to local-only exposure.
- Route policy manifest drift has been fixed.
- Python, web, and workshop dependency audits are clean at moderate severity.
- Full backend test suite passed after hardening: `1,387 passed`.
- Web lint, typecheck, tests, build, and audit passed after hardening.

### Cleared or superseded older gaps

- Runtime auth-secret guard exists.
- API docs are gated outside local/dev.
- CORS is explicit, not wildcard.
- SMTP and frontend base URL entries are represented in deployment config.
- Client/provider notification read actions write audit events.
- Client-admin provider invite flow exists in API and web onboarding, including audit trail and no plaintext password in the client response.

## 2. Release freeze gate

These are the minimum tasks before treating the current state as a frozen presentation or pilot release.

| Gate | Status | Owner | Notes |
| --- | --- | --- | --- |
| Mixed dirty tree reconciled | Open | Engineering | Current tree includes hardening work plus pre-existing WhatsApp, onboarding, seed, render, and demo-deploy changes. Review before commit. |
| Hardening changes committed | Open | Engineering | Commit only the approved hardening/finalization scope, or intentionally include the broader dirty work after review. |
| Staging deploy smoke test | Open | Engineering | Verify login, provider portal, client portal, upload, reviewer decision, report generation, and notification surfaces against real staging env. |
| Production env checklist completed | Open | Platform | Confirm secrets, CORS, SMTP, WhatsApp/Twilio, AI keys, database, storage, and backup settings. Do not print secrets into docs. |
| Demo data boundary confirmed | Open | Product/Ops | Confirm demo accounts, fixture data, and local storage artifacts cannot be confused with production data. |
| Final demo rehearsal | Open | Product/Engineering | Run the scripted demo once from clean browser state and capture any blockers. |

## 3. P0 finalization work

P0 means required before a paid pilot or client-facing production environment.

1. Reconcile and freeze the current branch.
   - Separate hardening/finalization edits from older WhatsApp/demo-deploy/onboarding edits.
   - Decide whether to ship all dirty work together or split into separate commits.
   - Commit with a validation summary.

2. Deploy a staging environment that mirrors production.
   - Managed Postgres.
   - S3-compatible object storage.
   - Render/Railway/Fly/Cloud Run backend.
   - Vercel frontend.
   - SMTP, WhatsApp/Twilio, AI provider, and allowed origins configured.

3. Run staging smoke tests.
   - Provider login and workspace confirmation.
   - Client login and provider invite.
   - Provider upload and duplicate pre-check.
   - Reviewer approval, rejection, clarification, and exception.
   - Client dashboard, vendors, reports, audit package export.
   - Notification fanout in passive and active modes.

4. Lock production data policy.
   - Document which seeded/demo accounts are safe only for demo.
   - Confirm real production users are provisioned through approved flows.
   - Archive or remove generated local storage/report exports that are not needed for the pilot.

## 4. P1 system completion work

P1 means required for a complete self-serve system, but not necessarily blocking a controlled pilot if operations can cover the gap.

1. Finish V2.2 real backend wiring.
   - Done/current: `/api/v1/portal/workspaces/{id}/onboarding` already exposes `why`, `format`, `next_action`, and `reviewer_note`; `/portal/onboarding` consumes the enriched response directly.
   - Retire remaining legacy mock/adaptation shims where real API payloads now exist.
   - Replace the remaining opaque provider workspace token dependency with JWT/RBAC ownership checks.

2. Complete user provisioning flows.
   - Client invitation and activation flow for new client admins.
   - Provider invitation resend/revoke/status management.
   - Role-management UI for client admins and LegalShelf operators.

3. Complete source-of-truth importers.
   - Field dictionary for JotForm, Google Sheets, and any legacy Excel inputs.
   - Idempotent PostgreSQL importer.
   - Duplicate/unmappable/divergence report.

4. Complete document intelligence.
   - Async extraction job lifecycle.
   - Persistent extracted fields, evidence, review status, and export batches.
   - Reviewer accept/correct/reject UI before legal approval.
   - CSV/XLSX exports first, then Google Sheets sync.

5. Complete notifications.
   - Provider alerts for overdue/rejected/action-required states.
   - Reviewer SLA and queue-depth alerts.
   - Client digests through email, WhatsApp, and eventually Slack.

6. Complete operations and observability.
   - Backups and restore rehearsal.
   - Structured logs and dashboard monitors.
   - Error alerting for auth, upload, report generation, email, WhatsApp, and AI calls.
   - Runbook for incident triage and client support.

## 5. P2 polish

- Pay down existing backend Ruff debt in report rendering, prompts, and scripts.
- Migrate FastAPI startup from `on_event` to lifespan.
- Replace `vite-tsconfig-paths` with Vite native `resolve.tsconfigPaths` when safe.
- Create formal asset-retention rules for fixtures, sample docs, sales collateral, generated exports, and workshop artifacts.
- Add scheduled dependency audit coverage for API, web, and workshop tooling.

## 6. Presentation positioning

Use this positioning now:

"CheckWise is a hardened pilot-ready compliance platform. The system demonstrates the real REPSE/document workflow end to end: provider onboarding, document upload, reviewer decisions, audit trail, client visibility, reports, and notification foundations. The remaining work is the final production completion track: staging deployment, self-serve provisioning polish, source-of-truth importers, document-intelligence review loops, and operations hardening."

Avoid calling it:

- Fully finished production system.
- Fully self-serve onboarding platform.
- Complete OCR/document-intelligence system.
- Fully migrated source-of-truth platform.

## 7. Immediate next batch

Recommended next engineering batch:

1. Review and split the dirty tree.
2. Commit the hardening/finalization scope.
3. Deploy staging.
4. Run the staging smoke script.
5. Continue V2.2 by retiring remaining legacy mock/adaptation shims and planning the provider JWT/RBAC replacement.
