---
Document: ISO/IEC 27001:2022 + 27002:2022 Gap Analysis & Control Matrix (Statement-of-Applicability draft)
ID: CW-ISO-27001-gap
Owner: Lead Engineer / acting CISO (Jose Pablo Samano)
Version: 0.1 (draft)
Effective: 2026-06-16
Review cadence: annual + on material change
ISO refs: ISO/IEC 27001:2022 (clauses 4–10); ISO/IEC 27002:2022 (Annex A controls 5–8)
Status: DRAFT — ISO-readiness evidence, NOT a certification claim
---

# ISO 27001 / 27002 Gap Analysis — CheckWise

> **Readiness statement.** CheckWise is **not ISO 27001 certified** and this document does **not** assert certification. It is a readiness self-assessment: it maps the platform's current technical controls to ISO/IEC 27002:2022 Annex A and to the ISO/IEC 27001:2022 management-system clauses, then records the gap to certification readiness. Certification requires an established ISMS, management commitment, a completed risk treatment cycle, internal audit, management review, and a Stage 1/2 audit by an accredited body — see §3.

## 1. Scope & method

- **Scope of assessment:** the CheckWise SaaS — FastAPI API (Render), Next.js app (Vercel), PostgreSQL (Neon), object storage (Cloudflare R2), CI/CD (GitHub Actions), and the supporting sub-processors. See [ASSET_INVENTORY.md](ASSET_INVENTORY.md).
- **Method:** code-grounded review (2026-06-15 security/perf audit + 2026-06-16 ISO-readiness audit across 7 control domains), verifying each control against real code paths. Evidence is cited as `file:line` where applicable.
- **Status legend:** ✅ Implemented · 🟡 Partial · ⛔ Gap (not implemented) · ➖ Inherited from cloud provider / Not applicable.

## 2. ISO/IEC 27001:2022 management-system clauses (4–10)

The Annex A *controls* are comparatively strong; the **management system** around them is the larger gap — expected for a small engineering team that has prioritised technical hardening over formal governance.

| Clause | Requirement | Status | Evidence / Gap |
|---|---|---|---|
| 4 Context | Scope, interested parties, ISMS boundary | 🟡 | Scope drafted here + asset inventory; not yet a signed ISMS scope statement. |
| 5 Leadership | Policy, roles, management commitment | ⛔ | No signed Information Security Policy; CISO role is informal (lead engineer acting). **Action: appoint owner, sign top-level policy.** |
| 6 Planning | Risk assessment, risk treatment, objectives, SoA | 🟡 | [RISK_REGISTER.md](RISK_REGISTER.md) drafted; this matrix is the proto-SoA. No formal risk-acceptance sign-off yet. |
| 7 Support | Resources, competence, awareness, documented info | 🟡 | This `docs/compliance/` suite is the documented-information base; no security-awareness training records. |
| 8 Operation | Operational planning & control, run the risk treatment | 🟡 | Strong operational controls in code; treatment plan not yet executed as a tracked programme (see [REMEDIATION_TRACKER.md](REMEDIATION_TRACKER.md)). |
| 9 Performance eval | Monitoring, internal audit, management review | ⛔ | No internal-audit schedule, no management-review minutes, no security metrics/KPI. Audit logging exists (telemetry) but no review cadence. |
| 10 Improvement | Nonconformity, corrective action, continual improvement | 🟡 | Remediation tracker + periodic audits provide the mechanism; not yet formalised as corrective-action records. |

**Headline:** to reach certification readiness the dominant work is **management-system formalisation** (policy, roles, risk-treatment sign-off, internal audit, management review), not new code.

## 3. Path to certification readiness (what's still required)

1. Appoint an information-security owner; sign a top-level Information Security Policy.
2. Complete and sign off the risk assessment + treatment plan ([RISK_REGISTER.md](RISK_REGISTER.md)); formalise this matrix as the **Statement of Applicability** with per-control justifications.
3. Stand up the management cadence: internal audit schedule, management review, security metrics.
4. Close the P0/P1 technical gaps in [REMEDIATION_TRACKER.md](REMEDIATION_TRACKER.md) (esp. MFA, JWT revocation, malware scanning, branch protection, BCP drill).
5. Operate the ISMS for an evidence period (typically ~3 months) accumulating records ([evidence/README.md](evidence/README.md)).
6. Engage an accredited certification body for Stage 1 (documentation) then Stage 2 (implementation) audit.

