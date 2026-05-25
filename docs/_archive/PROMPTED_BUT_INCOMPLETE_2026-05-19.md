# Prompted-but-Incomplete Features

> **Date:** 2026-05-19
> **Question this answers:** *What does CheckWise visibly promise the user that doesn't actually fully work end-to-end on production today?*
> **Confidence:** Every item below is backed by either a code reference (file:line) or a `TODO[backend-integration]` / `TODO[security-backend]` marker the codebase itself ships.
> **Method:** UI promise sweep (Explore agent) + TODO/FIXME/legacy/deprecated grep across `backend/app` + `frontend/{app,components,lib}` + cross-reference with `docs/ROADMAP.md`, `docs/REPORTS_ARCHITECTURE.md` §21, `docs/CHECKWISE_1_6.md`, `docs/CHECKWISE_2_0.md`, `docs/system-workflow-map/README.md`.

---

## Reading guide

Each finding is tagged with a **tier**:

- **🔴 P0 — affects Jorge's test session today.** Will visibly mislead him or break a primary flow.
- **🟡 P1 — affects production launch.** Works for a single supervised tester; not safe to expose to multiple unsupervised users.
- **🟢 P2 — scale / polish / roadmap.** Documented in the roadmap. Not pretending to work yet.

Within each tier, sorted by impact.

---

## 🔴 P0 — Will visibly affect Jorge's test today

### P0-1 · The `/portal/entra-a-tu-espacio` confirmation form persists to localStorage only

**What Jorge sees:** After login, he lands on a confirmation screen showing his workspace identity (LegalShelf - CheckwiseDEMO, RFC SNM070412PT7) and a form asking him to confirm name / phone / job title / contact preference. He fills it in, clicks **"Entrar a mi espacio"**, sees a loading state, then routes to his dashboard.

**What actually happens:** [`app/portal/entra-a-tu-espacio/page.tsx:82`](apps/web/app/portal/entra-a-tu-espacio/page.tsx) calls `saveEditableProfile(workspace_id, profile)` from `lib/mock/corrections.ts` — a mock helper that awaits 300ms and writes the data to `localStorage['checkwise.mock.profile.{workspace_id}.v1']`. **No POST to the backend.** When his browser session ends, the data is gone. If you ever inspect Postgres for that profile data, it will not be there.

**Why it slipped:** `TODO[backend-integration]` in [`lib/mock/corrections.ts:12`](apps/web/lib/mock/corrections.ts) and [`lib/workspace/resolver.ts:13`](apps/web/lib/workspace/resolver.ts). Documented in [CHECKWISE_1_6.md:158](docs/CHECKWISE_1_6.md).

**Mitigation for the test:** brief Jorge that this confirmation step is informational; the persistent record of him is the User + ProviderWorkspace row you created in Neon (which IS real and correct). Tell him "what you type in the confirmation form is for our records during the test session; we'll capture it manually."

---

### P0-2 · Workspace Identity Card displays client-synthesized data, not backend-fetched

**What Jorge sees:** On the same workspace-entry screen, locked tenant fields (workspace_id, RFC, role, company legal name, email domain) appear in a "Verifica tus datos protegidos" card.

**What actually happens:** [`lib/workspace/resolver.ts:44-80`](apps/web/lib/workspace/resolver.ts) (`buildWorkspaceContext`) synthesizes those values from the in-memory PortalSession + the optional invitation token. The comment at line 38-39 calls it an *"interim hack"*. The values *happen to be correct* for Jorge because they match the DB row you created — but the security claim ("backend is source of truth for protected fields") is not actually enforced by this render path.

**Why it slipped:** Two `TODO[security-backend]` markers ([`lib/workspace/types.ts:26`](apps/web/lib/workspace/types.ts), [`app/portal/entra-a-tu-espacio/page.tsx:52`](apps/web/app/portal/entra-a-tu-espacio/page.tsx)) — both flagging that backend must re-verify every value at render time.

**Tester impact:** Looks fine for this test (values match DB). The risk is "what looks like a verified server-render is actually a client-side echo of the session token." A clever tester poking the network tab will notice.

