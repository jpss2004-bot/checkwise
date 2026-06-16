---
Document: Security & Compliance Remediation Tracker
ID: CW-ISO-remediation-tracker
Owner: Lead Engineer / acting CISO (Jose Pablo Samano)
Version: 0.1
Effective: 2026-06-16
Review cadence: per audit + monthly during active remediation
ISO refs: ISO/IEC 27001:2022 cl.10 (improvement); ISO 37001:2016 cl.10
Status: LIVE tracker
---

# Remediation Tracker — CheckWise

Consolidates findings from the **2026-06-15 security/perf audit** and the **2026-06-16 ISO-readiness audit** (7 domains: auth, authz/tenant-isolation, file/storage, API edge, audit/37001, infra/secrets, frontend/UX). Status: ✅ Fixed (this pass) · 🔧 Fixed earlier (2026-06-15) · 📋 Open/planned · ➖ Accepted/by-design.

## 1. Fixed in the 2026-06-16 ISO-readiness pass

All changes are in the working tree (not committed/pushed) and validated: `ruff` clean on changed files, app builds (173 routes), 13 new regression tests + 87 existing auth/cross-tenant/config tests pass; the 2 portal failures are the pre-existing stub-PDF environmental issue (`requiere_aclaracion` vs `pendiente_revision`), reproduced on HEAD.

| ID | Finding | Sev | Fix | Files |
|---|---|---|---|---|
| FILE-DEL-1 | Cross-tenant document destruction — shared content-addressed object deleted on cancel/rollback without a reference check | **High** | `_delete_orphaned_objects()` refcount guard; only deletes when no `Document` still references the key; fails safe (skip on uncertainty) | `apps/api/app/api/v1/portal.py` |
| ENC-1 | DB TLS not enforced in code (libpq defaults to `prefer` → silent plaintext) | **High** | Auto-pin `sslmode=require` for non-local Postgres URLs (preserves explicit stricter modes); boot warning on insecure mode | `apps/api/app/core/config.py` |
| ENC-2 | Object server-side-encryption relied on provider default, not asserted in code | Med | `ServerSideEncryption=AES256` on both S3/R2 write paths; config flag `STORAGE_SSE_ALGORITHM` | `apps/api/app/services/storage.py`, `config.py` |
| AUDIT-SHARE | Report share-link disclosure to external parties invisible (mint/revoke unaudited) | **High** | `report.share_minted` / `report.share_revoked` audit events with actor/IP/UA/audience/expiry (never the token) | `apps/api/app/api/v1/reports.py` |
| AUTH G-4 | No common/breached-password check (composition-only) | Med | Offline common-password denylist wired into the password validator | `apps/api/app/core/common_passwords.py`, `auth.py` |
| AUTH G-7 | Logout not audited (session-end had no trail) | Low | `auth.logout` audit event (best-effort principal resolution; never fails logout) | `apps/api/app/api/v1/auth.py` |
| API GAP-2 | CSP only on JSON responses | Low | `frame-ancestors 'none'; base-uri 'none'` CSP subset on **every** response | `apps/api/app/main.py` |
| API GAP-6 | 500 handler could reflect any Origin if `CORS_ORIGINS=*` | Low | Dropped the `"*" in allowed_origins` reflection branch (exact-match only) | `apps/api/app/main.py` |
| FILE GAP-6 | No `no-store` on sensitive document responses | Low | `Cache-Control: no-store, private` on the 3 document `FileResponse` paths + `ResponseCacheControl` on presigned URLs | `portal.py`, `client.py`, `reviewer.py`, `storage.py` |
| CICD-1 | No SAST in CI | Med | CodeQL workflow (python + javascript-typescript) | `.github/workflows/codeql.yml` |
| CICD-2 | No automated dependency-update PRs | Med | Dependabot (pip + npm + github-actions, weekly) | `.github/dependabot.yml` |
| CICD-3 (partial) | No code-ownership / change-control mapping | Med | `CODEOWNERS` mapping security-critical paths (enforcement pending branch protection) | `.github/CODEOWNERS` |
| GOV-DOCS | No ISO governance/evidence layer | — | This `docs/compliance/` suite (16 documents) | `docs/compliance/` |

## 2. Open / planned (prioritised)

### P0 — Critical security (next code phase)
| ID | Finding | Sev | Recommended action | Effort |
|---|---|---|---|---|
| AUTH-MFA | No MFA/2FA anywhere | High | TOTP (pyotp) opt-in; enforce for `internal_admin`/`platform_admin`; recovery codes | L |
| AUTH-JWT | JWTs non-revocable for 24h; reset/disable/compromise don't kill live tokens | High | `User.token_epoch` claim; reject stale tokens; bump on password change/disable → also enables "log out all sessions" | M |
| DOC-AV | No malware scanning on documents that reach external auditors | High | ClamAV/clamd scan on intake (background, quarantine on hit) | M–L |
| BCP-R2 | R2 object-versioning state contradicted across runbooks → possible permanent loss | High | Verify Cloudflare console; enable versioning; reconcile `OPERATOR_RUNBOOK_V1.md` vs `PRODUCTION_ENV_SETUP_CHECKLIST.md` | S |

