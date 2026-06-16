---
Document: Access Control Policy
ID: CW-ISO-access-control
Owner: Lead Engineer / acting CISO (Jose Pablo Samano)
Version: 0.1 (draft)
Effective: 2026-06-16
Review cadence: annual + on material change
ISO refs: ISO/IEC 27002:2022 — 5.15 (access control), 5.16 (identity management), 5.17 (authentication information), 5.18 (access rights), 8.2 (privileged access rights), 8.5 (secure authentication)
Status: DRAFT — ISO-readiness evidence, NOT a certification claim
---

# Access Control Policy — CheckWise

> **Scope.** CheckWise is a multi-tenant SaaS for Mexican REPSE labor-compliance,
> operated by LegalShelf. This policy governs logical access to the CheckWise
> application, its data (Postgres on Neon, object storage on Cloudflare R2), and
> the administrative consoles. Physical access and corporate-device access are
> out of scope for this draft and tracked separately.
>
> **Honesty note.** This is an internal readiness document. It describes controls
> that exist in the codebase today and explicitly flags gaps (notably the absence
> of MFA). It does **not** assert ISO/IEC 27001 certification. Items not yet
> verified against an external source are marked **⚠ TO VERIFY**.

---

## 1. Access-control principles

CheckWise access decisions follow five principles, enforced primarily in
`apps/api/app/api/v1/auth.py` (the auth dependencies) and the per-router role
gates:

| Principle | What it means here | Where enforced |
|---|---|---|
| **Least privilege** | A user holds only the roles their job requires. Roles are granted per-organization via the `Membership` table, not globally. | `MembershipRole` (`apps/api/app/constants/roles.py`); membership grants in `admin.py`. |
| **Need-to-know** | Tenant data is visible only to members of that tenant (organization). The one deliberate exception is the cross-tenant `reviewer` role (see §6). | `require_org_role` re-checks membership in the path's `organization_id` against the DB. |
| **Deny-by-default** | Every protected endpoint requires an authenticated principal; missing/invalid credentials → `401`, missing role → `403`. A user flagged `must_change_password` can reach only two whitelisted paths. | `get_current_user`, `require_role`, `require_any_role`, `_PASSWORD_GATE_ALLOWED_PATHS`. |
| **Tenant isolation** | Authorization is re-evaluated server-side against the live DB on each request, so a stale-but-valid JWT cannot use a role/membership it has since lost. | `require_org_role` queries `Membership` with `status == "active"` rather than trusting token claims alone. |
| **Privileged-access separation** | IT/platform duties (`platform_admin`) are split from compliance-operations duties (`internal_admin`); granting a privileged role is itself gated. | `_assert_can_grant_role` (ADMIN-1), `admin.py`. |

---

## 2. Roles and access model (ISO 27002 5.15, 5.18)

CheckWise has six effective principals. Five are user-account roles on the
`Membership` table; the sixth is a non-user workspace session.

| Role | Purpose | Scope | Auth mechanism |
|---|---|---|---|
| `platform_admin` | IT console (`/platform/*`): user provisioning, audit-log explorer, feedback triage, soft-delete/restore. | Cross-tenant **administrative** surface only. | User JWT |
| `internal_admin` | LegalShelf compliance staff: full operational surface. Superset of `platform_admin` for the purpose of granting privileged roles. | Cross-tenant operational. | User JWT |
| `reviewer` | Validates uploaded documents **across all tenants** — cross-tenant **by design** (see §6). | Cross-tenant (document review queue). | User JWT |
| `client_admin` | Primary contact for a client tenant; manages that tenant's users (subject to `seat_limit`) and views its compliance state. | Single tenant. | User JWT |
| client user | Non-admin member of a client tenant. | Single tenant. | User JWT |
| provider (vendor) | External vendor uploading compliance evidence via a workspace-scoped portal. **Not a user account** — authenticates a *workspace*, not a person. | Single workspace. | Portal session token (httpOnly signed cookie `checkwise_portal_session`) + `X-Workspace-Token` header during cutover. |

Notes:
- `platform_admin` was introduced in the platform rework and **backfilled onto
  every existing `internal_admin`** (migration 0044), so the split is
  non-breaking; one person may hold both roles today.
- The provider portal is intentionally separate from user auth. It is documented
  here for completeness but is governed by the portal session/CSRF logic in
  `apps/api/app/api/v1/portal.py`, not by the user JWT flow.

---

## 3. Identity lifecycle (ISO 27002 5.16, 5.18)

