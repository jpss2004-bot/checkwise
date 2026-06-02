# Archived docs

Frozen historical context kept for traceability. **Do not treat
anything here as current** — the canonical docs live at the
`docs/` root.

This folder was created on 2026-05-25 as part of the P4 sale-
readiness audit cleanup (`P4-07` in
[`docs/audits/SALE_READINESS_INTERNAL_FINDINGS_2026-05-25.md`](../audits/SALE_READINESS_INTERNAL_FINDINGS_2026-05-25.md)).
A buyer's CTO reading the repo for the first time should be able to
find the *current* architecture / handoff / runbook docs without
wading through six versions of the redesign plan; that's what this
archive serves.

## What lives here

| File | Status | Reason |
|------|--------|--------|
| `CHECKWISE_1_5.md` | superseded | Pre-1.6 product spec. |
| `CHECKWISE_1_6.md` | superseded | Pre-2.0 product spec. |
| `CHECKWISE_2_0.md` | superseded | Now superseded by ROADMAP.md + the in-tree audit dossier. |
| `DEMO_1.7.1.md` | superseded | Demo script for the 1.7.1 milestone; obsolete after the 2026-05 rotation. |
| `PRE_REDESIGN_SYSTEM_MAP.md` | superseded | System map snapshot before the 2026-05 portal redesign. Live map is `docs/MAP.md` / `docs/PROJECT_STRUCTURE.md`. |
| `PROVIDER_REPORTS_REDESIGN_AUDIT.md` | superseded | Audit closed; findings absorbed into `handoffs-2026-05/PROVIDER_REPORTS_SESSION_HANDOFF.md`. |
| `PROVIDER_REPORTS_REDESIGN_PLAN.md` | superseded | Plan shipped; live behavior documented under `REPORTS_*.md`. |
| `handoffs-2026-05/` | superseded | 13 dated handoffs and audit snapshots from the 2026-05 stabilization push, archived in the 2026-06-02 cleanup (`AUDIT_NEXT_SESSION_READINESS.md`, `AUTH_ROLE_FLOW_AUDIT_2026-05-18.md`, `FRIDAY_MEETING_ACTION_MATRIX.md`, `FULL_SYSTEM_AUDIT.md`, `MONDAY_READINESS_AUDIT.md`, `NEXT_SESSION_HANDOFF.md`, `PROD_AUDIT_2026-05-18.md`, `PROVIDER_REPORTS_AI_AUDIT_2026-05-19.md`, `PROVIDER_REPORTS_SESSION_HANDOFF.md`, `PROVIDER_REPORTS_VISUAL_AUDIT_2026-05-19.md`, `REPORTS_AUDIT_2026-05-18.md`, `STABILIZATION_AUDIT_2026-05-18.md`, `USER_TEST_READINESS.md`). |

## When to move something here

A doc belongs in `_archive/` when **all three** are true:

1. The behavior it described has been re-implemented or superseded.
2. Nothing in `docs/` at the root currently links to it as live truth.
3. Removing it from the root would not surprise a future maintainer
   reading the project handoff cold.

Otherwise, leave it at the root. When in doubt, move it here with
a short note in this table — the archive is cheap; the buyer-review
friction of an outdated doc at the root is not.
