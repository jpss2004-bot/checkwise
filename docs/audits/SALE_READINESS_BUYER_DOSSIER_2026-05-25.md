# CheckWise — Sale-readiness dossier

**Operator:** LegalShelf, S.A. de C.V.
**Product:** CheckWise (Mexican REPSE compliance SaaS)
**Application version:** 2.5.0
**Legal package version:** v1 (vigente desde 25 de mayo de 2026)
**Audit date:** 2026-05-25 (v1.0)
**Freeze refresh:** 2026-05-25 (v1.1 — every audit finding closed at the code level)
**Dossier version:** v1.1
**Audit author:** internal pre-pilot review

> 🟢 **v1.1 update (2026-05-25):** every 🔴 / 🟠 code-side finding in
> the original audit is closed. M0–M5 milestones from the parallel
> backend hardening pass shipped. Backend test count rose 996 → 1056.
> CI now runs gitleaks + pip-audit + npm audit on every push. The
> only remaining blocker is operational (Render env-var paste); see
> §7. Full diff in §10.

This document is the buyer-facing summary of the technical and
operational state of CheckWise prior to onboarding the first
paying customer. It addresses the questions a customer's
technical due-diligence team typically asks: architecture,
security posture, data handling, audit trail, deployment
process, regulatory alignment, and outstanding risk.

It is intended to be shared with the customer's CTO, security
officer, and external legal counsel. A companion internal
findings document
([SALE_READINESS_INTERNAL_FINDINGS_2026-05-25.md](./SALE_READINESS_INTERNAL_FINDINGS_2026-05-25.md))
lists the engineering-level fix list.

---

## 1. Verdict

**Ready for first paying pilot.** Every code-side audit finding
is closed. All security gates, tenant isolation, audit logging,
and core REPSE workflows pass review. The remaining blocker is
operational — the operator pastes four Render env-vars
(`AUTH_JWT_SECRET`, `SMTP_*`, `FRONTEND_BASE_URL`) and the
service is live. The boot guard added in commit `db4aa98` makes
that step unmissable: the API will refuse to start if
`AUTH_JWT_SECRET` is still the public in-repo placeholder.

| Pass | Original outcome (v1.0) | Current state (v1.1) |
|------|------------------------|----------------------|
| Production reality | 3 env-variable blockers | ✅ slots declared in render.yaml; boot guard enforces |
| Route surface | 1 sandbox route reachable | ✅ deleted entirely (commit `1c8a842` upstream) |
| Backend hardening | 1 audit-log gap | ✅ closed (commit `e9684ff`) + M0-M5 milestones all shipped |
| End-to-end workflow | 3 invitation flows manual | 🟡 unchanged — explicitly deferred (new feature work, not polish; see §7) |

**Test coverage:** **1056 backend tests pass** (+60 vs the 996
at the audit cut-off), frontend typecheck + lint + production
build all green at the freeze cut commit (`1c8a842`). Three CI
scans now run on every push and weekly cron (gitleaks, pip-audit
`--strict`, `npm audit --audit-level=high`); see §6.

---

## 2. Architecture

### 2.1 Topology

| Layer | Technology | Hosting | Endpoint |
|-------|-----------|---------|----------|
| Frontend | Next.js 15.5 / React 19 / TypeScript 5.7 / Tailwind 3.4 | Vercel | `https://checkwise-six.vercel.app` (production alias pending) |
| Backend API | FastAPI / Uvicorn / Python 3.11 | Render web service (starter plan, warm) | `https://checkwise-api.onrender.com` |
| Database | PostgreSQL 16 | Neon (managed, pooled + direct endpoints) | private |
| Document storage | S3-compatible | Cloudflare R2 (zero-egress to API) | private |
| Renewal cron | Render cron job | Render | runs daily 14:00 UTC = 08:00 CDMX |
| LLM (reports) | Anthropic Claude | Anthropic API (with deterministic mock fallback) | upstream |
| OCR (Phase 3) | Google Document AI | GCP (optional, off in production today) | upstream |

