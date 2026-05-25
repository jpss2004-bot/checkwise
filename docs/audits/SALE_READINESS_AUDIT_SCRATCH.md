# Sale-readiness audit — scratch findings (2026-05-25)

Internal scratchpad. Used during the four-pass audit to capture
findings before they're sorted into the buyer-facing report and the
internal findings list. **Not a deliverable in itself.**

Severity tags:
- `🔴 P0` — must fix before first paying pilot signs
- `🟠 P1` — must fix in the first 30 days of the pilot
- `🟡 P2` — quality of life, nice to have
- `📘 NOTE` — observation worth surfacing in the buyer dossier or
  the architecture section

---

## Pass 4 — Production reality (complete)

### Infrastructure mapping

- **API**: Render web service `checkwise-api` at `https://checkwise-api.onrender.com`. Python 3.11, Uvicorn, starter plan ($7/mo, warm). `autoDeploy: true` from `main`. Build: `pip install -e . && playwright install --with-deps chromium`. Pre-deploy: `alembic upgrade head` against `DIRECT_DATABASE_URL` (Neon direct endpoint). Health check: `/health` returns `{status:ok}` ✓.
- **Frontend**: Vercel project at `https://checkwise-six.vercel.app`. Next.js 15.5, served from `sfo1` edge.
- **Database**: Neon Postgres. Pooled (`DATABASE_URL`) for runtime, direct (`DIRECT_DATABASE_URL`) for Alembic.
- **Storage**: Cloudflare R2 (`STORAGE_BACKEND=s3`, `STORAGE_BUCKET=checkwise-prod`, `AWS_S3_ENDPOINT` per Render env).
- **Renewal cron**: Render cron `checkwise-renewal-dispatch` daily 14:00 UTC = 08:00 CDMX.
- **OpenAPI / `/docs`**: blocked on prod ✓ (returns 404).
- **AUTH_JWT_SECRET, DATABASE_URL, AWS_*, ANTHROPIC_API_KEY, SLACK_*** all marked `sync: false` in `render.yaml` (not committed). ✓.

### Findings

