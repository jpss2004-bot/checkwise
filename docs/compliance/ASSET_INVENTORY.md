---
Document: Inventory of Information & Associated Assets
ID: CW-ISO-asset-inventory
Owner: Lead Engineer / acting CISO (Jose Pablo Samano)
Version: 0.1 (draft)
Effective: 2026-06-16
Review cadence: annual + on material change
ISO refs: ISO/IEC 27002:2022 §5.9 (Inventory of information and other associated assets); supports §5.10, §5.12, §5.13, §8.10
Status: DRAFT — ISO-readiness evidence, NOT a certification claim
---

> **Scope & disclaimer.** Internal ISMS-readiness evidence for CheckWise (operated by LegalShelf, S.A. de C.V.). **Not** a claim of ISO/IEC 27001 certification, audit, or "passing ISO," and **not** legal advice. Classification labels (T0–T3) reference the scheme in `docs/compliance/DATA_CLASSIFICATION.md`. Secret **values** are never recorded here — names and locations only.

**Owner of record for all assets below:** Lead Engineer / acting CISO (Jose Pablo Samano), LegalShelf. As the organization matures, per-asset owners should be delegated; until then a single accountable owner is declared for auditor credibility.

**Classification legend:** T0 Public · T1 Internal · T2 Confidential · T3 Restricted (highest element wins). See the classification scheme for definitions and handling rules.

---

## 1. Information assets

| # | Asset | Type | Owner | Location / Provider | Class. | Notes |
|---|-------|------|-------|---------------------|--------|-------|
| A1 | **Tenant document store** — raw vendor tax/payroll/IMSS/INFONAVIT/CSF/REPSE PDFs | Data | Lead Eng. (CISO) | Cloudflare R2 (S3-compatible), bucket `checkwise-prod` | **T3** | Source of truth for evidence bytes. Keyed by `documents.storage_key`. Encrypted at rest (R2 unconditional + explicit SSE `AES256`, ENC-2). Served only via short-lived presigned URLs (default 15 min). May contain *datos sensibles* (CURP, NSS, SBC, cuotas). |
| A2 | **Application database** | Data | Lead Eng. (CISO) | PostgreSQL on **Neon** (pooled endpoint at runtime, direct endpoint for migrations) | **T3** | 38 tables (§3). Holds tenant records, extracted metadata, reports, audit log, and one-way credential derivatives (bcrypt/SHA-256/HMAC). At-rest encryption managed by Neon (⚠ TO VERIFY cipher/CMK per plan). TLS pinned `sslmode=require` in prod (ENC-1). |
| A3 | **Audit log** | Data | Lead Eng. (CISO) | Neon (`audit_log` table) | **T2** | Append-only: actor_id/type, action, entity, before/after JSON, plus request provenance `ip_address` + `user_agent` (migration 0043). High-integrity evidence; underpins the "bitácora de auditoría inmutable" privacy-notice commitment. |
| A4 | **Secrets & signing/API keys** | Data | Lead Eng. (CISO) | Render env vars (`sync: false`) + Vercel project env | **T3** | `AUTH_JWT_SECRET`, R2 creds, `DATABASE_URL`/`DIRECT_DATABASE_URL`, `ANTHROPIC_API_KEY`, Twilio token, Meta WhatsApp token, SMTP password, Slack tokens, Google Doc AI JSON. **Never** in the repo. `.gitignore` blocks `.env*`; `.gitleaks.toml` scans. API refuses to boot in non-local if the placeholder JWT secret leaks. |
| A5 | **Source code** | Software | Lead Eng. (CISO) | GitHub `jpss2004-bot/checkwise` (private) | **T1** | FastAPI backend (`apps/api`) + Next.js frontend (`apps/web`). Secrets externalized (A4). Auto-deploys from `main`. |
| A6 | **API service** | Service | Lead Eng. (CISO) | FastAPI/uvicorn on **Render** (`checkwise-api`, plan `starter`) | **T2** | Long-lived ASGI process. `/docs` disabled outside local by default. Health-gated rollouts (`/health`). Processes T3 data → service treated as Confidential infrastructure with T3 data flowing through. |
| A7 | **Frontend — public marketing site** | Service | Lead Eng. (CISO) | Next.js on **Vercel** | **T0** | Landing pages, brand assets, published legal package, public contact/feedback forms. |
| A8 | **Frontend — client/admin app** | Service | Lead Eng. (CISO) | Next.js on **Vercel** | **T2** | Authenticated surfaces for `client_admin`/client users and `internal_admin`/`reviewer`. Renders tenant-scoped Confidential data; session via httpOnly cookie (FE-SEC cutover). |
| A9 | **Frontend — provider portal** | Service | Lead Eng. (CISO) | Next.js on **Vercel** | **T2/T3** | Workspace-scoped session token (httpOnly signed cookie, `checkwise_portal_session`). Where vendors upload T3 evidence; the upload surface handles Restricted data. |
| A10 | **Renewal-reminder cron** | Service / Job | Lead Eng. (CISO) | Render cron `checkwise-renewal-dispatch` (`0 14 * * *` UTC) | **T2** | Pure DB writes (renewal_reminders + notifications). Needs only `DATABASE_URL` (+ messaging creds for fanout). Idempotent via unique constraint. |
| A11 | **Reporting-reminder cron** | Service / Job | Lead Eng. (CISO) | Render cron `checkwise-reporting-dispatch` (`5 14 * * *` UTC) | **T2** | Recurring REPSE calendar threshold events; in-app + email + SMS fanout. Idempotent via `notification_dispatch` unique key. |
| A12 | **Report exports & artifacts** | Data | Lead Eng. (CISO) | R2 (export bytes) + Neon (`report_exports`, `report_versions`) | **T2** | DOCX/PDF/PPTX/HTML renders of compliance reports. Share links tokenized (hash-only), optionally password-protected + watermarked + expiring (`report_shares`). |
| A13 | **Metadata XLSX exports** | Data | Lead Eng. (CISO) | Local FS (dev) / R2 mirror under `metadata_exports/` (prod) | **T2** | Per-upload + per-client master workbooks. Best-effort; failure never blocks upload. |
| A14 | **Object-storage backups / PITR** | Infra | Lead Eng. (CISO) | Neon continuous backup (PITR) + R2 bucket lifecycle | **T3** | Neon keeps ~7-day point-in-time restore on launch tiers per `docs/runbooks/OPERATOR_RUNBOOK_V1.md` (⚠ TO VERIFY exact retention/plan + R2 lifecycle config). Backups inherit the classification of their source. |
| A15 | **Redis (rate-limit backing store)** | Infra | Lead Eng. (CISO) | **Planned — not yet provisioned** | **T1** | `REDIS_URL` unset → in-memory sliding-window limiter, correct only on a single worker. Must be provisioned before scaling Render workers > 1 (boot warning INFRA-2). |

