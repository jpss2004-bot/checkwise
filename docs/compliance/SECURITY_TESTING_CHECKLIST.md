---
Document: Security Testing Checklist
ID: CW-ISO-sec-testing-checklist
Owner: Lead Engineer / acting CISO (Jose Pablo Samano)
Version: 0.1 (draft)
Effective: 2026-06-16
Review cadence: annual + on material change
ISO refs: ISO/IEC 27002:2022 8.29 (security testing in development & acceptance)
Status: DRAFT — ISO-readiness evidence, NOT a certification claim
---

> A reusable pre-release / periodic security-testing instrument for CheckWise. Engineering-governance evidence for an ISO/IEC 27001 readiness effort — **not** a certification claim. Run before a security-relevant release and on a periodic cadence (target: quarterly). Each item is a checkable assertion with a how-to-verify. Mark `[x]` when verified for the release under test; leave `[ ]` and note the gap otherwise.

**How to use:** copy this checklist into the release ticket / audit handoff, fill the boxes, and attach evidence (test run output, screenshots of headers, Security-tab state). Items marked **⚠ TO VERIFY** are not yet automated — verify manually and record the result.

---

## 1. Authentication

- [ ] **Passwords are bcrypt-hashed, never stored or logged in plaintext.** Verify: inspect `app/services/auth.py` `hash_password`; confirm no password value appears in logs/audit rows.
- [ ] **Composition + breached-password denylist enforced.** Verify: `pytest -q -k common_password` (`tests/test_iso_hardening.py::TestCommonPasswordDenylist`); `_enforce_password_rules` rejects denylisted-but-well-formed passwords.
- [ ] **Account lockout after repeated failures.** Verify: 5 failed logins → `429`; cleared on success / password reset / reactivate. Backed by migration `0045_user_account_lockout` (`AUTH_LOCKOUT_THRESHOLD=5`, `AUTH_LOCKOUT_MINUTES=15`).
- [ ] **JWT secret is real in production (boot guard).** Verify: the in-code placeholder cannot boot a non-local environment — `_validate_boot_security` in `app/core/config.py` aborts. Confirm production `AUTH_JWT_SECRET` is a fresh 32+ char value.
- [ ] **Session token transport is hardening to httpOnly cookie.** Verify: `AUTH_SESSION_COOKIE_NAME="checkwise_session"`, `Secure`+`SameSite` set; logout clears it (`tests/test_iso_hardening.py::TestLogoutAudit`). **⚠ TO VERIFY** — frontend cutover from `localStorage` to cookie is staged, not yet fully deployed (`_handoff/hardening-batch-2026-06-15.md`).
- [ ] **Logout writes an audit row.** Verify: `POST /api/v1/auth/logout` → `204` and one `auth.logout` `AuditLog` row with the actor id (`TestLogoutAudit`).

## 2. Authorization & tenant isolation (IDOR)

- [ ] **RBAC enforced on every privileged endpoint.** Verify: routes use `require_role` / `require_any_role` (`app/api/v1/auth.py`); a `client_admin` cannot reach `internal_admin`/`platform_admin` routes.
- [ ] **Object-level scoping: cross-tenant reads return 404 (no enumeration).** Verify: `pytest -q tests/test_cross_tenant_reports_shares_exports.py` — 16 report/version/AI/export/share/preset endpoints + 2 audit-package probes all reject org-B-vs-org-A with `404` (or `403` on the `_resolve_client_id` audit-package gate). A `200` here is a real leak.
- [ ] **Client-supplied tenant identifiers are re-resolved, never trusted.** Verify: endpoints taking `client_id`/`organization_id` route through `_actor_from` / `_resolve_client_id` rather than using the parameter directly.
- [ ] **`platform_admin` cannot self-escalate.** Verify: regression for audit finding `ADMIN-1` (self-escalation fixed; see `_handoff/audit-security-perf-2026-06-15.md`).
- [ ] **Report shares/exports cannot be accessed across tenants.** Verify: `DELETE /reports/shares/{id}` and `GET /reports/exports/{id}` 404 cross-tenant (covered in the cross-tenant suite).

## 3. Input validation & file upload