### 3.1 Provisioning (joiner)

- **Admin-created only.** There is no public self-registration for staff, client,
  or reviewer accounts. Accounts are created by an authorized admin through the
  platform/admin user-management endpoints (`POST /admin/users`).
- **Temporary credential + forced first-login change.** New accounts are created
  with `must_change_password = True`. On first login the JWT is issued, but
  `get_current_user` restricts the principal to a narrow whitelist
  (`/api/v1/auth/me`, `/api/v1/auth/set-password`) until the user sets a personal
  password via `POST /api/v1/auth/set-password`. The gate is enforced in **one
  place** (`get_current_user`) rather than per-router, so a missed dependency
  cannot accidentally open the surface.
- **Invite / activation.** First-login activation flows through `/activate`; an
  invite-link flow is a noted nice-to-have (**⚠ TO VERIFY** whether a tokenized
  invite email is in place vs. an admin-communicated temporary password).

### 3.2 Modification (mover)

- Role and membership changes are made through the admin user-management
  endpoints. Membership rows carry a `status` and are re-evaluated live, so a
  removed role takes effect on the next request regardless of an unexpired JWT.
- Email/identity changes mirror to the linked `Client.email` and notify both
  parties (platform rework Phase 3).
- Granting a **privileged** role (`internal_admin` / `platform_admin`) is gated —
  see §6 (ADMIN-1).

### 3.3 Periodic access review

- **Proposed cadence: quarterly.** The acting CISO (or delegate) reviews every
  active `Membership`, confirms each privileged-role holder still requires it,
  and confirms no orphaned accounts remain after staff/customer departures.
- Procedure and log template are in §7.

### 3.4 Deprovisioning (leaver)

CheckWise supports three escalating revocation mechanisms; all are auditable.

| Mechanism | Effect | Reversible? | Source |
|---|---|---|---|
| **Account disable** (`status != "active"`) | Login and `get_current_user` both reject the account (`401 "Tu sesión ya no está activa."`). | Yes (admin re-activates). | `login`, `get_current_user`. |
| **Soft-delete** (`deleted_at` set; migration 0042) | Row retained for audit/accidental-delete recovery; user excluded from active queries via a partial unique index `WHERE deleted_at IS NULL`. Restore/preview supported (platform rework Phases 5–6). | Yes (restore). | `User` model; `/platform/*` soft-delete/restore. |
| **Account lockout** (migration 0045) | Automatic temporary lock after repeated failed logins (see §4.2). | Auto-clears after cooldown; or admin reset/reactivate. | `_register_failed_login`, `_is_account_locked`. |

- **Hard purge** of soft-deleted users is **DEFERRED** — `users.id` foreign keys
  lack cascade, so a destructive purge cron is not yet safe to run. **⚠ TO
  VERIFY** before any hard-delete tooling is enabled.
- Stateless JWTs cannot be server-revoked individually. Logout is a cookie clear
  (`POST /api/v1/auth/logout`, audited). Effective forced logout of an
  already-issued token relies on account disable + the 24h token TTL, plus the
  one-time cookie cutover that invalidated all localStorage sessions on deploy.
  **Gap:** there is no server-side JWT denylist / immediate global revocation
  (**⚠ TO VERIFY** acceptable per risk appetite; mitigated by short TTL).

---

## 4. Authentication standard (ISO 27002 5.17, 8.5)

### 4.1 Password policy (enforced server-side)

Enforced in `_enforce_password_rules` and `_apply_password_change`
(`apps/api/app/api/v1/auth.py`) — i.e. a direct API call cannot bypass the UI:

| Rule | Value | Source |
|---|---|---|
| Minimum length | **≥ 12 characters** | `_enforce_password_rules` |
| Character classes | at least one **uppercase**, one **lowercase**, one **digit** | `_enforce_password_rules` |
| Common-password denylist | rejects high-frequency/breached passwords that pass composition (offline list, no network call) | `is_common_password` (`core/common_passwords.py`); AUTH G-4 |
| Password history | new password must not match the last *N* hashes **or** the current one | `_apply_password_change`, `PASSWORD_HISTORY_DEPTH` (`services/auth.py`) — **⚠ TO VERIFY exact depth value** |
| Hashing | **bcrypt**, cost factor 12 (`AUTH_BCRYPT_ROUNDS`) | `config.py`, `hash_password` |
| Reset link TTL | 60 minutes; single-use; siblings invalidated on use | `PASSWORD_RESET_EXPIRES_MINUTES`, `reset_password` |

