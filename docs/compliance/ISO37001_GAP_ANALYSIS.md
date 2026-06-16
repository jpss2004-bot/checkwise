---
Document: ISO 37001:2016 Anti-Bribery Readiness & Capability Gap Analysis
ID: CW-ISO-37001-gap
Owner: Lead Engineer / acting CISO + Compliance lead (Jose Pablo Samano)
Version: 0.1 (draft)
Effective: 2026-06-16
Review cadence: annual + on material change
ISO refs: ISO 37001:2016 (clauses 4–10), with emphasis on 5.3.2, 7.5, 8.2, 8.7, 8.8, 8.9
Status: DRAFT — readiness evidence, NOT a certification claim
---

# ISO 37001 Anti-Bribery Readiness — CheckWise

> **Two lenses.** ISO 37001 readiness for CheckWise has two distinct meanings, and this document covers both:
> 1. **Platform capability** — does CheckWise *support* its clients' anti-bribery / anti-corruption controls (traceability, approval flows, segregation of duties, evidence preservation, accountability)? This is the product angle and where CheckWise is **strong**.
> 2. **Organizational ABMS** — does the company LegalShelf operate its own ISO 37001 anti-bribery management system? This is **largely not started** (a small-company governance gap, not a product gap).
>
> CheckWise is **not ISO 37001 certified**. This is a readiness assessment.

CheckWise's domain (REPSE labor-compliance, third-party/vendor evidence) makes anti-corruption *traceability* core to its value: the platform's job is to make "who reviewed, approved, rejected, or changed what, and on what evidence" provable. That is exactly the control posture ISO 37001 expects of record-keeping (7.5) and controls (8.7).

## 1. Platform capability vs ISO 37001 control needs

| Capability ISO 37001 expects | CheckWise support | Status | Evidence / Gap |
|---|---|---|---|
| **Clear approval flows** | Document review workflow: provider submits → reviewer decides (approve/reject/clarify/exception) | ✅ | `submission_workflow.py` decision path (atomic status + history + validation event + audit row). |
| **Traceable decisions** | Every reviewer decision writes `submission.reviewer_decision` with actor, before/after, reason | ✅ | `submission_workflow.py:279,409`. |
| **Audit logs for sensitive actions** | Broad audit coverage (auth, decisions, admin, downloads, consent, **report-share mint/revoke**, **logout**) | ✅/🟡 | [AUDIT_LOGGING_SPEC.md](AUDIT_LOGGING_SPEC.md); gaps: report create/edit lifecycle, share *consume*, audit-log read. |
| **Conflict-of-interest flags** | — | ⛔ | **No COI flag/field on vendors or reviewers.** Top 37001 capability gap (DD-37001). |
| **Evidence preservation** | Content-addressed immutable document store; append-only audit log; report versioning | ✅ | `storage.py` (sha256 keys); migration `0031_audit_log_append_only.py`. |
| **User accountability** | Named-actor attribution on actions; IP/UA provenance on auth + admin | ✅/🟡 | `audit_log` model; gap: `actor_type` defaults to `"system"` (G-5) — recommend explicit. |
| **Documented review steps** | Decision reason/observations captured + document status history | ✅ | `DocumentStatusHistory`, `ValidationEvent`. |
| **Segregation of duties** | Provider (submits) ≠ Reviewer (decides) ≠ Client (consumes); enforced by role architecture | ✅ | Provider authenticates via workspace portal-session token; cannot hold `reviewer`/`internal_admin` role (`roles.py`). |
| **Role-based approvals** | Decisions gated to `reviewer`/`internal_admin`; auto-approval dark-by-default & fully gated | ✅ | `reviewer.py` role gate; `auto_approval.py` (disabled by default, audited as `system.auto_approved`). |
| **Anti-corruption compliance workflow** | Correction-request flow, exception handling, renewal reminders | ✅ | `correction_request_service.py`; renewal crons. |
| **Supplier/provider due diligence** | — | ⛔ | **No due-diligence record, risk rating, screening, sanctions/PEP, or beneficial-owner data on `Vendor`.** (DD-37001). |
| **Third-party risk checks** | — | ⛔ | Same as above; no risk tier on vendors. |
| **Policy acknowledgement tracking** | Legal consent gate (terms/privacy) accepted + audited | 🟡 | `client.py`/`portal.py` `*.legal_consent_accepted`; covers ToS/privacy, not an anti-bribery policy ack. |
| **Escalation workflows** | Clarification/exception statuses; correction requests to admins | 🟡 | Present for document review; no dedicated compliance-escalation/COI path. |
| **Exception handling** | `exception` decision outcome, audited | ✅ | `submission_workflow.py`. |
| **Evidence of who reviewed/approved/rejected/changed** | Decision + actor + reason + before/after + timestamp | ✅ | The decision audit spine — CheckWise's strongest 37001 asset. |
| **Immutable / tamper-resistant records** | DB-level append-only audit log | ✅/🟡 | Triggers prevent UPDATE/DELETE; **bypassable by a DB superuser / no hash-chain** (G-6) — see hardening below. |
| **Whistleblowing / raising concerns (8.8)** | — | ⛔ | No in-product channel to raise a corruption concern confidentially. |