---

### P0-3 · Contact form on the public landing goes nowhere

**What anyone sees:** Visit `https://checkwise-six.vercel.app/` → scroll to "Solicitar información" → fill name, company, email, role, message → submit → success message with folio ID like `req-mock-7f2k...`.

**What actually happens:** [`components/marketing/contact-form.tsx:51-68`](apps/web/components/marketing/contact-form.tsx) calls `submitContactRequest()` from [`lib/mock/contact-requests.ts`](apps/web/lib/mock/contact-requests.ts) — local stub that returns a fake ID. **No CRM, no Slack, no email, no DB row.** If anyone other than Jorge visits the prod URL and submits, that request is lost.

**Why it slipped:** `TODO[backend-integration]: replace with a POST to a real endpoint` in [`lib/mock/contact-requests.ts:9`](apps/web/lib/mock/contact-requests.ts).

**Mitigation:** If you're showing the landing page to anyone, tell them "the contact form on production is currently a demo — to actually reach us, write to [email]." Or land a quick `POST /api/v1/contact` endpoint that drops into a Slack webhook before exposing the URL to anyone but Jorge.

---

### P0-4 · `/portal/onboarding` requirement cards show real status + mocked educational copy mixed together

**What Jorge sees:** Onboarding checklist with cards per required document. Each card has: requirement title, why-this-matters paragraph, accepted format hint, next-action CTA, and reviewer note (when rejected).

**What actually happens:** [`lib/api/portal-adapters.ts:74-92`](apps/web/lib/api/portal-adapters.ts) — the *status* (aprobado / rechazado / pendiente / etc.) comes from the real backend at `/api/v1/portal/workspaces/{id}/onboarding`. The *educational copy* (`why`, `format`, `next_action`, `reviewer_note`) comes from a frontend dictionary `ENRICHMENT_BY_CODE` keyed by requirement_code. If the backend ever adds a requirement code the frontend doesn't recognize, the card falls back to generic copy.

**Why it slipped:** `TODO[backend-integration]` at [`lib/api/portal-adapters.ts:11`](apps/web/lib/api/portal-adapters.ts). The backend is supposed to grow these fields; until then the adapter bridges.

