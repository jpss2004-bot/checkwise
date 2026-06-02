# Phase 2 — Claude document analysis (shadow mode)

CheckWise pre-validation now has a pluggable AI provider boundary. The
existing regex/keyword classifier (`services/document_intelligence.py`)
keeps running inline during intake and continues to drive every
user-visible status, badge and reviewer message. In parallel, a
background **shadow runner** asks Claude to read the uploaded PDF and
produce a second extraction; the result lands in new `shadow_*`
columns on `DocumentInspection` for offline comparison.

The provider portal is unchanged. The admin reviewer detail page gains
one collapsible card — _Comparación IA (interna)_ — that shows the
heuristic and Claude extractions side by side.

---

## Why shadow first

REPSE compliance documents drive material legal decisions. Two
non-negotiable constraints frame the rollout:

1. **AI may support extraction and pre-validation, but never grant
   final compliance approval for critical REPSE documents.** Legal
   review remains required for every meaningful status transition.
2. **No user-visible behaviour change without evidence.** A confidence
   score from a model the team has not yet calibrated against real
   CheckWise fixtures cannot be the input to a status decision today.

Shadow mode satisfies both. Claude runs on every supported upload but
its output is invisible to the provider and unhooked from the status
machine. The legal team uses the comparison card and (eventually) a
batch query against the `shadow_*` columns to calibrate Claude vs. the
heuristic. When the data justifies it, flipping Claude from "shadow"
to "primary" is a config change (`DOCUMENT_ANALYSIS_PROVIDER=anthropic`
plus a small `status_from_inspection` widening) rather than a rewrite.

---

## Architecture

```
                              ┌─────────────────────────────────────┐
intake POST  ──►  storage  ──►│  finalize_intake_submission         │
                              │   1. inspect_pdf                    │
                              │   2. analyze_document_text (regex)  │ user-visible
                              │   3. persist Submission/Document/   │  status flow,
                              │      DocumentInspection/Validation  │   unchanged
                              │   4. db.commit()                    │
                              │   5. BackgroundTask.add_task ──┐    │
                              └────────────────────────────────┼────┘
                                                               │
                  ┌────────────────────────────────────────────▼────────────┐
                  │  shadow_runner.run_shadow_analysis (FastAPI BG task)    │
                  │   1. build_document_analysis_provider()                 │
                  │   2. check_org_daily_quota(org_id)                      │
                  │   3. provider.analyze(pdf_path, requirement context…)   │
                  │   4. open new SessionLocal; write shadow_* columns;     │
                  │      emit shadow_analysis_completed ValidationEvent     │
                  │   5. db.commit() / db.close()                           │
                  └─────────────────────────────────────────────────────────┘
```

### File map

| Path                                                              | Role                                                         |
|-------------------------------------------------------------------|--------------------------------------------------------------|
| `app/services/document_analysis/base.py`                          | `DocumentAnalysisProvider` Protocol, `AnalysisResult` dataclass |
| `app/services/document_analysis/heuristic.py`                     | Adapter — wraps `analyze_document_text` behind the ABC       |
| `app/services/document_analysis/anthropic_provider.py`            | Claude provider; PDF as `document` block, forced tool use     |
| `app/services/document_analysis/prompt_registry.py`               | Resolves requirement → versioned prompt file                  |
| `app/services/document_analysis/prompts/*.md`                     | One file per supported requirement (`base`, `csf_sat`, `opinion_32d`, `repse_stps`, `imss_pago`) |
| `app/services/document_analysis/spend_limiter.py`                 | Per-org daily call cap (Redis sliding window when available)  |
| `app/services/document_analysis/factory.py`                       | Builds the right provider from settings; falls back on errors |
| `app/services/document_analysis/shadow_runner.py`                 | `BackgroundTask` entry point; opens its own DB session        |
| `app/services/submission_service.py`                              | Adds `background_tasks` param; queues shadow run after commit |
| `app/api/v1/portal.py`                                            | Declares `BackgroundTasks` on the two workspace upload routes |
| `app/api/v1/reviewer.py`                                          | Exposes `shadow_analysis` block on the reviewer detail        |
| `app/models/entities.py`                                          | Adds `shadow_*` columns on `DocumentInspection`               |
| `alembic/versions/0032_doc_inspection_shadow.py`                  | Migration (additive, reversible)                              |
| `apps/web/components/checkwise/admin/shadow-comparison-card.tsx`  | Admin-only Spanish comparison UI                              |

### Persistence contract

New columns on `document_inspections`:

| Column                  | Type                       | Semantics                                                                 |
|-------------------------|----------------------------|---------------------------------------------------------------------------|
| `shadow_provider_id`    | `varchar(120)`             | `anthropic:claude-sonnet-4-6`, `heuristic:v1`, …                          |
| `shadow_prompt_version` | `varchar(60)`              | Prompt file stem, e.g. `csf_sat.v1`. NULL for heuristic.                  |
| `shadow_signals`        | `JSONB` (`JSON` on SQLite) | Mirrors `DocumentSignals`; `_meta` subkey carries model token usage etc.  |
| `shadow_confidence`     | `float`                    | Denormalized copy of `signals.requirement_match_confidence`.              |
| `shadow_latency_ms`     | `integer`                  | Wall-clock duration of the provider call.                                 |
| `shadow_error`          | `text`                     | One of `timeout` / `unsupported_size_or_type` / `malformed_response` / `provider_error:<Class>` / `daily_cap_exceeded`. NULL on success. |
| `shadow_completed_at`   | `timestamptz`              | NULL ⇒ shadow run has not finished yet (or shadow is disabled).           |

