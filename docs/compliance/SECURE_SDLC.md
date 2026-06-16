---
Document: Secure Software Development Lifecycle (SDLC)
ID: CW-ISO-secure-sdlc
Owner: Lead Engineer / acting CISO (Jose Pablo Samano)
Version: 0.1 (draft)
Effective: 2026-06-16
Review cadence: annual + on material change
ISO refs: ISO/IEC 27002:2022 8.25 (secure development lifecycle), 8.26 (application security requirements), 8.27 (secure system architecture & engineering principles), 8.28 (secure coding), 8.29 (security testing in development & acceptance), 8.30 (outsourced development), 8.8 (management of technical vulnerabilities)
Status: DRAFT — ISO-readiness evidence, NOT a certification claim
---

> Engineering-governance evidence for an ISO/IEC 27001 readiness effort. Describes how security is built into the CheckWise development lifecycle. **Not** a certification claim. Aspirational controls are flagged; unverified items are marked **⚠ TO VERIFY**.

## 1. Secure development principles (8.25, 8.27)

CheckWise is a multi-tenant REPSE-compliance SaaS holding sensitive labour-compliance documents for multiple client tenants. The architecture and process are built on these principles:

1. **Defence in depth.** Authentication, per-object authorization, CSRF protection, security headers, and content-addressed storage are independent layers; no single control is the only thing standing between tenants.
2. **Tenant isolation by default.** Every data-bearing endpoint scopes to the caller's organization/client. Cross-tenant access returns `404` (no enumeration), not `403`, on report/share/export surfaces.
3. **Fail closed.** Security guards abort rather than degrade: the API refuses to boot with a placeholder JWT secret or insecure DB TLS in production; CSRF guards reject in production when Origin/Referer is absent.
4. **Thin routers, logic in services.** Routers under `apps/api/app/api/v1/` parse/dispatch/respond; business logic and validation live in `apps/api/app/services/` (`CONTRIBUTING.md`). This keeps authz and validation centralised and testable.
5. **Single source of truth for domain values.** Status codes, roles, and institutions are enums mirrored backend↔frontend (`statuses.py` ↔ `statuses.ts`); no inline magic strings in conditionals.
6. **Secrets never in code.** All production secrets are injected via the platform (Render/Vercel) with `sync: false`; the repo is scanned for committed secrets on every push.
7. **Append-only, auditable state changes.** Migrations are append-only; meaningful state transitions write audit rows.

### 1.1 Architecture context (8.27)

| Layer | Technology | Security-relevant notes |
|-------|------------|-------------------------|
| Frontend | Next.js / TypeScript on Vercel | Security headers + CSP via `next.config.ts`; edge auth guard in `middleware.ts`. |
| Backend | FastAPI / Python 3.11 on Render | Single ASGI app; security-header middleware on every response (`app/main.py`); RBAC + tenant scoping in routers/services. |
| Database | Postgres on Neon | Runtime via pooled endpoint; Alembic via direct endpoint. TLS (`sslmode=require`) enforced for non-local. |
| Object storage | Cloudflare R2 (S3-compatible) | Content-addressed keys (sha256); server-side encryption (`AES256`) on writes; refcount guard before delete. |
| Source / CI | GitHub `jpss2004-bot/checkwise` | CI + Security + CodeQL workflows; CODEOWNERS; Dependabot. |

## 2. Application security requirements (8.26)

Security requirements are captured as code controls and as the periodic-audit backlog (`_handoff/audit-*.md`). Baseline requirements every change must respect:

- **AuthN:** password-based login issuing a JWT; bcrypt password hashing; account lockout after repeated failures (migration `0045_user_account_lockout`: `AUTH_LOCKOUT_THRESHOLD=5`, `AUTH_LOCKOUT_MINUTES=15`, `429` on locked login, cleared on success/reset).
- **Password policy:** composition rules **plus** a common/breached-password denylist (`app/core/common_passwords.py`, enforced by `_enforce_password_rules` in `app/api/v1/auth.py`).
- **Session transport:** JWT is being migrated from `localStorage` to an httpOnly, `Secure`, `SameSite` cookie (`AUTH_SESSION_COOKIE_NAME = "checkwise_session"`) to remove XSS token theft. Cookie-authenticated mutations are CSRF-guarded.
- **AuthZ:** role-based (`require_role` / `require_any_role`, roles `internal_admin`/`reviewer`/`client_admin`/`platform_admin`) **and** object-level tenant scoping (`_actor_from`, `_resolve_client_id`).
- **Data in transit:** TLS to the DB enforced in non-local environments.
- **Data at rest:** R2 server-side encryption (`AES256`) on object writes; Neon-managed encryption for the database.
- **Auditability:** authentication events (incl. logout), report-share disclosures, and submission state transitions write audit rows.

