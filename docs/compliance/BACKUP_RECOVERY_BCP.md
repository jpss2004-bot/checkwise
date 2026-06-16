---
Document: Backup, Recovery & Business Continuity Plan (BCP)
ID: CW-ISO-backup-recovery-bcp
Owner: Lead Engineer / acting CISO (Jose Pablo Samano)
Version: 0.1 (draft)
Effective: 2026-06-16
Review cadence: annual + after any incident or drill
ISO refs: ISO/IEC 27002:2022 8.13 (information backup), 5.29 (information security during disruption), 5.30 (ICT readiness for business continuity); supports 8.14 (redundancy of facilities)
Status: DRAFT — ISO-readiness evidence, NOT a certification claim
---

# CheckWise — Backup, Recovery & Business Continuity Plan

> **Scope of this document.** Operational-resilience *evidence* for an
> ISO/IEC 27001-aligned ISMS. Draft; **not** a certification claim. It builds on,
> and does not supersede, the existing runbooks:
> - [`docs/runbooks/OPERATOR_RUNBOOK_V1.md`](../runbooks/OPERATOR_RUNBOOK_V1.md) — §7 (backup + restore) and §3 (key rotation) hold the literal steps.
> - [`docs/runbooks/PRODUCTION_ENV_SETUP_CHECKLIST.md`](../runbooks/PRODUCTION_ENV_SETUP_CHECKLIST.md) — secret/env re-provisioning.
> - [`docs/runbooks/STAGING_DEMO_DEPLOY.md`](../runbooks/STAGING_DEMO_DEPLOY.md) — full rebuild on isolated infra (doubles as a DR rehearsal pattern).
> - [`render.yaml`](../../render.yaml) — service topology, build/migration contract, env-var inventory.
> Companion document: [`INCIDENT_RESPONSE_PLAN.md`](INCIDENT_RESPONSE_PLAN.md).

---

## 1. Purpose & scope

Define how CheckWise data is backed up, how fast and how completely we can
recover each data store, and how the service degrades when an upstream provider
fails. CheckWise is a multi-tenant REPSE-compliance SaaS holding tenant
compliance *evidence* (a deletion or corruption is a customer-trust and a
potential LFPDPPP event), so recoverability is a first-class requirement.

**Architecture in scope (per `render.yaml` + runbooks):**

| Layer | Provider | Notes |
|---|---|---|
| Backend API + crons | **Render** (`checkwise-api` web; `checkwise-renewal-dispatch`, `checkwise-reporting-dispatch` crons) | `starter` plan; **single uvicorn worker**; migrations via `preDeployCommand: alembic upgrade head`. |
| Frontend | **Vercel** | Next.js; redeployable from source. |
| Database | **Neon** PostgreSQL (`checkwise-prod`) | Pooled (`DATABASE_URL`) + direct (`DIRECT_DATABASE_URL`) endpoints; PITR + branch snapshots. |
| Object storage | **Cloudflare R2** (`checkwise-prod` bucket, S3-compatible) | Tenant evidence PDFs; content-addressed keys. |
| Secrets | **Render env vars** (`sync: false`) | Not stored in repo; re-provisioned from sources. |
| Source code | **GitHub** (`jpss2004-bot/checkwise`, branch `main`) | Auto-deploys to Render + Vercel. |
| AI | **Anthropic API** | Report planner/generator/copilot; degrades to deterministic mock. |
| Email / messaging / alerts | SMTP, Twilio/Meta, Slack | Notification fan-out; degrade to skipped+audited. |

---

## 2. Backup strategy per data store

### 2.1 Neon PostgreSQL — the system of record

- **Continuous backup / PITR.** Neon provides continuous backup and
  point-in-time restore automatically. **The team takes a Neon snapshot (sibling
  branch) before every migration deploy** — this is the established workflow
  (see MEMORY: named pre-deploy Neon anchor branches; e.g. `br-weathered-cake-…`,
  `br-steep-cake-…`). Migrations auto-run via `render.yaml` `preDeployCommand`, so
  the snapshot is the rollback anchor for a bad migration.
- **Restore primitives:** Neon dashboard → `checkwise-prod` → Branches → new
  branch from a point-in-time / named snapshot.
- **⚠ TO VERIFY — PITR retention window.** Operator Runbook §7 notes the free/
  launch tiers keep **~7 days** of PITR and that the window must be confirmed in
  the Neon dashboard before the first paying pilot. **Action:** confirm the live
  plan's retention and record it here.

### 2.2 Cloudflare R2 — tenant evidence objects

- Objects are written with content-addressed keys; deletes use idempotent S3
  `DeleteObject`.
