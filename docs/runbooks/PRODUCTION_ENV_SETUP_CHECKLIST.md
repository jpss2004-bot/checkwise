# Production environment setup checklist

**Audience:** Jose Pablo (operator). Render dashboard work.
**Estimated time:** 15-20 minutes including verification.
**Last updated:** 2026-05-25 (post sale-readiness audit).
**Related:** [SALE_READINESS_BUYER_DOSSIER_2026-05-25.md](../audits/SALE_READINESS_BUYER_DOSSIER_2026-05-25.md) §7 lists these as the three blockers between the current state and the first paying pilot.

This checklist resolves the three production-environment blockers
identified by both the internal sale-readiness audit and the
parallel backend hardening pass. None of these require a code
change — they are Render dashboard env-var operations.

Work in the order listed. **Do not skip the verification step
under each section.**

---

## 1. AUTH_JWT_SECRET — must be a strong random value

### Why

The repo ships with a placeholder default
`"checkwise-local-dev-secret-change-me-please-min-32-chars"` in
`apps/api/app/core/config.py:47`. If the Render env value is ever
unset, the API silently boots with the placeholder. Anyone reading
the public repo can mint valid JWTs and impersonate any user.

### What to do

1. Open the Render dashboard → `checkwise-api` service →
   **Environment** tab.
2. Find `AUTH_JWT_SECRET`.
3. If the value is empty, missing, or matches the placeholder
   above:
   - On your laptop, run: `openssl rand -hex 32`
   - Paste the 64-character hex output as the new
     `AUTH_JWT_SECRET` value.
   - Click **Save Changes**.
   - Render automatically redeploys.

### Verification

After the redeploy completes (~2-3 minutes):

```bash
# Expect HTTP 401 with "Invalid credentials" (any login attempt with a
# placeholder-minted token would have been accepted; this confirms
# the secret rotated).
curl -X POST https://checkwise-api.onrender.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"x"}'
```

If you have existing JWT tokens in any browser, they will be
invalidated by the rotation. Tell early users to log in again
(one-time cost).

---

## 2. SMTP_* — transactional email delivery

### Why

Three features depend on SMTP being configured: password reset,
reviewer-decision emails (shipped 2026-05-25), and renewal-reminder
emails (shipped 2026-05-25). Without these env vars, all three
silently no-op with `smtp_not_configured` and the pilot customer
sees only in-app notifications. The Audit Log records the
"skipped" status so you can confirm later that nothing went out.

### What to do

You need SMTP credentials for the outbound mailbox (the address
that emails appear FROM). Common options for Mexican operators:

- **Gmail Workspace SMTP** — `smtp.gmail.com:587`, STARTTLS, app
  password.
- **SendGrid** — `smtp.sendgrid.net:587`, API-key as password.
- **Postmark** — `smtp.postmarkapp.com:587`, server-token as both
  user and password.
- **AWS SES** — `email-smtp.us-east-1.amazonaws.com:587` (or your
  region), IAM SMTP credentials.

For each, set these env vars on the same Render Environment tab:

| Key | Value (example for Postmark) | Notes |
|-----|------------------------------|-------|
| `SMTP_HOST` | `smtp.postmarkapp.com` | Provider's documented SMTP host |
| `SMTP_PORT` | `587` | 587 for STARTTLS, 465 for SSL |
| `SMTP_USERNAME` | `<provider-username>` | Server-token for Postmark, API-key for SendGrid, mailbox address for Gmail |
| `SMTP_PASSWORD` | `<provider-password>` | Sensitive; this is the only field whose value goes through `sync: false` |
| `SMTP_FROM_EMAIL` | `noreply@checkwise.mx` | Address that appears in the From: header |
| `SMTP_FROM_NAME` | `CheckWise` | Display name in the From: header |
| `SMTP_USE_TLS` | `true` | Use STARTTLS on port 587 |
| `SMTP_USE_SSL` | `false` | Set true ONLY if using port 465 |

Click **Save Changes**. Render redeploys.

### Verification

Trigger a real forgot-password flow:

1. Open `https://checkwise-six.vercel.app/login` (or the new prod
   hostname once configured per §3 below).
2. Click "Olvidé mi contraseña".
3. Enter the operator's own email (e.g. `jsamano@legalshelf.mx`).
4. Submit.
5. Check the inbox for an email "Restablece tu contraseña de
   CheckWise" within 60 seconds.

If the email lands → SMTP is correctly configured.
If not → check Render service logs for the most recent
`POST /api/v1/auth/forgot-password` and read the SMTP error.