## 3. Secure coding standards (8.28)

These are mandatory and are checked in review (Code Owner on security-critical paths) and by SAST.

| Standard | Rule | Grounding in repo |
|----------|------|-------------------|
| **Input validation** | All request bodies are Pydantic models; reject malformed input at the edge. File uploads must pass a type + magic-byte gate. | Pydantic schemas across `app/api/v1/*`; PDF gate in `submission_service.py` rejects anything without the `%PDF-` signature ("El archivo no es un PDF válido…"). |
| **Parametrized queries** | Use the SQLAlchemy ORM / parameter binding. Never build SQL by string concatenation of user input. | SQLAlchemy 2.0 throughout `app/models/` + services. |
| **Object-level authorization** | Every resource fetch is scoped to the caller's tenant; cross-tenant probes return `404` (no enumeration). Never trust a client-supplied `org_id`/`client_id` without re-resolving it against the caller. | `_actor_from(current)` scoping; `_resolve_client_id` gate; regression-tested in `tests/test_cross_tenant_reports_shares_exports.py`. |
| **No secrets in code** | No credentials, tokens, or keys in source. The one allowlisted string is the local-dev JWT placeholder, which the boot guard refuses in production. | `.gitleaks.toml` allowlist; gitleaks job in `security.yml`. |
| **JWT boot guard** | The API must refuse to start in a non-local environment if `AUTH_JWT_SECRET` is the in-code placeholder, or if DB TLS is weakened. | `_validate_boot_security` + `sslmode` check in `app/core/config.py`. |
| **CSRF on cookie mutations** | Cookie-authenticated mutating requests must pass an Origin/Referer allowlist, failing closed in production. | `_enforce_cookie_csrf` (auth) mirrors `enforce_portal_csrf` (portal). |
| **Security headers** | Every API response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, a CSP subset (`frame-ancestors 'none'; base-uri 'none'`), and HSTS in production. | Response middleware in `app/main.py`; frontend headers + CSP in `next.config.ts`. |
| **CORS** | Reflect only exact-match allowlisted origins; credentials enabled only for those origins. | `CORSMiddleware` with `allow_origins=allowed_origins`, `allow_credentials=True` (`app/main.py`); origins from `CORS_ORIGINS` + `FRONTEND_BASE_URL`. |
| **Storage delete safety** | Never delete a content-addressed object another tenant still references. | Refcount guard `_delete_orphaned_objects` (`app/api/v1/portal.py`); tested in `test_iso_hardening.py`. |
| **No `--no-verify`, append-only migrations** | Don't bypass the pre-commit hook; never edit a merged migration. | `CONTRIBUTING.md`. |
| **Lint / style** | `ruff` (rules `E,F,I,UP,B`) backend; `eslint` + `tsc --noEmit` frontend. | `pyproject.toml` `[tool.ruff]`; CI `frontend` job. |

### 3.1 Threat-modeling expectations

- Changes to authentication, authorization, tenant isolation, storage, or the audit trail (the CODEOWNERS-protected paths) require a lightweight threat-model note in the PR: *what trust boundary does this touch, and what is the abuse case?*
- The standing top threats for CheckWise are: **cross-tenant data exposure (IDOR)**, **document/report exfiltration via shares/exports**, **auth bypass / token theft**, and **malicious file upload**. New features near these surfaces must state how they preserve the existing control.
- **⚠ TO VERIFY** — threat modeling is currently informal (captured in PR discussion + the audit handoffs). **Target:** a short, recorded STRIDE-style note per security-critical PR.

## 4. Security testing in the lifecycle (8.29)

Covered in depth by the companion checklist `docs/compliance/SECURITY_TESTING_CHECKLIST.md`. Summary of in-pipeline gates:

| Gate | Tool | When | Fails build on |
|------|------|------|----------------|
| Lint + unit/integration tests | `ruff` + `pytest` (backend); `tsc`/`eslint`/`next build` (frontend) | Every PR + push to `main` (`ci.yml`) | Any failure |
| Secret scanning | gitleaks | Every PR + push + weekly cron (`security.yml`) | Any committed secret |
| Python dependency CVEs | pip-audit (`--strict --local`) | Every PR + push + weekly cron | **Any** vulnerability |
| Node dependency CVEs | npm audit (`--audit-level=high`) | Every PR + push + weekly cron | High or critical |
| SAST (semantic) | CodeQL (`security-and-quality`, Python + TS/JS) | Every PR + push + weekly cron (`codeql.yml`) | Alerts to Security tab; **⚠ TO VERIFY** — not yet a hard merge gate (pending branch protection) |
| Tenant-isolation regression | `tests/test_cross_tenant_reports_shares_exports.py`, `tests/test_iso_hardening.py` | Inside `pytest` on every PR | Any cross-tenant `200` |