- **⚠ TO VERIFY / RECONCILE — object versioning contradiction.** The two runbooks
  **disagree**:
  - **Operator Runbook §7:** versioning is **NOT** enabled — *"R2 documents are not
    currently versioned. A deletion is permanent within R2 unless object
    versioning is enabled"* (recommends enabling it before the first paying pilot).
  - **PRODUCTION_ENV_SETUP_CHECKLIST.md ("does NOT cover"):** versioning **IS**
    configured — *"R2 bucket lifecycle / backup retention — already configured via
    Cloudflare R2 versioning."*
  These contradict, and the answer determines whether an R2 object deletion is
  recoverable at all. **Action:** check the live bucket setting in the Cloudflare
  console, reconcile both runbooks, and update §3 below. **Until confirmed, plan
  for the worst case: no versioning → deletions are permanent**, and the only
  recourse is whatever `audit-package.zip` a customer happened to export
  (Operator Runbook §6/§7).

### 2.3 Secrets — Render environment variables

- Secrets live as Render env vars with `sync: false` (never in the repo; `.env`
  is gitignored + gitleaks per the 2026-06-15 audit). There is **no secret
  "backup"** by design — secrets are **re-provisioned from their source of truth**:
  - `AUTH_JWT_SECRET` → re-mint (`openssl rand -hex 32`); rotation = global
    force-logout (Operator Runbook §3.1).
  - `DATABASE_URL` / `DIRECT_DATABASE_URL` → Neon dashboard.
  - `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_S3_ENDPOINT` → Cloudflare R2.
  - SMTP, `ANTHROPIC_API_KEY`, Twilio/Meta, Slack tokens → respective consoles.
  - The full inventory + which features each gates is in `render.yaml` and
    `PRODUCTION_ENV_SETUP_CHECKLIST.md`.
- **Re-provision procedure:** the env-var paste sequence in
  `PRODUCTION_ENV_SETUP_CHECKLIST.md` reconstitutes a Render service's full
  secret set in 15–20 minutes.
- **⚠ TO VERIFY.** No off-box encrypted record of *which* sources/accounts hold
  each secret beyond the operator's password manager. **Action:** keep a sealed
  inventory (names + source location, never values) for a backup responder.

### 2.4 Source code — GitHub

- Authoritative in GitHub (`jpss2004-bot/checkwise`, `main`); auto-deploys to
  Render + Vercel. Distributed git clones are de-facto backups. A specific commit
  can be redeployed via Render → Manual Deploy.
- `requirements.lock` pins the backend dependency tree (added after a fastapi
  dep-drift crash-loop on 2026-06-15) — rebuilds are reproducible.

### 2.5 Backup strategy summary

| Data store | Mechanism | Frequency | Restore primitive | ⚠ verify |
|---|---|---|---|---|
| Neon Postgres | Continuous PITR + pre-migration named snapshots | Continuous + per migration | Branch from PITR/snapshot | Retention window (§2.1) |
| R2 objects | Object versioning **(state disputed)** | — | Cloudflare console (if versioned) | **Versioning on/off (§2.2)** |
| Secrets | Re-provision from source | On demand | `PRODUCTION_ENV_SETUP_CHECKLIST.md` | Sealed inventory (§2.3) |
| Source | GitHub `main` + clones | Continuous | Redeploy a commit | — |

---

## 3. RTO / RPO targets (PROPOSED — pending sign-off)

> These are **PROPOSED** defaults sensible for an early-pilot SaaS. They are
> **not yet validated by a drill** and require IR Lead / business sign-off.
> "Achievable today?" reflects current infra honestly.

| Scenario | RTO (proposed) | RPO (proposed) | Achievable with today's infra? |
|---|---|---|---|
| Bad deploy / app regression | **≤ 30 min** | **0** (no data change) | **Yes** — Render Manual Deploy rollback; env-var rollback is instant + lossless. |
| Bad migration | **≤ 1 hr** | **≤ 1 migration** (pre-migration snapshot) | **Yes** — pre-migration Neon snapshot is the anchor; `preDeployCommand` blocks traffic if migration fails. |
| Neon DB corruption / accidental data loss | **≤ 4 hrs** | **≤ 5 min** (PITR granularity) | **Likely**, bounded by the PITR window (⚠ §2.1) and an *untested* restore path. |
| R2 object loss / corruption | **≤ 4 hrs** | **0 if versioned; otherwise unbounded** | **Conditional on §2.2** — unknown until versioning is confirmed. |
| Full Render service loss | **≤ 4 hrs** | **0** (DB/storage are external) | **Yes** — rebuild service from `render.yaml` + re-provision secrets. |
| Full region/provider loss (Neon or R2) | **≤ 24 hrs** | **≤ PITR window** | **Partial** — single-region today; no warm standby (see §5). |
| Anthropic API outage | **0** (graceful degrade) | **N/A** | **Yes** — auto-falls back to deterministic mock LLM with honest UI banner. |