Then trigger one reviewer decision against a seeded submission
(internal_admin account) to confirm the new transactional path
delivers too. Look in the `audit_log` table for action
`email.transactional_sent` and status `sent`.

---

## 3. FRONTEND_BASE_URL — email CTA links

### Why

The transactional email helper builds CTA URLs by prefixing
`settings.FRONTEND_BASE_URL` to the path. Default is
`http://localhost:3000`. If unset on Render, every email that
makes it out has dead localhost links.

### What to do

1. On the same Environment tab, add a new variable:
   - Key: `FRONTEND_BASE_URL`
   - Value: the production frontend URL **without trailing slash**.
     Today: `https://checkwise-six.vercel.app` (or the chosen final
     hostname like `https://app.checkwise.mx` once the DNS cutover
     happens).
2. Click **Save Changes**. Render redeploys.

### Verification

After the SMTP test above succeeds, open the email and inspect
the CTA link. It should start with the production hostname,
never `localhost`. If wrong, fix the value and re-trigger.

### Note on Vercel

If you cut over to a custom domain (e.g. `app.checkwise.mx`),
update **two** things in addition to the DNS record:

- `FRONTEND_BASE_URL` here on Render.
- `CORS_ORIGINS` on Render — add the new origin to the
  comma-separated list. Otherwise the frontend will hit CORS
  errors on every API request.

---

## 4. Verify no demo accounts exist on production

### Why

The repo has documented demo passwords for four accounts
(`ada@legalshelf.mx`, `cliente.demo@checkwise.mx`,
`boss.demo@checkwise.mx`, `proveedor.demo@checkwise.mx`). The
audit confirmed (by login attempt) that all four are now
invalid in production. Re-confirm so you can sign the buyer
dossier with confidence.

### What to do

```bash
# Each should return HTTP 401 "Invalid credentials". If ANY returns
# HTTP 200, escalate immediately: a demo account is still active.
for email in ada@legalshelf.mx cliente.demo@checkwise.mx \
             boss.demo@checkwise.mx proveedor.demo@checkwise.mx; do
  echo "=== $email ==="
  case $email in
    ada@legalshelf.mx) pw='(rotated 2026-05-18 · ask operator)' ;;
    cliente.demo@checkwise.mx) pw='(rotated 2026-05-18 · ask operator)' ;;
    boss.demo@checkwise.mx) pw='(rotated 2026-05-18 · ask operator)' ;;
    proveedor.demo@checkwise.mx) pw='(rotated 2026-05-18 · ask operator)' ;;
  esac
  curl -sS -X POST https://checkwise-api.onrender.com/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$email\",\"password\":\"$pw\"}" \
    -o /dev/null -w "HTTP %{http_code}\n"
done
```

All four MUST return `HTTP 401`. If any returns `HTTP 200`, sign in
to that account, rotate its password, and document the rotation.

---

## 5. Verify the JWT secret rotation worked end-to-end

After steps 1-4 are complete:

1. Log in to the platform via the frontend as the operator
   account.
2. Open the browser DevTools → Application → Local Storage →
   `checkwise.admin.session.v1` (or `client.session` /
   `portal.session` per the persona).
3. Copy the `access_token` value. Decode the header at
   [jwt.io](https://jwt.io) — confirm `alg: HS256` and a recent
   `iat` timestamp.

If everything looks normal, the production environment is set up
correctly.

---

## Roll-back

All four operations above are env-var changes only. Roll-back is:

1. Remove or revert the env var on the Render dashboard.
2. Wait for the automatic redeploy.

Nothing in the database or storage changes. Roll-back is
instant and lossless.

---

## What this checklist does NOT cover

- **Custom domain DNS cutover** to `app.checkwise.mx` — handled by
  your DNS provider + Vercel. Once cut over, update
  `FRONTEND_BASE_URL` and `CORS_ORIGINS` here.
- **WhatsApp transactional outbound** — still blocked on the
  actual WhatsApp Business number. Out of scope until you provide
  it.
- **Stripe / payment integration** — out of scope for this
  checklist; pre-pilot, payment is handled out of band.
- **R2 bucket lifecycle / backup retention** — already configured
  via Cloudflare R2 versioning; no Render env change needed.

---

## Sign-off

When all five sections are green, the production environment is
ready for the first paying pilot per the audit verdict in
`docs/audits/SALE_READINESS_BUYER_DOSSIER_2026-05-25.md` §7.
Mark this complete in your operator log with the timestamp and
the new commit SHA being deployed.