**Verdict (platform):** CheckWise already delivers the *spine* of an anti-corruption evidence system — traceable, attributable, immutable decision records with structural separation of duties. The two material **capability** gaps are **(a) third-party due-diligence / COI layer** and **(b) a whistleblowing/concern channel**, plus tamper-evidence hardening of the audit log.

## 2. Organizational ABMS (ISO 37001 clauses 4–10)

| Clause | Requirement | Status | Gap / Action |
|---|---|---|---|
| 4 | Context, scope, bribery risk assessment | ⛔ | No documented bribery-risk assessment for LegalShelf as an organization. |
| 5.1 Leadership | Top-management commitment | ⛔ | Not documented. |
| 5.2 | Anti-bribery policy | ⛔ | **No anti-bribery policy** published/acknowledged. **Action: author + require acknowledgement.** |
| 5.3 / 5.3.2 | Roles; anti-bribery compliance function; **segregation of duties** | 🟡 | Product-level SoD is strong; **organizational** anti-bribery compliance function not appointed. |
| 6 | Planning, objectives | ⛔ | No anti-bribery objectives. |
| 7.2 | Competence / 7.3 awareness / 7.4 communication | ⛔ | No anti-bribery training/awareness. |
| 7.5 | Documented information | 🟡 | The platform's evidence capability is excellent; org-level documented info not started. |
| 8.2 | **Due diligence** (on transactions, projects, business associates) | ⛔ | Neither the org nor the product captures structured due-diligence records — the central 8.2 gap (DD-37001). |
| 8.3 | Financial controls / 8.4 non-financial controls | 🟡 | Product provides non-financial compliance controls; org financial controls out of scope here. |
| 8.5 | Anti-bribery commitments from business associates | ⛔ | Not captured. |
| 8.6 | Gifts, hospitality, donations | ⛔ | No policy/register. |
| 8.7 | Implementing controls (managed by the org) | ✅(product) | The CheckWise control set itself is a strong 8.7 implementation for clients. |
| 8.8 | **Raising concerns (whistleblowing)** | ⛔ | No confidential reporting channel. |
| 8.9 | **Investigating & dealing with bribery** | 🟡 | Audit-log evidence supports investigation; no documented investigation procedure (overlaps [INCIDENT_RESPONSE_PLAN.md](INCIDENT_RESPONSE_PLAN.md)). |
| 9 | Monitoring, internal audit, management review | ⛔ | Not established (same as ISO 27001 clause 9). |
| 10 | Nonconformity & continual improvement | 🟡 | Remediation tracker provides the mechanism. |

## 3. Prioritised remediation (37001-specific)

| Pri | Item | ISO 37001 | Effort | Notes |
|---|---|---|---|---|
| **High** | **Vendor due-diligence / COI model** — add risk tier, COI flag, screening date/result, screened-by to `Vendor`; surface in expediente + report | 8.2, 8.3 | L | Schema + UI; the single biggest capability gap (DD-37001). |
| **High** | **Report lifecycle audit** — `report.created/updated/version_created/deleted/exported` events | 7.5, 8.7 | M | Share mint/revoke already audited (2026-06-16, AUDIT-SHARE); extend to create/edit/export (AUDIT-RPT-1). |
| **High** | **Audit-log read auditing + external-auditor export** — `audit_log.viewed`/`audit_log.exported` + a gated CSV/JSON export | 7.5.3, 9.2 | S–M | Makes log access self-traceable and gives auditors a deliverable (G-4). |
| **Med** | **Tamper-evidence** — run app under a non-owner DB role (revoke ALTER/TRUNCATE on `audit_log`) and/or add a per-row hash-chain | 7.5, control integrity | M/L | Closes the superuser-bypass note in `0031` (G-6). |
| **Med** | **Explicit actor attribution** — require `actor_type` (no silent `"system"` default) | accountability | S | G-5 defense-in-depth. |
| **Med** | **Whistleblowing / raise-a-concern channel** | 8.8 | M | Confidential reporting path (could reuse feedback infra with confidentiality). |
| **Med** | **Anti-bribery policy + acknowledgement tracking** | 5.2, 8.5 | M | Author policy; track ack like the existing legal-consent gate. |
| **Low** | **Within-staff four-eyes** on reviewer-role grants | 5.3.2 | M | Optional second-approver for privileged-role grants. |
| **Low** | **Consistent audit home** — mirror metadata-export events into `audit_log` | 7.5 | S | G-8. |

## 4. What is genuinely strong (do not regress)

- **Structural maker-checker**: the uploader of evidence can never approve it (provider vs reviewer are different principals by architecture).
- **Atomic, attributable decision trail** with reason + before/after + status history.
- **DB-enforced append-only audit log** — a real immutability control most SaaS lack.
- **Dark-by-default, fully-gated, fully-audited auto-approval** — automation that still preserves the evidence trail.
- **ADMIN-1 privilege-escalation guard** — prevents lateral self-escalation of staff roles.

See also: [AUDIT_LOGGING_SPEC.md](AUDIT_LOGGING_SPEC.md), [ROLE_PERMISSION_MATRIX.md](ROLE_PERMISSION_MATRIX.md), [REMEDIATION_TRACKER.md](REMEDIATION_TRACKER.md).
