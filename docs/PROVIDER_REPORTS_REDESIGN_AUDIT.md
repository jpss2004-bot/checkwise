# Provider Reports — Redesign Audit (2026-05-18)

**Audit scope.** Document the *current* state of the Reports section as it
applies to the provider role, after P1 (provider-first reports via
workspace-derived visibility) merged in `d05fba3`. No code changes. No
recommendations yet — just an honest snapshot of what is in place, what
works, and where the provider experience falls short of "the strongest
part of CheckWise."

Companion docs:
- [REPORTS_ARCHITECTURE.md](REPORTS_ARCHITECTURE.md) §22–§25 (R1.0 → P1
  shipped state)
- [REPORTS_AUDIT_2026-05-18.md](REPORTS_AUDIT_2026-05-18.md) (general
  Reports module audit)
- [PROVIDER_DASHBOARD_READ_MODEL.md](PROVIDER_DASHBOARD_READ_MODEL.md)
  (canonical provider read model — the data source any provider report
  should consume)
- [PROVIDER_PORTAL_CANONICAL_READS.md](PROVIDER_PORTAL_CANONICAL_READS.md)
  (Phase 5 — onboarding + calendar enrichment fields)
- [EVIDENCE_SLOTS.md](EVIDENCE_SLOTS.md)
- [WORKFLOW_STATE_MACHINE.md](WORKFLOW_STATE_MACHINE.md)

Repo state at audit time: branch `main` @ `bb32cd4`, working tree clean,
up to date with `origin/main`. Frontend dev server :3000, backend uvicorn
:8000, and `checkwise-postgres` Docker container :5432 all responding.

---

## 0. TL;DR

The provider Reports section is **structurally complete** but
**experientially generic**.

What works (P1, just shipped):
- `/portal/reports` is now a thin `PortalAppShell` wrapper around the
  shared `<ReportsListView role="portal">` component (R2/P1).
- Provider visibility is derived from `ProviderWorkspace.owner_user_id`
  — no new `MembershipRole`, no schema change.
- `visible_audiences(actor)` returns `(VENDOR_FACING,)` for
  workspace-owner providers, plus an automatic
  `Report.vendor_id == actor.workspace_vendor_id` clause for
  cross-vendor isolation.
- Three provider presets (`provider-current-state`,
  `provider-missing-documents`, `provider-recent-rejections`) seeded
  via `presets_for_roles(roles, is_workspace_owner=True)`.
- `POST /reports/from-preset` auto-resolves `vendor_id` + `client_id`
  for workspace owners.
- Seven new tests in `test_reports_presets.py` lock down: preset
  visibility, auto-resolve, cross-vendor isolation, audience
  boundary, admin/client_admin regression guards.

What is *not* yet provider-grade:
1. The editor at `/portal/reports/[id]` is **the same generic AI
   canvas** an admin uses. No provider-specific surface, no upload
   deeplinks, no inline doc-state badges, no "fix this and resubmit"
   CTAs, no deadline warnings.
2. The block registry has **no provider-aware blocks**. All six
   block types (`text`, `divider`, `executive_summary`, `kpi_strip`,
   `vendor_risk_matrix`, `ai_recommendation`) are oriented at admin /
   client framing. There is no `missing_documents` block, no
   `recent_rejections` block, no `upcoming_deadlines` block — even
   though the dashboard read model already returns all three datasets.
3. The provider Reports list page **does not surface compliance state
   at a glance.** The provider sees a list of past reports + preset
   cards, but not "your current semaphore is yellow," "you have 3
   rejected docs," or "next deadline in 5 days." All that data is one
   `GET /portal/workspaces/{id}/dashboard` call away and is rendered
   today on `/portal/dashboard` only.
4. **The reports are AI prose-first.** The three presets shape prompts,
   but the actual content is a stream of generated Markdown. There is
   no structured guidance, no interactive checklist, no link from a
   rejected document mentioned in the AI output back to the upload
   flow.
5. **No empty-state guidance** specific to the provider. A first-time
   provider lands on `/portal/reports`, sees three preset cards plus
   an empty table, and has no clear sense of what to click first.

---

## 1. Current architecture (provider slice)

### 1.1 Routes (frontend)

| Route | Implementation today | Shell |
|---|---|---|
| `/portal/reports` | thin wrapper → `<ReportsListView role="portal">` (P1) | `PortalAppShell` + `withOnboardingGate` |
| `/portal/reports/[id]` | thin wrapper → shared `<ReportEditor>` (R1.0.1) | `PortalAppShell` + `withOnboardingGate` |
| `/portal/reports/[id]/print` | shared print view | unframed |

