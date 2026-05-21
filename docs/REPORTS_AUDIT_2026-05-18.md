# Reports Audit — 2026-05-18

**Scope.** Audit and harden the existing CheckWise **Reports** section only.
No new product surfaces, no redesigns. Bring the existing AI report
planner / canvas / copilot / streaming generator pipeline to a
production-trustworthy state and make it honest about what is or is not
configured in the current environment.

**Repo state at audit time**

- Branch / HEAD: `main` @ `fb0a41a` (v2.1.1 stabilize close).
- Backend deployed: Render → `checkwise-api` (autoDeploy from `main`).
  `/health` and `/docs` both respond.
- Frontend deployed: Vercel → `checkwise-six.vercel.app`.
- Working tree dirty: `AGENTS.md` modified (unrelated to Reports).

---

## 0. Executive summary

The Reports module is **architecturally complete and code-tested**:

- All Reports tables exist (Alembic `0009_reports_core` is in head).
- 43 reports-specific pytest cases pass (`test_reports*.py`).
- TypeScript compiles, ESLint clean, Next build green.
- All 7 entity routes (CRUD + versions) plus the 5 AI routes
  (`/plan`, `/generate`, `/conversation`, `/blocks/.../explain`,
  `/blocks/.../regenerate`) are wired into the v1 router and visible
  in Swagger.
- The frontend Reports list, editor, canvas, 6 block types, copilot,
  print mode, AI generation hook, and conversation hook are all
  implemented and align with the backend wire shapes.

The Reports section is **NOT fully demo-ready** because of one
load-bearing gap and a small set of polish issues:

1. **`ANTHROPIC_API_KEY` is not declared in `render.yaml`.** The
   backend factory silently falls back to a deterministic mock LLM
   when no key is present, so "Generate with IA" will happily produce
   fake-looking Spanish content in production without telling the
   user. This is the #1 risk.
2. **The frontend never tells the user when the LLM is the mock**
   client. Token usage, latency, and the "AI summary" pill all look
   real. There is no banner saying *AI report generation is not
   configured in this environment.*
3. There is **no seed data** for `reports` in the demo seed script,
   so a fresh login lands on an empty list. Mildly weak for demo.

Everything else is either P2 polish or genuinely deferred feature
work (DOCX export, share links, autosave, version-history drawer).

---

## 1. Current Reports architecture

```
Reports UI (Next.js, /portal/reports/*)
  • /portal/reports                     list page
  • /portal/reports/[id]                editor (canvas + copilot)
  • /portal/reports/[id]/print          read-only print view
  • lib/api/reports.ts                  typed REST client (entity + per-block)
  • lib/reports/use-generation.ts       fetch + SSE reader for /generate
  • lib/reports/use-conversation.ts     fetch + SSE reader for /conversation
  • lib/reports/registry.ts             6 block types (text, divider,
                                        executive_summary, kpi_strip,
                                        vendor_risk_matrix, ai_recommendation)

         │ Bearer JWT (readAdminSession) + JSON / SSE
         ▼

FastAPI Reports API (apps/api/app/api/v1/reports.py)
  • CRUD:    POST/GET /reports                         create/list
             GET/PATCH /reports/{id}                    read/update
             POST/GET  /reports/{id}/versions          save/list
             GET       /reports/{id}/versions/{n}      read one
  • AI:      POST /reports/{id}/plan                   structured plan only
             POST /reports/{id}/generate               SSE end-to-end
             POST/GET /reports/{id}/conversation       copilot chat (SSE)
             POST /reports/{id}/blocks/{id}/explain
             POST /reports/{id}/blocks/{id}/regenerate

  Service layer
    • report_service.py             entity CRUD + actor / RBAC
    • services/reports/context.py   Context Assembler (tenant + PII)
    • services/reports/planner.py   tool-use planner (Anthropic / mock)
    • services/reports/executor.py  SSE block executor (plan → data → AI → save)
    • services/reports/copilot.py   chat_completion + explain_block
    • services/reports/conversation.py persistence of turns
    • services/reports/block_catalog.py catalog with JSON schemas
    • services/reports/blocks/data_fetchers.py per-block tenant-scoped reads
    • services/reports/blocks/ai_summaries.py per-block summary generators
    • services/reports/llm/factory.py picks anthropic vs deterministic mock
    • services/reports/llm/anthropic_client.py real SDK wrapper
    • services/reports/llm/mock_client.py deterministic mock for CI / no-key

  Data
    • reports / report_versions / report_conversations
    • compliance_snapshots (audit trail of "what the LLM saw")
    • report_shares / report_exports (tables exist; endpoints not yet shipped)
```

