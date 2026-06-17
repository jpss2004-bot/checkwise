# Phase 4b — graduating comprehension to provider-facing (data-gated follow-up)

_Status: deferred until prod calibration data exists. The engine (Phases
0–3) and the calibration instrument (Phase 4a) are shipped; this is the
remaining, deliberately-gated step._

## What's already shipped

| Phase | Commit | What |
|---|---|---|
| 0 | `e06777d` | Deep tier gets the full situation context + adaptive thinking |
| 1 | `847a167` | Per-document comprehension (`obligation_satisfaction`, key_facts, status, discrepancies) on the deep tier; persisted to `DocumentInspection.shadow_signals['comprehension']` |
| 2 | `ae08e5d` / `60d25f9` | Expediente situational pass (`expediente_assessments`) + debounced after-deep-run trigger |
| 3 | `cfa6cab` / `766f234` | Reviewer surface: comprehension + expediente rendered on the reviewer card |
| 4a | _this_ | `scripts/calibrate_comprehension.py` — the precision instrument |

All behaviour is **reviewer-facing and additive** — nothing changes what
the provider sees yet. Feature flags default **off**.

## To activate the engine in prod (prerequisite for any calibration)

1. Run migration `0047` (snapshot Neon first).
2. `DOCUMENT_ANALYSIS_PROVIDER=anthropic` (likely already set for the
   revalidation feature) and confirm `DOCUMENT_ANALYSIS_MODEL` (the deep
   model — `claude-sonnet-4-6`, or flip to `claude-opus-4-8`).
3. `DOCUMENT_ANALYSIS_EXPEDIENTE_ENABLED=true` to turn on the situational
   pass.

The deep tier fires on escalation triggers (low triage confidence,
high-stakes requirement, prior risk), so comprehension accrues on flagged
docs first.

## The 4b staging (mirrors the auto-approve engine)

1. **Accumulate** — let the deep tier run in prod until each requirement
   code has a meaningful number of terminal decisions with comprehension.
2. **Measure** — `cd apps/api && .venv/bin/python -m
   scripts.calibrate_comprehension`. Read the per-code
   `satisfied_precision` and the graduation simulation. A code is a
   candidate only when `satisfied AND confidence ≥ threshold` clears the
   **≥99%** precision bar on its own history.
3. **Unlock one code at a time** — never blanket-enable.

## The async-surfacing wrinkle (the real design work in 4b)

Provider-facing prevalidation signals are built **synchronously at
upload** (`app/services/prevalidation.py::build_initial_validations`,
from the heuristic `DocumentSignals`). Comprehension is computed
**after the intake transaction commits**, in the background shadow
runner. So at upload time the comprehension does not exist yet.

⇒ Graduation is **not** an edit to `build_initial_validations`. It means
surfacing comprehension-derived signals on the provider's **async**
submission-detail view (`app/api/v1/portal.py` — the provider endpoint,
which the provider re-fetches after the deep pass lands), gated per-code.
Keep "signal, never verdict": surface the obligation read as an advisory
signal, not an approval.

## Config knobs to add when building 4b

Mirror `AUTO_APPROVE_*` in `app/core/config.py`:

- `COMPREHENSION_PROVIDER_FACING_ENABLED: bool = False` — master switch.
- `COMPREHENSION_UNLOCKED_REQUIREMENT_CODES: str = ""` — CSV, populated
  **manually**, one code at a time, from a calibration report proving
  ≥99% precision for that code.
- `COMPREHENSION_MIN_CONFIDENCE: float` — per-document floor on
  `obligation_satisfaction.confidence` before a code's signal surfaces.

## Integration point

`app/api/v1/portal.py` provider submission-detail: when the master switch
is on, the requirement code is unlocked, the doc has a comprehension with
`verdict == "satisfied"` and `confidence ≥ COMPREHENSION_MIN_CONFIDENCE`,
add/replace the provider-facing `requirement_match` signal with the
comprehension-backed read (and surface `not_satisfied` as an attention
signal). The reviewer surface (`app/api/v1/reviewer.py`) already shows the
full comprehension regardless — this only changes the provider view.
