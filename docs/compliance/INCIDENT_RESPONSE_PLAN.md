---
Document: Incident Response Plan (IRP)
ID: CW-ISO-incident-response
Owner: Lead Engineer / acting CISO (Jose Pablo Samano)
Version: 0.1 (draft)
Effective: 2026-06-16
Review cadence: annual + after any incident or drill
ISO refs: ISO/IEC 27002:2022 5.24, 5.25, 5.26, 5.27, 5.28 (information security incident management); ISO/IEC 27035 (incident management — spirit); supports 27002 5.7 (threat intelligence) and 5.5 (contact with authorities)
Status: DRAFT — ISO-readiness evidence, NOT a certification claim
---

# CheckWise — Incident Response Plan

> **Scope of this document.** This is operational-resilience *evidence* for an
> ISO/IEC 27001-aligned ISMS. It is a draft and does **not** assert that
> CheckWise or LegalShelf hold any ISO certification. It builds on the existing
> operational runbooks and does not supersede them:
> - [`docs/runbooks/OPERATOR_RUNBOOK_V1.md`](../runbooks/OPERATOR_RUNBOOK_V1.md) — §8 already contains an incident one-pager; this plan formalizes and extends it.
> - [`docs/runbooks/PRODUCTION_ENV_SETUP_CHECKLIST.md`](../runbooks/PRODUCTION_ENV_SETUP_CHECKLIST.md) — env-var / secret operations.
> - [`docs/runbooks/STAGING_DEMO_DEPLOY.md`](../runbooks/STAGING_DEMO_DEPLOY.md) — isolated rebuild path.
> - [`render.yaml`](../../render.yaml) — service topology and env-var contract.
> Companion document: [`BACKUP_RECOVERY_BCP.md`](BACKUP_RECOVERY_BCP.md).

---

## 1. Purpose & scope

CheckWise is a **multi-tenant SaaS for Mexican REPSE labor-compliance** operated
by LegalShelf (legalshelf.mx). It stores tenant compliance evidence — vendor
RFCs, social-security numbers (NSS), CSF/REPSE/patronal documents, risk scores —
which qualifies as **personal data** (and partly **sensitive personal data**)
under Mexico's *Ley Federal de Protección de Datos Personales en Posesión de los
Particulares* (LFPDPPP). An incident here can carry both security and regulatory
consequences.

This plan covers any **information security incident** affecting CheckWise
production: confidentiality, integrity, or availability events across the
backend (FastAPI on Render), frontend (Next.js on Vercel), database
(PostgreSQL on Neon), object storage (Cloudflare R2), cron jobs (Render), and
the supplier chain (Neon, R2, Anthropic, SMTP provider, Twilio/Meta, Slack,
Vercel).

It is read **alongside** the Operator Runbook, which holds the exact CLI/dashboard
commands. Where this plan says "rotate `AUTH_JWT_SECRET`," the literal steps live
in Operator Runbook §3.1.

---

## 2. Roles & responsibilities

CheckWise is operated by a very small team; one person holds multiple roles
today. The plan still names each role so a future hire or external responder can
slot in.

| Role | Current holder | Responsibilities during an incident |
|---|---|---|
| **Incident Response Lead (IR Lead)** | Jose Pablo Samano (acting CISO) | Declares the incident + severity, owns the timeline, makes the contain/eradicate/recover calls, owns the post-incident review. Single decision-maker. |
| **Technical Lead** | Jose Pablo Samano (same person today) | Executes Render/Neon/R2/Vercel actions: log pull, secret rotation, snapshot/restore, rollback. Captures evidence. |
| **Communications Lead** | Jose Pablo Samano (same person today) | Drafts internal + tenant + (if needed) regulator-facing comms. Owns the affected-tenant list. |
| **Legal / Privacy counsel** | External — LegalShelf counsel | Consulted for any suspected personal-data breach to decide LFPDPPP notification obligations (see §6). **This plan never substitutes for legal advice.** |
| **Supplier liaison** | IR Lead | Opens support cases with Neon / Cloudflare / Anthropic / Vercel / Twilio when the root cause is upstream. |