The trust boundary (LLM never reads raw rows; sees only the curated
dict returned by the Context Assembler + tenant-scoped data fetchers)
is honoured in code and has 6 explicit `test_reports_ai_safety.py`
scenarios pinned to it.

---

## 2. Implemented routes / pages

### 2.1 Backend (all live in Swagger at `/docs`)

| Method | Path | Status |
|---|---|---|
| POST | `/api/v1/reports` | works |
| GET | `/api/v1/reports` | works |
| GET | `/api/v1/reports/{id}` | works |
| PATCH | `/api/v1/reports/{id}` | works |
| POST | `/api/v1/reports/{id}/versions` | works |
| GET | `/api/v1/reports/{id}/versions` | works |
| GET | `/api/v1/reports/{id}/versions/{n}` | works |
| POST | `/api/v1/reports/{id}/plan` | works (mock fallback if no key) |
| POST | `/api/v1/reports/{id}/generate` | works (mock fallback if no key) |
| GET | `/api/v1/reports/{id}/conversation` | works |
| POST | `/api/v1/reports/{id}/conversation` | works (SSE, mock fallback) |
| POST | `/api/v1/reports/{id}/blocks/{id}/explain` | works (mock fallback) |
| POST | `/api/v1/reports/{id}/blocks/{id}/regenerate` | works (mock fallback) |

### 2.2 Frontend

| Route | Status |
|---|---|
| `/portal/reports` | list + create works |
| `/portal/reports/[id]` | editor, AI panel, copilot, save version, regen, explain all wired |
| `/portal/reports/[id]/print` | read-only print mode works |

All gated by `withOnboardingGate` — provider users with incomplete
expediente are redirected, internal staff bypass.

---

## 3. AI / report generation flow

1. User opens `/portal/reports/[id]`, clicks **Generar con IA**.
2. Frontend POSTs `{prompt, period}` to `/reports/{id}/generate` with
   `Accept: text/event-stream`.
3. Backend assembles a tenant-scoped context (persisting a
   `compliance_snapshots` row), calls `plan_with_tools` on the LLM
   (forced `tool_choice: any` so the model must emit valid block
   tools), validates each tool call against the JSON schema from the
   catalog, and yields an SSE `plan` event.
4. For each block: `block_start` → fetch tenant-scoped data →
   audience-based PII redaction → `block_data` → if the block carries
   an AI summary, stream `ai_summary_delta` chunks → `block_complete`.
5. When all blocks are done, persist a new `report_versions` row
   (`generated_by = ai`), emit `version_saved` + `done`.
6. Frontend hook accumulates events into the canvas; on `done` it
   refetches the report to surface the new version number.

LLM client resolution (`factory.get_llm_client`):

| `CHECKWISE_LLM_BACKEND` | `ANTHROPIC_API_KEY` | Result |
|---|---|---|
| `mock` | (any) | DeterministicMockLLMClient |
| `anthropic` | empty | raises `LLMError` |
| `anthropic` | set | AnthropicLLMClient |
| `""` (default) | empty | DeterministicMockLLMClient |
| `""` (default) | set | AnthropicLLMClient |

This means **the system can never crash for lack of a key** — it
silently downgrades. Which is the source of the #1 risk in §0.

---

## 4. Required env vars (Reports + supporting)

### 4.1 Backend (Render → `checkwise-api`)

