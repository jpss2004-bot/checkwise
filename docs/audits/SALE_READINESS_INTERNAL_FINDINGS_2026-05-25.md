# CheckWise — Sale-readiness internal findings

**Audit date:** 2026-05-25
**Audit author:** internal pre-pilot review
**Companion document:** [SALE_READINESS_BUYER_DOSSIER_2026-05-25.md](./SALE_READINESS_BUYER_DOSSIER_2026-05-25.md)

Engineering-facing list of every gap, bug, inconsistency, and
risk found across the four audit passes. Use this to schedule
fix work; do not share verbatim with customer-facing
counterparties.

## Severity legend

- 🔴 **P0** — must fix before the first paying pilot signs.
- 🟠 **P1** — must fix in the first 30 days of the pilot.
- 🟡 **P2** — quality / polish; ship when convenient.
- 📘 **NOTE** — architectural observation worth knowing; not a fix.

---

## P0 — block sale until cleared

| ID | Severity | Title | Where | Why it matters | Fix path |
|----|----------|-------|-------|----------------|----------|
| P4-01 | 🔴 P0 | `AUTH_JWT_SECRET` has a placeholder default with no runtime guard | `apps/api/app/core/config.py:47` | If the Render env value is ever cleared or missing, the API silently boots with the in-code placeholder. The placeholder is in a public repo. Anyone reading it could mint valid JWTs. | Either (a) confirm via Render dashboard that the env is set to the operator's random value AND add a runtime validator that refuses to boot when `CHECKWISE_ENV != "local"` AND `AUTH_JWT_SECRET == "checkwise-local-dev-secret-change-me-please-min-32-chars"`, or (b) remove the default entirely and crash on missing-env. (a) is the safer move because (b) breaks tests that import settings outside of CI. |
| P4-02 | 🔴 P0 | `render.yaml` omits SMTP env vars (`SMTP_HOST`/`SMTP_USERNAME`/`SMTP_PASSWORD`/`SMTP_FROM_EMAIL`) | `render.yaml` | Transactional email (password reset, reviewer decisions, renewal reminders) silently `skipped` with `"smtp_not_configured"`. The new email feature shipped 2026-05-25 is dead in prod until SMTP is set. | Add the four env entries with `sync: false` to `render.yaml`, then paste credentials in the Render dashboard. Sanity-check by triggering a forgot-password flow and confirming the email lands. |
| P4-03 | 🔴 P0 | `render.yaml` omits `FRONTEND_BASE_URL` | `render.yaml` | Transactional email CTAs default to `http://localhost:3000`. Even when SMTP works, every email link points at the developer's loopback. | Add `FRONTEND_BASE_URL=https://app.checkwise.mx` (or the chosen production hostname) to `render.yaml`. Verify by reading the email body of a triggered reviewer decision in staging. |
| P2-04 | 🔴 P0 | Transactional email shipped without SMTP env safety check | `apps/api/app/services/transactional_email.py` | Cross-reference of P4-02. The new email pipeline depends on SMTP being configured. Without it, the pilot customer believes "the platform sends email" but nothing leaves the system. | Tied to P4-02 fix. Consider adding a single startup log line: "Transactional email: enabled / disabled (SMTP not configured)". |

---

## P1 — fix within 30 days of pilot start

| ID | Severity | Title | Where | Why it matters | Fix path |
|----|----------|-------|-------|----------------|----------|
| P4-04 | 🟠 P1 | 7+ docs still list literal demo passwords for accounts that are now invalid on prod | `docs/CREDENTIALS.md`, `docs/DEMO_LOGIN_MATRIX.md`, `docs/DEMO_1.7.1.md`, `docs/NEXT_SESSION_HANDOFF.md`, `docs/PROVIDER_REPORTS_SESSION_HANDOFF.md`, `docs/EXECUTIVE_REPORT_V2_LIVE_EVIDENCE.html`, `docs/AUDIT_NEXT_SESSION_READINESS.md` | Reading the repo creates the impression that credentials are committed. Confirmed via prod login attempts that the four accounts return `Invalid credentials` (operator already rotated), but the docs lie. A buyer's security review would flag this. | Either delete the rows entirely, mark them as `"<rotated; ask operator>"`, or move them into a single `LOCAL_DEV_CREDENTIALS.md` that is `.gitignore`d. The fastest fix is the marker text + a footer linking to the doc that explains the rotation history. |
| P3-01 | 🟠 P1 | `mark-read` / `mark-all-read` notification mutations do not write `audit_log` rows | `apps/api/app/api/v1/client.py:1693,1712` (and the equivalent provider endpoints) | A forensic reader cannot answer "who marked which notifications as read and when". Every other client mutation writes one row; these two are the only gap found in the backend audit. | Add `add_audit_event(db, action="client.notification_read", entity_type="client_notification", entity_id=notification_id, actor_type="client_admin", actor_id=current.user.id, metadata={...})` after the `row.read_at` assignment in both endpoints. Same shape on the provider side. Add a single integration test asserting the row lands. |
| P2-01 | 🟠 P1 | No code-level client invitation flow | `apps/api/app/api/v1/admin.py` `create_client` | When admin creates a client, no automated email goes to the new client_admin email. Admin must manually share credentials. Workable for one pilot, brittle past that. | Pipeline: on `POST /admin/clients`, generate a single-use invitation token, store hash in a new `client_invitations` table, send the client_admin an email with the link to a self-set-password page (reuse the password-reset machinery). Estimated 0.5d. |
| P2-02 | 🟠 P1 | No vendor self-add for `client_admin` | `apps/api/app/api/v1/admin.py:430-540` | `POST /api/v1/admin/vendors` requires `internal_admin`. Client_admins cannot add their own providers. LegalShelf ops becomes a chokepoint for every new vendor. | Add `POST /api/v1/client/vendors` gated on `client_admin` with the same body shape, scoping to the caller's client_id. Wire a "Agregar proveedor" CTA on `/client/vendors`. Estimated 0.5d. |
| P2-03 | 🟠 P1 | No provider invitation flow | `apps/api/scripts/add_provider_to_existing_client.py` (manual today) | Admin runs a CLI script to mint `User` + `ProviderWorkspace` rows and shares access out of band. Brittle. | Same shape as P2-01 but issuing a provider workspace + access token. Pair with P2-02 so the client_admin adding a vendor can immediately invite the provider user. Estimated 1d combined with P2-02. |