**Tester impact:** subtle — the page looks complete. But two requirements with the same status get identical copy from the dictionary, and a real reviewer note (which doesn't exist server-side yet) cannot be passed through.

---

### P0-5 · No password reset / "forgot password" flow

**What Jorge sees:** Login page. If he forgets the password you sent him, there's no "¿Olvidaste tu contraseña?" link.

**What actually happens:** Doesn't exist. The auth backend exposes only `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, `POST /api/v1/auth/set-password` ([`apps/api/app/api/v1/auth.py:247-304`](apps/api/app/api/v1/auth.py)). The third only works when the user is already authenticated with the must-change-password JWT.

**Mitigation:** if Jorge gets locked out, you (operator) regenerate his bcrypt hash locally and run an `UPDATE users SET password_hash=..., must_change_password=true WHERE email=...` in Neon. Same workflow as the initial account creation.

---

## 🟡 P1 — Works for one tester, blocks broader launch

### P1-1 · `/activate?token=...` flow is fully demo-mocked

**What it looks like:** A welcome-email-style invitation flow where a new vendor clicks a link, lands at `/activate?token=...`, sees a 3-step wizard, sets a password, lands in the portal.

**What actually happens:** [`lib/mock/invitations.ts`](apps/web/lib/mock/invitations.ts) — tokens are issued, verified, and consumed entirely in `localStorage['checkwise.mock.invitations.v1']`. There is no `Invitation` table, no token signing service, no `POST /api/v1/invitations` endpoint, no email transport. The only token that resolves is the literal string `"demo"`, hardcoded in the mock module.

**`writePortalSession` shim:** [`lib/session/portal.ts:125-132`](apps/web/lib/session/portal.ts) populates an in-memory cache when the mocked activation completes. A page reload bounces the user back to `/`. Console-warns at runtime: *"writePortalSession is a transition shim; the real session is the httpOnly cookie minted by POST /api/v1/portal/enter."*

**Why Jorge is unaffected:** he never enters this code path. He logs in at `/login` with the manually-created credentials, which uses the REAL `POST /api/v1/auth/login` and a real JWT.

**To launch beyond Jorge:** build `POST /api/v1/invitations` (admin issues a token), `GET /api/v1/invitations/{token}` (validate), `POST /api/v1/invitations/{token}/consume` (set password + return session), plus email transport. Documented in [CHECKWISE_1_5.md:95](docs/CHECKWISE_1_5.md).

---

### P1-2 · No welcome / activation / notification email transport

**What's shipped:** [`apps/web/lib/email/welcome.ts`](apps/web/lib/email/welcome.ts) — a templating module that produces the HTML + plaintext bodies. It is rendering-only; no provider wired.

**What's NOT shipped:** the SMTP / Resend / Postmark / SES adapter, the queue, the backend endpoint that triggers it, the unsubscribe handler. `TODO[backend-integration]` at line 14.

**Tester impact today:** you hand-deliver Jorge's credentials out-of-band (Signal / WhatsApp / in-person). Fine for one user. Doesn't scale.

---

### P1-3 · `POST /api/v1/submissions` is the legacy intake path; `POST /api/v1/portal/workspaces/{id}/submissions` is canonical

**What's marked deprecated:** [`apps/api/app/api/v1/endpoints.py:84-85`](apps/api/app/api/v1/endpoints.py) — `deprecated=True`, summary literally says "Legacy native-intake submission (deprecated)". Comment at [`portal.py:1436`](apps/api/app/api/v1/portal.py): *"Tenant-safe replacement for the legacy `POST /api/v1/submissions`."*

**What still calls the deprecated endpoint:** [`components/checkwise/document-submission-form.tsx`](apps/web/components/checkwise/document-submission-form.tsx). However, this component is in our confirmed-orphan list (no consumers), so the deprecated endpoint shouldn't be hit in the live flow.

**What Jorge actually hits:** the canonical workspace-scoped endpoint (via the `intake-wizard.tsx` at `/portal/upload`).

**Risk:** if a stray code path still hits the legacy endpoint, it won't enforce tenant isolation as strictly. Removing the legacy endpoint + the orphan form together is the cleanup.

---

### P1-4 · Provider portal still authenticates with the V1.2 opaque `X-Workspace-Token`

**What's shipped:** [`apps/api/app/api/v1/portal.py:24`](apps/api/app/api/v1/portal.py): *"The legacy `X-Workspace-Token` header is still accepted by reads as a fallback for callers that haven't migrated yet."* The dual-path is documented and is intentional during the V1.x → V2.2 migration window.

**What's NOT shipped:** the unified provider-JWT migration. Provider portal still uses the opaque token model from V1.2; staff users (admin/reviewer/client_admin) use the JWT/RBAC model from V1.3. Two auth strategies coexist.

**Tester impact today:** invisible. Both paths work, both enforce tenant isolation.

**Roadmap:** V2.2 mock→real wiring ([ROADMAP.md:151](docs/ROADMAP.md)) is the rip-the-bandaid task.

---

### P1-5 · `ReportShare` + `ReportExport` exist as DB models with no service layer

**What's promised by the schema:** [`apps/api/app/models/entities.py:606-645`](apps/api/app/models/entities.py) defines `ReportShare` (signed delivery to external vendors) and `ReportExport` (async PDF / DOCX render workers).

**What's NOT shipped:**
- No router endpoint to create / consume share links.
- No worker to render exports asynchronously.
- Schemas marked *"placeholder schemas"* at [`apps/api/app/schemas/reports.py:142`](apps/api/app/schemas/reports.py).

**What Jorge gets instead:** browser print-to-PDF via `window.print()` from the `/portal/reports/[id]/print` route. Works, just not server-side.

**Roadmap:** [REPORTS_ARCHITECTURE.md §21 deferred](docs/REPORTS_ARCHITECTURE.md) — "server-rendered DOCX/PDF, signed-link sharing, autosave, Inspector panel".

---

### P1-6 · No client/admin endpoint to re-download original uploaded PDFs

**What's missing:** [`docs/system-workflow-map/README.md`](docs/system-workflow-map/README.md) explicitly calls out: *"No existe endpoint final de descarga segura de documentos para cliente/admin."* `S3StorageService` has `presigned_download_url()` ([`storage.py:213`](apps/api/app/services/storage.py)) but no router exposes it.

**Tester impact:** Jorge uploads a PDF, sees its status, but cannot re-download it through the UI. If he asks "where did my file go?" the answer is "the system has it, you just can't see it from here yet."

---

### P1-7 · `astream_text` for the Anthropic client raises `NotImplementedError`

**What's promised by the LLM client protocol:** async streaming for concurrent per-block generation, used by the copilot in 3.3c.

**What actually happens:** [`apps/api/app/services/reports/llm/anthropic_client.py:134-149`](apps/api/app/services/reports/llm/anthropic_client.py) — `astream_text` raises NotImplementedError with the message *"Async streaming arrives in Phase 3.3c when the copilot needs concurrent per-block streams."*

**Tester impact:** none today — the copilot uses `stream_text` (sync) under the hood. The dead branch only matters if someone wires a parallel-streams path.

---

### P1-8 · Block Inspector for editing per-block config doesn't ship

**What the UI hints at:** in [`kpi-strip.tsx:140`](apps/web/components/checkwise/reports/blocks/kpi-strip.tsx) the editor footer says *"4 métricas. Configurable desde el inspector."* and there's a "Cambiar formato" button that cycles the first metric's format as a placeholder. Several other blocks have similar copy.

**What's NOT shipped:** the right-rail Inspector panel where authors configure block parameters (deferred to 3.5 per the same file's comment).