| ID | Sev | Finding | Evidence |
|----|-----|---------|----------|
| P4-01 | 🔴 P0 | `AUTH_JWT_SECRET` has a default placeholder value `"checkwise-local-dev-secret-change-me-please-min-32-chars"` in code. No runtime validator refuses to boot when `CHECKWISE_ENV=production` AND the secret is the placeholder. If Render env is ever cleared, the API silently runs with the placeholder, and anyone reading the public repo can mint valid JWTs. | `apps/api/app/core/config.py:47` |
| P4-02 | 🔴 P0 | `render.yaml` does NOT declare `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`. If they're not set manually in the Render dashboard, the new transactional email (reviewer decisions + renewals) silently no-ops in prod with `smtp_not_configured`. Same risk for password reset. | `render.yaml` (no SMTP entries) |
| P4-03 | 🔴 P0 | `render.yaml` does NOT declare `FRONTEND_BASE_URL`. The transactional email helper falls back to the in-code default `http://localhost:3000`, so emails (if SMTP works) embed dead localhost CTA links. | `apps/api/app/core/config.py:51` |
| P4-04 | 🟠 P1 | 4 docs still document live demo passwords (`demo1234`, `BossDemo!2026`, `CheckWiseDemo!2026`, `ClienteDemo!2026`) for `ada@legalshelf.mx`, `boss.demo@checkwise.mx`, `proveedor.demo@checkwise.mx`, `cliente.demo@checkwise.mx`. **Login attempts against prod confirm all four are now invalid** — operator already rotated. But docs are misleading: dev/buyer/CTO reading the repo would try them, conclude prod is insecure. | `docs/CREDENTIALS.md:18-61`, `docs/DEMO_LOGIN_MATRIX.md:23-26`, `docs/DEMO_1.7.1.md:14-16`, `docs/EXECUTIVE_REPORT_V2_LIVE_EVIDENCE.html:921-924`, `docs/NEXT_SESSION_HANDOFF.md:88-91`, `docs/PROVIDER_REPORTS_SESSION_HANDOFF.md:78` |
| P4-05 | 🟡 P2 | `/dev/calendar-preview` route is publicly reachable on prod (HTTP 200, no auth, no robots gate). Content is harmless UI sandbox but signals "unfinished" to a sales prospect inspecting URLs. | `apps/web/app/dev/calendar-preview/page.tsx`, `curl https://checkwise-six.vercel.app/dev/calendar-preview` → 200 |
| P4-06 | 🟡 P2 | `apps/web/.env.local.example` recommends `NEXT_PUBLIC_DEMO_MODE=true`, which exposes the "Usar PDF demo" button in the intake wizard. A new Vercel deploy that copies the example as a template would ship the demo button to prod. | `apps/web/.env.local.example:7` |
| P4-07 | 🟡 P2 | `docs/` directory has 66 Markdown files (~14k LOC), many superseded (`CHECKWISE_1_5.md`, `CHECKWISE_1_6.md`, `CHECKWISE_2_0.md`, `DEMO_1.7.1.md`, multiple `PROVIDER_REPORTS_*` documents, `PRE_REDESIGN_*`, `REDESIGN_GUARDRAILS.md`, `PROMPTED_BUT_INCOMPLETE_2026-05-19.md`, etc.). Hard for a buyer's CTO to find current docs. | `docs/` listing |
| P4-08 | 🟡 P2 | Two committed PDF artifacts (`docs/audits/security/BACKEND_HARDENING_PASS_2026-05-25.pdf`, `docs/legal/checkwise-paquete-legal-simple-v1-2026-05-25.pdf`) are user-generated, untracked, sitting in the working tree. Unclear whether they should ship to the repo or stay local. | `git status` |
| P4-09 | 📘 NOTE | `render.yaml` correctly marks every secret as `sync: false` and the `.gitignore` blocks `.env`, `*.pem`, `*-credentials*.json`. Defense-in-depth is in place. | `.gitignore`, `render.yaml` |
| P4-10 | 📘 NOTE | `dev_seed.py` refuses to run against any DB whose host isn't `localhost`/`127.0.0.1`/`*.local`, unless `CHECKWISE_ALLOW_SEED_AGAINST=<host>` is set. Hardens the rotation that happened on 2026-05-18 (per `PROD_AUDIT_2026-05-18.md`). | `apps/api/scripts/dev_seed.py:1287-1321` |
| P4-11 | 📘 NOTE | OpenAPI surface (`/openapi.json`, `/docs`, `/redoc`) blocked on prod via `ENABLE_API_DOCS` defaulting off outside local. | `apps/api/app/core/config.py:223-228`, `curl /openapi.json` → 404 |
| P4-12 | 📘 NOTE | No committed secrets / API keys / certificates found in source tree. | grep sweep |
| P4-13 | 🟡 P2 | 2 source-code TODOs survive (only): `app/core/rate_limit.py:7` (replace with Redis pre-scale) and `app/portal/calendar/page.tsx:187` (comment, not code). | grep sweep |

### Things deferred to other passes

- **Endpoint role-gate inventory** → Pass 3 ✓
- **Tenant isolation across `client_id`** → Pass 3 ✓
- **Audit log completeness check** → Pass 3 ✓
- **Per-page UI inconsistencies** → Pass 1
- **End-to-end workflow walkthrough** → Pass 2

---

## Pass 3 — Backend hardening (complete)

### Approach

Delegated to an Explore agent reading every router under
`apps/api/app/api/v1/`, plus services, models, config, rate
limiter and storage layer. The agent did NOT modify any code.
Cross-referenced against the public Pass 4 reachability tests
where possible.

### Summary by category

1. **Role gates** — every mutating admin/reviewer/client endpoint
   is gated via `require_role()` or `require_any_role()`. Auth
   endpoints (login, forgot-password, contact, feedback) are
   appropriately unauthenticated but rate-limited. No ungated
   mutations found.
2. **Tenant isolation** — client-scoped endpoints validate
   `client_id` through `_resolve_client_id()` which enforces
   membership. Portal workspace endpoints validate `workspace_id`
   against session claims. Cross-tenant reads isolated via
   role+filter.