**Definitions.** **RTO** = max tolerable time to restore service. **RPO** = max
tolerable data loss measured in time.

---

## 4. Restore procedures

All procedures defer to **Operator Runbook §7** for literal steps; this section
adds sequencing + verification.

### 4.1 Database restore (Neon)
1. Neon dashboard → `checkwise-prod` → Branches → **new branch from point-in-time**
   (or from the relevant pre-migration named snapshot).
2. **Validate before cutover:** point a local API (or the staging service) at the
   restored branch's `DATABASE_URL`; run the **smoke probes** (Operator Runbook §2):
   `/health`, `/api/v1/health/db`, a login returning the Spanish `401`,
   `/docs` → `404`.
3. Cut production `DATABASE_URL` (and `DIRECT_DATABASE_URL`) on Render to the
   restored branch → Render redeploys.
4. Re-run smoke probes against prod. Confirm crons still resolve `DATABASE_URL`
   via `fromService` (they inherit it from `checkwise-api` per `render.yaml`).

### 4.2 Object restore (R2)
- **If versioning is enabled (⚠ confirm §2.2):** restore prior object versions via
  the Cloudflare R2 console.
- **If not:** there is no native recovery. The only recourse is re-uploading from
  whatever `audit-package.zip` export a customer recently pulled (Operator Runbook
  §6/§7). Treat this as a **known recovery gap** until versioning is confirmed on.

### 4.3 Secret re-provisioning
- Follow `PRODUCTION_ENV_SETUP_CHECKLIST.md` to repopulate Render env vars from
  source. Rotating `AUTH_JWT_SECRET` force-logs-out all sessions (expected;
  one-time re-login). Verify via the boot guard (service refuses placeholder) +
  smoke probes.

### 4.4 Full service rebuild (DR)
- Use `render.yaml` (Blueprint) to recreate `checkwise-api` + both crons; re-provision
  secrets (§4.3); point at the live (or restored) Neon DB + R2 bucket; redeploy the
  frontend on Vercel. The `STAGING_DEMO_DEPLOY.md` runbook is the rehearsed
  template for standing up the full stack on fresh infra (against *isolated* data).

---

## 5. Business-continuity scenarios (provider outage & failover posture)

CheckWise is **single-region / single-instance** today. Posture per provider:

| Provider | Failure mode | Current posture / degradation | Failover today |
|---|---|---|---|
| **Render** (API) | Service/instance down | Full outage of API + crons. Rollback via Manual Deploy for *bad-deploy* cases. | **None warm.** Rebuild from `render.yaml` (RTO ≤ 4 hrs). **⚠ single uvicorn worker** amplifies any stall (PERF-10). |
| **Neon** (DB) | Endpoint/region down or corruption | API `/health/db` fails → effectively full outage (system of record). | PITR/branch restore for data events; **no cross-region standby**. RPO bounded by PITR window. |
| **Cloudflare R2** | Bucket/region down | Uploads + document preview/download fail (SEV2); reads of compliance *metadata* (in Postgres) still serve. | **No second bucket / region** today. Recovery of *deleted* objects depends on versioning (⚠ §2.2). |
| **Vercel** (frontend) | Project/region down | UI unreachable; API still serves programmatic clients. | Redeploy from source; Vercel handles its own edge redundancy. |
| **Anthropic** (AI) | API down / rate-limited | **Graceful degradation by design:** report planner/blocks/copilot fall back to the **deterministic mock LLM**; generated content shows an honest in-UI banner. Per-user AI rate limits (15/min, 120/hr) bound runaway cost. | No failover needed — degrade, don't fail. |
| **SMTP** | Provider down / misconfigured | Outbound email no-ops with `delivery_status='smtp_not_configured'` (audited); in-app notifications still land. | Swap provider creds (Operator Runbook §3.2). |
| **Twilio / Meta** (WhatsApp/SMS) | Down / not enabled | Fan-out marks messaging dispatch `skipped` and audits it; other channels unaffected. | Feature-flag gated (`MESSAGING_ENABLED`, `WHATSAPP_*`). |
| **Slack** (ops alerts / "Reportar") | Down | Feedback/contact rows still persist; `slack_delivery_status='skipped'`. | Persistence-first by design; no data loss. |

**Single-region risk (explicit).** All primary compute (Render), DB (Neon), and
storage (R2) run in a single region with no warm standby. A regional provider
outage is a **multi-hour** event recovered by rebuild + restore, not by failover.
This is an accepted early-stage posture documented here for transparency; revisit
before scaling commitments (see §6).

