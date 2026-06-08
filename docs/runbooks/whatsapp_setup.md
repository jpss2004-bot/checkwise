# WhatsApp Cloud API · operator setup

CheckWise can deliver renewal threshold reminders and reviewer-decision
notifications via WhatsApp using Meta's Cloud API direct (no BSP
middleman). The code lands behind `WHATSAPP_ENABLED=false` by default,
so prod stays quiet until you finish the steps below.

This runbook is for the operator. The code-side surface is documented
in [`apps/api/app/services/whatsapp_delivery.py`](../../apps/api/app/services/whatsapp_delivery.py),
[`apps/api/app/services/whatsapp_templates.py`](../../apps/api/app/services/whatsapp_templates.py),
and [`apps/api/app/services/transactional_whatsapp.py`](../../apps/api/app/services/transactional_whatsapp.py).

---

## Prerequisites

- A **Meta Business Account** that owns the WhatsApp Business Account
  (WABA).
- A **verified sender phone number** registered to the WABA. Meta gives
  you a free test number you can use during onboarding, but production
  needs a verified business number with a display name.
- Owner-level access to the WABA in Meta Business Manager.

---

## Step 1 — Submit the three templates for approval

Meta requires every outbound utility message to use a pre-approved
template. The canonical submission payload lives at
[`docs/runbooks/whatsapp_templates.json`](./whatsapp_templates.json).
The three templates are:

| Name | Category | Used by |
|---|---|---|
| `cw_renewal_threshold` | UTILITY | Renewal cron at 7 / 0 / -7 / -14 / -21 / -28 day thresholds (catalog `whatsapp_eligible=true` rows). |
| `cw_reviewer_decision` | UTILITY | Reviewer decision (approved / rejected / clarification requested). |
| `cw_phone_otp` | AUTHENTICATION | `POST /api/v1/me/phone-verification/issue` — the 6-digit OTP code. |

To submit each one:

1. Open **Meta Business Manager** → **WhatsApp Manager** → **Account
   tools** → **Message templates**.
2. Click **Create template** → pick **Utility** (or **Authentication**
   for `cw_phone_otp`).
3. Paste the template's name and language (`es_MX`).
4. Body: copy the body text verbatim from
   [`whatsapp_templates.json`](./whatsapp_templates.json), including
   the `{{1}}`, `{{2}}` … placeholders in order. Meta's UI accepts
   the JSON example block inline — paste the `example.body_text`
   array so reviewers see realistic content.
5. Footer: copy the footer text verbatim.
6. Submit. Approval is usually 24-48 hr. Templates start in
   `PENDING_REVIEW`; once they flip to `APPROVED` they're callable.

If Meta rejects a template, edit the body to match their feedback
(typically: too promotional, too short, missing context). Don't change
the variable count or order without also updating
[`whatsapp_templates.py`](../../apps/api/app/services/whatsapp_templates.py)
— the parameters are positional and the dispatch table in
[`fanout.py`](../../apps/api/app/services/notifications/fanout.py)
hands them to Meta in that exact order.

---

## Step 2 — Mint a long-lived access token

1. In Meta Business Manager → **Business settings** → **System
   users**, create a system user (or reuse one) with the WABA's
   `whatsapp_business_messaging` permission.
2. Generate a token. Pick **Never** for expiration so the cron doesn't
   silently fail in 60 days.
3. Copy the token to `WHATSAPP_ACCESS_TOKEN` on the API server's env.

Meta's docs note that even "never" tokens can be invalidated by an
account admin or by Meta's automated trust signals — set a quarterly
calendar reminder to verify the token still resolves with a manual
`/me` call.

---

## Step 3 — Find the Phone Number ID

WhatsApp Manager → your WABA → **Phone numbers** → click the number →
the URL contains the phone number ID, or copy it from the "Phone
number ID" field on the page.

Set `WHATSAPP_PHONE_NUMBER_ID=<id>` on the API server's env.

---

## Step 4 — Flip the kill switches

There are two switches and they do different things. Flip them in
this order:

### 4a. Enable Meta credentials + the OTP path