3. **Audit log completeness** — every admin mutation, reviewer
   decision, document download, client profile update, legal
   consent, and provider upload writes an `audit_log` row. Two
   notification mutation endpoints (`mark-read`,
   `mark-all-read`) DO NOT audit.
4. **Spanish errors** — most user-facing errors are Spanish; the
   feedback router has a handful of English technical messages.
5. **422 edge cases** — Pydantic constraints in place
   (`min_length`/`max_length`/`Field(...)`); file size cap
   enforced via `MAX_UPLOAD_SIZE_BYTES` in prevalidation +
   storage; ContactRequestCreate, ClientCreate/Update, audit
   filters all bounded.
6. **Rate limits** — login per-(IP,email); forgot-password
   per-email + per-IP; public contact + feedback IP-hashed;
   authenticated feedback per-user 10/min.
7. **File caps / extensions** — `MAX_UPLOAD_SIZE_BYTES=15MB`,
   `ALLOWED_FILE_EXTENSIONS=".pdf"` enforced via prevalidation;
   multi-file finalize relies on same prevalidation chain.
8. **Secrets scan** — no hardcoded API keys, SMTP credentials,
   Slack tokens, or AWS keys found in source. Only the dev
   placeholder for `AUTH_JWT_SECRET` (already captured as
   `P4-01`).
9. **Misc smells** — no raw SQL string formatting; stateless
   JWT auth (no CSRF needed); stack traces hidden in production;
   one moderately-permissive CORS shape.

### Findings