**Graceful-degradation principle.** The system is built to **persist-then-fan-out**
and to **degrade, not crash**, when a non-critical dependency (Anthropic, SMTP,
Twilio, Slack) is unavailable. Critical-path dependencies (Render, Neon, R2) do
*not* have this cushion — their loss is an availability incident (see IRP §4–5).

---

## 6. Gaps to close (action list)

| # | Gap | Severity | Action | Owner |
|---|---|---|---|---|
| 1 | **⚠ R2 object-versioning state is contradictory** between the two runbooks (§2.2). Determines whether object deletion is recoverable at all. | High | Verify live Cloudflare setting; **enable if off**; reconcile both runbooks + this doc. | IR Lead |
| 2 | **No tested RTO/RPO drill yet.** Targets in §3 are PROPOSED/untested. | High | Run a quarterly restore drill (§7) + sign off the RTO/RPO table. | IR Lead |
| 3 | **⚠ Neon PITR retention window unconfirmed** on the live plan (§2.1). | Med | Confirm in Neon dashboard; record here. | IR Lead |
| 4 | **Single uvicorn worker** (PERF-10) amplifies any event-loop stall; cannot raise workers safely until Redis is provisioned (in-memory rate-limiter double-counts per worker; INFRA-2). | Med | Provision Redis (`REDIS_URL`), then raise worker count. | Tech Lead |
| 5 | **No Redis yet** — rate-limit + lockout backing is in-memory/DB; multi-worker correctness blocked. | Med | Provision Redis before scale-out. | Tech Lead |
| 6 | **Single-region / no warm standby** for Render/Neon/R2 (§5). | Med | Decide acceptable RTO at scale; evaluate cross-region/standby before larger commitments. | IR Lead |
| 7 | **No sealed off-box secret inventory** for a backup responder (§2.3). | Med | Maintain names+sources (never values) in a sealed store. | IR Lead |
| 8 | **R2 access logging unconfirmed** (forensic trail; cross-ref IRP §7). | Low | Confirm/enable access logging. | Tech Lead |
| 9 | **`statement_timeout` not yet enforced** (PERF-9) — a runaway query has no DB-side backstop (pgbouncer delivery caveat). | Low | Deliver via Neon pooler; backstop runaway queries. | Tech Lead |
| 10 | **No documented backup IR/ops responder** (cross-ref IRP §2). | Med | Name + document a backup. | IR Lead |

> Cross-reference: items 4, 5, 9 originate in
> `_handoff/audit-security-perf-2026-06-15.md` (PERF-9/10, INFRA-2) and remain
> open recommendations there.

---

## 7. Quarterly restore-drill checklist & log

Run **once per quarter** (and after any major infra change). The drill proves the
RTO/RPO targets in §3 are real. Use the staging/isolated path
(`STAGING_DEMO_DEPLOY.md`) so production is never at risk.

**Drill checklist:**

- [ ] **DB restore:** create a Neon branch from a point ~24 h ago; point a local/
      staging API at it; run smoke probes (Operator Runbook §2). Record wall-clock
      time → compare to RTO.
- [ ] **Confirm PITR window** matches §2.1; note the oldest restorable timestamp.
- [ ] **R2 recovery:** attempt to restore a prior version of a test object.
      Records whether versioning is actually on (resolves §2.2) and the recovery
      time.
- [ ] **Secret re-provision:** stand up a throwaway/staging service from
      `render.yaml` and repopulate env vars from source per
      `PRODUCTION_ENV_SETUP_CHECKLIST.md`; confirm boot + smoke probes.
- [ ] **Full rebuild rehearsal (optional, annual):** rebuild the whole stack on
      isolated infra per `STAGING_DEMO_DEPLOY.md`.
- [ ] **Graceful-degradation check:** unset `ANTHROPIC_API_KEY` on staging; confirm
      reports fall back to the mock with the honest banner; confirm SMTP-unset
      no-ops are audited as `smtp_not_configured`.
- [ ] **Record results** in the log below; file any new gap into §6.

**Restore-drill log (template):**

| Drill date | Run by | DB restore time (RTO) | PITR window observed (RPO) | R2 versioning confirmed? | Secret re-provision OK? | Degradation check OK? | Gaps found | Notes |
|---|---|---|---|---|---|---|---|---|
| YYYY-MM-DD | <name> | <hh:mm> | <Ndays / <Nmin> | Yes / No | Yes / No | Yes / No | … | … |

**Records location:** keep this table appended at the bottom of this file (or in
`docs/compliance/restore-drills/`), and reference the latest drill date in §3 once
the PROPOSED targets are validated and signed off.

---

*End of CW-ISO-backup-recovery-bcp v0.1 (draft). Review annually and after any
incident or drill. This document is ISO-readiness evidence and is not a claim of
ISO certification.*