> **⚠ TO VERIFY — single-person risk.** Today one person holds IR Lead,
> Technical, and Comms. This is a key-person availability gap. **Action:** name a
> documented backup responder before the first paying pilot scales, and record
> their contact in §3.

---

## 3. Contacts & escalation path

> Store live phone numbers and out-of-band contacts in the operator's password
> manager, **not** in this repo. This table holds roles and channels only.

| Need | Channel / where | Notes |
|---|---|---|
| Declare an incident | Operator decision; log opened under `docs/incidents/` | IR Lead declares. |
| Internal ops alert | Slack `#checkwise-feedback` | Existing ops channel; also where in-app "Reportar" feedback and contact-form intents land. |
| Render (backend/cron) status & support | Render dashboard → service → Logs / Events; Render support | Health, deploy rollback, env vars. |
| Neon (Postgres) support | Neon dashboard → project `checkwise-prod` | PITR, branch snapshots. |
| Cloudflare R2 support | Cloudflare dashboard → R2 | Object recovery, versioning. |
| Anthropic API status | Anthropic Console / status page | AI report degradation. |
| Vercel (frontend) support | Vercel dashboard | Frontend availability. |
| Twilio / Meta WhatsApp | Provider consoles | Messaging outbound. |
| Legal / privacy counsel | LegalShelf counsel (out-of-band) | Engage on suspected personal-data breach. |

**Escalation rule of thumb:** any **SEV1 or SEV2** is declared and worked by the
IR Lead immediately. **SEV1 with suspected personal-data exposure** additionally
triggers the §6 notification workflow and engages counsel **without delay**.

---

## 4. Severity classification (SEV1–SEV4)

Severity drives response speed and who gets pulled in. Pick the **highest**
matching row. (This refines the SEV-1/2/3 terms already in Operator Runbook §8;
SEV4 is added here for tracking low-grade events.)

| Sev | Definition | CheckWise-specific examples | Target first response |
|---|---|---|---|
| **SEV1** | Confirmed or strongly suspected breach of tenant data confidentiality or integrity, **or** total loss of service, **or** confirmed credential compromise. | • **Cross-tenant data exposure** — one tenant can read/author against another tenant's `client_id`/`vendor_id` (cf. the REPORT-1 class of bug, fixed 2026-06-15). • **Credential compromise** — `AUTH_JWT_SECRET`, R2 keys, `DATABASE_URL`, or Anthropic key leaked. • **Document-store breach** — unauthorized read/exfil of R2 evidence objects. • **Ransomware / destructive action** against Neon or R2. • **Prolonged full outage** — `/health` 5xx for all users. | **Immediate.** Declare, page IR Lead, start the clock. |
| **SEV2** | One major capability broken; rest of system serves users. No confirmed data exposure. | • Uploads failing (R2 creds/quotas). • Reports blank (`ANTHROPIC_API_KEY` unset → mock LLM). • Transactional email not delivering (`smtp_not_configured`). • Renewal/reporting cron failing repeatedly. • A single **supplier degraded** (e.g. Neon read-latency spike, Anthropic 5xx) without data loss. | Same business day. |
| **SEV3** | Localized / cosmetic; a single user or non-critical path affected. | • One user locked out (lockout cooldown). • Single tenant sees a rendering glitch. • A non-critical Slack delivery skipped. | Next sprint; no emergency rollback. |
| **SEV4** | Near-miss, low-grade anomaly, or security observation with no current impact. | • Suspicious-but-blocked login pattern in the audit log. • A latent finding from a security pass with no live trigger. • Single spurious 5xx. | Log + track; fold into hardening backlog. |

> A **supplier breach** (Neon / R2 / Anthropic / Vercel / Twilio / SMTP) is
> classified by *impact on CheckWise data*, not by where it happened: confirmed
> exposure of our tenant data via a supplier = **SEV1**; supplier degradation
> with no data impact = **SEV2**.

---

## 5. Incident lifecycle (detect → triage → contain → eradicate → recover → review)

The phases below map to ISO 27035 / 27002 5.24–5.27. Each lists **concrete
CheckWise actions**; literal commands live in the Operator Runbook sections cited.