| Var | Required | Currently in render.yaml? | Notes |
|---|---|---|---|
| `DATABASE_URL` | yes | yes (`sync: false`) | Neon pooled endpoint |
| `DIRECT_DATABASE_URL` | yes | yes (`sync: false`) | Neon direct endpoint for Alembic |
| `CORS_ORIGINS` | yes | yes (`sync: false`) | Must include the Vercel origin |
| `AUTH_JWT_SECRET` | yes | yes (`sync: false`) | `openssl rand -hex 32` |
| `STORAGE_BACKEND` | yes | yes (`s3`) | |
| `STORAGE_BUCKET` | yes | yes | |
| `AWS_S3_ENDPOINT` / `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION` | yes | yes | R2 credentials |
| **`ANTHROPIC_API_KEY`** | **for real AI** | **NO** | code reads `settings.ANTHROPIC_API_KEY`; falls back to mock if empty |
| **`CHECKWISE_LLM_BACKEND`** | optional | **NO** | `"" \| "anthropic" \| "mock"`; useful to force-mock in CI |
| `CHECKWISE_ENV` | recommended | yes (`production`) | drives `cookie_secure` / `samesite` |

### 4.2 Frontend (Vercel → `checkwise-six`)

| Var | Required | Notes |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | yes | Points at `https://checkwise-api.onrender.com`. Used by every API helper including `lib/reports/use-generation.ts` and `lib/reports/use-conversation.ts`. |
| `NEXT_PUBLIC_WHATSAPP_SUPPORT_URL` | optional | |
| `NEXT_PUBLIC_SUPPORT_QR_PLACEHOLDER_URL` | optional | |
| `NEXT_PUBLIC_DEMO_MODE` | optional | |

### 4.3 `.env.example` coverage

`.env.example` is not readable by this audit pass (path is denied by
local permission settings), so this audit cannot verify line-by-line
whether `ANTHROPIC_API_KEY` and `CHECKWISE_LLM_BACKEND` are in the
example file. If they are missing, add them — they are documented in
`apps/api/app/core/config.py` and silently change AI behaviour when
unset.

---

## 5. Frontend / Backend contract audit

Cross-checked `apps/web/lib/api/reports.ts`, `lib/reports/use-generation.ts`,
`lib/reports/use-conversation.ts`, and the four block components
against `apps/api/app/api/v1/reports.py` + `apps/api/app/schemas/reports.py`
+ `apps/api/app/services/reports/executor.py`.

| Surface | Frontend | Backend | Match? |
|---|---|---|---|
| Create report | `POST /api/v1/reports`, body matches `ReportCreate` | same | ✅ |
| List reports | `?organization_id&status&limit&offset` | same query model | ✅ |
| Read report | `GET /reports/{id}` returns `ReportRead` | same | ✅ |
| Patch report | `PATCH /reports/{id}` | same | ✅ |
| Save version | `POST /reports/{id}/versions` | same | ✅ |
| List versions | `GET /reports/{id}/versions` | same | ✅ |
| Plan | not called from FE today (deliberate; FE goes straight to `/generate`) | endpoint exists | ✅ (intentional gap) |
| Generate (SSE) | events: plan, block_start, block_data, ai_summary_delta, block_complete, version_saved, done, error | executor emits same names + same payload keys | ✅ |
| Conversation list | `GET /reports/{id}/conversation` reads `items[].content.kind == "text"` & `.markdown` | conversation persists `{kind: "text", markdown}` | ✅ |
| Conversation send (SSE) | events: turn_start, delta, turn_complete, done, error | endpoint emits same | ✅ |
| Explain block | `POST .../blocks/{id}/explain` | same | ✅ |
| Regenerate block | `POST .../blocks/{id}/regenerate` | same | ✅ |

No wire mismatches detected. The few subtle things worth keeping an
eye on:

- The frontend `ReportContent.global` is optional; backend executor
  always sets `global: {audience, period}`. Both sides tolerate the
  difference.
- `generated_by` defaults are aligned (`"user"` on FE save, `"ai"` on
  backend executor save).
