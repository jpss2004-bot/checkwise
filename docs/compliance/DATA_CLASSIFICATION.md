---
Document: Data Classification & Labelling Scheme
ID: CW-ISO-data-classification
Owner: Lead Engineer / acting CISO (Jose Pablo Samano)
Version: 0.1 (draft)
Effective: 2026-06-16
Review cadence: annual + on material change
ISO refs: ISO/IEC 27002:2022 §5.12 (Classification of information), §5.13 (Labelling of information); supports §5.9, §5.10, §5.14, §8.10, §8.12
Status: DRAFT — ISO-readiness evidence, NOT a certification claim
---

> **Scope & disclaimer.** This document is internal ISMS-readiness evidence for CheckWise (operated by LegalShelf, S.A. de C.V.). It is **not** a claim that CheckWise is ISO/IEC 27001-certified, audited, or "passes ISO." It is **not** legal advice. Where it touches Mexican data-protection law (LFPDPPP), it summarizes the posture already published in `docs/legal/aviso-de-privacidad-v2.md` and defers to that notice and to LegalShelf's counsel for any authoritative interpretation.

This scheme is the classification authority referenced by the asset inventory (`docs/compliance/ASSET_INVENTORY.md`).

---

## 1. Purpose

CheckWise is a multi-tenant SaaS that ingests sensitive third-party (vendor) tax, labour and payroll documentation per client tenant, validates it, and produces auditable REPSE-compliance reports. The data ranges from public marketing copy to vendor payroll evidence containing data the published privacy notice itself flags as *datos personales sensibles*. A single, consistently applied classification scheme lets every later control (access, encryption, retention, logging, deletion) be derived from the tier rather than re-argued per asset.

---

## 2. The four tiers

| Tier | Label | One-line definition | Impact if disclosed/lost |
|------|-------|---------------------|--------------------------|
| **T0** | **Public** | Information deliberately published to anyone. | Negligible. |
| **T1** | **Internal** | Operational information not meant for the public, but whose disclosure would cause limited harm. | Low — embarrassment, minor operational friction. |
| **T2** | **Confidential** | Tenant-scoped business information and personal data of moderate sensitivity; disclosure breaches a tenant boundary or a person's privacy. | Moderate-to-high — tenant trust, contractual breach, LFPDPPP exposure. |
| **T3** | **Restricted** | The most sensitive data CheckWise holds: *datos personales sensibles* (per the aviso de privacidad), authentication secrets, and signing keys. | Severe — regulatory liability under LFPDPPP, credential compromise of the whole platform, harm to data subjects. |

Classification is assigned to the **highest** tier any element within an asset warrants. A document store that mixes a CSF (T2) and a payroll proof carrying CURP + salario base de cotización (T3) is classified **T3**.

---

## 3. Tier definitions, CheckWise examples, and handling rules

### T0 — Public

**Definition.** Content intended for unrestricted publication. No confidentiality obligation; integrity and availability still matter (defacement / outage).

**CheckWise examples.**
- Marketing landing-page copy, brand assets (`brand_assets/`), public SEO content.
- The published legal package: `docs/legal/aviso-de-privacidad-v2.md`, `terminos-de-uso-v2.md`, `aviso-de-consentimiento-v2.md` (intended to be world-readable).
- Public API health endpoint (`/health`) response.

| Dimension | Rule |
|-----------|------|
| Storage | Anywhere, incl. public CDN / Vercel edge. |
| Transmission | No encryption requirement (TLS still used by default). |
| Access | Public / unauthenticated read. Write restricted to staff. |
| Retention | Indefinite while relevant. |
| Deletion | Standard; no special handling. |
| Logging | Not required for confidentiality. |

### T1 — Internal

**Definition.** Day-to-day operational information that should stay within LegalShelf and authenticated users, but whose leak would cause only limited harm.

**CheckWise examples.**
- Source code in the GitHub repo `jpss2004-bot/checkwise` (private repo; secrets are externalized — see T3). Note: the repo deliberately commits a *non-secret placeholder* `AUTH_JWT_SECRET`, and the API refuses to boot in non-local environments if that placeholder leaks into deployment (`app/core/config.py`).
- Internal runbooks, architecture docs, audit reports under `docs/`.
- Aggregated, non-identifying product analytics (`wise_events`) and statistical compliance patterns (the privacy notice reserves the right to compute "estudios estadísticos agregados").
- Non-tenant-identifying application logs.

| Dimension | Rule |
|-----------|------|
| Storage | LegalShelf-controlled systems / private repos only. |
| Transmission | TLS in transit. |
| Access | Authenticated staff or contributors; least-privilege. |
| Retention | While operationally useful. |
| Deletion | Standard delete. |
| Logging | Access to bulk internal data should be attributable. |

### T2 — Confidential

**Definition.** Tenant-scoped business data and personal data of moderate sensitivity. Disclosure crosses a tenant boundary, breaches a contract, or exposes ordinary personal data under LFPDPPP. **This is the default tier for anything tenant-scoped that is not sensitive enough to be T3.**