### 5.1 Detect
- **Signals:** Render deploy/health alerts; Render emails the project owner on any
  **non-zero cron exit** (renewal/reporting dispatch); failed health probes
  (`/health`, `/api/v1/health/db` — Operator Runbook §2); user/tenant report via
  in-app **"Reportar"** → Slack `#checkwise-feedback`; anomalies in the
  **append-only audit log** (`audit_log` table — login success/failure with IP/UA,
  report and share events, admin actions); supplier status pages.
- **Action:** capture the raw signal (screenshot, log line, request payload) before
  touching anything.

### 5.2 Triage
- Confirm the symptom: hit `/health` and `/api/v1/health/db`. If either is 5xx →
  treat as availability incident.
- Open **Render → checkwise-api → Logs**, filter `ERROR`, capture the most recent
  stack trace (Operator Runbook §8 "First 5 minutes").
- Assign **severity (§4)**. Declare the incident, open the incident log record
  (§8), start the timeline (CDMX time).
- **Stop making it worse:** do not merge to `main` until there is a hypothesis
  (Operator Runbook §8).

### 5.3 Contain
Goal: stop the bleeding without destroying evidence.
- **Cross-tenant exposure suspected** → capture evidence (URL, request body,
  response), then **rotate `AUTH_JWT_SECRET`** (Operator Runbook §3.1) to force a
  clean global re-auth while investigating. **Do not delete data** — the audit-log
  row is the forensic record.
- **One compromised account** → use the narrowest tool (Operator Runbook §4):
  disable the `User` row (`status='disabled'` → next request gets
  `401 Tu sesión ya no está activa.`), or force a password rotation
  (`must_change_password=true`). Account-lockout (`AUTH_LOCKOUT_THRESHOLD=5`,
  `AUTH_LOCKOUT_MINUTES=15`) already throttles online guessing.
- **Credential leak** → rotate the affected secret(s) on Render immediately
  (`AUTH_JWT_SECRET`, R2 `AWS_*`, SMTP, `ANTHROPIC_API_KEY`, `DATABASE_URL` /
  `DIRECT_DATABASE_URL`) — Operator Runbook §3. Treat the leaked value as burned.
- **Destructive action on data** → **do not delete or overwrite.** Immediately
  take/confirm a **Neon snapshot/branch** and note the last-known-good timestamp
  for PITR (see BCP). For R2, check object-versioning state before any cleanup
  (⚠ contradiction — see §9).
- **Full outage** → roll back via **Render → Manual Deploy → previous successful
  commit**; record the failing commit SHA first.
- **Supplier incident** → open the supplier support case; throttle/disable the
  dependent feature if it is amplifying impact (e.g. Anthropic down → AI reports
  degrade to the mock backend by design; confirm the honest in-UI banner shows).

### 5.4 Eradicate
- Identify and remove the root cause: the offending commit, a misconfiguration, a
  leaked credential's blast radius, or a supplier-side fix.
- Land the fix as a **separate clean commit** (do not bury it in the rollback) and
  deploy through the normal gate (migrations run via `preDeployCommand`; snapshot
  Neon first if the fix carries a migration — see BCP).
- Confirm leaked credentials are fully rotated everywhere they appear
  (web + both crons share several `sync: false` vars in `render.yaml`).

### 5.5 Recover
- Restore service and/or data: redeploy the fixed build; restore Neon to a clean
  point if data integrity was hit (procedure in BCP §4); restore R2 objects if
  versioning permits (⚠ §9).
- Run the **smoke probes** (Operator Runbook §2): `/health`, `/api/v1/health/db`,
  a login returning the Spanish `401`, and `/docs` returning `404` in prod.
- Re-enable any feature throttled during containment. Confirm cron idempotency/
  catch-up behaved (renewal/reporting crons are idempotent and self-catch-up per
  `render.yaml`).
- Communicate "resolved" to affected tenants per §6.

### 5.6 Post-incident review (PIR)
- Write a **one-page postmortem within 72 hours** using the template already in
  **Operator Runbook §8 "Post-incident"**, filed under
  `docs/incidents/YYYY-MM-DD-<slug>.md`.
- The PIR must cover: timeline, root cause, blast radius (who/what data/how long),
  detection (and what would have caught it sooner), fix (commit SHA), and
  **prevention** (a new test, monitor, or runbook entry).