### 4.2 Account lockout (DB-backed)

Distinct from the per-IP/email rate limiter — it counts **consecutive** failed
logins **per account** (defeats slow guessing from rotating IPs):

| Setting | Default | Behavior |
|---|---|---|
| `AUTH_LOCKOUT_THRESHOLD` | 5 | After 5 consecutive failures the account is locked. `0` disables. |
| `AUTH_LOCKOUT_MINUTES` | 15 | Lock duration. A locked login returns **`429`**, even with the correct password. |
| Counter reset | — | Cleared on any successful login, password change, or admin reset/reactivate. |

Backed by `User.failed_login_count` + `User.locked_until` (migration 0045).
Failed and successful logins are written to the append-only audit log with IP +
user-agent (`auth.login.failed`, `auth.login.succeeded`, `auth.logout`).

### 4.3 Rate limiting (anti-brute-force / anti-enumeration)

| Surface | Default cap | Notes |
|---|---|---|
| Login | 10/min per (IP+email); 30/min per IP | `AUTH_LOGIN_RATE_LIMIT_PER_MINUTE` |
| Forgot-password | 5/hr per email; 10/hr per IP | generic response prevents account enumeration |
| Share-link unlock | 5/min, 30/hr | `SHARE_UNLOCK_RATE_LIMIT_*` |

> **⚠ TO VERIFY (operational):** The rate limiter is in-memory and only enforces
> correctly on a **single** uvicorn worker. `REDIS_URL` must be provisioned
> before scaling Render beyond one worker/instance, or the caps silently weaken
> by the worker multiple. The config emits a soft boot warning when `REDIS_URL`
> is unset on a non-local deploy.

### 4.4 Session / JWT handling

| Property | Value | Source |
|---|---|---|
| Algorithm | HS256 | `AUTH_JWT_ALGORITHM` |
| Lifetime | **24h** (1440 min) | `AUTH_JWT_EXPIRES_MINUTES` |
| Storage | httpOnly cookie `checkwise_session` (moved off `localStorage` per FE-SEC-1) | `login`, `AUTH_SESSION_COOKIE_NAME` |
| Cookie flags | `Secure` + `SameSite=None` in any non-local env (cross-site Vercel↔Render); `Lax` locally | `cookie_secure`, `cookie_samesite` |
| CSRF | Origin/Referer allowlist on cookie-authenticated **mutating** requests; bearer-header requests bypass (not ambient) | `_enforce_cookie_csrf`, `allowed_csrf_origins` |
| Secret hygiene | API **refuses to boot** in non-local if `AUTH_JWT_SECRET` is the in-code placeholder (audit P4-01) | `_validate_boot_security` |
| Transport | `sslmode=require` auto-pinned on the DB URL in non-local (fail-closed TLS) | `_ensure_sslmode_require` |

### 4.5 GAP — Multi-Factor Authentication (MFA) is NOT implemented

> **This is a known, open gap. CheckWise has no MFA today** — not for client users,
> not for `internal_admin`, not for `platform_admin`. Authentication is
> single-factor (password) for all roles. There is no TOTP, WebAuthn, SMS OTP, or
> email step-up for login. (A WhatsApp/SMS OTP exists for *phone-number
> verification* — `POST /api/v1/me/phone-verification/issue` — but it is **not** a
> login factor.)
>
> **Recommendation (priority):** Implement MFA for **privileged roles first**
> (`platform_admin`, `internal_admin`, `reviewer`), then `client_admin`. WebAuthn
> or TOTP preferred over SMS. Track as a Statement-of-Applicability deviation for
> ISO 27002 8.5 until closed. **⚠ TO VERIFY** target date.

---

## 5. Authentication information handling (ISO 27002 5.17)

- Passwords are never stored or logged in plaintext; only bcrypt hashes persist
  (`User.password_hash`, `PasswordHistory`).
- Login responses use a **generic 401** for both unknown-email and bad-password,
  and run a dummy bcrypt verify on the unknown branch to keep timing comparable —
  no account-existence oracle.
- Reset-token errors are uniform across "never existed / used / expired" to avoid
  a token-probing oracle.
- 401 responses return a stable generic message rather than echoing JWT-library
  internals (INFRA-6).
- Secrets (`AUTH_JWT_SECRET`, SMTP/Twilio/Meta/Anthropic/R2 credentials) are
  injected via environment (`sync: false` in `render.yaml`) and never committed;
  `.env*` is git-ignored except `.env.example`.

---