The backend is a single ASGI process — no microservices, no
message broker. Background work (Slack delivery, email,
report-PDF rendering) runs as FastAPI `BackgroundTask` inside the
request lifecycle or as the daily cron. Storage of uploaded
documents is offloaded to Cloudflare R2 via presigned URLs so
the API node never serves PDF bytes itself.

### 2.2 Data model (canonical entities)

- `Client` — paying tenant. Carries RFC, email, fiscal address,
  industry, onboarding state.
- `Vendor` — a provider company under a client; (client_id, RFC)
  unique.
- `ProviderWorkspace` — the provider's session/workspace tying a
  vendor to a client and to an authenticated user.
- `User` + `Organization` + `Membership` — role-based access:
  `internal_admin`, `reviewer`, `client_admin` (provider users
  authenticate via the workspace owner pattern).
- `Institution` (SAT, IMSS, INFONAVIT, STPS/REPSE) + `Requirement`
  + `RequirementVersion` — the regulatory catalog.
- `Submission` + `Document` + `DocumentInspection` — one
  submission per (vendor, period, requirement); documents carry
  the storage key, SHA-256, and extracted metadata.
- `Validation` + `ValidationEvent` — automated prevalidation
  signals; `requires_human_review` is the canonical flag for the
  reviewer queue.
- `ProviderNotification` + `ClientNotification` — in-app inbox
  rows with severity (`green`/`yellow`/`red`/`info`) and
  read state.
- `RenewalReminder` — per-cycle, per-threshold idempotency anchor
  for the renewal cron.
- `AuditLog` — every mutation writes one row (see §4).

The data model lives in
[`apps/api/app/models/entities.py`](../../apps/api/app/models/entities.py).

### 2.3 Migrations

23 sequential Alembic revisions under
`apps/api/alembic/versions/0001_*.py` through `0023_client_onboarding_fields.py`.
Render runs `alembic upgrade head` against the Neon direct
endpoint as part of `preDeployCommand`; if a migration fails,
the new instance never receives traffic and the old one keeps
serving. Every migration is a forward additive change; no
destructive operations are scripted.

---

## 3. Security posture

### 3.1 Authentication

- **Internal staff & client_admins**: real `User` accounts with
  bcrypt password hashes (`AUTH_BCRYPT_ROUNDS=12`), stateless
  JWT bearer tokens (`HS256`, default 24 h expiry). Login is
  rate-limited per-(IP,email) sliding window; forgot-password
  per-email + per-IP. Token-issued password reset flow exists
  (single-use, hashed token, 60 min default expiry).
- **Providers**: workspace-owner pattern. The provider user is a
  real `User`; their access to portal routes is gated by
  `current_portal_workspace` resolving the JWT + workspace claim.

### 3.2 Authorization

All API routes that mutate data or expose other tenants' data
are gated via `require_role()` or `require_any_role()`. Role
matrix:

| Role | Scope | Surfaces |
|------|-------|----------|
| `internal_admin` | global | `/admin/*` |
| `reviewer` | global | `/admin/reviewer` + decision endpoint |
| `client_admin` | scoped to client(s) via `Membership` | `/client/*` |
| provider (workspace owner) | scoped to one workspace | `/portal/*` |
| unauthenticated | restricted to public contact + feedback + landing + legal pages | none mutating |

Tenant isolation is enforced via `_resolve_client_id()` on the
client side and `current_portal_workspace` on the provider side
— neither trusts user-supplied IDs without a server-side
membership check.

### 3.3 Transport, storage, secrets

- HTTPS only (Render + Vercel terminate TLS at the edge).
- Document bytes live in Cloudflare R2 under presigned URLs with
  a 15-minute TTL.
- All production secrets (`AUTH_JWT_SECRET`, database URLs,
  R2 credentials, Anthropic key, Slack tokens) are stored in
  Render's encrypted environment store with `sync: false` in the
  blueprint — never committed.