- Feed prevention items into the security/hardening backlog
  (cf. `_handoff/audit-security-perf-2026-06-15.md`). Update **this plan** and the
  runbooks if the response revealed a gap (ISO 27002 5.27 — learning from incidents).

---

## 6. Data-breach notification (LFPDPPP)

> **This section is operational guidance, not legal advice. For any suspected
> personal-data breach, engage LegalShelf counsel before deciding whether,
> whom, and when to notify. Counsel makes the call.**

CheckWise processes personal data (vendor RFCs, NSS, contact data) and some
sensitive data on behalf of tenant *responsables*; LegalShelf generally acts as an
**encargado / co-controller** depending on the contract. Mexico's **LFPDPPP**
(DOF 5-jul-2010) and its Reglamento (DOF 21-dic-2011) impose security and breach
obligations; the relevant provisions include **Art. 19/20 LFPDPPP** (security
duties and the duty to inform affected data subjects of breaches that materially
affect their rights, *without delay* once confirmed) and **Reglamento Art. 61–66**
(security measures and breach-handling). The supervisory authority lineage is the
former IFAI/INAI (see `docs/legal/references.md`).

**Operational workflow when a personal-data breach is suspected (SEV1):**

| Step | Action | Owner |
|---|---|---|
| 1 | Preserve evidence (§7) and contain (§5.3). | Technical Lead |
| 2 | Determine **what data, whose, how much, how long exposed** — reconstruct from the append-only `audit_log` (`entity_type`/`entity_id`/`actor_id`/IP/UA) and Render/Vercel logs. | IR Lead |
| 3 | **Engage counsel immediately.** Provide the §2 facts. Counsel decides notification obligations + timing under LFPDPPP. | Comms Lead + counsel |
| 4 | Notify the affected **tenant(s)** (the *responsables*) per contract — they may have their own downstream duties to their data subjects and to the authority. | Comms Lead |
| 5 | If counsel directs, support tenant/authority notifications with the factual record (cause, affected data, corrective + preventive measures). | IR Lead |
| 6 | Record all notifications and timings in the incident log (§8). | IR Lead |

> **⚠ TO VERIFY / RECONCILE.** The production privacy notice
> (`docs/legal/aviso-de-privacidad-v2.md`) commits to an *"bitácora de auditoría
> inmutable"* and reasonable security measures but does **not** spell out a breach-
> notification procedure, and `docs/legal/references.md` does not yet cite the
> LFPDPPP breach articles explicitly. **Action:** have counsel confirm the exact
> notification triggers/wording and align the privacy notice + DPA with this plan.

---

## 7. Evidence preservation

Forensic integrity matters for both root-cause analysis and any LFPDPPP/legal
process. **Preserve before you remediate** wherever containment allows.

| Source | What it gives you | How to capture | Retention |
|---|---|---|---|
| **Append-only audit log** (`audit_log` table) | Who did what, when, from which IP/UA: login success/failure, report create/patch/generate, share mint/consume/revoke, admin actions, audit-package exports (with the exact filter dict). `before`/`after` JSON on mutations. | Query by `entity_type`+`entity_id` (indexed) or `actor_id` (indexed); export the relevant rows to the incident folder. **Do not delete or mutate rows** — the table is append-only by design (privacy notice commits to its immutability). | Lifetime of the table; snapshot the relevant rows into the incident record. |
| **Render logs** (`checkwise-api`, both crons) | Stack traces, request lines, deploy/rollback events, cron exit codes. | Render dashboard → service → Logs; copy the relevant window into the incident folder (Render log retention is finite — capture early). | Capture immediately; Render retention is limited. |
| **Vercel logs** (frontend) | Edge/SSR errors, request provenance for the web tier. | Vercel dashboard → project → Logs. | Capture immediately. |
| **R2 access** | Object reads/writes/deletes on the evidence bucket. | Cloudflare R2 dashboard / access logs (⚠ confirm access logging is enabled — see §9). | Capture immediately. |
| **Neon** | PITR window + branch snapshots = a forensically clean point-in-time copy of the DB *as of* the incident. | Create a Neon branch at the incident timestamp **before** any restore overwrites state. | Per Neon plan retention (⚠ confirm window — see BCP). |
| **Deploy provenance** | The exact commit live at incident time. | `render.yaml` autodeploys `main`; record the SHA from Render → Events. | In the incident record. |