```bash
# In apps/api/.env (or your prod env-var store)
WHATSAPP_ENABLED=true
WHATSAPP_DRY_RUN=false
WHATSAPP_PHONE_NUMBER_ID=<phone_id>
WHATSAPP_ACCESS_TOKEN=<system_user_token>
WHATSAPP_API_VERSION=v21.0
WHATSAPP_DEFAULT_LANGUAGE_CODE=es_MX
WHATSAPP_DEFAULT_COUNTRY_CODE=52
```

At this point the **phone-verification OTP** path (`/me/phone-verification/issue`)
starts working — it calls Meta directly and uses `cw_phone_otp`.
The **fanout** (renewal cron, reviewer decisions) still sends via
Twilio SMS, because the native-templates flag below is still off.

### 4b. Reverse the SMS-first cutover

Only do this once `cw_renewal_threshold` AND `cw_reviewer_decision`
both show `APPROVED` in WhatsApp Manager:

```bash
WHATSAPP_NATIVE_TEMPLATES_ENABLED=true
```

Restart the API + both notification crons (renewal + reporting
dispatch on Render). On the next dispatch loop, renewal and
reviewer-decision events ship via native Meta templates instead of
falling through to Twilio SMS. Reporting events (Group B) and
account-invitation events (`account.invitation_sent`) keep flowing
through Twilio because they do not yet have approved Meta
templates; that's intentional and audited via the dispatch row's
`whatsapp_status="sent" backend="twilio"`.

### Rollback

`WHATSAPP_NATIVE_TEMPLATES_ENABLED=false` reverts the fanout to
SMS-first behavior within one restart cycle. `WHATSAPP_ENABLED=false`
on top of that disables Meta entirely (the OTP path will then
return `skipped_disabled` from `send_whatsapp_template`). No code
revert is ever required.

---

## Step 5 — Dry-run before live

To preview what the code would send without actually contacting Meta:

```bash
WHATSAPP_ENABLED=true WHATSAPP_DRY_RUN=true ...
```

In dry-run mode, `send_whatsapp_template` logs the full payload at
`INFO` level under the `checkwise.whatsapp_delivery` logger and
returns a `skipped_dry_run` status. Useful while templates are still
in review.

---

## Audit + observability

Two audit-log signals to monitor, depending on path:

**Legacy transactional path** (still used by the renewal-dispatch
direct callers — being phased out by the unified fabric):

- `action = "whatsapp.transactional_sent"`
- `entity_type = "submission" | "provider_workspace" | "client"`
- `metadata.status` = `sent | skipped_* | failed`
- `metadata.template` = template name
- `metadata.error` = Meta's error body when `status == "failed"`

**Unified fanout path** (active when `WHATSAPP_NATIVE_TEMPLATES_ENABLED=true`):

- `action = "notification.whatsapp_dispatched"`
- `entity_type = "user"`, `entity_id` = recipient user id
- `metadata.event_type` = catalog event_type (e.g. `renewal.threshold.t-0`)
- `metadata.template_name` = Meta template that was attempted
- `metadata.status` = `sent | skipped | failed`
- `metadata.error` = stamping reason or Meta error body
- `metadata.message_id` = Meta `wamid.*` on success
- `metadata.phone_last4` = last four digits of recipient phone
  (PII-safe; full E.164 is never logged in audit metadata)

Twilio SMS sends do NOT write this row — only Meta backend attempts
do. To monitor Meta health, filter the audit log by
`action = "notification.whatsapp_dispatched"` and group by
`metadata.status` + `metadata.template_name`.

---

## Cost notes

- Meta charges per **conversation** (a 24-hour window per recipient),
  not per message, for utility templates. As of late 2025 the Mexico
  utility-template price is roughly MX$1.20–1.50 per conversation.
- The renewal cron at 30 / 14 / 7 / 0 / -7 / -14 / -21 / -28 days
  produces up to 8 conversations per (recipient × requirement × cycle)
  pair. Audit thresholds in `renewal_dispatch.py` if cost becomes an
  issue.
- Reviewer decisions are 1 conversation per decision per recipient.

---

## Rollback

Set `WHATSAPP_ENABLED=false`. The renewal cron and reviewer-decision
path still try to call the dispatcher, the dispatcher returns
`skipped_disabled` immediately, no Meta API request is made, and the
audit log records the skip. No code revert required.
