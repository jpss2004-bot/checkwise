---
Document: Supplier / Sub-processor Risk Register
ID: CW-ISO-vendor-risk
Owner: Lead Engineer / acting CISO (Jose Pablo Samano)
Version: 0.1 (draft)
Effective: 2026-06-16
Review cadence: annual + on material change (new sub-processor, region change, breach)
ISO refs: ISO/IEC 27002:2022 — 5.19 (supplier relationships), 5.20 (addressing security in supplier agreements), 5.21 (managing security in the ICT supply chain), 5.22 (monitoring & review of supplier services), 5.23 (information security for use of cloud services)
Status: DRAFT — ISO-readiness evidence, NOT a certification claim
---

# Supplier / Sub-processor Risk Register — CheckWise

> **Scope.** This register covers **CheckWise's own third-party suppliers** — the
> ICT supply chain and cloud services CheckWise depends on to operate (hosting,
> storage, database, AI, messaging, email, ops tooling, CDN). It is the supplier
> side of ISO 27002 5.19–5.23.
>
> **Not in scope here:** This is distinct from the **ISO 37001 anti-bribery vendor
> due-diligence performed on CheckWise's *customers'* providers** (the REPSE
> vendors that customers vet through the product). For that customer-facing
> due-diligence programme, see the ISO 37001 documentation. **⚠ TO VERIFY** the
> exact path of that doc — at time of writing no `docs/**/37001` file exists in
> this repo; the anti-bribery programme should be cross-linked here once created
> (suggested: `docs/compliance/ANTIBRIBERY_VENDOR_DD.md`).
>
> **Honesty note.** Data-Processing Agreements (DPAs) and security postures below
> are marked **⚠ TO VERIFY** because they have **not** been independently confirmed
> for this draft. Regions reflect the intended/likely configuration and must be
> confirmed against each provider's dashboard. This document does not assert ISO
> certification. No secrets or credentials appear here.

---

## 1. Sub-processor / third-party register

Grounded in `render.yaml` and `.env.example` (the live integration surface).
Data-classification scheme used below: **Confidential** (PII, compliance
documents, credentials), **Internal** (operational metadata, ops messages),
**Public/None** (no customer data).