**CheckWise examples.**
- **Compliance reports** and their versions, snapshots, exports and share links (`reports`, `report_versions`, `compliance_snapshots`, `report_exports`, `report_shares`).
- **The audit log** (`audit_log`) — append-only record of actor, action, before/after diffs, plus request provenance (`ip_address`, `user_agent`). High integrity value; classified Confidential because it can reconstruct tenant activity and contains IPs.
- Client/tenant org records, vendor records, contracts (`clients`, `organizations`, `vendors`, `contracts`) — company names, RFC of the company, fiscal address, REPSE folios, contract terms.
- Ordinary personal data: user/contact names, business emails, phone numbers (`users`, `client_notifications`, `contact_requests`, `feedback_reports`), worker names and job titles extracted from documents.
- Document inspection metadata and detected fields (`document_inspections`) — detected RFCs, dates, forensic/authenticity findings.
- Notification content and dispatch records (`provider_notifications`, `client_notifications`, `notification_dispatch`).

| Dimension | Rule |
|-----------|------|
| Storage | Encrypted at rest. PostgreSQL on Neon (managed, encrypted at rest; ⚠ TO VERIFY exact Neon at-rest cipher/CMK posture per plan). Object artifacts (report exports) in Cloudflare R2 — encrypted at rest unconditionally + explicit SSE header (`STORAGE_SSE_ALGORITHM=AES256`, control ENC-2 in `app/services/storage.py`). |
| Transmission | TLS required. DB connections pin `sslmode=require` in non-local envs (control ENC-1, `app/core/config.py`); a plaintext-downgrade `sslmode` raises a boot warning. |
| Access | Authenticated **and tenant-scoped**. Role-gated: `client_admin`/client users see only their org; `reviewer` validates across tenants; `internal_admin` ops. Share links are tokenized (only a SHA-256 hash stored — `report_shares.token_hash`), may carry a password (`password_hash`), expiry and watermark, and unlock attempts are rate-limited. |
| Retention | Per the privacy notice: kept for the life of the proveedor↔contratante relationship plus the additional period required by fiscal/regulatory rules; then **blocked before definitive cancellation**. |
| Deletion | Logical/soft-delete with a recovery window (e.g. `users.deleted_at` + `deleted_by_user_id` + reason). ⚠ TO VERIFY: a hard-purge cron is **not yet implemented** (users.id FKs lack cascade — see memory/handoff). |
| Logging | Mutations recorded in `audit_log` with actor + IP + user-agent. |

### T3 — Restricted

**Definition.** The most sensitive data CheckWise holds — (a) personal data the published aviso de privacidad explicitly labels *dato sensible*, and (b) authentication secrets and signing keys whose compromise breaks platform security. Maximum protection.

**CheckWise examples — sensitive personal data (vendor evidence PDFs).** These live as files in the R2 tenant document store, with extracted fields in Postgres:
- CURP del trabajador / del proveedor persona física *(dato sensible)*
- Imagen y fecha de nacimiento del proveedor persona física *(dato sensible)*
- Número de Seguridad Social de los trabajadores
- Cuotas obrero-patronales *(dato sensible)*, salario base de cotización *(dato sensible)*, aportaciones de vivienda *(dato sensible)*
- Firma del proveedor persona física
- → The raw vendor tax/payroll/IMSS/INFONAVIT PDFs in `documents.storage_key` are therefore **Restricted**, because any one of them may carry the above.

