# QA results — 2026-05-18

Companion to `docs/FULL_SYSTEM_AUDIT.md`. Records exactly what was tested, how, and the pass/fail.

## Test environment

- Branch: `main`
- Baseline commit: `5559e1c`
- Backend: FastAPI on `127.0.0.1:8000` (uvicorn `--reload`, real Anthropic key in `.env`)
- Frontend: Next.js dev on `localhost:3000`
- Postgres: docker-compose `checkwise-postgres`, healthy
- LLM backend: Anthropic (planner `claude-sonnet-4-5-20250929`, content `claude-haiku-4-5-20251001`)

## Flows tested

### Auth — verified end-to-end via curl

| Account | Login result | Roles | Routes to |
|---|---|---|---|
| `ada@legalshelf.mx` / `(rotated 2026-05-18 · ask operator)` | **200** | `internal_admin`, `reviewer` | `/admin/reviewer` |
| `cliente.demo@checkwise.mx` / `(rotated 2026-05-18 · ask operator)` | **200** | `client_admin` | `/client/dashboard` |
| `boss.demo@checkwise.mx` / `(rotated 2026-05-18 · ask operator)` | **200** | *(none)* | `/portal/entra-a-tu-espacio` |
| `proveedor.demo@checkwise.mx` / `(rotated 2026-05-18 · ask operator)` | **200** (must_change_password=true) | *(none)* | `/activate` |

### Backend API surface — verified via curl

Admin (`ada`):

| Endpoint | Code | Note |
|---|---|---|
| `GET /api/v1/auth/me` | 200 | |
| `GET /api/v1/admin/overview` | 200 | |
| `GET /api/v1/admin/clients` | 200 | |
| `GET /api/v1/admin/vendors` | 200 | |
| `GET /api/v1/admin/requirements` | 200 | |
| `GET /api/v1/admin/calendar` | 200 | |
| `GET /api/v1/admin/audit-log` | 200 | |
| `GET /api/v1/reviewer/queue` | 200 | |
| `GET /api/v1/reports` | 200 | |
| `GET /api/v1/reports/_presets` | 200 | 3 admin presets |
| `GET /api/v1/reports/_engine` | 200 | `{"backend":"anthropic"}` |
| `GET /api/v1/client/me` | 200 | admins can cross-tenant by design |

Client (`cliente.demo`):

| Endpoint | Code | Note |
|---|---|---|
| `GET /api/v1/auth/me` | 200 | |
| `GET /api/v1/client/me` | 200 | |
| `GET /api/v1/client/overview` | 200 | |
| `GET /api/v1/client/vendors` | 200 | 3 seeded vendors |
| `GET /api/v1/client/activity` | 200 | |
| `GET /api/v1/client/calendar` | 200 | |
| `GET /api/v1/client/submissions` | 200 | |
| `GET /api/v1/reports` | 200 | only `client_facing` audiences |
| `GET /api/v1/reports/_presets` | 200 | empty list (no client presets in R1.0 yet) |
| `GET /api/v1/admin/overview` | **403** | correct — forbidden by role |
| `GET /api/v1/reviewer/queue` | **403** | correct — forbidden by role |

### Reports AI generation — verified end-to-end

```
POST /api/v1/reports/{id}/generate
prompt: "Resumen ejecutivo breve sobre el estado actual."

30 SSE events in ~11s:
  plan
  block_start, block_data, ai_summary_delta(×N), block_complete  (executive_summary)
  block_start, block_data, block_complete                        (kpi_strip)
  block_start, block_data, block_complete                        (vendor_risk_matrix)
  block_start, block_data, ai_summary_delta(×N), block_complete  (ai_recommendation)
  version_saved
  done
```

This confirms: planner reaches Anthropic → executor fetches per-block data → AI summaries stream → version persists → SSE closes cleanly.

### Pages tested

**Code-verified only — not browser-clicked this session.** All page files exist and import successfully (verified via `next build` earlier in the project history at commit `6ba0d33`). The previous session pushed the user to do manual browser smoke; the user reported "all tests passed" before issuing this audit prompt.

## Bugs found

| ID | Severity | Location | Status |
|---|---|---|---|
| B4 | P1 | `apps/web/app/admin/_shell.tsx:74` rejected reviewer-only users | **fixed** |
| B5 | P1 | `pytest` failed when real `ANTHROPIC_API_KEY` was in env | **fixed** |
| B3 | P2 | `/admin/login` legacy double-hop redirect | filed, not fixed |

P0 / additional P1 bugs: none found via static + API audit.

## Bugs fixed

### B4 — AdminShell now accepts reviewer-only users

```diff
-    if (!current.roles.includes("internal_admin")) {
+    if (
+      !current.roles.includes("internal_admin") &&
+      !current.roles.includes("reviewer")
+    ) {
       router.replace("/admin");
       return;
     }
```

`apps/web/app/admin/_shell.tsx` — 12 lines changed. Reviewer-only users (none currently seeded but the role exists) can now reach `/admin/reviewer`, their primary surface.

### B5 — pytest LLM isolation via conftest.py

```python
# apps/api/tests/conftest.py
import os
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["CHECKWISE_LLM_BACKEND"] = "mock"
```

Runs at session import. Strips any inherited Anthropic key and forces the deterministic mock. **Verified: 320/320 pytest pass** with no env tricks at the command line.

## Test results

| Check | Before this session | After this session |
|---|---|---|
| `ruff check app tests` | clean | clean |
| `pytest -q` (vanilla shell) | 4 failed, 316 passed | **320 passed** |
| `tsc --noEmit` | clean | clean |
| `next lint --quiet` | clean | clean |
| API admin smoke | 12/12 200 | 12/12 200 |
| API client smoke | 9/9 200 + 2/2 403 | 9/9 200 + 2/2 403 |
| Real Anthropic `/generate` SSE | 30 events / 11s | 30 events / 11s |

## Unresolved issues

- **B3** — `/admin/login` double-hop redirect. Cosmetic only.
- **Browser click verification** — every shipped surface needs manual click-through. Not done in this session.
- **Production AI key** — Render still doesn't have `ANTHROPIC_API_KEY` set; the production `/admin/reports` banner will still say "no AI" until it's configured.
- **Production seed accounts** — none exist. Provisioning a real production login is a separate task.

## Deferred (product feature gaps)

- R1.0.1 — shared editor across admin/portal shells
- R1.1 — client preset gallery + 3 client-facing presets
- R1.2 — `external_signed` signed-link delivery for vendors
- R2 — interactive filters
- Server-side DOCX / PDF export
- 5 mock modules still backed by `apps/web/lib/mock/*` (documented as `TODO[backend-integration]`)

## Confidence level

- **High** on code correctness: ruff + tsc + lint + 320 pytest + curl matrix all green.
- **High** on auth + role routing: verified per-role API smoke.
- **High** on AI report pipeline: end-to-end Anthropic streaming verified.
- **Medium** on per-page UX (loading / error / empty states): not browser-verified.
- **Medium** on per-button behavior: not browser-clicked.
- **N/A** on production AI report flow: depends on the user setting `ANTHROPIC_API_KEY` in the Render dashboard.

## Recommendation for next session

If browser smoke today produces no P1s, this branch is ready to push and the natural next step is **R1.1 (client preset gallery)** — it mirrors R1.0 cleanly and closes the second role surface.

If browser smoke finds problems, fix those first; everything below R1.1 is product evolution, not stabilization.