| Vendor | Service / role | Data shared / processed | Data classification | Region (intended) | DPA / security-posture | Criticality | Notes |
|---|---|---|---|---|---|---|---|
| **Neon** | Managed PostgreSQL (primary application database) | All structured app data: users, memberships, tenants, vendors, submissions metadata, audit log, password **hashes** (never plaintext). | **Confidential** (incl. PII) | **⚠ TO VERIFY** (likely AWS `us-*`) | **⚠ TO VERIFY** DPA + SOC 2; TLS in transit pinned (`sslmode=require`) | **Critical** | Hard availability dependency — DB down = app down. Pooled + direct endpoints. Named pre-deploy branch snapshots used as rollback anchors. |
| **Cloudflare R2** | S3-compatible object storage (uploaded compliance PDFs + metadata XLSX) | Customer-uploaded REPSE documents (CFDI, IMSS/SAT proofs, contracts) — **the most sensitive content**; metadata exports. | **Confidential** (incl. PII) | **⚠ TO VERIFY** (R2 `auto`/global) — **data-residency question for MX PII** | **⚠ TO VERIFY** DPA; SSE `AES256` sent on every write + R2 at-rest encryption | **Critical** | Availability + confidentiality dependency. Presigned URLs TTL 15 min. Residency must be confirmed for Mexican-PII obligations. |
| **Render** | Application hosting (FastAPI web service + renewal/reporting crons) | Processes all request data in memory; holds env-injected secrets (JWT secret, DB URL, all API keys). TLS terminated here. | **Confidential** (transient) | **⚠ TO VERIFY** (region set at service creation) | **⚠ TO VERIFY** DPA + SOC 2 | **Critical** | Compute availability dependency. Secrets live in Render env (`sync: false`). Ephemeral FS — no durable customer data at rest on Render. |
| **Vercel** | Frontend hosting (Next.js) + CDN/edge for the web app | Serves UI; proxies/forwards authenticated requests. No durable customer data; receives request data in transit. | **Internal** (transient; auth cookies transit) | Global edge | **⚠ TO VERIFY** DPA | **High** | Front-door availability dependency. Cross-site cookie setup with Render drives `SameSite=None; Secure`. |
| **Anthropic (Claude)** | AI: report planner/generator, Wise copilot, optional document-analysis shadow runner | Report context; **document contents are sent only when the shadow analyzer is enabled** (`DOCUMENT_ANALYSIS_PROVIDER=anthropic`). | **Confidential** (when document analysis enabled) | **⚠ TO VERIFY** (US) | **⚠ TO VERIFY DPA + Zero-Data-Retention (ZDR)** — `.env.example` explicitly states ZDR must be confirmed before enabling `anthropic` in prod | **High** | Document-analysis provider defaults **disabled**; reports/copilot fall back to a deterministic mock without a key. **Do not enable doc-analysis in prod until ZDR + DPA confirmed.** |
| **Twilio** | Outbound SMS (renewal/reporting reminders; active messaging channel today) | Recipient phone numbers + notification message bodies (may name a tenant/requirement). | **Confidential** (phone = PII) | **⚠ TO VERIFY** (US) | **⚠ TO VERIFY** DPA | **Medium** | Gated by `MESSAGING_ENABLED` + `TWILIO_ENABLED`; off → rows marked `skipped`. Not on the auth critical path. |
| **Meta — WhatsApp Cloud API** | Outbound WhatsApp templates (renewal/verification) + phone-verification OTP | Recipient phone numbers + templated message variables; phone-verification OTP. | **Confidential** (phone = PII) | **⚠ TO VERIFY** | **⚠ TO VERIFY** DPA + Meta data-use terms | **Medium** | Native templates gated by `WHATSAPP_NATIVE_TEMPLATES_ENABLED` (Meta template approval required); otherwise traffic falls through to Twilio SMS. |
| **SMTP email provider** (default template: Gmail / Google Workspace) | Transactional email (password-reset links, reviewer-decision, renewal reminders) | Recipient email addresses + email bodies containing reset links / compliance status. | **Confidential** (email = PII; reset links are bearer secrets) | **⚠ TO VERIFY** (Google US/global) | **⚠ TO VERIFY** DPA; STARTTLS (port 587, `SMTP_USE_TLS=true`) | **Medium-High** | `.env.example` defaults `SMTP_HOST=smtp.gmail.com` with an app password — **⚠ TO VERIFY the actual production mailbox/provider**. Unconfigured → email short-circuits and audit row marks `smtp_not_configured`. |
| **Slack** | Ops/notifications: contact-form delivery, internal feedback triage (+ screenshot), provider correction requests | Contact-form content (lead PII), tester feedback (may include a screenshot PNG), correction-request contact details. | **Internal / Confidential** (lead + correction PII; screenshots may show app data) | **⚠ TO VERIFY** (US) | **⚠ TO VERIFY** DPA | **Low-Medium** | All Slack delivery is **optional and fail-soft** — persistence happens regardless; missing token → `skipped`. Bot token needs `chat:write`+`files:write` for feedback screenshots. |
| **Google Cloud — Document AI** *(optional / not default)* | OCR fallback for scanned-PDF uploads | Scanned document image/text sent to GCP for OCR. | **Confidential** (when enabled) | `us` or `eu` (`GOOGLE_DOC_AI_LOCATION`) | **⚠ TO VERIFY** DPA | **Low** (optional) | `OCR_ENABLED=false` by default; scans route to `pendiente_revision` without it. Listed for completeness — only a sub-processor if enabled. |

**Infrastructure/CDN note (5.23):** Cloudflare also fronts CDN/DNS for CheckWise
properties; R2 above is the storage facet. **⚠ TO VERIFY** the full Cloudflare
account scope (DNS, WAF, CDN) and treat Cloudflare as a single critical supplier
relationship.

---

## 2. Risk notes per critical vendor (ISO 27002 5.21, 5.22, 5.23)

### Neon (Critical — database)
- **Availability dependency:** Total outage = full application outage. Mitigation:
  Neon's managed HA + named pre-deploy branch snapshots as rollback anchors.
  **⚠ TO VERIFY** RPO/RTO and that snapshots are taken **before** every migration
  deploy (this is the documented practice; confirm it is automated, not manual).
- **Data residency:** Holds Mexican-PII. Region must be confirmed and recorded.
- **Breach notification:** **⚠ TO VERIFY** contractual breach-notification window
  (target: ≤72h to CheckWise) in the DPA.

### Cloudflare R2 (Critical — document storage)
- **Confidentiality dependency:** Stores the most sensitive artifacts (raw
  compliance documents). SSE `AES256` is sent on writes and R2 encrypts at rest.
- **Data residency:** R2's `auto`/global placement is a **specific concern for
  Mexican-PII** obligations — must be confirmed and, if needed, jurisdiction-pinned.
- **Availability dependency:** Outage blocks uploads/downloads/report exports.
- **Breach notification:** **⚠ TO VERIFY** window in DPA.

### Render (Critical — compute + secret custody)
- **Availability dependency:** Hosts the API and the renewal/reporting crons.
- **Secret custody:** All production secrets are injected via Render env. A Render
  account compromise is a **secret-exposure event** → rotate `AUTH_JWT_SECRET`, DB
  creds, R2 keys, Anthropic/Twilio/Meta/SMTP keys. **⚠ TO VERIFY** a documented
  rotation runbook + Render SSO/MFA on the LegalShelf Render org.