**Tester impact:** Jorge can use blocks as the AI configures them. Editing them feels arbitrary — there's a token "Cambiar formato" demo button but no real config editor.

---

### P1-9 · `provider-missing-documents` and `provider-recent-rejections` presets render mostly empty data on a fresh workspace

**What Jorge sees if he picks them:** the report generates without errors, blocks render — but `attention_list`, filtered to states `missing/in_review/uploaded`, returns 0 rows because Jorge's workspace has zero submissions. Same with `provider-recent-rejections` — no rejected documents exist.

**Why:** the preset prompts are designed for an established workspace with history. A fresh workspace produces accurate-but-empty output.

**Mitigation:** brief Jorge to start with **`provider-current-state`** ("Mi estado de cumplimiento") which always produces signal even on day-1. Documented in [PROVIDER_REPORTS_AI_AUDIT_2026-05-19.md §4](docs/PROVIDER_REPORTS_AI_AUDIT_2026-05-19.md).

---

### P1-10 · Sentry / observability / log export are placeholders in `.env.example`

**What's listed:** [`.env.example`](.env.example) carries `SENTRY_DSN` and `LOG_LEVEL` under `# ── Observability (planned) ──`.

**What's wired:** nothing. No error reporting, no log aggregation, no metric export.

**Tester impact:** if something breaks during Jorge's test, the operator (you) is the error-reporting system. Open the Render logs tab in real time.

---

## 🟢 P2 — Roadmap, not pretending to work yet

These are documented as deferred in [docs/ROADMAP.md](docs/ROADMAP.md) and [docs/REPORTS_ARCHITECTURE.md §21](docs/REPORTS_ARCHITECTURE.md). No UI surface promises them.

- **8 additional block types** (beyond the 10 wired today) — REPORTS_ARCHITECTURE §21
- **Server-rendered PDF / DOCX exports** — see P1-5
- **Signed-link sharing for external vendors** — see P1-5 + REPORTS_ARCHITECTURE §21
- **Autosave** — currently every edit is manual save via the "Guardar" button; autosave deferred
- **Inspector panel** — see P1-8
- **JotForm / Google Sheets importers** — ROADMAP V2.3
- **OCR + structured extraction** — ROADMAP V2.4
- **Background jobs (Redis + RQ / Celery)** — ROADMAP V2.4; required for OCR + dedup + alerts
- **Notifications: vendor alerts, reviewer alerts, scheduled Slack/WhatsApp/email digests** — ROADMAP V2.5
- **Multi-region / load balancing / horizontal scale** — not in the current roadmap
- **2FA / SSO / SCIM** — basic email/password only today
- **Audit-log UI consumer surface** — `audit_log` table exists, `/admin/audit-log` page exists and reads from a real endpoint, but the consumer-grade UI (filters, exports, retention controls) is minimal