## 4. ISO/IEC 27002:2022 Annex A control matrix

### 4.1 Organizational controls (5.x)

| Control | Title | Status | Evidence / Gap |
|---|---|---|---|
| 5.1 | Policies for information security | ⛔ | No signed policy set yet; this suite is the draft basis. |
| 5.2 | Information security roles & responsibilities | 🟡 | Roles exist operationally; not formally assigned/documented. |
| 5.3 | Segregation of duties | 🟡 | **Strong structural SoD**: provider submits → reviewer decides → client consumes (provider can't hold reviewer role); ADMIN-1 escalation guard (`admin.py` `_assert_can_grant_role`). Gap: no four-eyes on staff reviewer-role grants. See [ISO37001_GAP_ANALYSIS.md](ISO37001_GAP_ANALYSIS.md). |
| 5.7 | Threat intelligence | ⛔ | No structured threat-intel intake. Low priority for this profile. |
| 5.8 | Information security in project management | 🟡 | Security reviews run per major change (audit handoffs); not yet a gated step. See [SECURE_SDLC.md](SECURE_SDLC.md). |
| 5.9 | Inventory of information & assets | ✅ | [ASSET_INVENTORY.md](ASSET_INVENTORY.md). |
| 5.10 | Acceptable use of assets | 🟡 | Terms of use exist (`docs/legal/terminos-de-uso-v2.md`); no internal AUP. |
| 5.12 | Classification of information | ✅ | [DATA_CLASSIFICATION.md](DATA_CLASSIFICATION.md) (4-tier). |
| 5.13 | Labelling of information | 🟡 | Scheme defined; systematic labelling not yet applied to all artefacts. |
| 5.14 | Information transfer | ✅ | TLS in transit (ENC-1), signed-URL document transfer (15-min TTL), no-store on sensitive bytes (FILE GAP-6). |
| 5.15 | Access control | ✅ | RBAC + tenant isolation; deny-by-default; object-level checks. See [ROLE_PERMISSION_MATRIX.md](ROLE_PERMISSION_MATRIX.md), [ACCESS_CONTROL_POLICY.md](ACCESS_CONTROL_POLICY.md). |
| 5.16 | Identity management | ✅ | Admin-provisioned identities, soft-delete, unique email identity. |
| 5.17 | Authentication information | 🟡 | Strong password policy (≥12+classes+history+**common-password denylist**, AUTH G-4), bcrypt-12, reset tokens hashed. **Gap: no MFA (AUTH-MFA), JWT non-revocable for 24h (AUTH-JWT).** |
| 5.18 | Access rights (review/removal) | 🟡 | Provisioning/removal solid; **no periodic access-review cadence yet** (procedure drafted in access policy). |
| 5.19–5.22 | Supplier relationships / ICT supply chain | 🟡 | [VENDOR_RISK_REGISTER.md](VENDOR_RISK_REGISTER.md); sub-processor DPAs ⚠ to verify. |
| 5.23 | Security for cloud services | 🟡 | Cloud providers selected for posture; formal cloud-security requirements not yet documented per vendor. |
| 5.24–5.28 | Incident management | 🟡 | [INCIDENT_RESPONSE_PLAN.md](INCIDENT_RESPONSE_PLAN.md) drafted; not yet exercised. |
| 5.29 | Continuity of information security | 🟡 | [BACKUP_RECOVERY_BCP.md](BACKUP_RECOVERY_BCP.md); no tested RTO/RPO drill yet. |
| 5.30 | ICT readiness for business continuity | 🟡 | Multi-provider cloud; single region/worker risk noted. |
| 5.31 | Legal, statutory, regulatory requirements | 🟡 | LFPDPPP avisos + consent gate (`docs/legal/`); no formal compliance register. |
| 5.33 | Protection of records | ✅ | **Append-only audit log** (migration `0031_audit_log_append_only.py`) — DB-enforced immutability. See [AUDIT_LOGGING_SPEC.md](AUDIT_LOGGING_SPEC.md). |
| 5.34 | Privacy & PII protection | 🟡 | Privacy notice + classification; no formal DPIA/ROPA. |
| 5.35–5.36 | Independent review / compliance | ⛔ | No independent review or internal-audit programme yet. |
| 5.37 | Documented operating procedures | ✅ | `docs/runbooks/` (operator runbook, prod-setup, staging). |

### 4.2 People controls (6.x)

| Control | Title | Status | Evidence / Gap |
|---|---|---|---|
| 6.1 | Screening | ⛔ | No documented background-screening for staff. |
| 6.2 | Terms & conditions of employment | ⛔ | Security responsibilities not yet in employment terms. |
| 6.3 | Security awareness, education & training | ⛔ | No training programme/records. **Action: establish.** |
| 6.4 | Disciplinary process | ⛔ | Not documented. |
| 6.5 | Responsibilities after termination | 🟡 | Account deprovisioning is technical-only; no formal offboarding checklist. |
| 6.7 | Remote working | 🟡 | Cloud-native; no documented remote-work security policy. |
| 6.8 | Information security event reporting | 🟡 | Slack `#checkwise-feedback`; not a formal event-reporting channel. |

### 4.3 Physical controls (7.x)

| Control | Title | Status | Evidence / Gap |
|---|---|---|---|
| 7.x | Physical & environmental security (data centre, equipment) | ➖ | **Inherited** from Render / Vercel / Neon / Cloudflare (SOC 2 / ISO 27001 data centres). CheckWise holds no production hardware. ⚠ Obtain & file provider compliance certificates as evidence. End-user-device controls (7.x for staff laptops) ⛔ not documented. |

### 4.4 Technological controls (8.x)

| Control | Title | Status | Evidence / Gap |
|---|---|---|---|
| 8.1 | User endpoint devices | ⛔ | No MDM / endpoint policy for staff devices. |
| 8.2 | Privileged access rights | ✅ | platform_admin/internal_admin split; ADMIN-1 self-escalation guard (`admin.py`). |
| 8.3 | Information access restriction | ✅ | Per-tenant object-level authz; 404-no-enumeration; reviewer scope documented as accepted risk. |
| 8.4 | Access to source code | 🟡 | Private GitHub repo; **branch protection not yet enforced** (direct-to-main) — CODEOWNERS added 2026-06-16. See [CHANGE_MANAGEMENT.md](CHANGE_MANAGEMENT.md). |
| 8.5 | Secure authentication | 🟡 | Constant-time auth, lockout, generic 401. **Gap: MFA.** |
| 8.6 | Capacity management | 🟡 | Single worker / no Redis yet; DB pool hygiene present. No `statement_timeout` (DB-1). |
| 8.7 | Protection against malware | ⛔ | **No AV/malware scanning** on uploaded documents that fan out to external auditors in ZIPs (DOC-AV). PDF active-content detected but advisory-only (FILE GAP-4). |
| 8.8 | Management of technical vulnerabilities | ✅ | pip-audit + npm audit in CI (weekly cron) + **CodeQL SAST + Dependabot** (added 2026-06-16); lockfile pinning; clean prod dependency audit. See [SECURE_SDLC.md](SECURE_SDLC.md). |
| 8.9 | Configuration management | 🟡 | `render.yaml` IaC + `.env.example`; JWT boot guard. No formal config-baseline review. |
| 8.10 | Information deletion | 🟡 | Soft-delete + **refcount-guarded object delete** (FILE-DEL-1, fixed 2026-06-16); **hard-purge cron deferred** (FK cascade gap). |
| 8.11 | Data masking | 🟡 | Credential derivatives only (bcrypt/SHA-256/HMAC); IP-hash for contact/feedback. No field-level masking in UI logs. |
| 8.12 | Data leakage prevention | 🟡 | Tenant isolation + signed-URL TTL + no-store; no egress DLP. |
| 8.13 | Information backup | 🟡 | Neon PITR + pre-migration snapshots; **R2 versioning unconfirmed (BCP-R2)** — see [BACKUP_RECOVERY_BCP.md](BACKUP_RECOVERY_BCP.md). |
| 8.15 | Logging | ✅/🟡 | Broad audit logging (auth, decisions, admin, downloads, **now report-share mint/revoke + logout**); gaps: report-create/edit lifecycle, audit-log read. See [AUDIT_LOGGING_SPEC.md](AUDIT_LOGGING_SPEC.md). |
| 8.16 | Monitoring activities | ⛔ | **No error monitoring / alerting** (Sentry planned). Audit log is not actively monitored. |
| 8.17 | Clock synchronization | ➖ | UTC server clocks via cloud providers; timestamps `utc_now()`. |
| 8.18 | Use of privileged utility programs | 🟡 | Admin endpoints gated; metadata dry-run gated by env flag. |
| 8.20 | Network security | ✅ | TLS everywhere; CORS allowlist; security headers + CSP subset on all responses (INFRA-1). |
| 8.21 | Security of network services | ✅ | Managed providers; HTTPS/HSTS. |
| 8.22 | Segregation of networks | ➖ | Provider-managed network isolation. |
| 8.23 | Web filtering | ➖ | N/A (no outbound proxy needed; SSRF surface verified absent). |
| 8.24 | Use of cryptography | ✅/🟡 | TLS in transit (ENC-1 pinned `sslmode=require`); R2 SSE-AES256 in code (ENC-2); bcrypt/JWT-HS256. **Gap: no documented key-management/rotation procedure (SEC-1).** |
| 8.25 | Secure development lifecycle | 🟡 | [SECURE_SDLC.md](SECURE_SDLC.md); CI gates present, branch protection pending. |
| 8.26 | Application security requirements | ✅ | Input validation (Pydantic), magic-byte upload check (FILE-1), object-level authz, CSRF guard. |
| 8.27 | Secure system architecture | ✅ | Chokepoint authz (`get_report`, `_resolve_client_id`), content-addressed storage, append-only audit. |
| 8.28 | Secure coding | ✅ | Parametrized ORM (no SQLi), header-injection-safe downloads, generic error bodies, **CodeQL** added. |
| 8.29 | Security testing in development & acceptance | 🟡 | Regression tests incl. cross-tenant + ISO-hardening suites; **no DAST/pentest yet**. See [SECURITY_TESTING_CHECKLIST.md](SECURITY_TESTING_CHECKLIST.md). |
| 8.30 | Outsourced development | ➖ | Development in-house (+ AI-assisted). |
| 8.31 | Separation of dev/test/prod | 🟡 | Local vs prod env gating; **no dedicated staging** (demo tier only). |
| 8.32 | Change management | 🟡 | [CHANGE_MANAGEMENT.md](CHANGE_MANAGEMENT.md); CI/snapshot discipline; enforcement (branch protection) pending. |
| 8.33 | Test information | ✅ | Tests use synthetic/in-memory SQLite; demo seeders, no real tenant PII in tests. |
| 8.34 | Protection of systems during audit testing | 🟡 | Tests isolated from dev DB (in-memory); documented gotcha exists. |

## 5. Summary scorecard

| Theme | Implemented | Partial | Gap | Inherited/NA |
|---|---|---|---|---|
| 27001 mgmt clauses (4–10) | 0 | 5 | 2 | — |
| Organizational (5.x) | 7 | 13 | 4 | — |
| People (6.x) | 0 | 3 | 5 | — |
| Physical (7.x) | 0 | 0 | 1 | 1 |
| Technological (8.x) | 12 | 11 | 3 | 5 |

**Interpretation:** the **technological control surface is strong** (the product is the hardened part). The gaps cluster in **management system, people controls, monitoring (8.16), malware (8.7), and a few authentication/backup items**. None of the open items are blockers to *operating* the product securely today; they are blockers to *certification*. Prioritised remediation: [REMEDIATION_TRACKER.md](REMEDIATION_TRACKER.md).
