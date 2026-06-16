---
Document: ISO-Readiness Evidence Suite — Index & Readiness Summary
ID: CW-ISO-readme
Owner: Lead Engineer / acting CISO (Jose Pablo Samano)
Version: 0.1 (draft)
Effective: 2026-06-16
Review cadence: per audit
ISO refs: ISO/IEC 27001:2022, ISO/IEC 27002:2022, ISO 37001:2016
Status: DRAFT — ISO-readiness evidence, NOT a certification claim
---

# CheckWise — ISO-Readiness Evidence Suite

> **Important — no certification claim.** CheckWise is **not** ISO 27001 or ISO 37001 certified. This suite is an honest **readiness** assessment: it documents what controls exist (with code evidence), what is missing or weak, and the roadmap to certification readiness. Certification requires an operating management system, an evidence period, and an audit by an accredited body. Nothing here should be represented to a customer as "ISO certified" or "ISO compliant" — the accurate phrasing is *"built to ISO 27001/27002 and 37001 control principles; certification-readiness in progress."*

This suite was produced by the **2026-06-16 ISO-readiness audit**, building on the **2026-06-15 security/performance audit** (`_handoff/audit-security-perf-2026-06-15.md`). Findings are code-grounded and verified against real paths.

## 1. How to read this suite

| If you want… | Read |
|---|---|
| The bottom line on ISO 27001/27002 readiness | [ISO27001_27002_GAP_ANALYSIS.md](ISO27001_27002_GAP_ANALYSIS.md) |
| The bottom line on ISO 37001 (anti-bribery) readiness | [ISO37001_GAP_ANALYSIS.md](ISO37001_GAP_ANALYSIS.md) |
| The ranked list of what to fix and its status | [REMEDIATION_TRACKER.md](REMEDIATION_TRACKER.md) |
| The risk picture (scored, with treatment) | [RISK_REGISTER.md](RISK_REGISTER.md) |
| Who can do what | [ROLE_PERMISSION_MATRIX.md](ROLE_PERMISSION_MATRIX.md) · [ACCESS_CONTROL_POLICY.md](ACCESS_CONTROL_POLICY.md) |
| What data exists and how it's classified | [ASSET_INVENTORY.md](ASSET_INVENTORY.md) · [DATA_CLASSIFICATION.md](DATA_CLASSIFICATION.md) |
| How traceability/audit works | [AUDIT_LOGGING_SPEC.md](AUDIT_LOGGING_SPEC.md) |
| Operational resilience | [INCIDENT_RESPONSE_PLAN.md](INCIDENT_RESPONSE_PLAN.md) · [BACKUP_RECOVERY_BCP.md](BACKUP_RECOVERY_BCP.md) |
| Engineering governance | [CHANGE_MANAGEMENT.md](CHANGE_MANAGEMENT.md) · [SECURE_SDLC.md](SECURE_SDLC.md) · [SECURITY_TESTING_CHECKLIST.md](SECURITY_TESTING_CHECKLIST.md) |
| Third-party/supplier risk | [VENDOR_RISK_REGISTER.md](VENDOR_RISK_REGISTER.md) |
| The evidence-collection structure | [evidence/README.md](evidence/README.md) |

## 2. Document set

**Analysis & registers**
- `ISO27001_27002_GAP_ANALYSIS.md` — Annex A control matrix + management-system clauses (proto-SoA).
- `ISO37001_GAP_ANALYSIS.md` — anti-bribery capability + organizational ABMS gaps.
- `RISK_REGISTER.md` — 25 scored risks with controls, residual, treatment.
- `REMEDIATION_TRACKER.md` — every finding → status (fixed/open/accepted).

**Policies & standards**
- `ACCESS_CONTROL_POLICY.md`, `DATA_CLASSIFICATION.md`, `ASSET_INVENTORY.md`, `ROLE_PERMISSION_MATRIX.md`, `AUDIT_LOGGING_SPEC.md`, `VENDOR_RISK_REGISTER.md`

**Procedures**
- `INCIDENT_RESPONSE_PLAN.md`, `BACKUP_RECOVERY_BCP.md`, `CHANGE_MANAGEMENT.md`, `SECURE_SDLC.md`, `SECURITY_TESTING_CHECKLIST.md`

**Evidence**
- `evidence/README.md` — folder map + collected-vs-needed status.

## 3. Readiness summary (2026-06-16)

**Posture: strong technical control surface, thin management/governance layer.** The product itself is well-hardened — structural tenant isolation (no exploitable IDOR found), append-only audit log, DB-backed lockout, constant-time auth, strict CORS/CSRF/headers, clean production dependency scan, secret-scanning in CI, and structural segregation of duties. The gaps cluster in (a) a few real technical items, (b) ISO 37001 traceability of the report deliverable + third-party due-diligence, and (c) the formal ISMS/ABMS management system.

**ISO 27001/27002:** technological controls largely Implemented/Partial; the dominant work is **management-system formalisation** (policy, roles, risk-treatment sign-off, internal audit, management review) plus **MFA (8.5), malware scanning (8.7), monitoring/alerting (8.16), and backup verification (8.13)**.

**ISO 37001:** the **decision/approval evidence spine is strong** (traceable, attributable, immutable, with maker-checker SoD). Capability gaps: **third-party due-diligence/COI layer**, **report-lifecycle + share-consume auditing** (share mint/revoke now done), **whistleblowing channel**, and **audit-log tamper-evidence hardening**. Organizational ABMS (anti-bribery policy, training) not yet started.

### Controls implemented in this pass (2026-06-16)
Cross-tenant data-destruction fix (refcount-guarded object delete), DB-TLS enforced in code, R2 SSE-AES256 in code, report share mint/revoke auditing, logout auditing, common-password denylist, universal CSP subset, no-store on documents, dropped wildcard-origin reflection, CodeQL SAST + Dependabot + CODEOWNERS, and this 16-document evidence suite. All backend changes validated (ruff clean, app builds, 13 new + 87 existing tests pass). Full detail and the prioritised remaining roadmap: [REMEDIATION_TRACKER.md](REMEDIATION_TRACKER.md).

### Top remaining priorities
1. **MFA** for privileged roles (R-03).
2. **Confirm/enable R2 object versioning** (R-06 — possible permanent data loss).
3. **Malware scanning** of uploaded documents (R-05).
4. **Branch protection** on `main` (R-18) — CODEOWNERS is in place; enforcement is the missing half.
5. **Report-lifecycle audit + vendor due-diligence/COI** (37001).
6. **Monitoring/alerting** (R-20) and a **tested backup-restore drill** (R-21).
7. **Stand up the ISMS** (policy, owner, internal audit, management review).

## 4. Maintenance

Update this suite on each security audit, incident, material architecture change, or new sub-processor. The `Version`/`Effective` headers and the remediation tracker are the change record. Treat every "⚠ TO VERIFY" marker as an open action.
