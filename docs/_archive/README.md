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
| `PROMPTED_BUT_INCOMPLETE_2026-05-19.md` | historical | Working notes from a single mid-rollout session. |
| `PROVIDER_REPORTS_REDESIGN_AUDIT.md` | superseded | Audit closed; findings absorbed into `PROVIDER_REPORTS_SESSION_HANDOFF.md`. |
| `PROVIDER_REPORTS_REDESIGN_PLAN.md` | superseded | Plan shipped; live behavior documented under `REPORTS_*.md`. |

## When to move something here

A doc belongs in `_archive/` when **all three** are true:

1. The behavior it described has been re-implemented or superseded.
2. Nothing in `docs/` at the root currently links to it as live truth.
3. Removing it from the root would not surprise a future maintainer
   reading the project handoff cold.

Otherwise, leave it at the root. When in doubt, move it here with
a short note in this table — the archive is cheap; the buyer-review
friction of an outdated doc at the root is not.