---

## 2. Supporting assets / third-party processors (sub-encargados)

Each is a sub-processor under the LegalShelf↔Responsable arrangement. Listed for §5.9 completeness and supplier-relationship tracking (§5.19–5.22).

| # | Processor | Type | Service to CheckWise | Data it can touch | Class. of that data | Notes |
|---|-----------|------|----------------------|-------------------|---------------------|-------|
| P1 | **Cloudflare R2** | Service / Infra | Object storage for vendor PDFs + exports | Vendor evidence files, report exports | **T3 / T2** | Encrypts at rest unconditionally; SSE header also sent. S3-compatible API. |
| P2 | **Neon** | Service / Infra | Managed PostgreSQL + PITR backups | Everything in A2/A3 | **T3** | Pooled + direct endpoints; TLS-required in prod. |
| P3 | **Render** | Service / Infra | API host + cron host + secrets store | All data in transit through the API; holds A4 secrets | **T3** | TLS terminated ahead of uvicorn (hence `X-Forwarded-For` provenance). |
| P4 | **Vercel** | Service / Infra | Frontend hosting (3 surfaces) | Renders T0–T3 to authorized users; holds `NEXT_PUBLIC_*` + frontend secrets | **T2** | Only `NEXT_PUBLIC_*` env reaches the browser. |
| P5 | **Anthropic (Claude API)** | Service | Document intelligence (shadow) + report generation + copilot | Uploaded PDF **content** when `DOCUMENT_ANALYSIS_PROVIDER=anthropic`; report context | **T3 / T2** | ⚠ Zero-Data-Retention (ZDR) must be confirmed on the Anthropic account before flipping the document-analysis provider to `anthropic` in prod (per `.env.example`). Default provider is `disabled`. |
| P6 | **Twilio** | Service | Outbound SMS notifications | Recipient phone number + rendered message body | **T2** | Active outbound channel today; gated by `MESSAGING_ENABLED`. |
| P7 | **Meta (WhatsApp Cloud API)** | Service | WhatsApp template delivery + phone-verification OTP | Recipient phone number + template variables | **T2** | Native templates gated on Meta approval + `WHATSAPP_NATIVE_TEMPLATES_ENABLED`; otherwise falls through to Twilio SMS. |
| P8 | **SMTP provider** | Service | Transactional email (reset, reviewer decisions, renewals) | Recipient email + message body + links | **T2** | If unconfigured, email short-circuits and writes `delivery_status="smtp_not_configured"` — no silent send. ⚠ TO VERIFY which SMTP vendor is contracted in prod. |
| P9 | **Slack (webhooks + bot)** | Service | Internal ops delivery: contact-form, feedback (w/ screenshot), correction requests | Lead/feedback content, optional screenshot, **peppered IP hash** (not raw IP) | **T2** | All fail-soft; persistence is canonical, Slack delivery is a side-effect. Feedback uses a bot token (PNG upload). |
| P10 | **Google Cloud Document AI** | Service | OCR fallback for scanned PDFs | PDF image content of scanned uploads | **T3** | Default `OCR_ENABLED=false`. Service-account JSON is an A4 secret. |
| P11 | **GitHub** | Service / Infra | Source hosting + CI | Source code (A5) | **T1** | Private repo `jpss2004-bot/checkwise`. |

