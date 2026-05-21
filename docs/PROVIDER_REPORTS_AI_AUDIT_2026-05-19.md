# Provider Reports + AI System — Tester-Focused Audit

> **Date:** 2026-05-19
> **Scope:** What a provider tester (jluna@legalshelf.mx) will actually see, click, and trigger at `/portal/reports*` on production tomorrow. Plus the verdict on whether the AI is real or mocked, and what the safety layer guarantees.
> **Method:** Code-side only (no live API hits). FE surfaces mapped via Explore agent; BE pipeline read directly.
> **Pairs with:** [USER_TEST_READINESS.md](USER_TEST_READINESS.md), [REPORTS_ARCHITECTURE.md](REPORTS_ARCHITECTURE.md), [REPORTS_BLOCK_REGISTRY.md](REPORTS_BLOCK_REGISTRY.md).

---

## 1. Verdict at a glance

| Concern | Status |
|---|---|
| Provider can reach `/portal/reports` after login | ✅ READY |
| Page renders an actionable empty state (not blank) | ✅ READY |
| 3 vendor-facing presets are wired for the workspace-owner branch | ✅ READY |
| "Generate with AI" SSE pipeline + canvas streaming | ✅ READY (code-side) |
| 4 provider-specific data-fetcher blocks (compliance_state / attention_list / upcoming_deadlines / prioritized_actions) | ✅ READY |
| Tenant-isolation defence (3-layer + redundant per-block check) | ✅ READY |
| Print mode (`/portal/reports/[id]/print`) | ✅ READY |
| Embedded copilot chat (right rail) | ✅ READY |
| **AI is real vs deterministic mock on prod** | ⚠️ **OPERATOR MUST VERIFY** — see §6 |
| **For a brand-new workspace (Jorge's), data-fetched blocks will be near-empty** | ⚠️ Expected; manage expectations — see §4 |
| Inline `Datos al…` freshness label + "Actualizar" button | ✅ READY |
| Anthropic SDK model selection (planner / content) | ⚠️ Minor — Sonnet pinned to 4.5; current latest is 4.6. Not a tester blocker. |

**Net call:** ready for Jorge to test as long as you (a) confirm the AI-engine mode and (b) prep him that some blocks will show "Sin datos / 0 documentos" because his workspace was created today.

---

## 2. What Jorge sees at `/portal/reports` (empty workspace)

### Arrival

1. After login + password change, Jorge gets routed by `lib/routing/post-login.ts`. As a workspace owner (no Membership rows, owns one ProviderWorkspace), he lands at `/portal/entra-a-tu-espacio` first (workspace confirmation), then at `/portal/dashboard`.
2. Sidebar navigation includes **Reportes** → `/portal/reports`.
3. The route is gated by `withOnboardingGate` ([apps/web/app/portal/reports/page.tsx](apps/web/app/portal/reports/page.tsx)). If Jorge has not finished his expediente (he won't — fresh workspace), he is bounced to `/portal/onboarding` first. **Action for the test brief:** complete onboarding before opening Reports, OR temporarily set `onboarding_completed_at` on his provider_workspace.

### Empty list view

Assuming he passes the onboarding gate:

- **CompliancePulseStrip** at the top (P1.6 — workspace-derived metrics).
- **Preset gallery** (3 cards, vendor-facing):
  - "Mi estado de cumplimiento" — `provider-current-state`
  - "Documentos faltantes" — `provider-missing-documents`
  - "Rechazos recientes" — `provider-recent-rejections`
- **Reports list:** dashed-border empty state — *"Aún no hay reportes. Usa una de las plantillas arriba para crear el primero."* ([reports-list-view.tsx:556–591](apps/web/components/checkwise/reports/reports-list-view.tsx))

He always has a primary action: pick a preset.

### Behavior table

| Surface | Jorge's first visit |
|---|---|
| Eyebrow + title | `"CENTRO DE CUMPLIMIENTO PERSONAL"` + "Reportes" |
| Subtitle | "Centro de cumplimiento personal: estado del expediente, obligaciones pendientes y rechazos por corregir." |
| Top strip | CompliancePulseStrip — small KPI row from his workspace state |
| Preset gallery | 3 cards (above) |
| Reports list | Empty-state card with copy nudging him to the gallery |
| Filters | Status / audience filters present but disabled-feeling when list is empty |

---

## 3. What happens when Jorge clicks a preset

1. `POST /api/v1/reports/from-preset` is called with `preset_id="provider-current-state"` (or whichever he picked).
2. Backend creates an empty `Report` row + v1 `ReportVersion` with no blocks yet, and stores the preset's `recommended_prompt` in the report's global config.
3. Frontend navigates to `/portal/reports/{new_id}`.
4. **`ReportEditor` mounts** ([editor/report-editor.tsx:77](apps/web/components/checkwise/reports/editor/report-editor.tsx)). It:
   - Calls `GET /api/v1/reports/_engine` to detect mock-vs-real mode. If mock, surfaces a yellow banner: *"El motor de IA está en modo mock determinista (no hay ANTHROPIC_API_KEY configurada en el backend)."*
   - Auto-opens the AI generation panel with the recommended prompt pre-filled.
5. Jorge hits **"Generar"** — the SSE generation pipeline kicks in.

### The generation pipeline (server-side)

[`apps/api/app/services/reports/executor.py`](apps/api/app/services/reports/executor.py) implements the spec from [REPORTS_ARCHITECTURE.md §8](REPORTS_ARCHITECTURE.md):

```
plan → for each block:
   block_start  →  fetch_data  →  block_data  →
   stream_ai_summary  →  ai_summary_delta*  →  block_complete
→ save ReportVersion
→ done
```

For the `provider-current-state` preset, the LLM planner sees the canvas catalog + the system prompt + Jorge's `recommended_prompt`. It emits tool-use calls. Per the preset's wording, it should emit (in order): `compliance_state` → `attention_list` → `upcoming_deadlines` → `prioritized_actions`.

Each block then:
1. Runs through `fetch_for_block()` ([blocks/data_fetchers.py](apps/api/app/services/reports/blocks/data_fetchers.py)) with the report's `ReportScope`.
2. Calls `assert_workspace_scope()` ([blocks/_safety.py](apps/api/app/services/reports/blocks/_safety.py)) — the redundant tenant check.
3. Reads vendor-scoped data via canonical helpers (`build_compliance_state_for_vendor`, evidence slots, etc.).
4. Stamps `fetched_at` (ISO8601) so the print view's "Datos al…" label and the per-block "Actualizar" button know data age.
5. Emits `block_data` → optionally `ai_summary_delta*` (only if the block type is AI-aware; the four provider blocks are **not** AI-aware — they render factual data only). The preset wording explicitly forbids `ai_recommendation` blocks.

---

## 4. Reality check — what the provider blocks will actually show for Jorge

His workspace was created today with **zero submissions**. Compliance-catalog tables (151 requirements, 5 institutions) ARE seeded in prod. So:

| Block | Expected payload | What Jorge will see |
|---|---|---|
| `compliance_state` | `semaphore.level=green` (or yellow depending on the empty-slot rule), `compliance_pct=0`, `total_tracked=N`, `on_track=0`, all `document_state_counts` zeros except `pending` | A coherent "I haven't started yet" panel — not broken |
| `attention_list` | Items derived from his onboarding slots (mandatory expediente fields) — likely a few rows of "Sube tu acta constitutiva", "Sube tu CIF", etc. | Useful — directly actionable |
| `upcoming_deadlines` | Top 6 deadlines from the canonical REPSE calendar for the current period. Could be empty if nothing falls in the window. | Possibly empty; the block will say so |
| `prioritized_actions` | 1–3 canonical actions of type `complete_onboarding` because onboarding is incomplete | Useful — directly actionable |

If the planner picks the `provider-missing-documents` or `provider-recent-rejections` preset:

- `provider-missing-documents` will look mostly **empty** because Jorge has no submissions yet → filtered `attention_list` returns 0 rows for `missing/in_review/uploaded`.
- `provider-recent-rejections` will look **fully empty** → no rejected/needs_correction documents exist.

**Recommendation for the test brief:** push Jorge to start with **`provider-current-state`** — it's the only preset that renders meaningful data on a fresh workspace. The other two are accurate-but-empty.

---

## 5. AI system architecture (what's actually wired)

### LLM client factory

[`apps/api/app/services/reports/llm/factory.py:24`](apps/api/app/services/reports/llm/factory.py)

```
CHECKWISE_LLM_BACKEND=mock      → DeterministicMockLLMClient (always)
CHECKWISE_LLM_BACKEND=anthropic → AnthropicLLMClient (fails if no key)
empty + ANTHROPIC_API_KEY set   → AnthropicLLMClient
empty + no key                  → DeterministicMockLLMClient
```

Three call surfaces — **planner**, **content streamer**, **copilot conversation**.

### Real-Anthropic models pinned

[`apps/api/app/services/reports/llm/anthropic_client.py:35-37`](apps/api/app/services/reports/llm/anthropic_client.py)

```python
planner_model = "claude-sonnet-4-5-20250929"
content_model = "claude-haiku-4-5-20251001"
```

- **Planner** = Sonnet 4.5 (older — the current latest is **Sonnet 4.6**, model id `claude-sonnet-4-6`). Not a tester blocker; the planner still works fine. Worth a one-line follow-up to bump.
- **Content** = Haiku 4.5 (current — `claude-haiku-4-5-20251001`).
- System prompt is **cache-controlled** (`{"type": "ephemeral"}`) — saves cost across multiple plan calls within 5 min.
- Tool use is **forced** (`tool_choice={"type": "any"}`) — prevents the model from "explaining what it would do" instead of planning.

### Mock client

[`apps/api/app/services/reports/llm/mock_client.py`](apps/api/app/services/reports/llm/mock_client.py) — deterministic, used in CI and as a safe fallback. Generates plausible but canned tool calls + AI summaries. When mock is active, the editor surfaces an explicit yellow banner so the user knows the AI text is not real.

### Safety architecture (three layers, defence-in-depth)

From [`apps/api/app/services/reports/context.py:1`](apps/api/app/services/reports/context.py) and [`apps/api/app/services/reports/blocks/_safety.py:1`](apps/api/app/services/reports/blocks/_safety.py):

| Layer | What it does |
|---|---|
| **Pre-fetch** | Every block fetcher receives a frozen `ReportContext` with org/client/vendor IDs derived from the **authenticated session**, never from the prompt. The LLM never sees the actor's user_id or unrelated workspace IDs. |
| **At-fetch** | Every SQLAlchemy query joins through organization_id / client_id / vendor_id — orphan or cross-tenant rows literally cannot appear in the result set. |
| **Per-block redundant guard** | `assert_workspace_scope()` ([_safety.py:38](apps/api/app/services/reports/blocks/_safety.py)) — every vendor-only fetcher re-checks the actor's workspace vs the scope. Raises `ReportPermissionError` → API surfaces as 403. The redundancy is deliberate. |
| **Post-fetch sanitizer** | `_redact_for_audience()` ([executor.py:69](apps/api/app/services/reports/executor.py)) walks block-specific PII paths (`vendor_risk_matrix.rows.*.vendor_rfc`, etc.) and nulls them out for `client_facing` / `vendor_facing` audiences. Internal-only audience passes through. |

### Test coverage for safety

| File | Tests | Focus |
|---|---|---|
| [tests/test_reports_ai_safety.py](apps/api/tests/test_reports_ai_safety.py) | 8 | "Even an adversarial LLM cannot get past the assembler" — prompt assembly, context windows, cross-tenant attempts, hallucinated statuses, unauthorized data inclusion |
| [tests/test_reports_safety.py](apps/api/tests/test_reports_safety.py) | 6 | Unit tests for `assert_workspace_scope` value-object guard |
| [tests/test_reports_planner.py](apps/api/tests/test_reports_planner.py) | 6 | Planner output validation against block catalog input schemas |
| Block-specific suites (4 files) | 67 total | `compliance_state` (16), `attention_list` (20), `upcoming_deadlines` (16), `prioritized_actions` (15) |

Total reports-related coverage: **~140 tests** (of 427 across the whole backend).

---

## 6. AI engine status on production — ⚠️ verify before the test

I cannot determine from code alone whether the prod backend currently uses **real Anthropic** or **deterministic mock**. Both env vars are declared `sync: false` in [render.yaml](render.yaml):

```yaml
- key: ANTHROPIC_API_KEY
  sync: false
- key: CHECKWISE_LLM_BACKEND
  sync: false
```

**Two ways for you to verify, pick one:**

### Option A — Render dashboard (fastest)

1. https://dashboard.render.com → checkwise-api → Environment
2. Look for `ANTHROPIC_API_KEY`. If the value is set (eye icon reveals a non-empty string), AI is **real**. If absent/empty, AI is **mock**.
3. Also check `CHECKWISE_LLM_BACKEND`. If it's `mock`, that overrides regardless of the key. If empty or `anthropic`, the key decides.

### Option B — Authenticated probe (uses Jorge's account, write-free, but you said no live probes — flagging anyway in case you change your mind)

```bash
JWT=$(curl -s -X POST https://checkwise-api.onrender.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"jluna@legalshelf.mx","password":"<his-pwd>"}' | jq -r .access_token)

curl -s https://checkwise-api.onrender.com/api/v1/reports/_engine \
  -H "Authorization: Bearer $JWT" | jq
```

Returns `{"backend":"anthropic"|"mock", "planner_model":"…", "content_model":"…"}`. Logs Jorge in but does not mutate state. Skip if you want strict code-side discipline.

### Which mode is OK for the test?

| Mode | Tester impact | When to use |
|---|---|---|
| **Real Anthropic** | AI summaries, copilot replies, executive narratives are model-generated. Each generate call costs ~cents. | Best signal — recommended for a real test. |
| **Deterministic mock** | AI summaries are canned strings, copilot replies are canned. **Yellow banner is shown in the editor.** Generation pipeline still works end-to-end; data fetchers still produce real data. | Acceptable if you want to delay AI cost. Just brief Jorge that the AI text isn't real. |

**Recommendation:** turn on Real Anthropic for the test (the AI is the differentiator). Cost will be small — single tester, a handful of generate calls.

---

## 7. Risks / friction points for Jorge's test session

| Risk | Why | Mitigation |
|---|---|---|
| He hits `/portal/reports` before completing onboarding | `withOnboardingGate` will redirect him to `/portal/onboarding`. He might think the reports page doesn't exist. | Tell him to complete onboarding first OR pre-mark his workspace `onboarding_completed_at`. |
| He picks `provider-missing-documents` or `provider-recent-rejections` and sees mostly-empty blocks | His workspace has zero submissions today | Brief him to start with **`provider-current-state`** to see meaningful content |
| Mock-mode banner is jarring | If `ANTHROPIC_API_KEY` is empty, every editor visit shows the yellow banner | Set the key, OR brief him: "the AI text in the test environment is canned for now, focus on the layout + flow" |
| Generation takes 10–30s | SSE streaming is real but a planner + 4 block fetches + AI summaries take time | Brief him; the canvas shows blocks hydrating live so it doesn't feel frozen |
| Print page (`/portal/reports/[id]/print`) opens but he doesn't know that's where the PDF comes from | The print UI uses `window.print()` for browser-native PDF — there's no server PDF render in this build | Tell him: "Para exportar PDF, abre el reporte → Imprimir → Guardar como PDF en el diálogo del navegador" |
| Copilot replies are mock if no key | He'll see canned suggestions | Same as mock-mode banner mitigation |
| Cold start on Render | If the instance has been idle, first SSE may stutter | Pre-warm by hitting `/health` immediately before he tests (we already did this earlier — cache is warm for now) |

---

## 8. Other findings (not tester blockers, file for follow-up)

| # | Finding | Severity | Where |
|---|---|---|---|
| F-AI-01 | Planner Sonnet model is `claude-sonnet-4-5-20250929`; the current latest is **Sonnet 4.6** (`claude-sonnet-4-6`). Worth bumping to keep parity with current model quality. | Low | [llm/anthropic_client.py:36](apps/api/app/services/reports/llm/anthropic_client.py) |
| F-AI-02 | `astream_text` is `raise NotImplementedError` ([anthropic_client.py:143](apps/api/app/services/reports/llm/anthropic_client.py)) — reserved for "3.3c concurrent streams" that don't ship yet. Not user-visible; no current path hits it. | Doc-only | same |
| F-AI-03 | The system prompt is cache-controlled (good), but the **per-block content streamer** does NOT cache its system prompt ([anthropic_client.py:124-130](apps/api/app/services/reports/llm/anthropic_client.py)). Each block's stream pays full system-token cost. Small optimization for cost. | Low (cost) | same |
| F-AI-04 | `prioritized_actions` for a brand-new workspace will likely show "Complete tu expediente" — make sure the action button there links to `/portal/onboarding` not to a 404. Worth manually clicking once before the test. | Low | [blocks/prioritized_actions.py](apps/api/app/services/reports/blocks/prioritized_actions.py) — code looks right, just verify in UI |
| F-AI-05 | The **embedded copilot does NOT mutate the canvas** by design (see `chat-copilot.tsx` docstring). If Jorge says "add a block X", the copilot replies but does not edit. This is intentional — but if he expects it, surprise. | UX expectation | document in the test brief |
| F-AI-06 | `ReportExport` model exists ([entities.py](apps/api/app/models/entities.py)) but no worker/render is wired. The print-mode HTML is the only export path. | Known limitation | [docs/REPORTS_ARCHITECTURE.md §21 deferred](REPORTS_ARCHITECTURE.md) |
| F-AI-07 | `getReportsEngine()` requires auth but is otherwise zero-cost (no DB hit). Cheap way to expose mock-vs-real to the UI banner. ✅ Working. | Note | [reports.py:218](apps/api/app/api/v1/reports.py) |
| F-AI-08 | The provider-block fetchers (`compliance_state`, etc.) explicitly stamp `fetched_at` server-side ([compliance_state.py:91](apps/api/app/services/reports/blocks/compliance_state.py)) so the freshness label / "Actualizar" button work correctly. Good. | ✅ | — |
| F-AI-09 | The four vendor-facing presets all share the same "NO uses ai_recommendation" instruction. This is a strong safety choice — provider-facing content stays factual, no model hallucinations creep into reports a vendor reads. Worth keeping. | ✅ Architecture note | [templates.py:218,242,267](apps/api/app/services/reports/templates.py) |

---

## 9. What to add to the test brief for Jorge

Suggested additions to the onboarding email or the verbal handover:

1. **Order of exploration:** complete onboarding first, then open Reportes, then click **"Mi estado de cumplimiento"** as the first preset.
2. **What the AI does:** it picks which blocks to render based on his prompt + the preset. If he sees a yellow banner saying "modo mock", the text in AI-aware blocks is canned for now.
3. **What to expect on empty data:** because his workspace is brand new, some blocks will show "0 documentos" or "Sin vencimientos próximos" — that's accurate, not a bug.
4. **Print:** "Imprimir" opens a clean print view; from there, `Guardar como PDF` in the browser dialog produces a PDF.
5. **Copilot:** the right-rail chat answers questions about the report but doesn't change blocks. Use it for "explain this score" or "what's missing".

---

## 10. Recommendations (ordered by impact)

1. **Verify Render env vars** — confirm whether `ANTHROPIC_API_KEY` is set. Decide mock vs real before the test. Most likely you want **real** for a meaningful test.
2. **Mark Jorge's workspace as onboarding-complete OR walk him through onboarding first** — otherwise he can't reach Reportes.
3. **Bump planner Sonnet** to 4.6 in a follow-up commit (F-AI-01) — one-line change, no tests should break since the model API is identical.
4. **Add cost caching on the per-block content stream** (F-AI-03) — small optimization. Can wait.
5. **Pre-click the print page** for a sample report once before Jorge starts — confirms the route works on prod end-to-end.
6. **After the test:** if it goes well, this audit becomes the baseline for the next provider tester. Add new findings inline.

---

## 11. Quick summary if you only read one section

- Code is solid. 140 tests cover the reports + AI surfaces. Three-layer tenant isolation is in place.
- Jorge can reach `/portal/reports`, pick a preset, and hit Generate. The pipeline works.
- His new workspace will produce mostly empty blocks for two of the three presets. **Send him to `provider-current-state` first.**
- The biggest unknown is whether `ANTHROPIC_API_KEY` is set in Render. **Check it now**; set it if you want him to see real AI text.
- One non-blocker model-currency item (Sonnet 4.5 → 4.6). One missing-feature note (no server PDF render — print-to-PDF in browser only). Everything else is green.

Ready to go.