**CheckWise examples — secrets & keys (never in the repo; injected as env vars):**
- `AUTH_JWT_SECRET` (session signing), R2 credentials (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`), `DATABASE_URL` / `DIRECT_DATABASE_URL`, `ANTHROPIC_API_KEY`, Twilio (`TWILIO_AUTH_TOKEN`), Meta WhatsApp (`WHATSAPP_ACCESS_TOKEN`), SMTP password, Slack tokens, Google Doc AI service-account JSON.
- Stored credential **derivatives** in the DB are one-way only: bcrypt password hashes (`users.password_hash`, `password_history`), SHA-256 of reset/share tokens, HMAC-SHA256 of OTP codes (`phone_verifications.code_hash`). The plaintexts are never persisted.

| Dimension | Rule |
|-----------|------|
| Storage | **Secrets:** only in the secrets manager (Render env vars, `sync: false`) and Vercel project env — never committed; `.gitignore` blocks `.env*`, `.gitleaks.toml` scans for leaks. **Sensitive PDFs:** R2 only, encrypted at rest + SSE header; file bytes and extracted metadata stored separately (per privacy notice "almacenamiento separado de archivos y metadata"). |
| Transmission | TLS mandatory, fail-closed. Sensitive files served only via short-lived presigned URLs (`S3_PRESIGNED_URL_TTL_SECONDS`, default 15 min), never public buckets. |
| Access | Strictly least-privilege and tenant-scoped. Document download is authorization-checked per request. Secrets are accessible only to the runtime process and named operators; rotate on suspected exposure. Auth hardening: bcrypt (cost 12), account lockout after N failed logins (`failed_login_count` / `locked_until`), login + reset + share-unlock rate limits. |
| Retention | Sensitive personal data: same regulatory-retention-then-block rule as T2, but with the strongest deletion discipline. Secrets: rotated periodically and on personnel/exposure change. |
| Deletion | Definitive cancellation after the blocking period; deletion of vendor PDFs must remove R2 object **and** derived metadata. ⚠ TO VERIFY: automated end-to-end purge not yet implemented (see T2 deletion note). |
| Logging | Every access/decision on Restricted data attributable in `audit_log`. **Never log secret values or full sensitive field contents** — names/locations only (this scheme and the inventory follow that rule). |

---

## 4. CheckWise data-category → tier map (quick reference)

| Data category | Tier | Where it lives |
|---------------|------|----------------|
| Vendor tax/payroll/IMSS/INFONAVIT/CSF/REPSE PDFs (may contain CURP, NSS, SBC, cuotas) | **T3 Restricted** | R2 (`documents.storage_key`) |
| Authentication secrets & signing/API keys | **T3 Restricted** | Render / Vercel env (never in repo) |
| Password hashes, token hashes, OTP HMACs | **T3 Restricted** | Neon (`users`, `password_*`, `report_shares`, `phone_verifications`) |
| Compliance reports / versions / exports / snapshots / share links | **T2 Confidential** | Neon + R2 (exports) |
| Audit log (actor, action, before/after, IP, UA) | **T2 Confidential** | Neon (`audit_log`) |
| Client/org, vendor, contract records (RFC, fiscal address, folios) | **T2 Confidential** | Neon |
| Ordinary personal data: names, business emails, phones, job titles | **T2 Confidential** | Neon (`users`, `contact_requests`, `feedback_reports`, notifications) |
| Document inspection metadata, detected fields, forensic findings | **T2 Confidential** | Neon (`document_inspections`) |
| Audit-technical data: IP address, user agent | **T2 Confidential** | Neon (`audit_log`); peppered IP **hash** only in `contact_requests`/`feedback_reports` |
| Source code, runbooks, internal docs, audit reports | **T1 Internal** | GitHub `jpss2004-bot/checkwise`, `docs/` |
| Aggregated/anonymized analytics & compliance statistics | **T1 Internal** | Neon (`wise_events`), derived |
| Marketing content, brand assets, published legal package, `/health` | **T0 Public** | Vercel / repo / web |

---

## 5. Labelling (ISO 27002 §5.13)

CheckWise does not stamp visible labels on every record; classification is **derived from location + data model** using the map in §4, which is the authoritative label registry. Practical labelling conventions:

- **Documents on disk/storage:** tier is implied by the store — anything in the R2 tenant document store (`documents.storage_key`) is treated as **T3 Restricted** by default.
- **Database tables:** the §4 map is the label of record; this doc and the asset inventory are kept in sync on material change.
- **Reports shared externally:** carry an explicit `watermark` and optional password + expiry on the share link (`report_shares`), which is the externally visible confidentiality marking.
- **Secrets:** labelled by exclusion — they exist only in the secrets manager and are blocked from the repo by `.gitignore` + `.gitleaks.toml`.
- **This evidence doc** is **T0/T1** and must never quote a secret value or a full sensitive field — only names and locations.

---

## 6. Mexican data-protection context (informational, not legal advice)

CheckWise operates under the **Ley Federal de Protección de Datos Personales en Posesión de los Particulares (LFPDPPP)**. Per `docs/legal/aviso-de-privacidad-v2.md`:

- **Roles.** LegalShelp acts as **Encargado** (processor) on behalf of each client, who is the **Responsable** (controller). Tratamiento is subordinated to the Responsable's instructions (art. 3, frac. VI).
- **Datos sensibles.** The notice explicitly classifies CURP, the proveedor persona física's image and birth date, cuotas obrero-patronales, salario base de cotización and aportaciones de vivienda as *datos sensibles* — this is the legal anchor for putting the vendor PDFs and their extracted fields in **T3**.
- **Security measures.** The notice commits to cifrado en tránsito, almacenamiento separado de archivos y metadata, control de accesos por rol, bitácora de auditoría inmutable, and revisiones periódicas. The T2/T3 handling rules above are how those commitments are realized in the architecture.
- **Retention.** Data kept for the relationship + the fiscally/regulatorily required period, then **blocked before definitive cancellation** — reflected in the Retention/Deletion rows.
- **ARCO / revocation.** Exercised through the Responsable, routed to `privacidad@legalshelf.mx`, answered within 10 business days. The classification scheme supports this by making it possible to locate a subject's data across the model (§4).

> ⚠ The privacy notice is reproduced "tal cual" including its own erratas; this section summarizes posture and must not be read as legal interpretation. Defer to counsel and to the canonical notice.

---

## 7. Open items (⚠ TO VERIFY)

- Exact Neon encryption-at-rest cipher and whether customer-managed keys (CMK) are in use on the current plan.
- End-to-end deletion: automated purge of soft-deleted records and orphaned R2 objects is **not yet implemented**.
- Formal data-retention schedule (concrete durations per fiscal/regulatory basis) is referenced by the privacy notice but not yet pinned in an internal policy doc.
- Whether `reviewer` cross-tenant access is constrained by an additional approval/audit step beyond the audit log.