---

## 9 confirmed orphan frontend files (V2.0/V2.1 leftovers)

Already documented in [AUDIT_NEXT_SESSION_READINESS.md §5.4](docs/AUDIT_NEXT_SESSION_READINESS.md). Reproduced for completeness:

- `apps/web/components/ui/stepper.tsx`
- `apps/web/components/checkwise/support-card.tsx`
- `apps/web/components/checkwise/confidence-badge.tsx`
- `apps/web/components/checkwise/portal/provider-context-bar.tsx` (superseded by PortalAppShell sidebar)
- `apps/web/components/checkwise/portal/suggested-actions.tsx`
- `apps/web/components/checkwise/workspace/correction-request-form.tsx`
- `apps/web/components/checkwise/document-submission-form.tsx`
- `apps/web/lib/demo-clients.ts`
- `apps/web/lib/portal-client.ts`

Each verified via symbol grep across `app/`, `components/`, `lib/`. Safe to delete in one commit; recommended for the cleanup PR after Jorge's test.

---

## Mitigations for Jorge's test today

In order of impact:

1. **Brief him explicitly about P0-1 + P0-2.** "The confirmation page after login is informational only for now; the real account record is in our database and is correct. Just click through it."
2. **Steer him to `provider-current-state` as the first preset** (P1-9). The other two will look empty.
3. **Tell him there's no password recovery** (P0-5). If he gets locked out, ping you and you'll reset.
4. **Watch the Render logs in another tab** during the test (P1-10). If anything explodes, you'll see it before he does.
5. **Don't share the landing-page URL with anyone other than Jorge** until P0-3 is fixed.

---

## Recommended fix order after the test

(Ranked by impact-per-hour-of-work)

1. **P0-3 (contact form → real backend)** — half-day. Either land `POST /api/v1/contact` with a Slack webhook, or replace the form with a `mailto:`. Visible to anyone hitting prod.
2. **P0-1 (entra-a-tu-espacio profile persistence)** — 1 day. Add a real `PATCH /api/v1/portal/workspaces/{id}/profile` endpoint, drop `saveEditableProfile` from mock.
3. **P1-1 (real invitation flow)** — 2-3 days. Backend table + endpoints + email transport (pairs with P1-2). Unblocks adding new testers without you running SQL each time.
4. **P0-5 (password reset)** — 1 day. Token-based reset email + endpoint. Unblocks scale.
5. **P1-6 (document re-download)** — half day. Already have `presigned_download_url()`; just expose it through a router with the right tenant guard.
6. **P1-5 (server-rendered PDF)** — 2-3 days if you want real PDF (e.g. Playwright / Puppeteer). Skip if browser-print is acceptable.
7. **Orphan cleanup** — 30 min. Stand-alone PR.
8. **P0-2 / P0-4 (backend-source-of-truth + onboarding enrichment)** — 1 day. The `portal-adapters.ts` mock-bridge dies.

---

## How to verify nothing else slipped

```sh
# Frontend TODO sweep
grep -rIn "TODO\[backend-integration\]\|TODO\[security-backend\]" frontend/{app,components,lib} --include='*.ts' --include='*.tsx'

# Backend legacy / deprecated / NotImplemented sweep
grep -rIn "deprecated=True\|legacy\|NotImplementedError\|TODO\|FIXME" backend/app --include='*.py' | grep -v __pycache__

# Confirm no new mock-data consumers slipped in
grep -rIn "from.*lib/mock" frontend/{app,components} --include='*.ts' --include='*.tsx'
```

All three commands should produce a stable result set tomorrow. Anything new = new debt.
