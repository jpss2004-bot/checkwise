---
Document: Information Security & Anti-Bribery Risk Register
ID: CW-ISO-risk-register
Owner: Lead Engineer / acting CISO (Jose Pablo Samano)
Version: 0.1 (draft)
Effective: 2026-06-16
Review cadence: quarterly + on material change or incident
ISO refs: ISO/IEC 27001:2022 cl.6.1; ISO 37001:2016 cl.6.1
Status: DRAFT — risk-acceptance sign-off PENDING
---

# Risk Register — CheckWise

Risk scoring: **Likelihood (L)** and **Impact (I)** each 1–5; **Score = L × I**. Bands: 1–4 Low, 5–9 Medium, 10–14 High, 15–25 Critical. "Residual" reflects risk *after* current controls. Treatment: **Mitigate / Accept / Transfer / Avoid**.

> Risk-acceptance for any **Accept** decision and any residual ≥ High requires the risk owner's sign-off (currently pending — see §3).

## 1. Risk register

| ID | Risk | Category | Inherent L×I | Current controls | Residual L×I | Treatment | Linked finding / doc |
|---|---|---|---|---|---|---|---|
| R-01 | Cross-tenant data exposure (one tenant reads another's documents/reports) | Confidentiality | 5×5=25 | Object-level authz at every by-id fetch; 404-no-enumeration; chokepoints (`get_report`, `_resolve_client_id`); REPORT-1 fix + cross-tenant regression tests | 2×5=10 | Mitigate | 27002 8.3; `test_cross_tenant_*` |
| R-02 | Cross-tenant **data destruction** via shared content-addressed object deleted on cancel/rollback | Integrity/Avail. | 4×4=16 | **Refcount guard before delete (FILE-DEL-1, fixed 2026-06-16)** + regression test | 1×4=4 | Mitigate | FILE-DEL-1 |
| R-03 | Account/credential compromise (no MFA; single-factor) | Auth | 4×5=20 | Strong password policy + common-password denylist (AUTH G-4), bcrypt-12, DB-backed lockout, login rate-limit, constant-time auth | 3×5=15 | Mitigate (MFA planned) | AUTH-MFA; 27002 5.17/8.5 |
| R-04 | Stolen/leaked JWT usable up to 24h; reset/disable don't revoke live tokens | Auth | 3×4=12 | 24h TTL; disable re-checked per request; cookie httpOnly+CSRF; logout audited | 3×4=12 | Mitigate (token-epoch planned) | AUTH-JWT |
| R-05 | Malware delivered via uploaded PDF, fanned out to external auditors in ZIPs | Integrity | 3×4=12 | `%PDF-` magic-byte check; decompression-bomb cap; content-addressed; active-content *detected* | 3×4=12 | Mitigate (AV scanning planned) | DOC-AV; FILE GAP-4 |
| R-06 | Permanent loss of tenant evidence document (delete with no recovery) | Availability | 3×5=15 | Soft-delete; refcount guard; Neon PITR for DB | 3×5=15 → TBD | Mitigate | **BCP-R2 (R2 versioning unconfirmed)** |
| R-07 | Disclosure of compliance evidence to external party via share link, untracked | Traceability | 3×4=12 | Share token hashed/expiring/revocable; **mint+revoke now audited (AUDIT-SHARE)**; access_count tracked | 2×3=6 | Mitigate | AUDIT-SHARE; share-*consume* per-view audit pending |
| R-08 | Database connection downgraded to plaintext (data in transit exposed) | Confidentiality | 3×5=15 | **`sslmode=require` pinned in code for non-local (ENC-1)** + boot warning on insecure mode | 1×5=5 | Mitigate | ENC-1 |
| R-09 | Object store at-rest exposure | Confidentiality | 2×5=10 | R2 at-rest by default + **SSE-AES256 asserted in code (ENC-2)**; private bucket; signed-URL TTL 15min | 1×5=5 | Mitigate | ENC-2 |
| R-10 | Privilege escalation by staff (platform_admin → internal_admin) | Auth | 3×5=15 | ADMIN-1 `_assert_can_grant_role` guard; role split | 1×5=5 | Mitigate | ADMIN-1 |
| R-11 | Audit-log tampering hides malicious activity | Integrity/NR | 3×5=15 | DB-level append-only triggers (migration 0031) | 2×4=8 | Mitigate (hash-chain + least-priv DB role planned) | G-6 |
| R-12 | Untraceable change to the core compliance deliverable (report create/edit/delete unaudited) | Traceability | 3×3=9 | Report read/write chokepoint; share+versioning; **create/edit/export still unaudited** | 3×3=9 | Mitigate (lifecycle audit planned) | AUDIT-RPT-1 |
| R-13 | DoS / resource exhaustion (no global body-size cap, single worker, no statement_timeout) | Availability | 3×3=9 | Per-file upload caps; endpoint rate-limits; pool hygiene | 3×3=9 | Mitigate | API GAP-1, DB-1, INFRA-1(rate) |
| R-14 | Brute-force / credential-stuffing | Auth | 4×3=12 | Per-IP + per-account rate-limit; lockout; generic 401; common-pw denylist | 2×3=6 | Mitigate | XFF first-hop trust (GAP-4) caveat |
| R-15 | Spoofed source IP via `X-Forwarded-For` (defeats per-IP limits, pollutes audit IPs) | Integrity (logs) | 3×2=6 | Per-account lockout bounds impact | 3×2=6 | Mitigate (right-most-hop planned) | INFRA-4 / API GAP-4 |
| R-16 | Supply-chain: vulnerable dependency ships to prod | Integrity | 3×4=12 | Lockfile pinning; pip-audit+npm audit (CI weekly); **CodeQL + Dependabot added**; clean prod audit | 1×4=4 | Mitigate | 27002 8.8 |
| R-17 | Committed secret / leaked credential | Confidentiality | 3×5=15 | `.gitignore` + gitleaks (full history, CI); secrets via Render env `sync:false`; JWT boot guard | 1×5=5 | Mitigate | 27002 8.24; SEC-2 (broad allowlist) |
| R-18 | Unauthorized change to prod (no branch protection; direct-to-main) | Change mgmt | 3×4=12 | CI/Security/CodeQL run; CODEOWNERS added; Neon snapshot discipline | 3×4=12 | Mitigate (branch protection planned) | CICD-3 |
| R-19 | Supplier/sub-processor breach or outage (Neon/R2/Render/Vercel/Anthropic) | Avail./Conf. | 3×4=12 | Reputable providers; multi-provider; IR plan | 2×4=8 | Mitigate/Transfer | [VENDOR_RISK_REGISTER.md](VENDOR_RISK_REGISTER.md); DPAs ⚠ to verify |
| R-20 | No detection/alerting of attack or anomaly | Detection | 4×3=12 | Audit logging (post-hoc); cloud provider logs | 4×3=12 | Mitigate (Sentry/alerting planned) | OBS-1; 27002 8.16 |
| R-21 | No tested recovery (RTO/RPO unproven) | Availability | 3×4=12 | Documented runbook; Neon PITR | 3×4=12 | Mitigate (drill planned) | BCP-2 |
| R-22 | PII mishandling / privacy non-compliance (LFPDPPP) | Compliance | 3×4=12 | Avisos + consent gate; classification; data minimization | 2×4=8 | Mitigate | 27002 5.34; counsel review |
| R-23 | **Anti-bribery: no third-party due-diligence / COI capture** | Compliance/37001 | 3×4=12 | Decision audit trail; evidence preservation | 3×4=12 | Mitigate (DD model planned) | DD-37001 |
| R-24 | **Anti-bribery: no whistleblowing channel** | 37001 8.8 | 2×3=6 | — | 2×3=6 | Mitigate (planned) | ISO37001 §3 |
| R-25 | Lost availability of rate-limiting on scale-out (in-memory limiter, no Redis) | Availability | 2×3=6 | Single-worker today (correct); boot warning | 2×3=6 | Accept (until scale-out) | INFRA-2 |

## 2. Risk heat summary

- **Critical residual (≥15):** R-03 (no MFA). 
- **High residual (10–14):** R-01, R-04, R-05, R-06, R-12, R-13, R-18, R-20, R-21, R-23.
- All others Medium/Low after current controls.
- **Largest single risk-reduction opportunities:** MFA (R-03), confirm/enable R2 versioning (R-06), AV scanning (R-05), branch protection (R-18), monitoring/alerting (R-20), BCP drill (R-21), vendor due-diligence (R-23).

## 3. Sign-off (pending)

| Role | Name | Decision | Date |
|---|---|---|---|
| Risk owner / acting CISO | Jose Pablo Samano | ☐ pending | — |

This register is a living document; update on each audit, incident, material change, or new sub-processor. Cross-references: [REMEDIATION_TRACKER.md](REMEDIATION_TRACKER.md), [ISO27001_27002_GAP_ANALYSIS.md](ISO27001_27002_GAP_ANALYSIS.md), [ISO37001_GAP_ANALYSIS.md](ISO37001_GAP_ANALYSIS.md).