The wrappers are ~25 LOC. All real UI lives in
`frontend/components/checkwise/reports/`.

### 1.2 Backend surface (provider-relevant)

| Endpoint | Behavior |
|---|---|
| `GET /api/v1/reports` | Lists reports filtered by `visible_audiences(actor)`. For workspace owners, also filters by `Report.vendor_id == actor.workspace_vendor_id`. |
| `GET /api/v1/reports/_presets` | Returns `presets_for_roles(actor.roles, is_workspace_owner=actor.is_workspace_owner)` — for providers, exactly the 3 vendor-facing presets. |
| `POST /api/v1/reports/from-preset` | Auto-resolves `vendor_id` + `client_id` from the caller's workspace when the preset audience is `vendor_facing`. |
| `POST /api/v1/reports/{id}/generate` | SSE generate. Reuses the same Context Assembler + planner — no provider-specific path. |
| `GET /api/v1/reports/_engine` | Reports the active LLM backend (`anthropic` or `mock`) so the editor can banner. |

The trust boundary is intact: the LLM never sees raw rows; the Context
Assembler is tenant-scoped + PII-redacted per audience. Six explicit
`test_reports_ai_safety.py` scenarios pin this.

### 1.3 Data sources

| Need | Existing read API | Used by reports today? |
|---|---|---|
| Compliance % + semaphore level + reason | `GET /portal/workspaces/{id}/dashboard.semaphore` | **No** |
| Document state counts (approved / in_review / uploaded / rejected / expired / …) | `.document_state_counts` | **No** |
| Items needing attention (rejected, possible mismatch, in-review, expired, with `due_in_days` + `href`) | `.attention_today` | **No** |
| Upcoming deadlines (next ≤5, ordered by `due_in_days`) | `.upcoming_deadlines` | **No** |
| Suggested actions (reupload / clarify / verify / upcoming) with priority + `href` | `.suggested_actions` | **No** |
| Reviewer notes per submission | `/portal/workspaces/{id}/submissions/{id}.reviewer_note` (Phase 5) | **No** |
| Onboarding completion % | `.onboarding_summary` | **No** |
| Lineage-aware "current" submission per slot | evidence-slot service (Phase 3) | **No** |

Every signal the provider report should rely on already exists,
production-quality, tenant-scoped, lineage-aware, and tested. The
reports module simply does not consume it yet.

---

## 2. What works today (verbatim)

### 2.1 `/portal/reports` — list page

- Loads the shared list view (search, status filter, audience filter
  hidden for portal role).
- Renders the 3 provider preset cards from `GET /reports/_presets` in a
  3-column grid.
- "Use template" → `POST /reports/from-preset` → redirect to
  `/portal/reports/{id}`.
- Empty state copy branches on `hasActiveFilter`.
- Loads, paginates, error and empty states present.

### 2.2 `/portal/reports/[id]` — editor

- Mounts the shared `<ReportEditor>` inside `PortalAppShell`.
- Canvas, AI prompt panel, copilot, per-block regenerate / explain,
  save version, print mode all functional.
- Pre-fills the AI prompt from `content_json.global.recommended_prompt`
  set by `from-preset` (R1.0). One-click "Generar con IA" runs.
- Engine banner: when backend resolves to mock LLM, a one-line warning
  renders above the canvas.

### 2.3 Provider presets — content

`backend/app/services/reports/templates.py`:

| Preset | Audience | Block plan (recommended_prompt) |
|---|---|---|
| `provider-current-state` "Mi estado de cumplimiento" | `vendor_facing` | exec summary + KPI strip (compliance %, in-review count, expired count, days to next deadline) + 3 prioritized actions |
| `provider-missing-documents` "Documentos faltantes" | `vendor_facing` | exec summary on expediente + KPI strip (obligations total, expired, in-review) + 3 prioritized actions ("qué subir primero" naming the institution) |
| `provider-recent-rejections` "Rechazos recientes" | `vendor_facing` | exec summary on audit + KPI strip (incidence counts) + 3 corrective actions |

All three plans are realized today as `text` + `executive_summary` +
`kpi_strip` + `ai_recommendation` blocks. The matrix block is shared
admin-style.

### 2.4 Permission helpers

`backend/app/services/report_service.py`:

```
visible_audiences(actor):
  is_internal              -> (INTERNAL_ONLY, CLIENT_FACING, VENDOR_FACING, EXTERNAL_SIGNED)
  client_admin             -> (CLIENT_FACING,)
  is_workspace_owner       -> (VENDOR_FACING,)     # P1
  else                     -> ()                   # default deny
```