- **Breach notification:** **⚠ TO VERIFY** DPA window.

### Anthropic (High — AI; conditional data exposure)
- **Conditional data exposure:** Customer **document contents** leave the boundary
  only when the shadow analyzer is enabled. **Gate:** confirm **Zero-Data-Retention
  + DPA** before flipping `DOCUMENT_ANALYSIS_PROVIDER=anthropic` in prod (this is
  already called out in `.env.example`).
- **Availability:** Degrades gracefully — falls back to deterministic mock; not an
  availability-critical dependency.

### SMTP / email (Medium-High — credential delivery)
- **Sensitive payload:** Password-reset emails carry **bearer secret links**
  (60-min TTL). A compromised sending mailbox could intercept reset flows.
- **⚠ TO VERIFY** the real production provider (the template defaults to Gmail) and
  that the sending account itself has MFA + restricted app-password scope.

### Twilio / Meta-WhatsApp (Medium — phone PII)
- Process recipient phone numbers + message bodies that may name a tenant. Both are
  feature-flag-gated and off the auth critical path.
- **⚠ TO VERIFY** DPAs and message-content data-retention settings on each.

---

## 3. Vendor onboarding due-diligence checklist (ISO 27002 5.19, 5.20)

Complete **before** a new sub-processor processes any customer data:

- [ ] Business need + data flow documented (what data, what classification, what
      direction).
- [ ] Data classification of shared data assigned (Confidential / Internal / Public).
- [ ] **DPA signed** (or provider's standard DPA accepted) covering processing
      scope, sub-processing, and deletion.
- [ ] Security posture reviewed: SOC 2 Type II / ISO 27001 cert / pen-test summary
      obtained and filed.
- [ ] **Data-residency** confirmed and acceptable for Mexican-PII obligations
      (especially storage + DB providers).
- [ ] **Breach-notification** commitment confirmed (target ≤72h to CheckWise).
- [ ] Encryption in transit (TLS) and at rest confirmed.
- [ ] Access model: least-privilege credentials minted; secrets stored only in
      env/secret manager (never committed); SSO/MFA enabled on the provider console
      where available.
- [ ] Feature-flag / kill-switch path identified so the integration can be disabled
      without a code deploy (CheckWise convention).
- [ ] Criticality rating assigned and entered in §1.
- [ ] Added to the public-facing sub-processor list / privacy notice if it processes
      customer PII. **⚠ TO VERIFY** alignment with `docs/legal/aviso-de-privacidad-v2.md`.

## 3b. Vendor offboarding checklist

- [ ] Revoke/rotate all credentials and API keys issued to or by the vendor.
- [ ] Confirm data deletion / return per the DPA; obtain written confirmation.
- [ ] Remove the integration's env vars from Render/Vercel; flip its kill switch.
- [ ] Update §1 register and the public sub-processor list / privacy notice.
- [ ] Record the offboarding in `docs/compliance/evidence/supplier-dpas/` (or a
      supplier-changes log).

---

## 4. Review cadence & monitoring (ISO 27002 5.22)

| Activity | Cadence | Owner |
|---|---|---|
| Full register review (this document) | Annual | acting CISO |
| New sub-processor / region change / data-flow change | On event (before go-live) | acting CISO |
| Re-collect SOC 2 / ISO certs for critical vendors | Annual | acting CISO |
| Vendor status-page / incident monitoring (Neon, R2, Render, Vercel) | Continuous (best-effort) | Eng on-call **⚠ TO VERIFY** formal monitoring |
| Confirm pre-migration DB snapshot practice | Each migration deploy | Lead Engineer |

---

## 5. Open items (summary)

| ID | Item | ISO ref | Status |
|---|---|---|---|
| VRR-DPA | DPAs unverified for **all** sub-processors | 5.20 | **⚠ TO VERIFY** — collect + file each |
| VRR-RES-DB | Neon region/residency unconfirmed (MX PII) | 5.23 | **⚠ TO VERIFY** |
| VRR-RES-R2 | R2 global placement vs MX-PII residency | 5.23 | **⚠ TO VERIFY** — possibly pin region |
| VRR-ZDR | Anthropic ZDR + DPA before enabling doc-analysis in prod | 5.21 | **⚠ TO VERIFY** — gate enforced by flag |
| VRR-SMTP | Actual prod email provider/mailbox (template = Gmail) | 5.19 | **⚠ TO VERIFY** |
| VRR-ROT | Secret-rotation runbook for a Render/account compromise | 5.21 | **⚠ TO VERIFY** |
| VRR-37001 | Cross-link to ISO 37001 customer-provider DD doc (not yet in repo) | 5.19 | **⚠ TO VERIFY** / create |
| VRR-PRIV | Sub-processor list aligned with published privacy notice | 5.20 | **⚠ TO VERIFY** |

---

*End of CW-ISO-vendor-risk v0.1 (draft).*