> **⚠ TO VERIFY — enforcement gap.** CI/Security/CodeQL *run* on every PR but are not yet *required* merge checks because branch protection on `main` is not enabled. See `CHANGE_MANAGEMENT.md` §6. **Target:** make them required.

## 5. Dependency & technical-vulnerability management (8.8)

**Lockfile discipline:**

- Backend floors are declared in `apps/api/pyproject.toml`; the full transitive tree is frozen in `apps/api/requirements.lock`. Render installs with `pip install -e . -c requirements.lock` so every deploy is byte-identical to the validated set (this closed the 2026-06-15 `fastapi 0.137` drift crash-loop).
- Known-CVE transitive floors are pinned explicitly in `pyproject.toml` (e.g. `idna>=3.15`, `starlette>=1.0.1`, `aiohttp>=3.14.0`) and moved up as new advisories land.
- Frontend: `package-lock.json` + `npm ci` (exact install).
- Regenerate the lock per the procedure in its header and re-run the full test suite before committing a dependency change.

**Detection + remediation loop:**

1. **Detect** — pip-audit + npm audit run weekly (Monday cron) and on every PR, so a CVE published against an already-pinned dep is flagged without a code change forcing it.
2. **Open the fix** — Dependabot (`.github/dependabot.yml`) opens weekly upgrade PRs for `pip`, `npm`, and `github-actions`; minor/patch grouped, majors individual, labelled `security`.
3. **Review + merge** — Dependabot PRs go through the same CI/Security/CodeQL gates and review as any change.
4. **Verify** — post-deploy smoke per `CHANGE_MANAGEMENT.md` §2.

**Patch SLA by severity (target):**

| Severity | Target time to patch in production |
|----------|-----------------------------------|
| Critical | ≤ 72 hours (emergency-change path if needed) |
| High | ≤ 7 days |
| Moderate | ≤ 30 days, batched with the weekly Dependabot run |
| Low | Best effort, next dependency sweep |

> **⚠ TO VERIFY** — the SLA table is a proposed target, not yet a measured/tracked metric. **Target:** track time-to-patch against this table and report it in the periodic security review.

## 6. Secrets management standard

| Control | Implementation |
|---------|----------------|
| No secrets in source | All production secrets are platform env vars with `sync: false` in `render.yaml` (DB URLs, R2 creds, `AUTH_JWT_SECRET`, SMTP, Twilio/WhatsApp, Anthropic, Slack). Frontend secrets via Vercel env. |
| Committed-secret prevention | `.gitignore` excludes `.env`/local secrets and `checkwise.db`; gitleaks scans full history on every push + weekly cron. `.gitleaks.toml` allowlists only the local-dev JWT placeholder + test fixtures. |
| Production safety net | Boot guard (`_validate_boot_security`) refuses to start in production with the placeholder JWT secret, so a leaked placeholder has no production value. |
| Rotation | JWT secret: generate with `openssl rand -hex 32`, set in Render, redeploy (invalidates existing sessions — schedule it). Other credentials rotated at the provider, then updated in Render/Vercel. **⚠ TO VERIFY** — no fixed rotation calendar yet. **Target:** a documented rotation cadence per secret class. |
| Never print secrets | Logs and audit rows record delivery *status* (e.g. `smtp_not_configured`, `slack_delivery_status="skipped"`), never credential values. |

## 7. Outsourced / AI-assisted development (8.30)

- CheckWise development is in-house (LegalShelf), with AI-assisted contributions (e.g. Codex, Claude). There is currently no third-party outsourced development vendor.
- **AI-assisted code is held to the identical bar as human-authored code:** same PR + review + CI/Security/CodeQL gates; AI-assisted commits carry the `Co-Authored-By:` trailer (`CONTRIBUTING.md`). Concurrent AI agents editing the same tree are coordinated so security-critical files (`lib/api/*`, auth) aren't changed blind (see the staged cookie cutover in `_handoff/hardening-batch-2026-06-15.md`).
- **⚠ TO VERIFY** — if/when external development is engaged, this section must add contractual security requirements, code-ownership/IP terms, and a right-to-audit clause per 8.30.

## 8. Periodic security review

- Recurring security/perf/quality audits are recorded under `_handoff/audit-*.md` (e.g. `audit-security-perf-2026-06-15.md`, `hardening-batch-2026-06-15.md`) and tracked to closure.
- Findings are coded (e.g. `REPORT-1`, `ADMIN-1`, `ENC-1`, `FILE-DEL-1`) and the highest-severity (cross-tenant exfiltration, privilege self-escalation) are fixed + regression-tested before close.
- This `docs/compliance/` tree is the standing evidence set; the checklist in §4 / `SECURITY_TESTING_CHECKLIST.md` is the reusable pre-release instrument.