### P1 — High ISO-readiness gaps
| ID | Finding | Sev | Action | Effort |
|---|---|---|---|---|
| AUDIT-RPT-1 | Report create/edit/version/delete/export unaudited | High | Add `report.*` lifecycle audit events in the reports service | M |
| DD-37001 | No vendor due-diligence / COI layer | High | Risk tier + COI flag + screening fields on `Vendor`; surface in expediente/report | L |
| FILE GAP-4 | PDF active-content (JS/launch/embedded) detected but advisory-only | Med | Route HIGH active-content to `REQUIERE_ACLARACION` (quarantine from ZIPs); extend detector | M |
| API GAP-1 | No global request-body-size cap (JSON DoS) | Med | ASGI middleware: 413 over `MAX_REQUEST_BODY_BYTES` (exempt upload paths) | S |
| API GAP-4 / INFRA-4 | XFF first-hop trusted (spoofable) | Med | Use right-most trusted hop / `--forwarded-allow-ips` | M |
| CICD-3 | Branch protection not enforced (direct-to-main) | Med | Enable on `main`: required PR + Code Owner review + required status checks (CI/Security/CodeQL) | S (config) |
| DB-1 | No `statement_timeout` backstop | Med | pgbouncer-safe per-session timeout | S–M |
| DB-2 | App runs as DB owner role (can DDL/bypass audit triggers) | Med | DML-only runtime role; reserve owner for Alembic | M |
| FILE GAP-2 | Expediente/audit ZIP fully buffered in RAM (OOM/DoS) | Med | Stream via `zipstream-ng`/spooled temp file | M |
| G-4 (audit) | Audit-log read not audited; no external-auditor export | Med | `audit_log.viewed`/`exported` + gated CSV/JSON export endpoint | S–M |
| G-6 (audit) | Audit immutability bypassable by DB superuser; no hash-chain | Med | Least-priv DB role + optional per-row hash-chain | M/L |
| AUTH-IDLE | 24h token, no idle timeout, no refresh | Med | Shorter access token + refresh, or idle timeout via token_epoch | M |
| OBS-1 | No error monitoring / alerting | Med | Wire Sentry; alert on lockout/5xx spikes | M |

### P2 — Governance / process
| ID | Finding | Action | Effort |
|---|---|---|---|
| MGMT-1 | No signed InfoSec/anti-bribery policy, no CISO appointment | Author + sign policies; appoint owner | M |
| MGMT-2 | No internal-audit/management-review cadence | Establish schedule + metrics | M |
| ACCESS-REV | No periodic access review | Quarterly access review + log (procedure drafted) | S |
| BCP-2 | No tested RTO/RPO drill | Quarterly Neon restore drill + log | M |
| TRAIN-1 | No security-awareness training | Establish programme + records | M |
| WB-1 | No whistleblowing channel (37001 8.8) | Add confidential concern channel | M |
| G-5 (audit) | `actor_type` defaults to `"system"` | Require explicit actor_type | S |
| SEC-1 | JWT HS256 single secret, no documented rotation | Rotation runbook (+ optional `kid` dual-key) | M |
| SEC-2 | gitleaks allowlists whole `scripts/` tree | Narrow allowlist to specific fixtures | S |

### P3 — UX trust (frontend)
| ID | Finding | Action | Effort |
|---|---|---|---|
| UX-3 | Weak tenant-boundary signal | Persistent org/RFC chip; "viewing client X" banner for staff | S–M |
| UX-1/UX-4 | No account/security page; no self-service password change for staff/provider | `/admin/cuenta` + portal "Seguridad" (reuse `setPassword`) | M |
| UX-2 | Inconsistent destructive-action confirmation (`window.confirm`, silent share-revoke) | Shared `<ConfirmDialog>`; gate revoke + portal deletes | M |
| SEC-3 (FE) | Raw backend error text surfaced in 17 components | `humanizeApiError(status)` mapper | M |
| SEC-1 (FE) | `/portal/*` not in edge middleware matcher | Add to matcher (portal cookie) or document | S |
| SEC-4 (FE) | Stale "JWT in localStorage" comments (code is correct) | Comment cleanup | S |

## 3. Accepted / by-design (documented risk acceptances)
| ID | Item | Rationale |
|---|---|---|
| REVIEWER-SCOPE | `reviewer`/`internal_admin` have intentional cross-tenant read | Platform operation requires it; mitigated by per-download audit + lockout. Logged as accepted risk (R-01 context). |
| LEGACY-INTAKE | Legacy `POST /submissions` trusts body tenant identity | Disabled in prod via `EXPOSE_LEGACY_SUBMISSIONS=false`; verify env (GAP-2). |
| INFRA-2 | In-memory rate limiter | Correct on single worker; Redis required before scale-out. |

## 4. Performance items (from 2026-06-15, tracked for completeness)
PERF-2/4/6 fixed; PERF-7 indexes (migration 0046) + PERF-5 background intake shipped 2026-06-15. PERF-1 (per-report context), PERF-8 (catalog cache), PERF-10 (workers post-Redis) remain recommended.
