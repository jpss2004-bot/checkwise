---
Document: Audit Logging Specification
ID: CW-ISO-audit-logging
Owner: Lead Engineer / acting CISO (Jose Pablo Samano)
Version: 0.1 (draft)
Effective: 2026-06-16
Review cadence: on logging change + annual
ISO refs: ISO/IEC 27002:2022 8.15 (logging), 8.16 (monitoring), 5.28 (evidence), 5.33 (record protection); ISO 37001 7.5
Status: DRAFT — ISO-readiness evidence
---

# Audit Logging Specification — CheckWise

Defines what CheckWise records as tamper-resistant audit evidence, the record format, the event taxonomy, retention, integrity protection, and access — the backbone of both ISO 27002 8.15 and ISO 37001 traceability.

## 1. Record model (`AuditLog`)

Source: `apps/api/app/models/entities.py` (`class AuditLog`) + writer `apps/api/app/services/audit_log.py`.

| Field | Meaning (the audit "5 Ws") |
|---|---|
| `id` | Record id |
| `created_at` | **WHEN** — tz-aware UTC timestamp |
| `actor_type` | **WHO (kind)** — `user` / `provider` / `reviewer` / `internal_admin` / `anonymous` / `system` |
| `actor_id` | **WHO (identity)** — user id (nullable) |
| `action` | **WHAT** — dotted event name (taxonomy below) |
| `entity_type` + `entity_id` | **WHAT (target object)** |
| `before` / `after` | **OUTCOME** — JSON state delta |
| `event_metadata` | Contextual JSON (workspace_id, client_id, audience, share_id, etc.) |
| `ip_address` / `user_agent` | **WHERE-FROM** — request provenance (migration 0043) |

## 2. Integrity & retention

- **Append-only (immutability):** migration `0031_audit_log_append_only.py` installs DB triggers that **reject UPDATE and DELETE** on `audit_log`. This is a genuine record-protection control (ISO 27002 5.33).
- **Known limitation (tracked, G-6):** the trigger is bypassable by a DB **superuser** (`ALTER TABLE … DISABLE TRIGGER`), and there is no hash-chain. Hardening plan: run the app under a non-owner, DML-only DB role and/or add a per-row `prev_hash` chain for tamper-evidence. See [REMEDIATION_TRACKER.md](REMEDIATION_TRACKER.md).
- **Retention:** audit records are retained for the life of the tenant relationship + the statutory REPSE/labor retention period. ⚠ **TO VERIFY** — pin a concrete retention duration in policy (recommend ≥ 5 years for compliance evidence) and confirm it against Neon storage/backup limits. Records are classified **Confidential (T2)** — see [DATA_CLASSIFICATION.md](DATA_CLASSIFICATION.md).
- **Provenance accuracy caveat:** `ip_address` is currently sourced from the first `X-Forwarded-For` hop (spoofable, INFRA-4). Treat IP as advisory until the right-most-hop fix lands.

## 3. Event taxonomy (current state)

✅ implemented · 🆕 added 2026-06-16 · 📋 planned (gap)

### Authentication & session
- ✅ `auth.login.succeeded`, `auth.login.failed` (IP/UA, reason)
- ✅ `auth.password_changed`, `auth.password_reset_requested`, `auth.password_reset_completed`
- 🆕 `auth.logout` (G-7 — best-effort principal, IP/UA)

### Document review (ISO 37001 decision spine)
- ✅ `submission.reviewer_decision` (approve/reject/clarify/exception; actor, before/after, reason)
- ✅ `system.auto_approved` (full eligibility-evidence snapshot)
- ✅ `submission.created`, `submission.uploaded`, `submission.replacement_linked`, `provider.submission_cancelled`
- ✅ `correction_request.submitted` (+ admin resolve)

### Reports & disclosure
- 🆕 `report.share_minted`, `report.share_revoked` (AUDIT-SHARE — actor, audience, expiry, share_id; never the token)
- 📋 `report.created` / `report.updated` / `report.version_created` / `report.deleted` / `report.exported` (AUDIT-RPT-1 gap)
- 📋 `report.share_consumed` (external view; partially covered today by `ReportShare.access_count` + `last_accessed_at`)

### Administration
- ✅ `admin.user.provisioned` / `.deleted` / `.restored` / `.identity_updated` / `_password_reset`
- ✅ `admin.user.membership_granted` / `_revoked` / `_promoted`
- ✅ `admin.vendor.*`, `admin.requirement.*`, `admin.client.updated`, `admin.workspace.updated`
- ✅ `client.user_*` (multi-user seats)
- ✅ legal-consent acceptance (`*.legal_consent_accepted`)

### Data access (evidence downloads)
- ✅ `*.expediente_downloaded`, `*.document_downloaded`, `client.audit_package_downloaded` (actor, doc id, filename, size)
- 📋 `audit_log.viewed` / `audit_log.exported` (G-4 gap — reading the log is not itself logged; no external-auditor export endpoint)
- 🟡 metadata workbook export logged as `ValidationEvent` (`metadata_table_exported`), not `AuditLog` (G-8 — inconsistent home)

## 4. What an event MUST capture (writer contract)

Every call to `add_audit_event(...)` for a **human** action MUST pass `actor_type` and `actor_id`; `"system"` is reserved for genuinely system-initiated actions. ⚠ Defense-in-depth gap (G-5): `actor_type` currently defaults to `"system"` — planned to be made explicit so a careless call can't mint an anonymous record for a human action.

For sensitive/disclosure actions, also capture: target `entity_type`/`entity_id`, `before`/`after` where state changes, `ip_address`/`user_agent`, and any disclosure context (audience, expiry) in `event_metadata` — **never** secrets/tokens/raw document bytes.

## 5. Monitoring (gap)

Audit logging is **telemetry, not detection** today — there is **no active monitoring/alerting** (ISO 27002 8.16, finding OBS-1). Planned: ship Sentry + structured log export; alert on auth-lockout bursts, 5xx spikes, and (once `audit_log.viewed` exists) anomalous audit-log access. Until then, the audit log supports *post-hoc* investigation (see [INCIDENT_RESPONSE_PLAN.md](INCIDENT_RESPONSE_PLAN.md)).

## 6. Access to audit records

- Read access: `platform_admin` via the `/platform/audit-log` explorer; `internal_admin` via admin surfaces. Client/provider users cannot read the audit log.
- ⚠ Access to the audit log is **not yet itself audited** (G-4) — close before relying on the log as sole evidence integrity.
- External-auditor export: **planned** (gated CSV/JSON) — see [evidence/README.md](evidence/README.md).