## 6. Privileged-access rules (ISO 27002 8.2)

### 6.1 platform_admin vs internal_admin split

- `/platform/*` (the IT console) is gated by a `PlatformUser` dependency so an
  IT-only `platform_admin` can provision ordinary client/provider accounts and
  run the audit-log explorer **without** holding the full compliance-operations
  surface that `internal_admin` carries.
- This is an intentional duty separation: IT administration is fenced off from
  day-to-day compliance review.

### 6.2 ADMIN-1 escalation guard

`_assert_can_grant_role` (`apps/api/app/api/v1/admin.py`) enforces that **only a
full `internal_admin` may create or grant a privileged role** (`internal_admin`
or `platform_admin`). Rationale: without it, a pure `platform_admin` could mint
itself `internal_admin` and reach the entire compliance surface — a self/lateral
privilege escalation. This guard was hardened in the 2026-06-15 security audit
(HIGH finding ADMIN-1). Granting non-privileged roles (`client_admin`,
`reviewer`) remains available to platform admins.

### 6.3 Reviewer cross-tenant scope — accepted, audited risk

- The `reviewer` role validates documents **across all tenants by design** — it is
  the human-review backbone of the compliance product and cannot be tenant-scoped
  without breaking the service model.
- **Risk acceptance:** This is a deliberate, documented exception to the
  tenant-isolation principle (§1). It is mitigated by: (a) every reviewer action
  being written to the append-only audit log with actor + IP + user-agent
  (migration 0043), and (b) the reviewer surface being read/validate-only, not
  tenant-administrative.
- **Owner:** acting CISO. **Review:** re-affirm each quarterly access review (§7).
  **⚠ TO VERIFY** that reviewer headcount is minimized and that reviewer accounts
  are MFA-protected once §4.5 is closed.

### 6.4 Privileged-access general rules

- Privileged actions are auditable (append-only `audit_log`, IP+UA captured).
- Privileged roles are granted to named individuals only — **no shared admin
  accounts** (**⚠ TO VERIFY** in the quarterly review).
- The cross-tenant administrative surface is the smallest set of people necessary
  (`platform_admin` for IT tasks, `internal_admin` for compliance ops).

---

## 7. Periodic access-review procedure (ISO 27002 5.18)

**Cadence:** quarterly (and on any departure or role change for the affected
account out-of-cycle).

**Steps:**
1. Export the current membership roster (all `Membership` rows with
   `status = 'active'`, joined to `User` email + `status` + `last_login_at`).
   Persist the export under `docs/compliance/evidence/access-reviews/`.
2. For each **privileged** holder (`platform_admin`, `internal_admin`,
   `reviewer`), confirm the role is still required. Revoke immediately if not.
3. Confirm there are no active accounts for departed staff/customers (cross-check
   against HR/customer-offboarding). Disable or soft-delete as appropriate.
4. Confirm no shared/generic accounts exist.
5. Spot-check the audit-log explorer for any privileged grant since the last
   review and confirm each was authorized.
6. Record results in the log template below; the reviewer signs off.

**Review log template** (one row per review cycle):

| Review date | Reviewer | Total active accounts | Privileged accounts (PA/IA/Rev) | Accounts revoked/disabled | Soft-deletes actioned | Anomalies found | Sign-off |
|---|---|---|---|---|---|---|---|
| YYYY-MM-DD | | | / / | | | | |

**Per-account exception register** (carry deviations forward):

| Account (email) | Role(s) | Justification | Approved by | Next re-confirm |
|---|---|---|---|---|
| | | | | |

---

## 8. Known gaps and deviations (summary)

| ID | Gap | ISO ref | Status |
|---|---|---|---|
| GAP-MFA | No MFA for any role (single-factor login) | 8.5 | **Open** — privileged roles first; **⚠ TO VERIFY** target date |
| GAP-REVOKE | No server-side JWT denylist / immediate global revocation | 5.18 | Mitigated by 24h TTL + account disable; **⚠ TO VERIFY** acceptable |
| GAP-PURGE | Hard-purge of soft-deleted users deferred (FK cascade missing) | 5.18 | Deferred; **⚠ TO VERIFY** |
| GAP-RL | In-memory rate limiter requires single worker until `REDIS_URL` set | 8.5 | Operational; **⚠ TO VERIFY** worker count |
| GAP-INVITE | Tokenized invite-link flow not confirmed (temp-password path) | 5.16 | **⚠ TO VERIFY** |

---

*End of CW-ISO-access-control v0.1 (draft).*
