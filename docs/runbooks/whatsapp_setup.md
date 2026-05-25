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

## Step 1 — Submit the two templates for approval

Meta requires every outbound utility message to use a pre-approved
template. The canonical submission payload lives at
[`docs/runbooks/whatsapp_templates.json`](./whatsapp_templates.json).
The two templates are:

| Name | Category | Used by |
|---|---|---|
| `cw_renewal_threshold` | UTILITY | Renewal cron at 30 / 14 / 7 / 0 / -7 / -14 / -21 / -28 day thresholds |
| `cw_reviewer_decision` | UTILITY | Reviewer decision (approved / rejected / needs clarification) |

To submit:

1. Open **Meta Business Manager** → **WhatsApp Manager** → **Account
   tools** → **Message templates**.
2. Click **Create template** → **Utility**.
3. Paste each template's name, language (`es_MX`), body text, and
   footer from `whatsapp_templates.json`. Meta's UI accepts the JSON
   shape inline for examples — copy them verbatim so the variable
   ordering matches what the code sends.
4. Submit. Approval is usually 24-48 hr. Templates start in
   `PENDING_REVIEW`; once they flip to `APPROVED` you can flip the
   `WHATSAPP_ENABLED` env var on the API.

If Meta rejects a template, edit the body to match their feedback
(typically: too promotional, too short, missing context). Don't change
the variable count or order without also updating
`whatsapp_templates.py` — the parameters are positional.

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

## Step 4 — Flip the kill switch

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

Restart the API. The next renewal cron fire will start sending
WhatsApp to users whose `contact_preference` is `whatsapp` or `both`,
provided their `User.phone` is set.

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

Every send (success, skip, failure) writes one audit row:

- `action = "whatsapp.transactional_sent"`
- `entity_type = "submission" | "provider_workspace" | "client"`
- `metadata.status` = `sent | skipped_disabled | skipped_no_recipient
  | skipped_not_configured | skipped_dry_run | skipped_phone_missing
  | skipped_preference_excludes_whatsapp | failed`
- `metadata.template` = template name
- `metadata.error` = Meta's error body when `status == "failed"`

Filter the audit log by this action to see delivery health.

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