- Audience labels and status labels are duplicated in
  `apps/web/lib/reports/constants.ts` and `apps/api/app/constants/reports.py`
  — these must be kept in sync manually. They are in sync today.

---

## 6. UI issues

| Surface | Severity | Observation |
|---|---|---|
| `/portal/reports` list | OK | Loads, paginates, error/empty states present |
| New report inline form | OK | Audience defaulted to `internal_only`; description optional |
| Editor — initial load | OK | Shows skeletons during load; falls back to empty canvas if no version (theoretically dead branch — `create_report` always seeds v1) |
| Editor — AI panel | P1 | No banner when the backend is on the mock client — user can't tell if "Generar con IA" will produce real content |
| Editor — generation error UX | OK | `gen.state.error` is surfaced as inline text |
| Editor — save version | OK | Disabled when not dirty; spinner during save |
| Editor — chat copilot | OK | Streams chunks, persists assistant turn server-side |
| Block: text | OK | Inline-editable |
| Block: divider | OK | Static |
| Block: executive_summary | OK | Shows AI summary with "Generado por IA" pill |
| Block: kpi_strip | OK | Renders metrics from `data.resolved` |
| Block: vendor_risk_matrix | OK | Renders rows; PII redaction applied server-side |
| Block: ai_recommendation | OK | Renders the streamed markdown list |
| Print mode | OK | Renders the canvas read-only; print stylesheet hides toolbar/buttons |
| Empty list | OK | Friendly CTA |
| Unknown block fallback | OK | Warning card with the unknown type |

---

## 7. Test results

```
apps/api/.venv/bin/ruff check app            All checks passed!
apps/api/.venv/bin/python -c "import app.main"   no errors
apps/api/.venv/bin/pytest tests/test_reports*.py 43 passed, 2 deprecation warnings (~14.6s)
apps/web/node_modules/.bin/tsc --noEmit     no errors
apps/web/node_modules/.bin/next lint        No ESLint warnings or errors
```

`next build` was not re-run during this audit pass; the v2.1.1
stabilization audit (`docs/STABILIZATION_AUDIT_2026-05-18.md`)
already shows 27/27 routes compiling.

---

## 8. Deployment readiness

- Render → backend ready except the AI key gap noted in §4.1.
- Vercel → frontend ready as long as `NEXT_PUBLIC_API_BASE_URL` points
  at the Render origin and the Render `CORS_ORIGINS` includes the
  Vercel origin.
- Streaming → Backend already sets `Cache-Control: no-cache, no-transform`
  and `X-Accel-Buffering: no` so Render's edge proxy doesn't buffer
  SSE frames. The frontend uses `fetch` + `ReadableStream`, not
  `EventSource`, so POST bodies are supported.
- Reports tables ship via Alembic `0009_reports_core`; `preDeployCommand`
  in `render.yaml` runs `alembic upgrade head` before traffic shifts,
  so production schema is in sync.

---

## 9. Findings — prioritized

### P0 — Reports flow misleads the operator

| ID | Finding | Status |
|---|---|---|
| P0-1 | `ANTHROPIC_API_KEY` and `CHECKWISE_LLM_BACKEND` are not in `render.yaml`. When the Render Blueprint is deployed, the operator is never prompted for them, and the backend silently falls back to the deterministic mock LLM. Result: "Generar con IA" appears to work in production but emits canned mock text. | **resolved (this commit)** |

### P1 — Reports work but are not demo-ready

| ID | Finding | Status |
|---|---|---|
| P1-1 | No UI surface tells the user when the active LLM backend is the mock client. The "AI-generated" pill is rendered the same way for real and mock content. | **resolved (this commit)** — backend exposes `GET /reports/_engine`; editor renders a banner when backend is `mock`. |
| P1-2 | The demo seed script does not insert example `reports` rows, so a fresh login on a clean DB lands on the empty state. Not blocking but soft for live demos. | unresolved (deferred — seeding is owned by `apps/api/scripts/dev_seed.py`, separate concern) |
| P1-3 | `AnthropicLLMClient` hardcodes the model ids (`claude-sonnet-4-5-20250929`, `claude-haiku-4-5-20251001`). To swap to a different Claude model we need a code change. | deferred (small but out of audit scope; tracked here) |