**Chain-of-custody note:** record who pulled which evidence and when, in the
incident log timeline. Keep evidence copies in the incident folder under
`docs/incidents/` (or a restricted store if it contains personal data — do **not**
commit personal data to git).

---

## 8. Incident log & records

**Where records live:** one Markdown file per incident under
`docs/incidents/YYYY-MM-DD-<slug>.md` (directory to be created on first use),
following the postmortem template in Operator Runbook §8. A running index table
(below) is maintained at the top of that directory's `README.md`.

**Incident log template (running index):**

| ID | Date opened (CDMX) | Sev | One-line summary | Status | Personal data involved? | Counsel engaged? | Postmortem link |
|---|---|---|---|---|---|---|---|
| INC-2026-NNNN | YYYY-MM-DD HH:MM | SEV_ | … | Open / Contained / Resolved / Closed | Yes / No / Unknown | Yes / No / N/A | `docs/incidents/…md` |

**Per-incident record (template):**

```
# INC-YYYY-NNNN — <one-line summary>
Severity: SEV_      Declared by: <IR Lead>      Opened: <CDMX timestamp>

## Timeline (CDMX)
HH:MM  <detection / observation>
HH:MM  <triage + severity assigned>
HH:MM  <containment action — e.g. rotated AUTH_JWT_SECRET>
HH:MM  <eradication / fix commit SHA>
HH:MM  <recovery + smoke probes green>
HH:MM  <resolved / tenant comms sent>

## Severity & classification rationale
## Root cause
## Blast radius (who saw it · how long · what data — if any)
## Personal-data assessment + counsel decision (LFPDPPP)   [if applicable]
## Evidence captured (audit_log rows, Render/Vercel logs, Neon branch, R2)
## Fix (commit SHA + summary)
## Notifications sent (tenant / authority / when)
## Prevention (test / monitor / runbook update + owner)
```

---

## 9. Known gaps & ⚠ TO VERIFY / RECONCILE items

| Item | Detail | Action |
|---|---|---|
| **⚠ R2 object-versioning contradiction (RECONCILE)** | **Operator Runbook §7 says R2 object versioning is NOT enabled** ("A deletion is permanent within R2 unless object versioning is enabled — recommend enabling it"). **`PRODUCTION_ENV_SETUP_CHECKLIST.md` ("What this checklist does NOT cover") says it IS** ("already configured via Cloudflare R2 versioning"). These contradict each other and directly affect document-store recovery during an incident. | **Verify the live R2 bucket setting in the Cloudflare console and reconcile both runbooks.** Until confirmed, assume the *worst case* (no versioning → deletions are permanent) when planning containment/recovery. |
| **⚠ Single-person IR team** | One person holds IR Lead, Technical, and Comms (§2). | Name + document a backup responder. |
| **⚠ R2 access logging** | Unconfirmed whether R2 access logs are enabled for forensic read/write/delete trails (§7). | Confirm and enable if absent. |
| **⚠ Log retention windows** | Render and Vercel log retention is finite and unconfirmed; Neon PITR window unconfirmed (see BCP). | Capture evidence early; confirm windows. |
| **Privacy-notice breach procedure** | Privacy notice + references.md don't yet document the LFPDPPP breach-notification path (§6). | Counsel to confirm; align docs. |
| **No per-user session revoke** | Only escape hatches are disable-user / force-password / global secret rotation (Operator Runbook §4). | Track as hardening item (per-session revoke). |
| **Share-event auditing partial** | Share mint/consume/revoke auditing was a recommended (not-yet-complete) item in the 2026-06-15 audit. | Track; needed for full forensic coverage of public shares. |
| **No tested IR drill yet** | This plan has not been exercised. | Run a tabletop drill (pair with the BCP restore drill) and record results. |

---

*End of CW-ISO-incident-response v0.1 (draft). Review annually and after any
incident or drill. This document is ISO-readiness evidence and is not a claim of
ISO certification.*
