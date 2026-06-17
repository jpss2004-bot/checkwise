# Pre-validation ↔ metadata merge

Date: 2026-06-17. Goal: stop the two document subsystems from doing the same
work twice, and route the AI comprehension that already runs into the metadata
fields it currently leaves blank.

## The two systems (audit summary)

- **Pre-validation** = live regex (`document_intelligence.analyze_document_text`
  → `prevalidation.build_initial_validations`, synchronous, drives status) +
  a Claude **shadow** comprehension layer (`document_analysis/`, async,
  reviewer-only, gated `DOCUMENT_ANALYSIS_PROVIDER=disabled`). The deep tier
  emits `document_understanding` incl. `key_facts:[{label,value}]`.
- **Metadata extraction** = a parametrization rulebook (`metadata_rules.py`,
  34 doc types) + a deterministic XLSX pipeline (`metadata_export.py`,
  `AUTO_METADATA_EXPORT_ENABLED=true`). It composes fields from DB context +
  rulebook fixed values and **leaves content-dependent fields blank**
  (`main_date`, `participants`, `start_date`, …, all declared
  `extraction_methods=(... "ai_assisted" ...)`), then builds
  `_build_ai_extraction_request` → `"status": "ready_for_n8n_ai_node"` for an
  external AI node **that was never wired up**.

The insight: the "external AI node" the metadata system waits for is the Claude
comprehension pass that already runs on the same PDF. They were never joined.

## SHIPPED — Phase 1+2 (commit `faf2037`, local main, NOT pushed)

Dedup + classify-once. `metadata_export` now reuses the intake
`PdfInspectionResult` + `DocumentSignals` (richer context + OCR-fallback text)
instead of re-opening the PDF and re-running `analyze_document_text`. New
optional `precomputed_text_extraction` arg is threaded
`export_metadata_table_after_upload` → `export_pdf_metadata_table` →
`build_pdf_metadata_dry_run_payload`; CLI / dry-run API / tests keep the
re-parse path. `_CLASSIFIER_TO_METADATA_CODE` gained the two unambiguous
mappings (`imss_liquidacion`, `infonavit_liquidacion`).

Verified: ruff clean; metadata + doc-intelligence unit suites pass, incl. new
`test_metadata_export_reuse.py` and a reuse-without-reparse regression in
`test_pdf_metadata_dry_run_tool.py`.

## TODO — enable the Anthropic provider (activation, not code)

Base comprehension needs **no migration** (shadow_* columns shipped in 0032,
already on prod). Only the expediente pass needs migration 0047.

**Blocker:** the comprehension code (`e06777d`..`f9a395a`) is on local main and
NOT on `origin/main` (verified). Local main has also **diverged 14/14** from
origin (concurrent Codex work). So the flag can't take effect in prod until the
code is reconciled + deployed. Do not push local main without resolving that.

Runbook once the code is deployed:
1. (Expediente only) Snapshot Neon prod → named sibling branch.
2. Reconcile divergence, push → Render deploy runs `alembic upgrade head`
   (applies 0047 if present).
3. Render dashboard env: `DOCUMENT_ANALYSIS_PROVIDER=anthropic`; confirm
   `ANTHROPIC_API_KEY` is set; (optional) `DOCUMENT_ANALYSIS_EXPEDIENTE_ENABLED=true`.
4. Smoke: upload a doc → reviewer card shows the comprehension section. Watch
   `DOCUMENT_ANALYSIS_DAILY_CAP_PER_ORG=200` / escalation cap `50`.
5. Rollback: set `DOCUMENT_ANALYSIS_PROVIDER=disabled` (service restart, no
   redeploy, no data change). Provider falls back gracefully if key/SDK missing.

## SHIPPED — Phase 3+4 (the real semantic merge), gated dark

The deep comprehension tier now also proposes values for the rulebook's
`ai_assisted` fields, and those fill the metadata workbook. Zero extra model
calls — it rides the comprehension pass that already runs.

- Deep tier (`anthropic_provider.analyze`) takes an optional
  `metadata_field_schema`; when supplied it uses a "comprehension + field
  suggestions" structured-output format and lists the fields in the user
  prompt. Returns `AnalysisResult.field_suggestions`
  (`[{field_key, value, confidence, evidence}]`). When absent the deep call is
  byte-for-byte unchanged.
- `shadow_runner` builds the schema only when gating is open, passes it to the
  escalation tier, persists suggestions to
  `shadow_signals['field_suggestions']`, and — after the deep run — calls
  `metadata_export.reexport_metadata_with_field_suggestions` to rewrite the
  workbook with the `ai_assisted` cells prefilled as `prefilled_needs_review`
  (never an approval; rulebook keeps `legal_approval_allowed=False`). The dead
  `ready_for_n8n_ai_node` envelope reports `fulfilled_by_comprehension`.
- The async re-export reconstructs context from the persisted submission and
  reuses the `DocumentInspection` signals (no re-parse).

Phase-4 gating (all default-off → ships dark):
`COMPREHENSION_FIELD_SUGGESTIONS_ENABLED` (master),
`COMPREHENSION_UNLOCKED_REQUIREMENT_CODES` (CSV, `*` = all; empty = none even
when enabled — graduate one code at a time via
`scripts/calibrate_comprehension.py`),
`COMPREHENSION_FIELD_SUGGESTION_MIN_CONFIDENCE` (default 0.55).

To activate (after the provider is on): set
`COMPREHENSION_FIELD_SUGGESTIONS_ENABLED=true` +
`COMPREHENSION_UNLOCKED_REQUIREMENT_CODES=<code>` in the Render dashboard.
Suggestions appear on the metadata XLSX as `prefilled_needs_review`.

Shares `document_analysis` infra with the comprehension overhaul
(`_handoff/comprehension-graduation-4b-followup.md`).
