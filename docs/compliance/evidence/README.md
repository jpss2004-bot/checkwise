---
Document: Compliance Evidence Collection — Structure & Index
ID: CW-ISO-evidence-readme
Owner: Lead Engineer / acting CISO (Jose Pablo Samano)
Version: 0.1 (draft)
Effective: 2026-06-16
Review cadence: annual + on material change
ISO refs: ISO/IEC 27001:2022 Clause 9.2 (internal audit), 9.3 (management review), 10 (improvement); ISO/IEC 27002:2022 5.28 (collection of evidence), 5.36 (compliance), 8.8 (vuln mgmt), 8.13 (backup)
Status: DRAFT — ISO-readiness evidence scaffold, NOT a certification claim
---

# CheckWise — Compliance Evidence Collection

> **Purpose.** This folder is where CheckWise (operated by LegalShelf) collects the
> artifacts an internal or external assessor would ask to see when evaluating the
> ISMS. It is organized so each ISO control area maps to a predictable location.
>
> **Honesty note.** This is a **scaffold**. Most subfolders are documented here but
> not yet populated — the "Status" table (§4) is explicit about what exists vs.
> what still needs to be produced. Nothing here asserts ISO/IEC 27001
> certification. Unverified or not-yet-produced items are marked **⚠ TO VERIFY** or
> **NOT STARTED**.
>
> **Sensitivity.** Evidence may contain PII, IPs, and internal identifiers. **Do
> not commit raw audit-log dumps, customer data, screenshots with PII, or any
> secret into git.** Store sensitive exports in a controlled location and keep only
> redacted samples + an index here. **⚠ TO VERIFY** the controlled evidence store
> (e.g. a private drive / secrets-aware bucket) — this git folder holds structure +
> redacted samples only.

---

## 1. How to use this folder

- Each top-level subfolder maps to one evidence category (§3).
- Where evidence is **produced by a system** (CI, Neon, the audit log), this README
  records **how to regenerate it** rather than storing a stale copy.
- Where evidence is a **point-in-time record** (an access review, an incident, a
  backup-restore drill), store the dated artifact in the matching subfolder and add
  a one-line entry to that folder's local index.
- File naming convention: `YYYY-MM-DD_<short-slug>.<ext>` so artifacts sort
  chronologically.

---

## 2. Directory map

```
docs/compliance/
├── ACCESS_CONTROL_POLICY.md        # CW-ISO-access-control  (policy — source of truth)
├── VENDOR_RISK_REGISTER.md         # CW-ISO-vendor-risk     (supplier/sub-processor register)
└── evidence/
    ├── README.md                   # ← this file (index + map + status)
    ├── policies/                   # Approved ISMS policies & their version history
    ├── risk/                       # Risk assessment, risk treatment plan, SoA
    ├── access-reviews/             # Quarterly access-review logs + roster exports
    ├── change-records/             # Change-management evidence (PRs, deploys, migrations)
    ├── incident-records/           # Security-incident tickets, timelines, post-mortems
    ├── backup-drill-logs/          # Backup + restore-drill results (Neon snapshots, R2)
    ├── vulnerability-scan-exports/ # Dependency/CI/security-scan artifacts
    ├── audit-log-exports/          # Redacted exports/queries from the append-only audit_log
    ├── training-awareness/         # Security-awareness training records & acknowledgements
    └── supplier-dpas/              # Signed DPAs, SOC 2 / ISO certs, supplier-change log
```

> The subfolders above are **documented, not pre-created as empty dirs**. Create a
> subfolder the first time you file evidence into it, and drop a one-line
> `INDEX.md` (or a `.gitkeep` with a note) describing its contents. The intended
> contents of each are defined in §3.

---

## 3. Subfolder definitions (intended contents)

| Subfolder | What goes here | Who produces it |
|---|---|---|
| `policies/` | The approved policy set (this Access Control Policy, an Information Security Policy, Acceptable Use, Incident Response, Backup, etc.) plus version history and approval dates. | acting CISO |
| `risk/` | Asset inventory, risk assessment, risk treatment plan, and the **Statement of Applicability (SoA)** mapping ISO 27002 controls to applicable/not-applicable + justification. | acting CISO |
| `access-reviews/` | Dated quarterly access-review logs and the membership-roster export each was based on (see Access Control Policy §7). | acting CISO / Lead Engineer |
| `change-records/` | Evidence that changes are reviewed & controlled: PR links, the direct-to-main commit history, `render.yaml` deploy config, and Alembic migration ledger (e.g. 0042 soft-delete, 0043 audit IP/UA, 0044 platform_admin, 0045 lockout). | Lead Engineer / Eng |
| `incident-records/` | One file per security incident: detection, timeline, scope, remediation, lessons. Plus a register of "none this period" attestations. | acting CISO |
| `backup-drill-logs/` | Records of Neon snapshot/restore drills and R2 durability checks: date, what was restored, RPO/RTO observed, pass/fail. | Lead Engineer |
| `vulnerability-scan-exports/` | Dependency-audit and security-scan outputs (see §3b for the current tooling reality). | Eng / CI |
| `audit-log-exports/` | **Redacted** samples/queries demonstrating the append-only `audit_log` captures auth events, privileged grants, and document decisions with actor + IP + UA. | Lead Engineer |
| `training-awareness/` | Security-awareness training completion records and policy-acknowledgement sign-offs for all staff with access. | acting CISO |
| `supplier-dpas/` | Signed DPAs, vendor SOC 2 / ISO 27001 certificates, and a supplier onboarding/offboarding change log (ties to the Vendor Risk Register). | acting CISO |