---

## 3. Data stores & the personal/sensitive data they hold

Personal-data categories use the labels from `docs/legal/aviso-de-privacidad-v2.md`. *(sensible)* marks data the privacy notice itself classifies as *dato personal sensible*.

| Store (table) | Provider | Personal / sensitive data held | Class. |
|---------------|----------|-------------------------------|--------|
| `documents` (+ bytes in R2) | R2 / Neon | The **evidence PDFs**: may contain CURP *(sensible)*, NSS, salario base de cotización *(sensible)*, cuotas obrero-patronales *(sensible)*, aportaciones de vivienda *(sensible)*, firma, imagen y fecha de nacimiento del proveedor PF *(sensible)*. Row holds filename, sha256, mime, size, storage_key. | **T3** |
| `document_inspections` | Neon | Detected RFCs, detected dates, period mentions, expected RFC, authenticity/forensic findings, shadow-AI signals. | **T2** |
| `clients` / `organizations` | Neon | Company name, **RFC de la sociedad**, business email, responsible_name, fiscal address, phone. | **T2** |
| `vendors` | Neon | Vendor name, **RFC**, contact name/email/phone, REPSE id, persona_type. | **T2** |
| `contracts` | Neon | Service object, REPSE folio, dates, estimated workers, work location. | **T2** |
| `users` | Neon | Full name, email, phone / phone_e164, job title; **bcrypt password hash** *(secret derivative)*; lockout counters; consent versions; soft-delete actor/reason. | **T3** (hash) |
| `password_reset_tokens` / `password_history` | Neon | Email; SHA-256 token hash; rolling bcrypt history. No plaintext. | **T3** |
| `phone_verifications` | Neon | phone_e164; HMAC-SHA256 OTP code hash. No plaintext code. | **T3** |
| `provider_workspaces` | Neon | Vendor display/filial name; opaque session `access_token`; consent timestamps. | **T2** |
| `audit_log` | Neon | actor_id, action, before/after JSON, **ip_address**, **user_agent**. | **T2** |
| `client_notifications` / `provider_notifications` / `notification_dispatch` | Neon | Recipient identity (user_id/role), title/body (may name a vendor/obligation), channel delivery status. | **T2** |
| `contact_requests` | Neon | Lead **name, email**, company, role, message; **peppered SHA-256 IP hash** (not raw IP); user_agent. | **T2** |
| `feedback_reports` | Neon / R2 | Submitter name/email/roles (or anonymous + peppered IP hash); URL/path; console logs; optional **screenshot** (R2). | **T2** |
| `reports` / `report_versions` / `compliance_snapshots` / `report_exports` / `report_shares` | Neon / R2 | Compliance findings per client/vendor; frozen data snapshots; export bytes; tokenized share links (hash-only, optional password hash). | **T2** |
| `wise_events` | Neon | Product-analytics events keyed to workspace/client/user; payloads are interaction metadata. | **T1** (aggregated) / **T2** (per-user rows) |

---

## 4. ISMS scope

**In scope** for the CheckWise ISMS (the systems that store, process, or transmit T2/T3 data):

- A1 tenant document store (R2) · A2 application database (Neon) · A3 audit log · A4 secrets · A6 API service · A8 client/admin frontend · A9 provider portal · A10/A11 cron jobs · A12 report exports · A13 metadata exports · A14 backups/PITR.
- Sub-processors P1–P10 that handle T2/T3 data (supplier-security scope).
- Supporting practices: RBAC (`internal_admin` / `platform_admin` / `reviewer` / `client_admin` / client user / provider via workspace token), auth hardening (bcrypt, lockout, rate limits), tenant isolation, encryption in transit + at rest, the audit trail, and the published legal/consent package.

**Out of scope (or limited scope):**

- A5 source code & A7 public marketing site & P11 GitHub — in scope for integrity/availability and secret-hygiene only; they hold no T2/T3 data by design (T0/T1).
- A15 Redis — **planned, not yet provisioned**; enters scope when introduced.
- End-user devices, corporate IT, and physical offices — **not yet defined** in this draft (⚠ TO VERIFY: confirm the ISMS boundary statement covers or explicitly excludes these).

---

## 5. Open items (⚠ TO VERIFY)

- **Neon at-rest encryption** cipher and CMK posture per current plan (A2/A14).
- **Backup retention** exact window and **R2 lifecycle** configuration (A14).
- **Anthropic ZDR** confirmation before enabling `DOCUMENT_ANALYSIS_PROVIDER=anthropic` in prod (P5).
- **Contracted SMTP vendor** identity in production (P8).
- **Redis** provisioning before scaling API workers > 1 (A15).
- **Per-asset owners** beyond the single accountable owner currently declared.
- **ISMS boundary** for end-user devices / corporate IT / physical sites (§4).
- **Sub-processor DPAs**: confirm signed data-processing agreements exist for each of P1–P10 (the privacy notice names "terceros" generically; individual contracts not verified from the repo).