`list_reports` additionally filters `Report.vendor_id ==
actor.workspace_vendor_id` for workspace owners. `get_report` returns
404 (not 403) for forbidden audiences to prevent id enumeration.
`presets_for_roles(roles, is_workspace_owner=…)` lets a preset opt in
via either `required_roles` intersection or
`(required_roles == () and is_workspace_owner)`.

### 2.5 Tests (P1)

`backend/tests/test_reports_presets.py` adds 7 P1 tests, each ~30–60
LOC. They lock: provider-only preset visibility, auto-resolve of
vendor + client ids, cross-vendor isolation in `list`, audience
boundary on `get`, admin-preset 403 for provider, regression guards
for admin & client_admin preset counts. All pass.

---

## 3. Why the provider Reports section feels weaker than admin / client

### 3.1 The editor is not provider-shaped

The shared `<ReportEditor>` is built for an internal staffer composing a
narrative. The provider's job is different: *understand my state, see
exactly what is wrong, click to fix it.* The current editor:

- Surfaces a text-first AI canvas — providers must read prose to learn
  what's wrong.
- Has no inline doc-state badges (the same provider sees rich
  "rechazado / requiere aclaración / posible mismatch" chips on the
  dashboard, but not in their report).
- Has no deeplink back to `/portal/upload?…`. The dashboard's
  `suggested_actions[i].href` is a ready-made URL that the report
  could render as a button, but doesn't.
- Has no period selector tuned to the provider's compliance calendar.
- Has no "regenerate from latest data" affordance — the user has to
  re-prompt to refresh.

### 3.2 The blocks are generic, not provider-aware

`frontend/lib/reports/registry.ts` registers 6 block types. None are
shaped around the provider story.

| Block | Provider relevance today |
|---|---|
| `text` | useful for narrative intros — fine |
| `divider` | cosmetic — fine |
| `executive_summary` | thin: shows completion %, risk count, in-review count. Doesn't pull the canonical semaphore (level + reason). |
| `kpi_strip` | configurable, but each KPI key is generic. No "next deadline countdown" affordance, no per-institution breakdown. |
| `vendor_risk_matrix` | admin/client-shaped — a provider does not need a cross-vendor matrix. They need to see *their own* slots. |
| `ai_recommendation` | prose. No clickable action chips, no priority chip, no href. |

Missing for the provider story (and trivial to add because the
dashboard read model already returns them):

- `compliance_state` block — the full semaphore widget (level, reason,
  compliance %, on_track / total_tracked). Direct port of the
  dashboard's HeroSemaphore.
- `attention_today` block — table or list of items needing action, with
  institution chip + state chip + `due_in_days` + clickable upload
  href. Direct port of the dashboard's AttentionList.
- `upcoming_deadlines` block — next ≤5 deadlines, ordered, with
  institution + period + days remaining + href. Direct port.
- `missing_documents` block — required slots in `missing` /
  `pendiente`, grouped by institution. Already named in the
  REPORTS_ARCHITECTURE.md §15 deferred list.
- `recent_rejections` block — rejected / requires-clarification /
  possible-mismatch slots, with reviewer_note + fix-it CTA. New, but
  the data is `attention_today` filtered to blocking states.
- `onboarding_progress` block — completion % + missing required +
  next milestone. Useful for *both* the provider's own report and an
  admin auditing a single vendor.

### 3.3 The list page has no compliance overview

`/portal/reports` is currently *just* a list page. A provider opens it
expecting to learn something about their state, but the page shows:

1. Eyebrow: "Centro de cumplimiento personal."
2. Preset cards (3 cards).
3. Filter bar.
4. Empty table (or a small history of past generations).

The dashboard payload that the `/portal/dashboard` page renders as a
hero is not used here. A redesign could legitimately fold a
"compliance pulse" strip above the preset gallery without changing any
backend contract.

### 3.4 The AI does not get provider-aware context

The Context Assembler in `services/reports/context.py` already
tenant-scopes data, but it does *not* pre-fetch the dashboard
read-model payload for workspace-owner actors. A provider asking
"what should I fix this month?" gets only what the planner asks for via
tool-use. The dashboard's `suggested_actions` (already computed,
already ordered, already linked) never reaches the planner system
prompt.

Practical implication: the LLM has to ask the catalog for blocks one
at a time and reconstruct what the dashboard already knows. Cheaper
and more grounded would be to inject a "current_provider_state"
summary into the planner system prompt for workspace-owner generates.

### 3.5 No structured action surface

Every report ends with an `ai_recommendation` block — three prose
bullets. There is no:

- Action priority chip (high / medium / low).
- Click-through to upload.
- "Mark as done" affordance.
- Persistence between report generations (each generation produces a
  new set of suggestions; there's no link to the dashboard's same
  list).

The dashboard already returns `suggested_actions[].priority` +
`.type` + `.href`. The report bullets discard that structure.

---

## 4. Risks worth naming

### 4.1 Visibility / tenant safety

- **Vendor isolation is enforced today**, both at `list_reports`
  (additional `vendor_id ==` filter) and at `get_report` (404 for
  forbidden audience). Tests
  `test_workspace_actor_list_only_returns_own_vendor` and
  `test_workspace_actor_cannot_read_client_facing` pin this.
- **Risk:** if we introduce provider-aware blocks that take a `vendor_id`
  config, the block's `data_fetcher` MUST re-assert vendor scope —
  do not trust the planner's config. The block registry's
  `data_fetcher(config, context, snapshot)` already passes the
  ReportContext, but new block authors might forget. **Action item
  for the redesign:** add an `assert_workspace_scope()` helper that a
  vendor-only block calls before fetching, mirroring the existing
  `assert_scoped()` helper.
- **Risk:** if a provider is allowed to view a report scoped to a
  different `vendor_id` (e.g., through a bug in `_actor_from`), the
  block-level vendor scope check is the second line of defense.

### 4.2 Provider identity ambiguity

A workspace owner could in principle be linked to *two* vendor
workspaces in the schema (one user owns two providers across
clients). Today `_actor_from` picks the first `ProviderWorkspace.owner`
row it finds. **Risk:** dual-ownership reports could leak between
vendors. The seed data does not exercise this case; the test suite
does not either.

### 4.3 AI hallucination on provider reports

Provider reports are *the highest-stakes generated content* in the
product — they're the one a non-technical user might read literally
and act on. The mock-engine banner exists; the per-block "AI-generated
· verify" pill exists. **Risk:** without grounded context injection,
the LLM can drift into generic compliance prose that doesn't reflect
the actual state. Mitigation requires injecting the dashboard payload
into the planner system prompt for vendor-facing generates.

### 4.4 Demo + seed gaps

`scripts/dev_seed.py` was adjusted in P1 to flip the seeded vendor
report to `vendor_facing` and add the boss client organization. But
the seed does not generate the per-slot evidence states a meaningful
provider report needs — a fresh boss.demo provider running "Mi estado
de cumplimiento" against the mock LLM today gets canned prose because
both the data and the model are stubbed.

### 4.5 Old portal list page divergence

`/portal/reports/page.tsx` was migrated to the shared list view in
P1. Stale snapshots of the prior V2.1 inline-create UI may exist in
git history. **Risk:** non-zero. **Action:** the redesign should
land on top of the shared list view, not the V2.1 inline-create
implementation.

### 4.6 Block registry symmetry

Every new block type needs both a frontend `BlockDefinition` (in
`frontend/lib/reports/registry.ts`) and a backend `data_fetcher` (in
`backend/app/services/reports/blocks/`). If they drift, the planner
will emit a config the renderer can't render, or vice versa.

---

## 5. What is salvageable verbatim

Re-using what P1 just shipped, with **zero rework**:

- The shared `<ReportsListView>` — adds new provider widgets without
  touching admin / client.
- The shared `<ReportEditor>` — same.
- The Context Assembler trust boundary — extend, do not bypass.
- The preset registry shape — add provider-specific block presets to
  the existing 3 preset entries.
- The dashboard read model + evidence-slot service — every provider
  block should be a thin adapter over these, not a new query path.
- The vendor isolation enforcement at both list and get layers.

---

## 6. Honest summary of where we stand

| Dimension | Provider Reports today |
|---|---|
| Visibility & tenant safety | ✅ production-quality (P1, tested) |
| List page parity with admin/client | ✅ shared component, role="portal" |
| Editor parity | ✅ shared component, mounts in PortalAppShell |
| Provider-shaped blocks | ❌ none — all 6 blocks are generic |
| Provider-shaped content (AI) | ⚠️ presets shape the prompt, but the LLM doesn't get the dashboard payload as grounding |
| Interactive action surface | ❌ AI prose only, no click-to-fix |
| Compliance pulse at-a-glance | ❌ not on the list page, not in the editor |
| Deeplinks to upload | ❌ |
| Empty-state guidance | ⚠️ generic, not provider-shaped |
| Demo-readiness | ⚠️ depends on seed quality + `ANTHROPIC_API_KEY` on Render |

The infrastructure is solid; the experience is generic. The redesign's
job is to *consume* what's already there.