- [ ] **All request bodies are validated Pydantic models.** Verify: no router reads raw unvalidated JSON; malformed payloads return `422`.
- [ ] **Upload type + magic-byte gate.** Verify: a non-PDF (or a `.pdf` without the `%PDF-` signature) is rejected with "El archivo no es un PDF válido…" — `submission_service.py` checks `application/pdf` **and** the `%PDF-` head.
- [ ] **Upload size is bounded and recorded.** Verify: `size_bytes` is captured and a zero-byte file fails the intake check (`submission_service.py`). **⚠ TO VERIFY** — confirm an explicit max-size limit is enforced at the edge (not just recorded).
- [ ] **Content-addressed storage delete is refcount-guarded.** Verify: `pytest -q -k Refcount` (`tests/test_iso_hardening.py::TestStorageRefcountGuard`) — a cancel/rollback never deletes an object another tenant still references; a true orphan is deleted once.
- [ ] **No injection via uploaded-document parsing.** Verify: PDF/OCR/QR extraction failures degrade gracefully (route to `pendiente_revision`) rather than executing or crashing; CodeQL flags unsafe deserialization/path-traversal.

## 4. API edge — headers, CORS, CSRF, rate-limit

- [ ] **Security headers on every API response.** Verify: `pytest -q -k SecurityHeaders` (`tests/test_iso_hardening.py`) — `Content-Security-Policy` contains `frame-ancestors 'none'` + `base-uri 'none'`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`. Plus `Referrer-Policy`, `Permissions-Policy`, and HSTS in production (`app/main.py`).
- [ ] **Frontend CSP present.** Verify: `next.config.ts` emits the enforced header set + CSP. **⚠ TO VERIFY** — frontend CSP is currently **report-only**; tighten `script-src` (drop `'unsafe-inline'` via nonce) and switch to enforcing before claiming full coverage (`_handoff/hardening-batch-2026-06-15.md`).
- [ ] **CORS reflects only exact-match allowlisted origins.** Verify: `CORSMiddleware` `allow_origins=allowed_origins` (from `CORS_ORIGINS` + `FRONTEND_BASE_URL`), `allow_credentials=True`; a non-allowlisted Origin gets no `Access-Control-Allow-Origin` (`app/main.py`).
- [ ] **CSRF guard on cookie-authenticated mutations.** Verify: `_enforce_cookie_csrf` (auth) and `enforce_portal_csrf` (portal) enforce an Origin/Referer allowlist and fail closed in production; a forged cross-origin mutation is `403`.
- [ ] **Rate limiting on sensitive endpoints.** Verify: `app/core/rate_limit.py` (Redis-backed sliding window when `REDIS_URL` set, in-memory otherwise) is applied to auth/portal/admin/shares routes. **⚠ TO VERIFY** — confirm the limiter is wired to login and share-mint specifically and behaves under the production Redis config.

## 5. Secrets

- [ ] **No secret committed to the repo.** Verify: gitleaks job green (`security.yml`); only the local-dev JWT placeholder + test fixtures are allowlisted (`.gitleaks.toml`).
- [ ] **Production secrets are `sync: false` env vars.** Verify: `render.yaml` — DB URLs, R2 creds, `AUTH_JWT_SECRET`, SMTP, Twilio/WhatsApp, Anthropic, Slack are all `sync: false`; none hard-coded.
- [ ] **No secret value appears in logs / audit rows / error responses.** Verify: delivery rows record *status* (`smtp_not_configured`, `slack_delivery_status="skipped"`), never credentials.

## 6. Dependencies

- [ ] **No high/critical CVE in Python deps.** Verify: pip-audit job green (`--strict --local`, `security.yml`).
- [ ] **No high/critical CVE in Node deps.** Verify: npm audit job green (`--audit-level=high`).
- [ ] **Backend install is reproducible.** Verify: `requirements.lock` present and used by Render (`pip install -e . -c requirements.lock`); known-CVE transitive floors pinned in `pyproject.toml` (`idna`, `starlette`, `aiohttp`).
- [ ] **Dependabot PRs are current.** Verify: `.github/dependabot.yml` active; no stale open security-labelled dependency PR past its SLA (`SECURE_SDLC.md` §5).

## 7. Logging & audit

- [ ] **Security-relevant events are audited.** Verify: auth events (incl. `auth.logout`), report-share disclosures, and submission state transitions write `AuditLog` rows via `services/audit_log.add_audit_event`.
- [ ] **Audit rows capture actor + IP.** Verify: actor id present (`TestLogoutAudit`); IP/UA columns populated (audit findings `INFRA` / platform-rework migrations 0043 / client_users IP).
- [ ] **Decisions aren't hidden in UI-only state.** Verify: state transitions go through the service layer, not just frontend state (`CONTRIBUTING.md`).

## 8. Infrastructure & deploy

- [ ] **DB connection uses TLS in production.** Verify: `pytest -q -k DbTls` (`tests/test_iso_hardening.py::TestDbTlsEnforcement`) — non-local URLs get `sslmode=require`; boot guard rejects `sslmode=disable|allow|prefer` on a non-local deploy.
- [ ] **Objects encrypted at rest.** Verify: `pytest -q -k Encryption` (`TestObjectEncryptionAtRest`) — `put_object` sends `ServerSideEncryption=AES256`.
- [ ] **Migrations run safely on deploy.** Verify: `render.yaml` `preDeployCommand: alembic upgrade head` runs before traffic shift; `CONCURRENTLY` indexes use an autocommit block (`0046`); a **Neon snapshot was taken before the migration deploy** (`CHANGE_MANAGEMENT.md` §4).
- [ ] **Health-gated rollout.** Verify: `/health` is the `healthCheckPath`; a failed migration leaves the old instance serving.
- [ ] **DB statement timeout configured.** **⚠ TO VERIFY — NOT yet implemented.** A server-side `statement_timeout` is noted as still worth adding (`app/db/session.py` PERF-9 note). **Recommend:** add a bounded `statement_timeout` to cap runaway queries.

---

## 9. Automated coverage that already exists

| Coverage | Where | Runs |
|----------|-------|------|
| Cross-tenant / IDOR negative tests (reports, versions, AI surface, exports, shares, presets, audit-package) | `apps/api/tests/test_cross_tenant_reports_shares_exports.py` | `pytest` in CI on every PR |
| ISO-hardening regressions (password denylist, DB TLS, SSE-at-rest, storage refcount guard, CSP/security headers, logout audit) | `apps/api/tests/test_iso_hardening.py` | `pytest` in CI on every PR |
| Lint + full backend test suite | `ruff` + `pytest` | CI `backend` job (`.github/workflows/ci.yml`) |
| Type-check + lint + build (frontend) | `tsc` + `eslint` + `next build` | CI `frontend` job |
| Secret scanning | gitleaks | `.github/workflows/security.yml` (PR + push + weekly cron) |
| Dependency CVEs | pip-audit + npm audit | `security.yml` (PR + push + weekly cron) |
| SAST (injection, path traversal, unsafe deserialization, hardcoded creds, SSRF) | CodeQL, Python + TS/JS | `.github/workflows/codeql.yml` (PR + push + weekly cron) |
| Automated dependency-update PRs | Dependabot | `.github/dependabot.yml` (weekly) |

## 10. Known gaps & recommended cadence

| Gap | Status | Recommendation |
|-----|--------|----------------|
| **DAST** (dynamic scanning of the running app) | **None today.** | Add an OWASP ZAP baseline scan against a staging deploy; target quarterly + before major releases. |
| **Penetration test** | **None performed.** Do **not** represent CheckWise as pen-tested. | Engage an external pentest at least annually and after any major architectural change; track findings to closure in `_handoff/`. |
| **Required-status-check enforcement** | CI/Security/CodeQL run but are **not** blocking merges (branch protection off). | Enable branch protection on `main` so these become required gates (`CHANGE_MANAGEMENT.md` §6). |
| **Staging environment for security E2E** | **None** (auth/CSRF/cookie flow verified via deliberate prod deploys). | Stand up a Render preview + Neon branch staging tier. |
| **Upload max-size enforcement** | **⚠ TO VERIFY** — size recorded; explicit edge cap unconfirmed. | Confirm/add a hard max upload size. |
| **DB `statement_timeout`** | **Not implemented** (PERF-9 note). | Add a bounded server-side timeout. |
| **Rate-limit wiring on login/share-mint** | **⚠ TO VERIFY** — limiter exists; per-endpoint application unconfirmed. | Verify and, if missing, apply to login + share-mint. |
| **Threat-model record per security PR** | **Informal.** | Adopt a short STRIDE-style note on CODEOWNERS-protected PRs (`SECURE_SDLC.md` §3.1). |
| **Patch-SLA tracking** | **Target only**, not measured. | Track time-to-patch against the SLA table (`SECURE_SDLC.md` §5). |