A `shadow_analysis_completed` ValidationEvent is emitted on every run,
success or failure, so the audit timeline preserves retries.

---

## Configuration

All settings backend-only. The frontend never sees the Anthropic key.

| Variable                              | Default                  | Purpose                                                                                  |
|---------------------------------------|--------------------------|------------------------------------------------------------------------------------------|
| `DOCUMENT_ANALYSIS_PROVIDER`          | `disabled`               | `disabled` \| `heuristic` \| `anthropic` \| `shadow` (alias of `anthropic`).             |
| `DOCUMENT_ANALYSIS_MODEL`             | `claude-sonnet-4-6`      | Claude model id; e.g. promote to `claude-opus-4-8` for hardest documents.                |
| `DOCUMENT_ANALYSIS_TIMEOUT_SECONDS`   | `30`                     | Hard timeout for the Anthropic call.                                                     |
| `DOCUMENT_ANALYSIS_MAX_FILE_MB`       | `30`                     | Pre-flight cap; Anthropic's hard cap is 32 MB.                                           |
| `DOCUMENT_ANALYSIS_MAX_PAGES`         | `100`                    | Pre-flight cap aligned with the 200k-context limit.                                      |
| `DOCUMENT_ANALYSIS_DAILY_CAP_PER_ORG` | `200`                    | Per-org/day call cap. `0` disables the cap.                                              |
| `ANTHROPIC_API_KEY`                   | (existing — Reports/Wise)| Reused; no new key needed.                                                               |

When `REDIS_URL` is configured, the per-org cap is enforced
cluster-wide via the existing M4 sliding-window limiter. Without
Redis, the cap is per-process — acceptable on Render's single-worker
plan but undercounts on multi-worker fleets.

---

## Initial supported document scope

The Anthropic provider produces good extractions for any document, but
the prompts are tuned for the four document types below. Anything else
falls back to `base.v1.md` — still valid, just without
document-type-specific guidance.

| Slug              | Requirement                                  | Institution | Prompt              |
|-------------------|----------------------------------------------|-------------|---------------------|
| `csf_sat`         | Constancia de Situación Fiscal               | SAT         | `csf_sat.v1.md`     |
| `opinion_32d_sat` | Opinión de Cumplimiento 32-D                 | SAT         | `opinion_32d.v1.md` |
| `repse_stps`      | Constancia / Registro REPSE                  | STPS        | `repse_stps.v1.md`  |
| `imss_pago`       | Comprobante de Pago IMSS (EMA, bancario, …)  | IMSS        | `imss_pago.v1.md`   |

Adding a new requirement is a two-file PR: drop
`prompts/<slug>.vN.md`, add a mapping entry in
`prompt_registry._REQUIREMENT_SLUG_RULES`. No migration, no config.

---

## Operational notes

* **Failure modes.** Every provider failure is converted to a
  categorised `shadow_error`. The intake transaction has already
  committed by the time the runner fires, so no failure can affect
  the user-facing flow.
* **Idempotency.** Re-running a shadow analysis for the same
  `document_id` overwrites the `shadow_*` columns and emits a fresh
  `shadow_analysis_completed` event. The audit timeline preserves
  every run.
* **Async semantics.** Shadow runs are scheduled via FastAPI's
  `BackgroundTask`. They execute on the same worker that handled the
  request, after the HTTP response is sent. A worker crash mid-run
  drops the shadow analysis silently — fine because the user-visible
  flow is unaffected and the next upload retries the provider.
* **Privacy / ZDR.** Do not flip `DOCUMENT_ANALYSIS_PROVIDER=anthropic`
  in production until Zero Data Retention is confirmed on the
  `ANTHROPIC_API_KEY` account. ZDR is required for sending vendor
  fiscal documents.
* **Cost.** A typical CheckWise PDF is 1–3 pages; per-call cost with
  Sonnet 4.6 is in the cents range. Prompt caching on the system
  prompt cuts repeat-call input cost by ~80% after the first call
  within the 5-minute TTL.

---

## Phase 3 prerequisites (not done in this phase)

1. Confirm Zero Data Retention with Anthropic on the prod API key
   account.
2. Provision Render env vars (`DOCUMENT_ANALYSIS_PROVIDER=anthropic`
   and the four limit/cap settings) via the browser Agent prompts
   in the Phase 3 plan.
3. Run the controlled production test against the test-account
   workspace with a sanitized fixture.
4. Watch the `shadow_analysis_completed` ValidationEvents and the
   reviewer comparison card for a week before considering promotion
   out of shadow.
