# CheckWise — Operator Runbook v1

**Audience:** Jose Pablo (operator) + future ops handoff.
**Goal:** one document covering every Render-dashboard or CLI
operation needed to run CheckWise in production — from the first
deploy through key rotation, force-logout, cron replay, and incident
response.

**Status:** v1 cuts on 2026-05-25 ahead of the first paying-pilot
freeze. Update the "Last verified" date at the bottom of each
section after every prod ops event.

---

## Table of contents

1. [First deploy + env vars](#1-first-deploy--env-vars)
2. [Health checks + smoke probes](#2-health-checks--smoke-probes)
3. [Key rotation (`AUTH_JWT_SECRET`, SMTP, R2)](#3-key-rotation)
4. [Force-logout one user](#4-force-logout-one-user)
5. [Renewal cron — replay + dry-run + skip](#5-renewal-cron)
6. [Audit-package export](#6-audit-package-export)
7. [Backup + restore](#7-backup--restore)
8. [Incident response one-pager](#8-incident-response-one-pager)

---

## 1. First deploy + env vars

The complete env-var paste sequence with verification commands lives
in [PRODUCTION_ENV_SETUP_CHECKLIST.md](PRODUCTION_ENV_SETUP_CHECKLIST.md).
Work through it once, in order, before the tester touches prod.

**Quick reference — the env vars the service refuses to start
without (P4-01 boot guard, audit 2026-05-25):**

| Env var | Source | Block-boot if missing? |
|---|---|---|
| `AUTH_JWT_SECRET` | `openssl rand -hex 32` | ✅ yes (refuses placeholder) |
| `DATABASE_URL` | Neon pooled endpoint | ✅ yes (alembic boot fails) |
| `DIRECT_DATABASE_URL` | Neon direct endpoint | ✅ yes (alembic boot fails) |
| `FRONTEND_BASE_URL` | `https://app.checkwise.mx` | ⚠️ warns at boot |
| `SMTP_HOST` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM_EMAIL` | Mail provider | silently no-ops outbound email |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `STORAGE_BUCKET` | Cloudflare R2 | document upload fails |
| `ANTHROPIC_API_KEY` | Anthropic Console | reports fall back to mock LLM |
| `SLACK_BOT_TOKEN` / `SLACK_FEEDBACK_CHANNEL_ID` | Slack app | "Reportar problema" persists rows but no Slack delivery |

The other env vars in `render.yaml` (`SLACK_CONTACT_WEBHOOK_URL`,
`SLACK_CORRECTION_WEBHOOK_URL`, `SUPPORT_WHATSAPP_URL`,
`CHECKWISE_LLM_BACKEND`) are optional — features that depend on
them degrade gracefully when empty.

**Last verified:** 2026-05-25.

---

## 2. Health checks + smoke probes

After every deploy, run these in order. Each takes <1 minute.

```bash
# 1. Render health-check (also gates the deploy itself).
curl -fsS https://checkwise-api.onrender.com/health
# expect: {"status":"ok"}

# 2. DB connectivity through the API.
curl -fsS https://checkwise-api.onrender.com/api/v1/health/db
# expect: {"database":"ok"}

# 3. Auth returns Spanish errors (M2 contract).
curl -fsS -X POST https://checkwise-api.onrender.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"ghost@example.com","password":"x"}'
# expect: 401 with detail "Credenciales inválidas."

# 4. /docs is gated off in prod (audit P4-11 NOTE).
curl -fsS -o /dev/null -w "%{http_code}\n" \
  https://checkwise-api.onrender.com/docs
# expect: 404
```

If any of these fail, **do not promote** the new build. Roll back
via the Render dashboard → service → **Manual Deploy** → pick the
previous successful commit.

---

## 3. Key rotation

### 3.1 `AUTH_JWT_SECRET`

Rotate when:
- A staff laptop with the value pasted in it is lost / stolen.
- Quarterly hygiene (recommended cadence).
- After a suspected token leak.

Steps:

```bash
# 1. Mint a new value locally.
openssl rand -hex 32

# 2. Render dashboard → checkwise-api → Environment → edit
#    AUTH_JWT_SECRET → paste the new value → Save Changes.

# 3. Render redeploys automatically. The boot guard verifies the
#    value is NOT the in-code placeholder (P4-01).

# 4. ALL existing JWTs become invalid on the next request. Every
#    logged-in user is force-logged-out at their next API call —
#    they re-login and get a new token signed by the new secret.
```

This is the global force-logout button. There is no per-user revoke
today; rotating the secret is how you invalidate one user's
session (it invalidates everyone, but the cost is one round of
re-login for active users).

### 3.2 SMTP credentials

If the SMTP provider rotates the password (Gmail app-password
expiration, SendGrid key rotation, etc.):

1. Mint the new credential in the provider's console.
2. Render dashboard → `checkwise-api` → Environment → update
   `SMTP_PASSWORD` (and `SMTP_USERNAME` if it changed).
3. Save → Render redeploys.
4. Verify by triggering a forgot-password flow and confirming the
   email lands.

### 3.3 R2 credentials

Mirror the SMTP flow. Update `AWS_ACCESS_KEY_ID` +
`AWS_SECRET_ACCESS_KEY` in the dashboard. Verify by uploading a
document via the portal and confirming it lands in the R2 bucket.

---

## 4. Force-logout one user

There is no per-user "kill session" endpoint today. Three escape
hatches, ordered by blast radius:

1. **Disable the User row** — `UPDATE users SET status='disabled'
   WHERE id='<user_id>'`. The next request from that user's JWT
   resolves the row, sees `status != "active"`, and returns
   `401 Tu sesión ya no está activa.` Other users unaffected.

2. **Set `must_change_password=true`** — `UPDATE users SET
   must_change_password=true WHERE id='<user_id>'`. The next
   request from that user resolves their row, hits the gate from
   commit `0d040f6`, and returns `403 Debes establecer una nueva
   contraseña antes de continuar.` The user can still hit
   `/auth/me` + `/auth/set-password` (the allow-list), so this is
   "force them to rotate their own password" rather than
   "lock them out".

3. **Rotate `AUTH_JWT_SECRET`** — see §3.1. Force-logs out
   everyone.

Pick the narrowest tool that resolves the incident.

---

## 5. Renewal cron

Daily Render cron at `0 14 * * *` UTC (08:00 CDMX). Full operational
detail in [`../RENEWAL_OPS.md`](../RENEWAL_OPS.md); the key facts:

- The cron is **idempotent**. The unique constraint on
  `renewal_reminders(workspace_id, requirement_code,
  cycle_anchor_date, threshold_days)` makes a repeat run on the
  same day a no-op.
- **Catch-up is automatic.** A missed day fires every threshold
  that crossed since the last successful run on the next run. No
  reminders are silently dropped.
- The dispatcher exits 0 on success. Render emails the project
  owner on any non-zero exit.

### Replay after a failure

```bash
# From a Render shell (easiest path):
python -m scripts.run_renewal_dispatch
```

### Dry-run before a real run

```bash
python -m scripts.run_renewal_dispatch --dry-run
# Rolls back the session — no rows inserted, no notifications
# written. Logs what WOULD have fired.
```

### Preview a future / past date

```bash
python -m scripts.run_renewal_dispatch --today 2026-12-01 --dry-run
```

### Manual one-shot write (CLI)

```bash
python -m scripts.write_renewal_reminder \
  --workspace-id <ws_id> \
  --requirement-code REC-CSF-... \
  --threshold-days 30
# Useful only for tests; the daily cron is the right channel.
```

---

## 6. Audit-package export

For a pilot customer asking "show me everything you have on
vendor X" — single command pulls every approved document for one
client across every period and bundles them as a ZIP with a
manifest.

**Endpoint:** `GET /api/v1/client/audit-package.zip?client_id=<id>`
(client_admin or internal_admin).

**Cap:** 200 files / 500 MB per export. Hit the cap → API returns
`413` with a Spanish message pointing the user at support for a
segmented download.

**Filter shape:**

```
GET /api/v1/client/audit-package.zip
    ?client_id=<id>
    &period_start=2026-01-01     (optional, ISO date)
    &period_end=2026-12-31       (optional, ISO date)
    &institutions=imss,infonavit (optional, csv of institution codes)
    &skip_manifest=true          (optional, debug only)
```

**Tenant gate:** `_resolve_client_id` (cross-tenant probes return
403 — verified by `test_cross_tenant_audit_package_zip_returns_403`).

**Audit-log row** lands per export with the exact filter dict so
forensic readers can replay who pulled what and when.

---

## 7. Backup + restore

### Backup

Neon Postgres handles continuous backup automatically. The free /
launch tiers keep ~7 days of point-in-time restore. The pilot tier
extends that depending on the Neon plan. Verify the retention
window in the Neon dashboard before the first paying pilot.

R2 documents are not currently versioned. A deletion is permanent
within R2 unless object versioning is enabled — recommend enabling
it in the Cloudflare R2 console for the production bucket before
the first paying pilot (`Settings → Object versioning → Enable`).

### Restore

**Database** — Neon dashboard → `checkwise-prod` → Branches → New
branch → from point in time. Validate by pointing a local API at
the branch's `DATABASE_URL`, run smoke probes (§2), then cut the
production `DATABASE_URL` to the restored branch.

**Documents (R2)** — if versioning is enabled, restore via the
Cloudflare console. If not, the only recourse is whatever
`audit-package.zip` exports a customer happened to pull recently.

---

## 8. Incident response one-pager

When something goes wrong in prod. Severity terms:

- **SEV-1** — data loss or cross-tenant leak suspected, OR the API
  is down for all users, OR a credential leak is confirmed.
- **SEV-2** — one feature broken (uploads, reports, email) but
  rest of the system serves users.
- **SEV-3** — cosmetic / one user affected.

### First 5 minutes (all SEVs)

1. **Stop making it worse.** Don't merge anything to `main` until
   you have a hypothesis.
2. **Confirm the symptom.** Hit `/health` and `/health/db`. If
   either returns 5xx, jump to "API down" below.
3. **Open the Render logs** → `checkwise-api` → Logs. Filter on
   ERROR level. Capture the most recent stack trace.

### SEV-1 playbook

- **Cross-tenant leak suspected** — get evidence (URL, request
  payload, response). Force-logout via `AUTH_JWT_SECRET` rotation
  (§3.1) — this buys you a clean state while you investigate.
  Don't delete data; the audit log row is your forensic record.
- **Credential leak confirmed** — rotate every affected key
  immediately (`AUTH_JWT_SECRET`, R2, SMTP, Anthropic). Pull the
  Slack channel logs to confirm no exfil.
- **API down for all users** — Render → Manual Deploy → previous
  successful commit. Document the failing commit's SHA before
  rolling back so the fix lands as a separate clean commit.

### SEV-2 playbook

- **Email not delivering** — check
  `audit_log.delivery_status='smtp_not_configured'` rows in the
  last hour. If present, the SMTP env vars are unset; jump to §3.2.
  If absent, the SMTP provider is rejecting — open their dashboard.
- **Uploads failing** — check R2 credentials (§3.3). Check the
  413 response detail; a UI showing 400 instead of 413 is a
  regression of M3.
- **Reports rendering blank** — `ANTHROPIC_API_KEY` may be unset
  → falls back to mock LLM. Verify in Render env. Reports
  generated with the mock have an honest banner in the UI.

### SEV-3 playbook

Open an issue, schedule a fix for the next sprint. No emergency
rollback.

### Post-incident

Write a one-page postmortem within 72 hours. Template:

```
# Incident YYYY-MM-DD — <one-line summary>

## Timeline (CDMX time)
HH:MM  <observation>
HH:MM  <action>
HH:MM  <resolved>

## Root cause
<2-3 sentences>

## Blast radius
<who saw the bug, for how long, what data — if any — was affected>

## Detection
<how we noticed; what would have caught it sooner>

## Fix
<commit SHA + one-line summary>

## Prevention
<what test / monitor / runbook entry would have prevented this>
```

File under `docs/incidents/YYYY-MM-DD-<slug>.md`.

---

**Last verified end-to-end:** 2026-05-25 (initial v1 cut).
**Next review:** before each major version cut, or after any
SEV-1 / SEV-2 incident.