---

## P2 — quality / polish

| ID | Severity | Title | Where | Why it matters | Fix path |
|----|----------|-------|-------|----------------|----------|
| P4-05 | 🟡 P2 | `/dev/calendar-preview` reachable on prod | `apps/web/app/dev/calendar-preview/page.tsx` | Sales prospect inspecting URLs finds an internal UI sandbox. Content is harmless but signals "unfinished". | Either move the route under a `dev` segment that's gated by env (`NEXT_PUBLIC_DEV_ROUTES=true`) or delete the route entirely. Lower friction: rename to `/_internal/calendar-preview` and add `robots.txt` disallow. |
| P4-06 | 🟡 P2 | `apps/web/.env.local.example` recommends `NEXT_PUBLIC_DEMO_MODE=true` | `apps/web/.env.local.example:7` | A new Vercel deploy that uses the example as a template enables the "Usar PDF demo" button in production. | Change default in the example to `false`; add a comment explaining the demo path. |
| P4-07 | 🟡 P2 | `docs/` has 66 files, many superseded | `docs/` | Hard for a buyer's CTO to find the current architecture doc among 6 versions of the redesign plan. | Move legacy `CHECKWISE_1_5.md`, `CHECKWISE_1_6.md`, `CHECKWISE_2_0.md`, `DEMO_1.7.1.md`, `PRE_REDESIGN_*`, `PROVIDER_REPORTS_REDESIGN_*`, `PROMPTED_BUT_INCOMPLETE_*`, etc. into `docs/_archive/`. Keep a top-level `docs/README.md` index that lists the current docs only. |
| P4-08 | 🟡 P2 | Two PDF artifacts in working tree (not committed) | `docs/audits/security/BACKEND_HARDENING_PASS_2026-05-25.pdf`, `docs/legal/checkwise-paquete-legal-simple-v1-2026-05-25.pdf` | Unclear whether they should land in the repo or stay local. | Operator decision: either `git add` + commit them as customer-facing artifacts or add a `*.pdf` line to `.gitignore` if these are local-only printables. |
| P4-13 | 🟡 P2 | Two source-code TODOs survive | `apps/api/app/core/rate_limit.py:7`, `apps/web/app/portal/calendar/page.tsx:187` | Cosmetic. The first is a real follow-up (Redis-back the rate limiter pre-scale); the second is a comment, not a TODO. | Convert the first into a tracked issue and remove the inline TODO; leave the comment-only one alone (it's just narrative). |
| P3-02 | 🟡 P2 | English error messages in feedback router | `apps/api/app/api/v1/feedback.py:115-120,126,204` | A Spanish-speaking pilot user pasting a screenshot too big sees an English 415. | Localize the three messages: "Demasiados reportes de este usuario. Espera un minuto e inténtalo de nuevo.", "La captura debe ser una imagen PNG válida.", "La descripción debe tener al menos 10 caracteres (excluyendo espacios)." |
| P3-03 | 🟡 P2 | CORS allows `["*"]` methods and headers | `apps/api/app/main.py:32-38` | Permissive but not exploitable because every state-changing endpoint enforces auth. Tightening is the right posture for buyer-audit. | Replace with `allow_methods=["GET","POST","PATCH","PUT","DELETE"]` and an explicit `allow_headers=["Content-Type","Authorization","X-Workspace-Token"]`. Run the full E2E suite afterwards to confirm nothing breaks. |
| P2-05 | 🟡 P2 | `FRONTEND_BASE_URL` would default to localhost if env unset | `apps/api/app/core/config.py:51` | Same root as P4-03; downgraded here because the P0 fix already covers it. Worth flagging that the SMTP-skipped path doesn't even produce wrong-link emails — but a future emails-without-SMTP path could. | Add a runtime validator: when `CHECKWISE_ENV != "local"` AND `FRONTEND_BASE_URL` starts with `http://localhost`, log a warning at startup. |
| P1-02 | 🟡 P2 | "Rechazado" label still used despite UX_COPY_RECOMMENDATIONS preferring "Requiere corrección" | `apps/web/components/checkwise/portal/requirement-status-badge.tsx:11` | The audit doc explicitly recommends the softer term to invite the provider to act rather than feel rejected. | Change the label in the badge map. Search for other surfaces still using "Rechazado" as a noun; the `STATUS_HEADLINE` in the submission detail already says "fue rechazado" verb-form which is fine. |
| P1-03 | 🟡 P2 | `/dev/calendar-preview` discoverable | (dup of P4-05) | See P4-05. | See P4-05. |
| P1-05 | 🟡 P2 | Notification-read mutations not audited | (dup of P3-01) | See P3-01. | See P3-01. |

---

## NOTE — architectural observations to keep in mind

| ID | Severity | Observation | Where |
|----|----------|-------------|-------|
| P4-09 | 📘 NOTE | `render.yaml` correctly marks every secret as `sync: false` and `.gitignore` blocks env files, certificates, and credentials JSONs. Defense in depth in place. | `.gitignore`, `render.yaml` |
| P4-10 | 📘 NOTE | `dev_seed.py` refuses to run against any non-localhost DB, hardening the rotation that happened on 2026-05-18. | `apps/api/scripts/dev_seed.py:1287-1321` |
| P4-11 | 📘 NOTE | OpenAPI surface (`/openapi.json`, `/docs`, `/redoc`) blocked on prod via `ENABLE_API_DOCS` default off. | `apps/api/app/core/config.py:223-228`, prod 404 |
| P4-12 | 📘 NOTE | No committed secrets / API keys / certificates found anywhere in source. | grep sweep |
| P3-04 | 📘 NOTE | File extension validation enforced inside `services/prevalidation.py`, not the router. Multi-file finalize relies on the same path. Document this in the architecture doc so it's not implicit. | `apps/api/app/services/prevalidation.py:38` |
| P3-05 | 📘 NOTE | Stateless JWT auth means no CSRF token machinery needed; verified by code review. | `apps/api/app/api/v1/auth.py` |
| P3-06 | 📘 NOTE | In-memory sliding-window rate limiter is fine for single-instance Render starter; on horizontal scale the counters would diverge per worker. Acceptable for first pilot. | `apps/api/app/core/rate_limit.py:7` |
| P3-07 | 📘 NOTE | `add_audit_event` is synchronous inside the request transaction. Today's audit writes are tiny JSON; no immediate concern. | `apps/api/app/services/audit_log.py` |
| P2-06 | 📘 NOTE | Renewal cron catch-up logic (`thresholds_crossed`) emits every missed threshold on the next run, so a missed cron day does not silently drop reminders. | `apps/api/app/services/renewal_dispatch.py:96-107` |
| P2-07 | 📘 NOTE | Audit ZIP cap is 200 files / 500 MB. A real customer with many providers across many periods may hit it; the endpoint returns a clear 413 with Spanish guidance. | `apps/api/app/services/audit_package.py:44-45` |
| P2-08 | 📘 NOTE | Document download (provider, client_admin, admin) is presigned via R2 in production. Zero egress on the API node for actual bytes. | `apps/api/app/api/v1/portal.py:2064-2076`, `apps/api/app/api/v1/reviewer.py` |
| P1-04 | 📘 NOTE | Sidebar collapse is portal-only; client and admin use a top-bar shell. Acceptable because of nav depth difference. | `apps/web/app/{client,admin}/_shell.tsx` |
| P1-06 | 📘 NOTE | Document status enum labels are unified across all surfaces after the 2026-05-24 commits. | `apps/web/components/checkwise/portal/requirement-status-badge.tsx` |
| P1-07 | 📘 NOTE | Admin UserMenu has no profile destination (`profileHref={null}`). Acceptable because internal_admin has no profile surface yet. | `apps/web/app/admin/_shell.tsx` |

---

## Triage suggestion

If you have one hour: P4-01, P4-02, P4-03, P3-01, P4-04 (replace
credentials with placeholders).

If you have a day: above plus P2-01 / P2-02 / P2-03 (the
invitation flows that unblock onboarding scale beyond one
manually-touched pilot).

If you have a week: everything in the P0 + P1 + the P2
localization (P3-02) + CORS tightening (P3-03) + dev-route
cleanup (P4-05/06/07).

## Stop-conditions

Defer everything else until the pilot is in front of real
users. The 996 backend tests + the typecheck + the build gate
catch the regressions. The audit found no structural risk to
the data model, no missed role gate, no leaked secret, no
broken tenant isolation.