### 3b. Reality check on automated evidence sources

| Evidence source | Exists today? | Notes |
|---|---|---|
| Append-only `audit_log` (actor, action, entity, before/after, **IP + UA**) | **Yes** | `AuditLog` model; IP/UA added in migration 0043. Covers `auth.login.succeeded/failed`, `auth.logout`, `auth.password_*`, privileged grants, document decisions. |
| Alembic migration ledger | **Yes** | Migrations through 0046 (`apps/api/alembic/`); `preDeployCommand: alembic upgrade head` in `render.yaml`. |
| Neon pre-deploy branch snapshots | **Partial / practice** | Used as rollback anchors before migration deploys. **⚠ TO VERIFY** automation + restore-drill records. |
| Secret hygiene boot guard | **Yes** | API refuses to boot in non-local with the placeholder JWT secret (`_validate_boot_security`). |
| Dependency pinning | **Yes** | `requirements.lock` + `render.yaml -c` pin (dependency hardening, 2026-06-15). |
| CI vulnerability scanning (SCA/SAST) | **⚠ TO VERIFY / likely NOT STARTED** | No scan workflow confirmed in repo. Recommend adding `pip-audit`/`npm audit`/Dependabot/CodeQL and exporting to `vulnerability-scan-exports/`. |
| Observability (Sentry/logs) | **Planned** | `SENTRY_DSN`/`LOG_LEVEL` are placeholders in `.env.example` ("Observability (planned)"). |

---

## 4. Evidence-type → location / how-produced mapping

| Evidence type | Lives in / produced by | Status |
|---|---|---|
| Access Control Policy | `docs/compliance/ACCESS_CONTROL_POLICY.md` (this suite) | **Collected (draft v0.1)** |
| Supplier / sub-processor register | `docs/compliance/VENDOR_RISK_REGISTER.md` (this suite) | **Collected (draft v0.1)** |
| Evidence index (this map) | `docs/compliance/evidence/README.md` | **Collected (draft v0.1)** |
| Quarterly access reviews | `evidence/access-reviews/` ← roster export from `Membership` + `User` | **NOT STARTED** — first review due |
| Change records | `evidence/change-records/` ← Git history, PRs, `render.yaml`, Alembic ledger | **Available at source; not yet curated** |
| Audit-log exports (redacted) | `evidence/audit-log-exports/` ← query the append-only `audit_log` | **Source live; sample not yet exported** |
| Backup / restore-drill logs | `evidence/backup-drill-logs/` ← Neon snapshot + restore drill | **⚠ TO VERIFY** — drill not yet recorded |
| Vulnerability-scan exports | `evidence/vulnerability-scan-exports/` ← CI SCA/SAST | **⚠ TO VERIFY / NOT STARTED** — tooling to add |
| Risk assessment + SoA | `evidence/risk/` | **NOT STARTED** |
| Incident records | `evidence/incident-records/` | **NOT STARTED** (no incidents recorded; add "none this period" attestation) |
| Training / awareness records | `evidence/training-awareness/` | **NOT STARTED** |
| Supplier DPAs / certs | `evidence/supplier-dpas/` ← collected per Vendor Risk Register | **⚠ TO VERIFY** — none filed yet |
| Prior security audit report | `docs/audits/` and the 2026-06-15 security/perf audit handoff | **Available** (cross-reference) |
| Legal: privacy notice & consent | `docs/legal/` (`aviso-de-privacidad-v2.md`, consent v2) | **Available** (cross-reference) |

---

## 5. "Collected vs. still needed" status summary

| # | Evidence area | Collected? | Gap / next action |
|---|---|---|---|
| 1 | Access control policy | ✅ Draft | Promote from draft → approved; capture approval date in `policies/`. |
| 2 | Sub-processor register | ✅ Draft | Close the **⚠ TO VERIFY** DPA/residency items in the register. |
| 3 | Evidence structure (this) | ✅ Draft | Populate subfolders as artifacts are produced. |
| 4 | Audit-log capability | ✅ In product | Export a redacted sample to `audit-log-exports/`. |
| 5 | Change management | ✅ At source | Curate a representative bundle in `change-records/`. |
| 6 | Risk assessment + SoA | ❌ Not started | Author risk register + Statement of Applicability in `risk/`. |
| 7 | Access reviews | ❌ Not started | Run first quarterly review (policy §7); file the log. |
| 8 | Backup/restore drill | ⚠ To verify | Perform + record a Neon restore drill (RPO/RTO). |
| 9 | Vulnerability scanning | ⚠ To verify | Add CI SCA/SAST (pip-audit/npm audit/Dependabot/CodeQL); export results. |
| 10 | Incident records | ❌ Not started | Stand up an incident log; add "none this period" attestation. |
| 11 | Training / awareness | ❌ Not started | Record staff security-awareness training + policy acknowledgements. |
| 12 | Supplier DPAs / certs | ⚠ To verify | Collect and file each critical vendor's DPA + SOC 2 / ISO cert. |
| 13 | **MFA evidence** | ❌ Not started | **No MFA exists** (see Access Control Policy §4.5) — implement for privileged roles, then evidence it. |

---

*End of CW-ISO-evidence-readme v0.1 (draft).*