| ID | Sev | Finding | Evidence |
|----|-----|---------|----------|
| P3-01 | 🟠 P1 | `POST /api/v1/client/notifications/{id}/read` and `POST /api/v1/client/notifications/read-all` mutate `read_at` without writing an `audit_log` row. Every other client mutation writes one (profile update, audit-package download). A forensic reader cannot answer "who marked which notifications as read and when". | `apps/api/app/api/v1/client.py:1693,1712` |
| P3-02 | 🟡 P2 | English error messages on the feedback router: `"Too many feedback reports — wait a minute and try again."` and `"Screenshot must be a PNG image"` and `"description must contain at least 10 non-whitespace characters"`. Surface to Spanish-speaking pilot users. | `apps/api/app/api/v1/feedback.py:115-120,126,204` |
| P3-03 | 🟡 P2 | CORS middleware uses `allow_methods=["*"]` and `allow_headers=["*"]`. Functionally fine because the API enforces auth on every state-changing endpoint, but tightening to an explicit allowlist is the right posture for a paying customer audit. | `apps/api/app/main.py:32-38` |
| P3-04 | 📘 NOTE | File extension validation is enforced inside `services/prevalidation.py`, not in the router signature. Multi-file finalize relies on the same path. Implicit but correct contract; worth documenting in the buyer dossier. | `apps/api/app/services/prevalidation.py:38`, `apps/api/app/api/v1/portal.py` multi-file path |
| P3-05 | 📘 NOTE | Stateless JWT auth + no cookie-based sessions → no CSRF token machinery needed. Confirmed by Pass 3 review. | `apps/api/app/api/v1/auth.py` |
| P3-06 | 📘 NOTE | Per-user rate limits are in-memory sliding windows (not Redis). Documented TODO in `app/core/rate_limit.py:7`. Acceptable for single-instance Render starter; becomes a correctness issue on horizontal scale (counters wouldn't share). Out of scope for first pilot. | `apps/api/app/core/rate_limit.py:7` |
| P3-07 | 📘 NOTE | `add_audit_event` runs synchronously inside the request transaction. A long-running audit insert would slow the user-visible path. Today's audit writes are tiny JSON; no immediate concern. | `apps/api/app/services/audit_log.py` |

---

## Pass 1 — Route walk per persona (static analysis)

Approach: cross-reference the 46-route inventory (`docs/PROJECT_STRUCTURE.md` + `apps/web/app/**/page.tsx`) against findings captured in this session and from prior audits. Routes I'd already smoke-tested in browser during this session are marked ✓.

### Inconsistencies / smells identified

| ID | Sev | Finding | Evidence |
|----|-----|---------|----------|
| P1-01 | 🟠 P1 | `docs/CREDENTIALS.md`, `docs/DEMO_LOGIN_MATRIX.md`, `docs/DEMO_1.7.1.md`, `docs/NEXT_SESSION_HANDOFF.md`, `docs/PROVIDER_REPORTS_SESSION_HANDOFF.md` still show literal demo passwords. Buyer-side legal counsel reading the repo will conclude credentials are committed. (Confirmed in Pass 4 that the four accounts no longer work on prod.) | grep sweep, Pass 4-04 |
| P1-02 | 📘 NOTE | The four reviewer decision actions render correct Spanish labels via `RequirementStatusBadge` (verified in this session for /admin/reviewer/[id]). The "Rechazado" label is still used in the badge despite UX_COPY_RECOMMENDATIONS suggesting "Requiere corrección". Not a bug; a copy-strategy gap. | `apps/web/components/checkwise/portal/requirement-status-badge.tsx:11`, `docs/UX_COPY_RECOMMENDATIONS.md` |
| P1-03 | 🟡 P2 | `/dev/calendar-preview` is reachable publicly (Pass 4-05). For Pass 1: a sales prospect curious about the URL bar finds an internal sandbox. | `apps/web/app/dev/calendar-preview/page.tsx`, Pass 4-05 |
| P1-04 | 📘 NOTE | Sidebar collapse is portal-only. `/client/_shell.tsx` and `/admin/_shell.tsx` use the `UserMenu` but do not have the collapsible sidebar (single-row top bar). Acceptable inconsistency since client + admin have less nav depth, but worth noting for buyer Q&A. | `apps/web/app/client/_shell.tsx`, `apps/web/app/admin/_shell.tsx`, `apps/web/components/checkwise/portal/portal-app-shell.tsx` |
| P1-05 | 🟡 P2 | The portal `/portal/notifications` and client `/client/notifications` are read surfaces — marking notifications as read is the only mutation. Per P3-01, those mutations don't audit. UX impact: not flagged in UI; security impact: forensic trail incomplete. | P3-01 |
| P1-06 | 📘 NOTE | The 11 status enum values render in ~5 distinct surfaces. The "Posible inconsistencia" / "Requiere corrección" / "Necesita aclaración" / "Excepción legal" labels are now consistent (verified via earlier unify commit + tests). | `apps/web/components/checkwise/portal/requirement-status-badge.tsx`, Pass 4-X sweep |
| P1-07 | 📘 NOTE | The /admin surface lacks a profile dropdown destination (UserMenu prop `profileHref={null}`). Acceptable since internal_admin doesn't have a profile surface yet; flag in buyer dossier as deliberate scoping. | `apps/web/app/admin/_shell.tsx` `UserMenu` props |

---

## Pass 2 — End-to-end workflow audit (static + workflow trace)

### Sale story — client signup → admin precharge → onboard → upload → review → renewal → audit ZIP

| Step | Surface | Code path | Status |
|------|---------|-----------|--------|
| 1. Sale closes; admin creates client + invites client_admin | `/admin/clients` form + `POST /api/v1/admin/clients` | `admin.py` `create_client` — requires `name`, `rfc`, `email` (P0-4 already shipped) | ✓ wired |
| 2. Client_admin receives credentials via … ? | No flow — admin must manually share credentials out of band | `apps/api/app/services/auth.py` has password reset but no invitation flow | 🟠 P1 gap |
| 3. Client_admin first login | `/admin/login` (note: client_admin uses the SAME login, not a separate one — confirmed via `apps/web/app/login/page.tsx`) → bounces to `/client/dashboard` | `auth.py` resolves role, redirects | ✓ |
| 4. Dashboard nags "Termina tu alta" | `/client/dashboard` with `OnboardingPromptBanner` while `profile.onboarding_completed_at IS NULL` | `apps/web/app/client/dashboard/page.tsx` | ✓ shipped this week |
| 5. Client_admin completes `/client/onboarding` | `PATCH /api/v1/client/profile` writes `onboarding_completed_at` + audit row | ✓ | ✓ |
| 6. Client_admin adds vendors / providers | `/admin/vendors` (admin) — there is NO `/client/vendors/new` flow | `admin.py` `create_vendor` requires admin role | 🟠 P1 gap: client_admin can VIEW vendors but cannot ADD vendors; only internal_admin can. The current shape forces LegalShelf operations to add every vendor. |
| 7. Provider receives invitation … ? | Same gap as #2 | No code-level invitation pipeline | 🟠 P1 gap |
| 8. Provider logs in, signs legal consent v1 | `/portal/entra-a-tu-espacio` with consent gate; checked v1 in Pass 4 | ✓ | ✓ |
| 9. Provider uploads document (single or multi-file) | `/portal/upload` → `POST /api/v1/portal/workspaces/{id}/submissions` | Verified in earlier session; multi-file enabled in this session | ✓ |
| 10. Reviewer reviews + decides | `/admin/reviewer/[id]` → `POST /api/v1/reviewer/submissions/{id}/decision`; provider gets in-app notification + (now) email | ✓ verified in earlier session; email path shipped this week | ✓ |
| 11. Renewal threshold crosses (cron at 14:00 UTC) | `scripts/run_renewal_dispatch.py` → in-app notifications + (now) emails to provider + client_admin | ✓ wired; needs SMTP config in prod (Pass 4-02) | 🔴 deps on Pass 4-02 |
| 12. Client_admin downloads audit ZIP with INDICE.pdf | `/client/auditoria` → `GET /api/v1/client/audit-package.zip` | ✓ verified in earlier session; includes INDICE.pdf via Playwright | ✓ |

### Workflow findings

| ID | Sev | Finding | Evidence |
|----|-----|---------|----------|
| P2-01 | 🟠 P1 | **No code-level client invitation flow.** When admin creates a client (step 1), there is no automated email to the client_admin's address (the new `email` column added in P0-4). The admin must manually share credentials. For a paying pilot this is workable but brittle. | `apps/api/app/api/v1/admin.py` `create_client` — no email-out call |
| P2-02 | 🟠 P1 | **No vendor self-add for client_admin.** The endpoint `POST /api/v1/admin/vendors` requires `internal_admin`. Client_admins cannot add their own providers; LegalShelf must do it. This forces a manual ops touchpoint for every new vendor. Not a blocker for a small pilot, but it scales poorly. | `apps/api/app/api/v1/admin.py:430-540`, no `/api/v1/client/vendors` POST |
| P2-03 | 🟠 P1 | **No provider invitation flow.** Same as P2-01 but for the provider user (the workspace owner). Today the admin manually creates `User` + `ProviderWorkspace` rows (via scripts) and shares the access token / password out of band. | `apps/api/scripts/add_provider_to_existing_client.py`, no in-app invitation surface |
| P2-04 | 🔴 P0 | **Transactional email needs SMTP env vars on Render.** Same as P4-02. If SMTP is not configured the cron and reviewer decision paths silently skip email; client / provider only see the in-app notification. For a paying pilot this is a regression vs the promise the email feature implies. | `render.yaml`, `apps/api/app/services/email_delivery.py:smtp_configured` |
| P2-05 | 🟡 P2 | **`FRONTEND_BASE_URL` not in render.yaml.** Same as P4-03. If transactional email DOES go out, CTAs would point at localhost. | `render.yaml` |
| P2-06 | 📘 NOTE | **Renewal cron is the single point that drives renewals.** If the cron fails (Render outage, deploy mid-cron, Neon timeout) on a given day, the `thresholds_crossed` catch-up logic emits every missed threshold on the next run — verified in tests. Good resilience. | `apps/api/app/services/renewal_dispatch.py:96-107` |
| P2-07 | 📘 NOTE | **Audit ZIP cap is 200 files / 500 MB.** For a real client with many providers and many periods, a cross-vendor audit package may hit the cap. The endpoint returns a clear 413 with a Spanish message guiding the user to narrow filters. No silent failure. | `apps/api/app/services/audit_package.py:44-45,134-140` |
| P2-08 | 📘 NOTE | **Document download (provider & admin) is presigned via R2 in production.** Storage layer returns `RedirectResponse` to a 15-minute presigned URL when R2 is configured; local FS falls back to `FileResponse`. Buyer's CTO will likely ask about this — answer: zero-egress on the API node for the actual bytes. | `apps/api/app/api/v1/portal.py:2064-2076`, `apps/api/app/api/v1/reviewer.py` |

