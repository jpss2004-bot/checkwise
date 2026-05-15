---
description: Audits CheckWise for local security, secret exposure, permission issues, tenant isolation, risky commands, dependency concerns and data privacy.
---

# CheckWise Security Skill

Use this for security, privacy, local configuration and risky operations.

## CheckWise security priorities

- Protect client/supplier documents.
- Protect secrets.
- Prevent data leakage between clients.
- Preserve auditability.
- Avoid automatic legal/fiscal approvals.
- Avoid accidental GitHub pushes or secret commits.

## Audit items

Review:

- .env handling.
- Git ignored files.
- Secret-like files.
- Dependency advisories.
- Upload validation.
- Tenant isolation assumptions.
- RBAC assumptions.
- Signed URL/storage assumptions.
- Audit log coverage.
- Destructive scripts.
- Git commands.

## Rules

Never print secrets.
Never read .env unless explicitly authorized.
Never approve sensitive legal/fiscal documents automatically.
Never recommend bypassing 2FA/RBAC/audit controls.