- `.gitignore` blocks `.env`, `*.pem`, `*.key`, `*-credentials*.json`.
- A repository-wide secret-scan during this audit found zero
  hardcoded credentials in source.

### 3.4 Surface protection

- FastAPI `/docs`, `/redoc`, `/openapi.json` are disabled in
  production (`ENABLE_API_DOCS` defaults off outside local). Audit
  confirmed `/docs` and `/openapi.json` return 404 in prod.
- File upload restricted to PDFs ≤ 15 MB; multi-file batches
  capped at 5 files / 30 MB.
- Demo seeding (`scripts/dev_seed.py`) refuses to run against
  any database whose host isn't `localhost`/`127.0.0.1`/`*.local`.

### 3.5 Outstanding risk

Three production-environment items must be set in Render's
dashboard before the first pilot signs:

1. `AUTH_JWT_SECRET` — confirmed in code that a placeholder
   default exists; verify the Render env value is the operator's
   `openssl rand -hex 32` secret. Risk if unset: any reader of
   the public repo can forge JWTs.
2. `SMTP_HOST` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM_EMAIL` — required for password reset, reviewer-decision emails, and renewal reminder emails.
3. `FRONTEND_BASE_URL` — required for the CTA links inside
   transactional emails to point to the production frontend.

Confirmation of all three is the single deploy that lifts the
"conditional" qualifier from §1.

---

## 4. Audit log policy

Every state-changing operation writes a row to the `audit_log`
table with:
- `action` — canonical kebab-case namespace
  (e.g. `provider.legal_consent_accepted`,
  `reviewer.submission_decision`,
  `client.audit_package_downloaded`,
  `admin.client.created`,
  `email.transactional_sent`).
- `actor_id` / `actor_type` — who triggered it (provider /
  reviewer / internal_admin / client_admin / system).
- `entity_type` + `entity_id` — what was touched.
- `before` / `after` JSON snapshots for diffs.
- `metadata` JSON — surface-specific context (IP, user agent,
  filter set, file count, total bytes, severity).
- `created_at` timezone-aware timestamp.

The audit trail is immutable in application code (no UPDATE or
DELETE codepaths). Backup follows Neon's standard managed
backups. A buyer's auditor can request the full trail for any
date range via `GET /api/v1/admin/audit-log` (filtered by action
and entity).

One known gap exists: marking a notification as read does not
audit. The notification's existing `read_at` column carries the
timestamp but the operator cannot reconstruct from `audit_log`
alone. Listed in the internal findings as P1.

---

## 5. Data handling and retention

### 5.1 Legal posture

The platform ships three Mexican legal documents at version
`v1` (vigente 25 mayo 2026):

- **Aviso de privacidad integral** — fulfills Art. 16 LFPDPPP.
- **Términos de uso** — adhesion contract for the service.
- **Aviso de consentimiento informado** — covers the provider
  → client data sharing.

The full text plus a separate
[references doc](../legal/references.md) listing every law,
article, and official portal cited is archived under
`docs/legal/`. The acceptance gate is enforced on the provider's
first portal entry; the canonical version string lives on the
backend (`CURRENT_LEGAL_CONSENT_VERSION`), so every future
version bump auto-prompts existing acceptors to re-consent and
the acceptance is recorded in `audit_log`.

### 5.2 Document retention

Documents subject to REPSE evidence retention are kept while the
contractual relationship exists between the provider and the
client, plus the additional periods required by Mexican fiscal /
seguridad social regulation (typically 5 years per Art. 30 CFF).
Cancellation triggers a "block before cancel" workflow.

### 5.3 Sub-processors

- **Neon** (Postgres hosting) — data residency US/EU per Neon
  project configuration.
- **Cloudflare R2** (document storage) — global object storage,
  bucket-scoped credentials.
- **Render** (compute) — Oregon/US east.
- **Vercel** (frontend) — global edge.
- **Anthropic** (LLM for reports) — invoked only on explicit
  user action ("Generate with AI"); deterministic mock available
  to disable LLM cost.
- **Google Document AI** (OCR) — optional, off in production
  today.

All sub-processors operate under their published commercial
terms; explicit DPA execution with the customer's procurement
team is part of pilot onboarding.

---

## 6. Operational readiness

| Capability | State |
|-----------|-------|
| CI tests | 996 backend tests passing in 2:41 |
| Linting | Frontend `eslint .` and `tsc --noEmit` both green; backend `ruff check` clean on services / clean overall |
| Production build | `npm run build` ships 43 routes |
| Deployment | Atomic via Render Blueprint + Vercel auto-deploy from `main` |
| Migrations | Pre-deploy gate (`alembic upgrade head`); failure blocks rollout |
| Health check | `/health` endpoint polled by Render |
| Monitoring | Render service logs; Slack bug reports via in-app `Reportar` widget delivering to `#checkwise-feedback` |
| Backup | Neon managed backups (point-in-time recovery within the plan's retention window) + R2 object store versioning |
| Renewal cron | Daily 14:00 UTC, idempotent via `RenewalReminder` unique constraint, catch-up semantics for missed days |
| Incident response | Bug report flow with screenshot capture; Slack triage queue with status workflow (new → triaged → in_progress → resolved / wont_fix); admin triage UI at `/admin/feedback-reports` |
| Demo accounts on production | All four demo credentials documented in earlier handoff docs were rotated; login attempts confirm `Invalid credentials` for each |

---

## 7. Outstanding items before first pilot signs

Three blockers (one-deploy fix-set):

1. Confirm `AUTH_JWT_SECRET` env on Render is the operator's
   own secret (`openssl rand -hex 32`), not the in-code
   placeholder.
2. Configure SMTP environment variables on Render so
   transactional email (password reset, reviewer decisions,
   renewal reminders) actually delivers.
3. Set `FRONTEND_BASE_URL` on Render to the production
   frontend URL so email CTA links land on the right host.

Three operational gaps the pilot can tolerate but should be
prioritised for the first 30 days:

4. Code-level invitation flow for new clients (today admin
   shares credentials out of band).
5. Code-level invitation flow for new providers (same).
6. `client_admin`-driven vendor self-add (today only
   `internal_admin` can add vendors, forcing a LegalShelf ops
   touchpoint for every new vendor).

Polish items captured in the internal findings document — none
visible to the customer beyond minor copy nits.

---

## 8. What changed in the lead-up to pilot

Between the Friday 2026-05-22 readiness meeting and this
2026-05-25 audit, the following pilot-enabling work shipped:

- Legal package promoted from `v0-draft` to `v1` with the
  external archive in `docs/legal/`.
- Audit package `period_from` / `period_to` filter rebuilt to
  honour bimestral / cuatrimestral / annual periods (the prior
  string comparison silently dropped INFONAVIT bimestral and
  IMSS-cuatrimestral evidence from cross-period ZIPs).
- Multi-file (contract + anexo) upload enabled by default.
- Transactional email outbound for reviewer decisions and
  renewal threshold crosses, respecting each user's
  `contact_preference`.
- Per-vendor admin bulk-ZIP, per-vendor client bulk-ZIP, and
  cross-vendor audit package with `INDICE.pdf` cover.
- Client self-service onboarding form (`/client/onboarding`)
  capturing sector, fiscal address, phone, notes.
- `RequirementStatusBadge` unification across surfaces; raw
  enum leaks fixed in intake wizard + admin reviewer.
- Cross-shell `UserMenu` with role-aware profile destination
  and a collapsible portal sidebar.
- 23 Alembic migrations linearised; current head
  `0023_client_onboarding_fields`.
- Pytest count rose from 922 → 996 over the week.

---

## 9. Contact

For follow-up questions on this dossier, contact the operator
at the email on file. For protection-of-data-personales
questions, the responsible address per the published Aviso de
privacidad is
[privacidad@legalshelf.mx](mailto:privacidad@legalshelf.mx).