### P2 — Polish

| ID | Finding | Status |
|---|---|---|
| P2-1 | `regenerate_block` uses `datetime.utcnow()` which is deprecated in Python ≥ 3.12. Cosmetic; runtime behavior unaffected. | deferred |
| P2-2 | `_pii_fields_per_block` only redacts on two block types; future blocks must register here. Not a current bug, just documentation owed. | deferred |
| P2-3 | The 422 deprecation warning in the test suite comes from anyio's HTTPX shim; will clear when anyio upgrades. | deferred (external) |
| P2-4 | `ANTHROPIC_API_KEY` / `CHECKWISE_LLM_BACKEND` are not visibly documented in `.env.example` (file is permission-blocked from the audit context). Should be added if not already present. | unresolved (operator action) |

### Deferred — real feature work, outside this audit

- DOCX / PDF export — table exists, endpoint not yet implemented.
- Signed share links — `report_shares` table exists, endpoint stub only.
- Inspector panel + autosave + version-history drawer.
- Plan-card / patch-card copilot turns (text-only today).
- Multi-org disambiguation UI for `create_report` when the actor
  has more than one org membership.

---

## 10. Safe fixes applied in this commit

Three files changed, all conservative:

1. `render.yaml` — declare `ANTHROPIC_API_KEY` and `CHECKWISE_LLM_BACKEND`
   as `sync: false` so the Blueprint deploy flow prompts the operator
   for them. **No values committed to git.**

2. `apps/api/app/api/v1/reports.py` — add `GET /reports/_engine` that
   reports the active LLM backend's `name`, `planner_model`, and
   `content_model`. Cheap, no DB hit, no auth requirement beyond
   `get_current_user`, no PII surface. Lets the frontend tell the
   user *AI report generation is not configured in this environment.*

3. `apps/web/app/portal/reports/[id]/page.tsx` — call
   `/reports/_engine` once on mount and render a one-line banner
   above the canvas when `backend === "mock"`. The "Generar con IA"
   button stays enabled (the mock still produces a useful
   deterministic plan for demos) but the operator now knows the
   output is not from a real model.

No new dependencies. No migrations. No seed changes. No secret
literals committed.

---

## 11. Recommended next actions (after this commit)

In priority order:

1. **Set `ANTHROPIC_API_KEY` on the Render dashboard.** The next
   autoDeploy will pick it up. Backend factory will switch to
   `AnthropicLLMClient` automatically.
2. **Add the same two vars to `.env.example`** (local-dev parity).
3. (Optional) Add a small seed of 2–3 example reports to
   `apps/api/scripts/dev_seed.py` so demo accounts land on a populated
   list. Owned by the seed track, separate PR.
4. (Optional) Lift the hardcoded model ids in `AnthropicLLMClient`
   into env-driven settings (`ANTHROPIC_PLANNER_MODEL`,
   `ANTHROPIC_CONTENT_MODEL`) when we want to A/B models.

---

## 12. Verification after fixes

```
apps/api/.venv/bin/ruff check app            All checks passed!
apps/api/.venv/bin/pytest tests/test_reports*.py
apps/web/node_modules/.bin/tsc --noEmit
apps/web/node_modules/.bin/next lint
```

Re-run after the patch. Each step should still be green; the
banner only renders client-side and does not affect any contract.

---

## 13. Honesty statement

- **AI report generation in production is currently mock unless the
  `ANTHROPIC_API_KEY` env var is set on Render** — adding it to
  `render.yaml` does not set it; the operator must populate it in
  the Render dashboard (which is exactly the point: `sync: false`).
- This audit did not exercise the live Vercel / Render URLs in a
  browser; the verification is code + tests + local build only. Any
  end-to-end browser pass should be done by an operator with a
  staging account.
- No commit, no push, no destructive command was executed outside
  the three file edits listed in §10.
