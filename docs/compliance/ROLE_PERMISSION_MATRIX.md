---
Document: User Role & Permission Matrix
ID: CW-ISO-role-matrix
Owner: Lead Engineer / acting CISO (Jose Pablo Samano)
Version: 0.1 (draft)
Effective: 2026-06-16
Review cadence: on RBAC change + quarterly access review
ISO refs: ISO/IEC 27002:2022 5.15, 5.18, 8.2, 8.3; ISO 37001 5.3.2
Status: DRAFT — ISO-readiness evidence
---

# Role & Permission Matrix — CheckWise

Source of truth: `apps/api/app/constants/roles.py` (`MembershipRole`) + the auth dependencies in `apps/api/app/api/v1/auth.py` / `app/core/security_gates.py`, verified against per-router authorization in the 2026-06-16 audit.

## 1. Principals

CheckWise has **two authentication mechanisms** and therefore two kinds of principal:

1. **Org-member users** — authenticate with a JWT (httpOnly cookie / bearer) and hold one or more `MembershipRole`s scoped to an `Organization`. Roles: `platform_admin`, `internal_admin`, `reviewer`, `client_admin`.
2. **Providers (vendors)** — authenticate to the portal with a **workspace-scoped portal-session token** (`issue_portal_session_token`), NOT an org membership. They can never hold a `MembershipRole`, so a provider can never become a reviewer/admin — this is the structural basis of segregation of duties.
3. **Public share viewers** — unauthenticated external parties holding a signed, expiring share token (read-only, single report version).

## 2. Role definitions

| Role | Tenancy scope | Purpose |
|---|---|---|
| `platform_admin` | Cross-tenant (IT console `/platform/*`) | IT administration: user provisioning, audit-log explorer, feedback triage. Separated from compliance ops (migration 0044). |
| `internal_admin` | Cross-tenant (staff) | Day-to-day compliance operations across all client tenants. |
| `reviewer` | Cross-tenant (by design) | Validates uploaded documents and renders decisions platform-wide. |
| `client_admin` | Single client org (tenant) | Manages a client organization's compliance view, vendors, and (if primary) its user seats. |
| `provider` (principal, not a role) | Single workspace (client×vendor) | Uploads evidence for the requirements assigned to its workspace. |
| public share viewer (token) | One report version | Read-only external view of a shared report. |

## 3. Capability matrix

✅ allowed · ➖ not applicable / no access · 🔒 own-tenant only · ⚠ cross-tenant by design (audited)

| Capability | platform_admin | internal_admin | reviewer | client_admin | provider | share viewer |
|---|---|---|---|---|---|---|
| Log in / manage own password | ✅ | ✅ | ✅ | ✅ | ✅ (portal) | ➖ |
| Provision/disable/delete users | ✅ | ✅ | ➖ | seats only 🔒 | ➖ | ➖ |
| Grant/revoke org memberships | ✅¹ | ✅¹ | ➖ | ➖ | ➖ | ➖ |
| View platform audit log | ✅ | ➖² | ➖ | ➖ | ➖ | ➖ |
| Review/approve/reject documents | ➖ | ✅ | ✅ | ➖ | ➖ | ➖ |
| Upload evidence documents | ➖ | ➖ | ➖ | ➖ | ✅ 🔒(workspace) | ➖ |
| View vendor/client documents | ⚠ | ⚠ | ⚠ | 🔒 | 🔒(own workspace) | ➖ |
| Create/edit compliance reports | ✅ | ✅ | ➖ | 🔒 | ➖ | ➖ |
| Mint/revoke report share link | ✅ | ✅ | ➖ | 🔒 | ➖ | ➖ |
| View shared report | ✅ | ✅ | ➖ | 🔒 | ➖ | ✅ (token, 1 version) |
| Export/download expediente & audit ZIP | ⚠ | ⚠ | ⚠ | 🔒 | 🔒(own) | ➖ |
| Manage requirements/catalog | ✅ | ✅ | ➖ | ➖ | ➖ | ➖ |
| Configure platform settings | ✅ | partial | ➖ | ➖ | ➖ | ➖ |

¹ Gated by **ADMIN-1** (`_assert_can_grant_role`, `admin.py`): a `platform_admin` cannot self-grant `internal_admin`/`platform_admin`. 
² `internal_admin` does not by default reach the `/platform/*` audit explorer unless they also hold `platform_admin` (most do today via migration 0044 backfill).

## 4. Enforcement notes (how the matrix is actually enforced)

- **Route-level**: dependency guards (`require_org_role`, `AdminUser`, `PlatformUser`, `current_portal_workspace`) gate each router.
- **Object-level**: every by-id resource fetch re-checks the object against the caller's resolved tenant scope and returns **404 (no enumeration)** on mismatch — verified across all routers (no exploitable IDOR found, 2026-06-16).
- **Privileged role re-validation**: `require_org_role` re-reads the live `Membership` table rather than trusting JWT claims.
- **Tenant chokepoints**: `_resolve_client_id` (client portal), `current_portal_workspace` (provider portal), `get_report` (reports).

## 5. Segregation-of-duties statement (ISO 37001 5.3.2)

The uploader of evidence (**provider**) and the approver of evidence (**reviewer**) are **architecturally distinct principals** — a provider authenticates via a workspace token and cannot acquire a reviewer role. The consumer (**client**) is a third, separate principal. This maker-checker separation is enforced by design, not by a runtime toggle. **Residual SoD gap:** within the staff tier, a single `internal_admin` can both grant a reviewer role and act as reviewer (no four-eyes on privileged-role grants) — tracked in [REMEDIATION_TRACKER.md](REMEDIATION_TRACKER.md) (P2).

## 6. Periodic access review

Quarterly, the risk owner reviews: active users per role, dormant accounts, `platform_admin`/`internal_admin` holders, and provider workspace tokens. Procedure + log template in [ACCESS_CONTROL_POLICY.md](ACCESS_CONTROL_POLICY.md).
