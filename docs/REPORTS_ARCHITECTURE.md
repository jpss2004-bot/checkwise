# CheckWise Reports — Architecture

Status: **Phase 3.0 deliverable.** Architecture lock for the AI-orchestrated Reports workspace. Read first; the block catalog lives in [REPORTS_BLOCK_REGISTRY.md](REPORTS_BLOCK_REGISTRY.md).
Locked: 2026-05-17, on `design/reports-architecture` branch.

Companion docs: [CHECKWISE_2_0.md](CHECKWISE_2_0.md), [DATA_MODEL.md](DATA_MODEL.md), [design-system/VISUAL_DIRECTION_2_X.md](design-system/VISUAL_DIRECTION_2_X.md).

---

## 1. Vision

Reports is **not** an export surface. It is a living compliance-intelligence workspace where operators describe what they need in natural language and an LLM-orchestrated engine composes a real, editable, exportable report from CheckWise's actual compliance state.

Compared in product-language:
- Notion's editable canvas
- Power BI's chart-as-block composition
- Linear's keyboard density
- ChatGPT Canvas / Claude Artifacts' streaming structured generation
- Stripe Dashboard's document-quality exports
- Vanta's compliance row patterns

Single product object:

```
ReportRequest (natural language)
  → ReportPlan (LLM-chosen sequence of block specs)
  → ReportVersion (rendered, editable, persisted)
  → Export (PDF / DOCX / shared link / presentation mode)
```

The user can enter at any layer. They can chat to plan a new report, click a template to start with a known plan, edit any block by hand after generation, ask the copilot to refine, regenerate one section, save a version, export, or share.

## 2. North-Star user flow

> **Operator** opens `/portal/reports` and clicks **New report**. A right-rail chat opens:
>
> ## "Hi — what would you like a report on?"
>
> They type: *"Generate a monthly REPSE risk summary for all providers missing SAT compliance."*
>
> The copilot acknowledges (1 line), then streams an **inline plan card** showing the 5 blocks it intends to render. The user can edit the plan or hit **Generate**.
>
> Blocks stream into the canvas left-side one at a time, top-to-bottom. Each block fades in with `cw-fade-up`, takes 1–4 seconds to fill (data fetched + LLM content composed). Each block carries an "AI-generated" pill if it contains generated text.
>
> When the report is complete the chat narrows; the user can keep refining ("add a section comparing this month to last", "tighten the executive summary", "remove the IMSS column from the matrix") and the copilot edits the canvas in place.
>
> The user clicks an executive-summary paragraph and inline-edits it. Autosave shows a tiny "saved 2s ago" timestamp.
>
> They click **Save version** → labeled snapshot. **Share** → modal with audience (`client_facing`), expiration, watermark, copy link. **Export → DOCX** → server generates, polled, downloaded.
>
> Two days later they reopen the report and ask: *"Refresh this with this week's data."* The copilot keeps the layout but pulls fresh data into every block.

## 3. Layered architecture

```
┌─ Frontend ─────────────────────────────────────────────────────┐
│  Canvas             Right-rail Copilot       Inspector / Edits │
│  (BlockNote +       (chat + plan card)        (block config)   │
│   custom blocks)                                                │
└──────────────────────┬─────────────────────────────────────────┘
                       │ SSE for streaming, REST for CRUD
┌──────────────────────▼─────────────────────────────────────────┐
│  FastAPI Reports API                                            │
│   /api/v1/reports/{*}, /api/v1/reports/{id}/generate,           │
│   /api/v1/reports/{id}/conversation, /api/v1/exports/{id},      │
│   /api/v1/shared/{token}                                        │
└──────┬────────────────┬────────────────────────────┬────────────┘
       │                │                            │
┌──────▼─────┐  ┌───────▼──────────┐   ┌─────────────▼───────────┐
│ Persistence│  │ Block Registry   │   │ LLM Orchestrator        │
│ (Postgres) │  │ (server-side)    │   │ • Planner (Claude)      │
│ reports +  │  │ data_fetcher +   │   │ • Block-content gen     │
│ versions   │  │ docx_renderer    │   │ • Refinement / chat     │
└─────┬──────┘  └────────┬─────────┘   │ • Tool-use (block schemas)│
      │                  │              └───────┬─────────────────┘
      └──── canonical compliance read models ◄──┘
            (tenant-scoped, never bypassed)
```

Three architectural commitments:

1. **The LLM never reads raw data.** It only sees data fetched + sanitized + tenant-scoped by the block registry's `data_fetcher`. The Block Registry is the trust boundary.
2. **AI-generated text is separated from canonical data** at the storage layer. Every block field that contains LLM output is marked `generated_by: "ai"` + carries `model_id` + `source_snapshot_id`. The UI shows an "AI-generated · Verify" annotation on those fields. Canonical data (a vendor's RFC, a submission's status, a deadline date) is never replaced by LLM output.
3. **Permission and audience are enforced server-side per request**, not via UI hiding. A `client_facing` report rendered to a `provider` viewer returns 403 even if the link is shared.

## 4. Data model (Postgres + Alembic)

```sql
-- Core report entity
reports (
  id              uuid PRIMARY KEY,
  tenant_id       uuid NOT NULL REFERENCES tenants(id),
  client_id       uuid NULL REFERENCES clients(id),   -- scope: client portfolio
  vendor_id       uuid NULL REFERENCES vendors(id),   -- scope: single vendor
  title           text NOT NULL,
  description     text,
  audience        text NOT NULL,  -- enum: internal_only|client_facing|vendor_facing|external_signed
  status          text NOT NULL,  -- draft|active|archived
  created_by      uuid NOT NULL REFERENCES users(id),
  created_at      timestamptz NOT NULL,
  updated_at      timestamptz NOT NULL,
  current_version_id  uuid NULL,   -- latest version (FK after report_versions exists)
  CHECK (client_id IS NOT NULL OR vendor_id IS NOT NULL OR audience = 'internal_only')
);

-- Every persisted snapshot of the report content
report_versions (
  id                uuid PRIMARY KEY,
  report_id         uuid NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
  version_number    int  NOT NULL,
  parent_version_id uuid NULL REFERENCES report_versions(id),
  label             text NULL,                -- "v1 draft", "after Pedro's edits", or NULL for autosaves
  content_json      jsonb NOT NULL,           -- the canvas tree (block array)
  plan_json         jsonb NULL,               -- the ReportPlan that produced this version
  generated_by      text NOT NULL,            -- 'user' | 'ai' | 'ai_refined'
  source_snapshot_id uuid NULL,               -- pointer to compliance_snapshots row used as data basis
  llm_metadata      jsonb NULL,               -- {model, prompt_hash, token_usage, cost_usd, latency_ms}
  created_by        uuid NOT NULL REFERENCES users(id),
  created_at        timestamptz NOT NULL,
  UNIQUE (report_id, version_number)
);
CREATE INDEX idx_report_versions_report ON report_versions(report_id, version_number DESC);

-- Chat conversation associated with a report
report_conversations (
  id              uuid PRIMARY KEY,
  report_id       uuid NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
  turn_number     int NOT NULL,
  role            text NOT NULL,  -- 'user'|'assistant'|'system'|'tool'
  content_json    jsonb NOT NULL, -- {text, plan_card?, tool_calls?, tool_results?}
  attached_version_id uuid NULL REFERENCES report_versions(id),  -- which version this turn produced/edited
  created_at      timestamptz NOT NULL,
  UNIQUE (report_id, turn_number)
);

-- Compliance data snapshots — what the LLM saw at generation time.
-- Decouples report generation from live data so reports are reproducible
-- and auditable. One snapshot can be reused across blocks of one version.
compliance_snapshots (
  id            uuid PRIMARY KEY,
  tenant_id     uuid NOT NULL,
  client_id     uuid NULL,
  vendor_id     uuid NULL,
  scope_filter  jsonb NOT NULL,  -- {period, institutions, audience, …}
  data_json     jsonb NOT NULL,  -- the captured rows
  taken_at      timestamptz NOT NULL,
  row_count     int NOT NULL,
  data_hash     text NOT NULL    -- sha256 of data_json
);

-- Shareable signed links
report_shares (
  id              uuid PRIMARY KEY,
  report_id       uuid NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
  version_id      uuid NOT NULL REFERENCES report_versions(id),
  token_hash      text NOT NULL UNIQUE,  -- sha256 of the signed JWT
  audience        text NOT NULL,
  watermark       text NULL,
  password_hash   text NULL,             -- optional password
  expires_at      timestamptz NULL,
  revoked_at      timestamptz NULL,
  created_by      uuid NOT NULL,
  created_at      timestamptz NOT NULL,
  last_accessed_at timestamptz NULL,
  access_count    int NOT NULL DEFAULT 0
);

-- Export artifacts
report_exports (
  id              uuid PRIMARY KEY,
  report_id       uuid NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
  version_id      uuid NOT NULL REFERENCES report_versions(id),
  format          text NOT NULL,         -- 'pdf'|'docx'|'pptx'|'html'
  status          text NOT NULL,         -- 'pending'|'rendering'|'ready'|'failed'
  storage_key     text NULL,             -- S3-style key when ready
  error_text      text NULL,
  bytes           int NULL,
  requested_by    uuid NOT NULL,
  requested_at    timestamptz NOT NULL,
  ready_at        timestamptz NULL,
  expires_at      timestamptz NULL
);
```

Five tables + one snapshot table. No per-block row — block data lives inside `report_versions.content_json` as a JSON tree. This matches how Notion / Linear / BlockNote persist their content and avoids a write-amplification problem when the user is dragging blocks around.

### Why a snapshot table?

Because the same report regenerated next week with refreshed data is a *different* report. The snapshot lets us:
- Reproduce a version exactly (regulatory / audit requirement).
- Diff "what the data said last week" vs "what it says now."
- Avoid double-charging LLM costs when the same plan + same snapshot is re-rendered (cache hit on `data_hash`).

### Migration sequence

```
0009_reports_core            -- reports + report_versions
0010_reports_conversations   -- report_conversations + compliance_snapshots
0011_reports_sharing_exports -- report_shares + report_exports
0012_reports_indexes_constraints  -- composite indexes, RBAC check constraints
```

Per [AGENTS.md](../AGENTS.md): migrations are append-only; never edit a merged migration.

## 5. Block model

A `Block` is a typed JSON object. Every block has:

```typescript
interface Block<TType extends string = string, TConfig = unknown, TData = unknown> {
  id: string;                         // stable across versions; new ones get a uuid
  type: TType;                        // discriminant — looks up the registry entry
  config: TConfig;                    // user-editable parameters (period, filters, columns)
  data: TData | null;                 // server-rendered data; null = needs fetching
  ai_summary: AISummary | null;       // generated text bound to this block, or null
  layout: {                           // canvas placement
    width: 'full' | 'half' | 'third';
    collapsed?: boolean;
  };
  locked?: boolean;                   // user can lock blocks against AI rewrite
}

interface AISummary {
  text: string;                       // markdown — the LLM-generated commentary
  model: string;                      // e.g., "claude-sonnet-4-6"
  prompt_hash: string;
  generated_at: string;               // ISO
  source_snapshot_id: string;
  citations: Citation[];              // optional links back to source rows
}
```

The canvas tree:

```json
{
  "schema_version": 1,
  "blocks": [
    { "id": "...", "type": "executive_summary", "config": {...}, "data": {...}, "ai_summary": {...}, "layout": {"width": "full"} },
    { "id": "...", "type": "vendor_risk_matrix", "config": {...}, "data": {...}, "ai_summary": null, "layout": {"width": "full"} },
    ...
  ],
  "global": {
    "period": "2026-M05",
    "primary_audience": "internal_only"
  }
}
```

The catalog of block types lives in [REPORTS_BLOCK_REGISTRY.md](REPORTS_BLOCK_REGISTRY.md).

## 6. Block Registry

Two halves, sharing the type contract.

### 6.1 Frontend half

`apps/web/lib/reports/registry.ts` — one entry per block type:

```typescript
interface BlockDefinition<TConfig, TData> {
  type: string;
  label: string;
  icon: Icon;                                                            // Phosphor
  configSchema: z.ZodSchema<TConfig>;
  dataSchema: z.ZodSchema<TData>;
  defaultConfig: TConfig;
  Component: React.FC<BlockProps<TConfig, TData>>;                       // canvas + print
  ExportSlide: React.FC<BlockProps<TConfig, TData>>;                     // presentation mode
  EditPanel: React.FC<BlockEditProps<TConfig>>;                          // right-rail inspector
  llmDescription: string;                                                // tool description for the planner
  llmExampleConfigs: { intent: string; config: TConfig }[];              // few-shot
}
```

Components are RSC-compatible where possible. Editor mode forces `"use client"` per [DESIGN.md](../DESIGN.md).

### 6.2 Backend half

`apps/api/app/services/reports/blocks/<type>.py` — one module per block:

```python
class BlockDefinition(BaseModel):
    type: Literal["vendor_risk_matrix"]
    config_schema: type[BaseModel]
    data_schema: type[BaseModel]
    llm_description: str
    llm_example_configs: list[dict]

def fetch_data(
    config: VendorRiskMatrixConfig,
    context: ReportContext,
    snapshot: ComplianceSnapshot,
) -> VendorRiskMatrixData:
    """Tenant-scoped data fetch. Snapshot is read-only here."""

def render_ai_summary(
    config: VendorRiskMatrixConfig,
    data: VendorRiskMatrixData,
    audience: ReportAudience,
    llm: LLMClient,
) -> AsyncIterator[str]:
    """Stream Markdown commentary. None if the block has no AI text."""

def render_docx(
    config, data, ai_summary,
) -> list[DocxElement]:
    """Build the DOCX representation."""
```

The shape is symmetric: TypeScript ↔ Pydantic via auto-generated types. We re-use the existing OpenAPI generation pipeline.

## 7. LLM Orchestration

Anthropic Claude. Two model tiers:

- **Planner / refinement:** `claude-sonnet-4-6` — needs strong reasoning + tool-use.
- **Per-block content + inline regenerate:** `claude-haiku-4-5` — faster, cheaper, sufficient for "summarize these rows" tasks.

The Anthropic SDK is added to backend deps in Phase 3.3. **Prompt caching is mandatory** on the planner — the catalog description + project context get cached once per session and the user's specific request becomes the suffix.

### 7.1 Planner (one LLM call per new request)

System prompt (cached):
- CheckWise product context (from `PRODUCT.md`).
- Audience rules (which fields each audience can see).
- Full block catalog: type + `llmDescription` + `llmExampleConfigs`.
- Output schema: JSON `ReportPlan`.

User turn:
- Natural-language request.
- Conversation history (last 6 turns).
- Current canvas state (compact summary) if refining an existing report.

Output (validated against zod):
```json
{
  "title": "Resumen REPSE — proveedores sin SAT, mayo 2026",
  "audience": "internal_only",
  "scope": { "period": "2026-M05", "client_ids": [], "vendor_ids": [], "filter": { "missing_institution": "sat" } },
  "blocks": [
    { "id": "b1", "type": "executive_summary", "config": {"focus": "missing_sat"} },
    { "id": "b2", "type": "vendor_risk_matrix", "config": {"filter": {"missing_institution": "sat"}, "sort": "risk_desc"} },
    { "id": "b3", "type": "missing_documents", "config": {"period": "2026-M05", "institutions": ["sat"]} },
    { "id": "b4", "type": "ai_recommendation", "config": {"based_on": ["b2", "b3"]} }
  ],
  "rationale": "User asked specifically about SAT-missing providers; matrix + missing-docs cover the data; exec summary + recommendation top and tail."
}
```

The planner uses **tool-use** with one tool per block type. Tools are stubs whose schemas mirror `configSchema`. This lets Claude validate config shapes during planning rather than at execution time.

### 7.2 Per-block content (one LLM call per block that has `ai_summary`)

System prompt (cached per request):
- Block-type-specific guidance ("you are summarizing a vendor risk matrix").
- Audience tone rules.
- Strict instructions: cite source rows by ID, never fabricate, return Markdown.

User turn:
- The fetched data (already tenant-scoped).
- The block config.

Streaming output is sent to the client over SSE as the response body, with framed deltas.

### 7.3 Refinement (chat copilot)

The copilot is **bounded to the report**:
- It can read the current canvas state.
- It can call the same tool catalog.
- It can produce a **patch plan**: `add_block`, `remove_block`, `edit_block_config`, `regenerate_ai_summary`, `update_metadata`.

Patch plans are validated and previewed in the chat as an "I'll do X — apply?" card before mutating the canvas. The user can hit a single keystroke to accept.

### 7.4 Data isolation guarantee

Three layers prevent cross-tenant leakage:

1. **Pre-fetch:** the data_fetcher receives a `ReportContext` containing `tenant_id`, `client_id`, `vendor_id`, `audience`. Every query is scoped by these. There is no path where the LLM names an entity that the data_fetcher then queries — block configs are validated against a whitelist of permitted IDs first.
2. **At-fetch:** SQLAlchemy queries always include the tenant filter. We add an `assert_scoped()` helper that fails if any SELECT lacks the tenant filter.
3. **Post-fetch:** before the LLM sees data, a sanitizer strips any field marked `pii: true` in the data schema unless the audience permits it.

## 8. Streaming pipeline (SSE protocol)

Endpoint: `POST /api/v1/reports/{id}/generate`

Request body:
```json
{ "prompt": "...", "conversation_turn_id": "..." }
```

Response: `text/event-stream`, ordered:

```
event: plan
data: { "plan": { ... } }

event: block_start
data: { "block_id": "b1", "type": "executive_summary" }

event: block_data
data: { "block_id": "b1", "data": { ... } }

event: ai_summary_delta
data: { "block_id": "b1", "delta": "Durante mayo " }

event: ai_summary_delta
data: { "block_id": "b1", "delta": "2026, 14 proveedores..." }

event: block_complete
data: { "block_id": "b1" }

...

event: version_saved
data: { "version_id": "...", "version_number": 1 }

event: done
data: { "total_latency_ms": 4823, "total_tokens": 12450, "cost_usd": 0.084 }
```

Client side: `useReportGeneration(reportId)` hook maintains a Zustand store of in-flight blocks. The Canvas re-renders incrementally; the user sees blocks materialize.

Errors: an `event: error` frame contains `{ block_id?, code, message }`. The hook surfaces inline in the affected block with a retry CTA.

## 9. Editor surface

### 9.1 BlockNote integration

We pick BlockNote because:
- Block-typed JSON model out of the box.
- Custom-block API (`createReactBlockSpec`) — every CheckWise block type registers as a BlockNote block.
- Drag/drop, slash menu, multi-column layouts included.
- ProseMirror under the hood — battle-tested.

We do **not** use BlockNote's text-formatting model for compliance content. Blocks containing tables, charts, and matrices are "atomic": BlockNote treats them as opaque, the contents are rendered by our own React components. Only the `text` block type (intro paragraphs, commentary) uses BlockNote's prose model directly.

### 9.2 Edit semantics

Per block:
- **Inline-editable text fields** (titles, captions, commentary text) — direct contenteditable + autosave debounced 1.5s.
- **Config edits** (date range, filter, columns) — happen in the right-rail **Inspector** panel, not inline. Saving the inspector triggers a `data` refetch.
- **AI summary regenerate** — button on the block header. Calls `POST /reports/{id}/blocks/{block_id}/regenerate`. Streams new content back.
- **Lock** — toggle on the block header. Locked blocks are protected from chat-copilot mutations.

### 9.3 Autosave + versioning rules

| Trigger | Behavior |
|---|---|
| Inline text edit (debounced 1.5s) | Patch `content_json`. **No new version row.** Update `updated_at`. |
| Config change → data refetch | Patch `content_json` + bump `data` field. **No new version row.** |
| AI regenerate of a block | Patch `content_json`. **No new version row.** AI metadata updated. |
| Generate / refinement turn | **New `report_versions` row** with `label = null`, `generated_by = 'ai_refined'`. |
| Manual "Save version" | **New `report_versions` row** with user-supplied label. |
| Every N=20 inline edits OR every 5 minutes whichever first | **Auto-version** with `label = "Auto-saved 14:32"`. |

Older auto-versions older than 30 days get garbage-collected unless `label != null`. We keep the most recent 5 auto-versions regardless of age.

### 9.4 Layout

```
┌─ Page header (PageHeader primitive) ─────────────────────────────┐
│  ← Reports  /  Resumen REPSE — mayo 2026         [Share][Export] │
│  cw-metadata-strip: AUDIENCE  internal_only  ·  v3  ·  saved 2s  │
└──────────────────────────────────────────────────────────────────┘
┌─ Canvas (max-w-5xl prose width) ─┬─ Right rail (380px) ─────────┐
│                                  │                              │
│  [executive_summary] full        │  ┌─ Chat copilot ─┐           │
│  [vendor_risk_matrix] full       │  │ ... messages ..│           │
│  [missing_documents] full        │  │                │           │
│  [ai_recommendation] full        │  │ ┌─ input ────┐ │           │
│                                  │  │ └────────────┘ │           │
│  + Add block                     │  └────────────────┘           │
│                                  │                              │
│                                  │  ─── or ───                  │
│                                  │  Inspector for selected block │
│                                  │                              │
└──────────────────────────────────┴──────────────────────────────┘
```

Right rail toggles between **Chat** and **Inspector** (selecting a block focuses Inspector; clicking the chat icon switches back). Single rail, two views, no horizontal splitting.

## 10. Chat copilot model

```typescript
interface ConversationTurn {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: TurnContent;
  attached_version_id?: string;
  created_at: string;
}

type TurnContent =
  | { kind: 'text'; markdown: string }
  | { kind: 'plan_card'; plan: ReportPlan; status: 'proposed' | 'accepted' | 'rejected' }
  | { kind: 'patch_card'; patches: ReportPatch[]; status: 'proposed' | 'accepted' | 'rejected' }
  | { kind: 'tool_call'; tool: string; args: unknown }
  | { kind: 'tool_result'; tool_call_id: string; result: unknown }
  | { kind: 'error'; code: string; message: string };
```

Conversation memory: last 12 turns plus the current canvas summary. Older turns are dropped from the LLM context but remain visible in the UI.

Suggested prompt seeds (rendered as chips above the input on a new report):

- *"Resumen mensual de cumplimiento para enviar al cliente."*
- *"Solo proveedores con IMSS o INFONAVIT vencidos."*
- *"Reporte ejecutivo comparando este trimestre con el anterior."*
- *"Auditoría completa con recomendaciones por proveedor."*

These come from a `getSuggestedPrompts({ audience, recent_activity })` helper, not hardcoded — they re-rank based on what the workspace has been working on.

## 11. Multi-format output

| Format | Implementation | Notes |
|---|---|---|
| **Web (primary)** | The canvas itself, with `data-density="dense"` and `.cw-prose` width cap on text blocks. | Interactive forever. |
| **Print / browser PDF** | Dedicated route `/portal/reports/[id]/print`. CSS `@page` rules. Block components have a `print:` modifier set per block. Print via browser. | No external dependency. v1 default. |
| **PDF (server-side)** | Optional. Renders the same React tree to HTML via a headless renderer, prints to PDF. Defer until print-mode shows real demand. | Phase 3.6 deferred unless requested. |
| **DOCX** | `python-docx`. Each block registers a `render_docx(config, data, ai_summary) -> list[DocxElement]` function. Server-side, async job for >5s renders. | Phase 3.6. |
| **Presentation mode** | Same React tree, different layout. Blocks render as slide-sized cards, paginated 1 block per slide for atomic blocks (matrix, chart) and 2-3 stacked for short blocks. Keyboard ←/→ to navigate. | In-app only for v1; PPTX export defers. |
| **Shared link (HTML)** | Public route `/shared/{token}` with no auth wrapper. Renders read-only canvas + watermark if configured. | Phase 3.7. |

## 12. Sharing + permissions

### 12.1 Audience matrix

| Audience | Who can read | What's visible |
|---|---|---|
| `internal_only` | `internal_admin`, `reviewer` | Everything. PII included. |
| `client_facing` | `client_admin` for the report's `client_id`; internal staff | PII redacted by default (operator can override per-block). |
| `vendor_facing` | The owner of `vendor_id` (provider users); internal staff | PII redacted. Audit-trail blocks excluded by default. |
| `external_signed` | Anyone with the signed link | Heavily redacted. Watermark mandatory. No raw-data tables. |

The same report can be exported with different audience effective rules without copying — the canvas state is unchanged, but the renderer applies audience-specific transforms. A `redacted` flag per data field controls visibility.

### 12.2 Shared link contract

JWT format:
```json
{
  "aud": "share:checkwise:reports",
  "report_id": "...",
  "version_id": "...",
  "audience": "client_facing",
  "exp": 1234567890,
  "iat": 1234567000,
  "jti": "..."
}
```

`jti` corresponds to `report_shares.id`. On every public-link read we look up the share by `jti`, confirm `revoked_at IS NULL` and `expires_at > now()`, then increment `access_count` and update `last_accessed_at`. Token is HS256-signed by the same `AUTH_JWT_SECRET` used elsewhere. Watermark — if set — overlays the user-facing copy with the configured string (e.g., "Borrador — no distribuir").

## 13. API surface

| Method + path | Purpose | Body / response |
|---|---|---|
| `POST /api/v1/reports` | Create empty report. | `{title, audience, scope}` → `{id}` |
| `GET /api/v1/reports` | List reports visible to caller. | filters + paging → array |
| `GET /api/v1/reports/{id}` | Fetch report + latest version. | → `{report, version}` |
| `PATCH /api/v1/reports/{id}` | Update metadata (title, audience, status). | partial fields |
| `GET /api/v1/reports/{id}/versions` | Version history. | array of summaries |
| `GET /api/v1/reports/{id}/versions/{n}` | Specific version. | full version |
| `POST /api/v1/reports/{id}/versions` | Manual save with optional label. | `{label?}` → `{version_id, version_number}` |
| `POST /api/v1/reports/{id}/generate` | **SSE.** Generate new version from prompt. | `{prompt, attached_turn_id?}` → SSE stream |
| `POST /api/v1/reports/{id}/conversation` | **SSE.** Send a chat turn; copilot returns plan/patch/text. | `{prompt}` → SSE stream |
| `GET /api/v1/reports/{id}/conversation` | Replay conversation. | array |
| `POST /api/v1/reports/{id}/blocks/{block_id}/regenerate` | **SSE.** Regenerate one block's ai_summary. | → SSE stream |
| `POST /api/v1/reports/{id}/exports` | Request export. | `{format}` → `{export_id, status}` |
| `GET /api/v1/exports/{id}` | Poll export status / download. | metadata + redirect |
| `POST /api/v1/reports/{id}/shares` | Create signed link. | `{audience, expires_at, watermark?, password?}` → `{token, url}` |
| `DELETE /api/v1/reports/{id}/shares/{share_id}` | Revoke link. | 204 |
| `GET /api/v1/shared/{token}` | **Public.** Read shared report. | report + version (audience-filtered) |

All except `/shared/{token}` require auth. `/generate`, `/conversation`, `/regenerate` are SSE; the rest are JSON.

## 14. Frontend route map

| Route | Purpose |
|---|---|
| `/portal/reports` | List view for providers. Existing scaffold absorbed; "New report" replaces the disabled "Generar reporte personalizado" button. |
| `/portal/reports/new` | Chat-first creation flow. |
| `/portal/reports/[id]` | Editor canvas + right-rail copilot. |
| `/portal/reports/[id]/print` | Print-only layout for browser-PDF export. |
| `/portal/reports/[id]/present` | Presentation mode. |
| `/admin/reports` | Internal-staff list across all workspaces. |
| `/admin/reports/[id]` | Same editor, internal-only audience defaults. |
| `/client/reports` | Client-portfolio list (client_admin only). |
| `/client/reports/[id]` | Editor with `client_facing` defaults. |
| `/shared/[token]` | Public read-only surface. Outside the standard shells. |

All editor routes share one canvas component. Audience defaults differ by entry route; the underlying entity is the same.

## 15. Component inventory (Phase 3.2 baseline)

`apps/web/components/checkwise/reports/`:

- `Canvas.tsx` — BlockNote shell + custom block specs
- `ChatCopilot.tsx` — right-rail copilot
- `PlanCard.tsx` — inline plan preview in chat
- `PatchCard.tsx` — inline patch preview in chat
- `BlockHeader.tsx` — shared block chrome: title, actions, AI pill, lock toggle
- `BlockInspector.tsx` — right-rail config editor
- `Toolbar.tsx` — page-level toolbar (share, export, version history)
- `VersionHistoryDrawer.tsx` — left-side drawer
- `blocks/` — one file per registered block (see catalog)

## 16. Sub-phase plan (3.0 → 3.7)

| Sub-phase | Branch | Scope | Approx. PR shape |
|---|---|---|---|
| **3.0 — Architecture lock** | `design/reports-architecture` *(this PR)* | This doc + block catalog + roadmap update. No code. | Docs-only |
| **3.1 — Backend foundation** | `feat/reports-backend` | Alembic migrations 0009–0012. SQLAlchemy models. Pydantic schemas. Read + write endpoints (no AI). Tests. | ~30 files, +1.5k lines |
| **3.2 — Canvas + 3 blocks** | `feat/reports-canvas` | BlockNote install. Canvas shell. Registry skeleton. 3 block implementations: `text`, `executive_summary` (static), `vendor_risk_matrix`. List view + editor route, **no AI**. Replaces the disabled button on `/portal/reports`. | ~25 files |
| **3.3 — AI planner + content streaming** | `feat/reports-ai` | Anthropic SDK in backend. Planner with tool-use. SSE generate endpoint. Streaming hook. AI summaries on 3 existing blocks. **AI data-isolation tests.** | ~20 files |
| **3.4 — Chat copilot + refinement** | `feat/reports-copilot` | Right-rail chat UI. Conversation persistence. Patch-card flow. Suggested-prompts chip rail. | ~15 files |
| **3.5 — Editing + autosave + versioning** | `feat/reports-editing` | Inline edits. Inspector panel. Autosave + auto-version rules. Version history drawer. Lock-block. | ~15 files |
| **3.6 — Export pipeline** | `feat/reports-export` | Print route. DOCX export via `python-docx`. Async export job state machine. Presentation mode layout. | ~20 files |
| **3.7 — Sharing + signed links** | `feat/reports-sharing` | `report_shares` migration finalized. Public `/shared/[token]` route. Audience-redacted rendering. Revoke + audit. | ~12 files |

Plus across sub-phases:
- **Block catalog expansion** — start with 3 blocks (3.2), add 4 more in 3.3, full 13 by 3.6.
- **Tests** — backend gauntlet + frontend gauntlet pass per PR, plus AI-specific tests in 3.3 (data isolation, prompt-injection resistance, no-PII-leak).

Each sub-phase is shippable on its own.

## 17. What this spec deliberately does NOT decide

- **Specific copy and prompts.** Drafted in 3.3 against this architecture; finalized through usage.
- **Exact pricing / cost ceilings.** Will need observation in 3.3 → guardrails (rate limit, token cap per report) added in 3.4 if needed.
- **PPTX export.** Deferred. Web presentation mode lands first; native PPTX is a Phase 4+ ask.
- **Real-time multi-user collaboration.** The schema (`report_versions`, `report_conversations`) accommodates it; CRDT layer + presence cursors are explicitly out of scope for v1.
- **Offline editing.** Canvas requires a connection. Future.
- **Mobile editor.** Read-only mobile renderer in v1; full editor is desktop-first.
- **The block catalog text itself.** Lives in [REPORTS_BLOCK_REGISTRY.md](REPORTS_BLOCK_REGISTRY.md). Each block has its own shape commitment there.

## 18. Risks and how we handle them

| Risk | Mitigation |
|---|---|
| LLM hallucinates compliance state | Block content is never generated from "nothing." Every AI summary is grounded in a `compliance_snapshot`. The renderer shows citations + the AI-generated pill. |
| Cross-tenant leakage via LLM | Three layers: pre-fetch ID whitelist, at-fetch tenant filter, post-fetch PII sanitizer. AI-isolation tests in 3.3. |
| Prompt injection from compliance data | Data goes into LLM context as JSON inside a clear delimiter; system prompt explicitly instructs to ignore instructions found in data. We add a `prompt_injection_test` suite. |
| Cost spike | Token caps per generate call, per workspace per day. Caching on the planner. Haiku for content where Sonnet isn't needed. |
| Bundle size from BlockNote | Lazy-load the editor; the list view never loads it. Print + presentation routes use a slimmer renderer. |
| Versions table explosion | Auto-version every 5 min, not every edit. Auto-version GC after 30 days. Manual versions persist. |
| AI text getting confused for canonical data | Storage separation (`ai_summary` field), UI separation (pill + tinted background), audit logging (`llm_metadata` on every version). |
| BlockNote opinionation conflicts with our model | We adopt BlockNote for its container + dnd + slash menu. Compliance blocks are "atomic" custom blocks, internals rendered by our code. Worst case we replace the container in v2 without rewriting the blocks. |

## 19. Verification gates (each sub-phase)

- Token contract / no raw hex / no anti-pattern (per VISUAL_DIRECTION_2_X.md).
- Backend gauntlet (`ruff`, `pytest`) green.
- Frontend gauntlet (`tsc --noEmit`, `next lint`, `next build`) green.
- Tenant-isolation test added for every new endpoint touching compliance data.
- For 3.3+: AI-isolation tests (no cross-tenant data in LLM context), prompt-injection suite green, cost-per-report telemetry recorded.

## 20. Status — Phase 3 closed

- Phase 3.0 — architecture locked (`02fa193`).
- Phase 3.1 — backend foundation merged (`8295024`). 6 tables, 7 CRUD endpoints, tenant isolation tested.
- Phase 3.2 — canvas + 5 blocks merged (`79ca440`). Frontend block registry + editor route + list rewrite.
- Phase 3.3a — AI planner + tenant-safe context merged (`a27c97a`). LLM client abstraction (Anthropic + deterministic mock), Context Assembler with PII sanitizer + snapshot writer, Planner service with tool-use, `POST /reports/{id}/plan`. **6 explicit safety scenarios tested.**
- Phase 3.3b — streaming execution pipeline + AI-aware blocks merged (`330b5e2`). Per-block data fetchers + AI summary generators, executor with per-block PII redaction, `POST /reports/{id}/generate` SSE, `ai_recommendation` block. End-to-end browser-verified (14-event sequence, persisted v2 with full provenance).
- **Phase 3.3c — embedded copilot + per-block actions + print mode** *(this PR — Phase 3 final)*. Right-rail chat copilot bound to one report, `report_conversations` persistence, refinement messages, suggested-prompts chip rail, per-block Regenerate + Explain actions, print-mode route at `/portal/reports/[id]/print` for executive-grade PDF via browser print.

**Phase 3 v1 closes after 3.3c merges.** The Reports module is now a living, AI-orchestrated compliance-intelligence workspace.

## 21. Deferred to a 2.2 production-polish track

The architecture spec named 14 block types + several v1 cuts that are deliberately out of scope for Phase 3 v1 because they're production polish, not core workflow:

| Deferred | Reason | Future home |
|---|---|---|
| Server-rendered DOCX export | Needs `python-docx` + async worker | 2.2 |
| Server-rendered PDF export | Print-mode already gives Cmd+P → PDF; server PDF needs Puppeteer or similar | 2.2 |
| Signed-link sharing (`/shared/[token]`) | Tables exist (`report_shares`); needs JWT + audience-redacted public route | 2.2 |
| Autosave + version-history drawer | Manual save works; autosave is polish | 2.2 |
| Inspector panel (config edits) | Inline block configs work today via small per-block hooks | 2.2 |
| Patch-card chat flow (copilot mutates canvas) | Today the copilot suggests, the user inserts from palette | 2.2 |
| 8 remaining block types from §15 | `compliance_heatmap`, `missing_documents`, `timeline`, `regulatory_status`, `exception_list`, `audit_trail`, `chart`, `evidence_attachment`, `vendor_comparison_table` | 2.2 or 2.3 |

None of these change the architectural contract — they extend it. Each can ship independently against the existing trust boundaries.

## 22. R1.0 — Role-aware reports surface (2026-05-18)

R1.0 turns Reports from a single provider-portal page into a role-aware intelligence layer with shared backend infrastructure.

### Role × audience matrix

| Membership role | Visible audiences (read) | Writable audiences (create / patch) |
|---|---|---|
| `internal_admin`, `reviewer` | all 4 | all 4 |
| `client_admin` | `client_facing` only | `client_facing` only |
| (no recognised role) | none — default-deny | none |

Source of truth: `visible_audiences()` and `writable_audiences()` in `apps/api/app/services/report_service.py`. The list endpoint intersects with `visible_audiences`; create + patch reject audiences outside `writable_audiences`; `get_report` returns 404 (not 403) for forbidden audiences to avoid id enumeration.

Vendor users are intentionally absent from the matrix in R1.0. Vendors do not hold a `User` row — they authenticate via `X-Workspace-Token` on the upload-flow portal. Vendor-targeted reports are delivered via the existing `external_signed` audience (Phase 2.2 share-link work).

### Preset registry

`apps/api/app/services/reports/templates.py` defines `ReportPreset` — a starting point for a report: title, description, audience, `required_roles`, and `recommended_prompt`. R1.0 ships three internal-only presets:

- `admin-daily-queue` — operational triage for the review team
- `admin-high-risk-vendors` — cross-vendor risk matrix
- `admin-monthly-operational` — monthly compliance overview

API surface:

```
GET  /api/v1/reports/_presets           # role-filtered list
POST /api/v1/reports/from-preset        # create + seed v1 from a preset
```

`from-preset` does **not** run AI generation at creation time. It creates a report with the preset's metadata and parks `recommended_prompt` on `content_json.global.recommended_prompt`. The editor reads that on first load and pre-fills + auto-opens the AI prompt panel, so "Use template" → Enter is a one-click flow without coupling preset creation to a streaming generation endpoint.

### Route surface

```
/admin/reports                          R1.0 — list + preset gallery for internal team
/admin/reports/[id]                     R1.0 — redirects to /portal/reports/[id]
/portal/reports                         existing — kept running unchanged
/portal/reports/[id]                    existing — editor (reads preset hint from global)
/client/reports                         R1.1 — not shipped
/share/r/[token]                        R1.2 — external_signed delivery, not shipped
```

The editor lives at exactly one place (`/portal/reports/[id]`) to avoid duplicating the 500-line surface. The shared-editor extraction is deferred to R1.0.1 once the admin surface proves itself.

### What is intentionally *not* in R1.0

- No client_admin presets — those land with R1.1 alongside the `/client/reports` surface.
- No new block types — the existing 6 cover all three presets.
- No interactive filters beyond audience + status — those land in R2.
- No automatic post-creation AI generation — kept as a manual click in the editor.
- No share-link delivery for vendors — deferred to R1.2.
- No shared editor component — the admin editor route redirects to the portal one.

R1.0 is the foundation. R1.1 (client surface) and R1.2 (vendor signed-link delivery) build directly on top without re-touching the permission helpers or the preset registry shape.

## 23. R1.1 — Client preset gallery (2026-05-18)

R1.1 closes the second of the three role-aware surfaces. `client_admin`
users now have a parallel preset experience to what `internal_admin`
got in R1.0. No new auth, no new schema, no new block types — purely
content + a new shell entry.

### New presets

Three `client_facing` presets in `apps/api/app/services/reports/templates.py`:

- `client-monthly-executive` — Resumen ejecutivo mensual
- `client-vendor-risk-matrix` — Matriz de riesgo de proveedores
- `client-missing-evidence` — Documentos faltantes por proveedor

Each declares `required_roles=(CLIENT_ADMIN, INTERNAL_ADMIN)`. Internal staff can author from client presets on behalf of a client; client_admins can only see and use these three (the 3 admin presets stay invisible to them).

### Auto-resolve client_id

`client_facing` presets require a `client_id` per the existing `_validate_scope` rule. The `POST /api/v1/reports/from-preset` endpoint now:

- For `client_admin` callers: auto-resolves `client_id` from the caller's `client_admin` membership (joins `Membership` → `Organization` and picks `Organization.client_id`).
- For `internal_admin` staff using a client preset: requires `client_id` in the request body.

`CreateFromPresetRequest` accepts optional `client_id` and `vendor_id` so the body path stays open for either role.

### New routes

```
/client/reports                         R1.1 — list + preset gallery for client_admin
/client/reports/[id]                    R1.1 — redirects to /portal/reports/[id]
```

The `ClientShell` nav gets a `Reportes` entry with `ChartLineUp` between `Entregas` and `Actividad`.

### What R1.1 does NOT ship

- No new block types.
- No shared editor component — `/client/reports/[id]` redirects to `/portal/reports/[id]` (R1.0.1 still pending).
- No interactive filters (R2).
- No vendor surface or signed-link delivery (R1.2).

After R1.1 the three-role promise is 2/3 fulfilled at the surface level:

| Role | Reports surface |
|---|---|
| internal_admin / reviewer | `/admin/reports` (R1.0) ✓ |
| client_admin | `/client/reports` (R1.1) ✓ |
| Provider (no user account) | `external_signed` signed-link delivery (R1.2 — not yet shipped) |

## 24. R2 — Interactive list filters + shared list view (2026-05-18)

R2 makes the role-aware list pages actually queryable instead of "everything visible to me." It also retires the near-duplicate admin / client list pages from R1.0 + R1.1 into a single shared component.

### What ships

**Backend (additive — no schema change):**

`GET /api/v1/reports` accepts a new optional `audience` query param (a `ReportAudience` enum value). The service layer's `list_reports()` takes an optional `audience` argument and uses it like so:

```python
allowed = visible_audiences(actor)
if not allowed:
    return [], 0
if audience is not None:
    if audience not in allowed:
        return [], 0           # forbidden → empty list, NOT 403
    stmt = stmt.where(Report.audience == audience.value)
else:
    stmt = stmt.where(Report.audience.in_([a.value for a in allowed]))
```

The `audience not in allowed → return [], 0` branch is intentional: a `client_admin` who asks for `?audience=internal_only` receives an empty page, not a `403`. This mirrors the not-found semantics elsewhere in the router (`get_report` returns `404` for forbidden-audience reads) so that the response shape never leaks the existence of internal_only rows that an unauthorised caller cannot see.

The existing `?status=` param continues to work; it composes cleanly with `?audience=` via SQL `AND`.

**Frontend:**

A new shared component at `apps/web/components/checkwise/reports/list/reports-list-view.tsx` owns the entire list body: preset gallery, filter bar, report table, empty state. It takes:

```ts
interface ReportsListViewProps {
  role: "admin" | "client" | "portal";
  editorHrefBase: string;          // "/admin/reports" or "/client/reports"
  presetCreateRedirectBase: string; // same shape — preset → editor
  eyebrowDescription: string;
  showAudienceFilter?: boolean;    // admin only
}
```

`apps/web/app/admin/reports/page.tsx` and `apps/web/app/client/reports/page.tsx` are now thin `unframed` shell wrappers (~25 LOC each) around this component. `/portal/reports` still uses its V2.1 implementation in R2 — migration is part of the proposed P1 (Provider-first Reports) slice.

### Filter UX

| Filter | Mechanism | Why |
|---|---|---|
| Title search | client-side substring, instant | typing has to feel instant; the page only holds up to 100 rows anyway |
| Estado | server-side via `?status=` | composes with pagination |
| Audiencia | server-side via `?audience=` (admin only) | composes with pagination; client_admins only see one audience so the filter would be a no-op |
| Limpiar | resets all three to default | only visible when any filter is active |
| Empty state | branches on `hasActiveFilter` | the "no reports yet" copy and the "no reports match" copy say different things and offer the right CTA |

The dropdowns are native `<select>` elements. No new dependency, full keyboard + a11y semantics for free, looks the same as every other form input in the codebase.

### Security boundary

The R2 filter does **not** weaken any existing audience boundary. Every layer still enforces `visible_audiences(actor)`:

1. The default-branch SQL clause (`Report.audience IN (visible_audiences)`) keeps the list scoped to what the actor can see when no filter is supplied.
2. The filter branch first checks `audience not in allowed → return [], 0` before adding the equality clause.
3. `get_report()` independently rejects forbidden-audience reads with a `404` — id enumeration of internal_only or vendor_facing reports is impossible.

Three tests in `apps/api/tests/test_reports_presets.py` lock this behavior in:

- `test_list_audience_filter_admin_narrows_to_one` — happy path.
- `test_list_audience_filter_client_admin_requesting_forbidden_returns_empty` — the security-critical case. Admin seeds an internal_only report **inside the client_admin's own org**; client_admin's call with `?audience=internal_only` returns `{"items": [], "total": 0}`.
- `test_list_status_filter_narrows_correctly` — orthogonal `status` partitioning.

### What R2 does NOT ship

- No date-range filter.
- No vendor / client selector dropdown.
- No URL-persisted filter state.
- No filters on `/portal/reports` (still uses the V2.1 implementation; migration is part of P1).
- No new audience values; no new presets; no new block types; no schema change.

After R2, the role-aware promise of Reports is structurally complete for admin and client_admin but still empty for the provider — the seeded vendor-facing reports cannot be reached because role-less actors' `visible_audiences()` returns `()`. That gap is the entire scope of P1 (Provider-first Reports), not part of R2.

## 25. P1 — Provider-first Reports (2026-05-18)

P1 makes the provider — the role most central to CheckWise's product story — a first-class Reports user. After P1, the three-role promise is structurally complete: admin, client_admin, and the role-less provider each have a populated list, a role-appropriate preset gallery, and an editor that mounts inside their own shell.

### Workspace-derived visibility (no new MembershipRole)

`ProviderWorkspace.owner_user_id` is already the authoritative link from a `User` to a `vendor_id` + `client_id`. P1 reuses that link instead of introducing a `vendor` membership role — keeping the role vocabulary stable and the single source of provider identity in `ProviderWorkspace`.

The `ReportActor` dataclass gains two optional fields:

```python
@dataclass(frozen=True)
class ReportActor:
    user_id: str
    organization_ids: tuple[str, ...]
    roles: tuple[str, ...]
    workspace_vendor_id: str | None = None  # P1
    workspace_client_id: str | None = None  # P1

    @property
    def is_workspace_owner(self) -> bool:
        return not self.roles and self.workspace_vendor_id is not None
```

`_actor_from(current, db)` in `api/v1/reports.py` does **one** extra SQL hit when the caller has no roles: look up their `ProviderWorkspace` and, when present, also fetch the matching client `Organization` so `create_report`'s owning-org resolution still works.

### Visibility / writability matrix update

| Actor shape | Visible audiences |
|---|---|
| `internal_admin` / `reviewer` | all 4 (unchanged) |
| `client_admin` | `(client_facing,)` (unchanged) |
| **role-less + `workspace_vendor_id` set** | **`(vendor_facing,)`** ← P1 |
| role-less + no workspace | `()` (default-deny, unchanged) |

The default branch of `list_reports()` (when no explicit audience filter is supplied) still uses `Report.audience IN (visible_audiences)`. For workspace-owners it adds **one more** WHERE clause: `Report.vendor_id == actor.workspace_vendor_id`. Cross-vendor reads return empty / 404, not 403, mirroring the not-found semantics already in place.

### Three provider presets

`apps/api/app/services/reports/templates.py`:

- `provider-current-state` — *Mi estado de cumplimiento*
- `provider-missing-documents` — *Documentos faltantes*
- `provider-recent-rejections` — *Rechazos recientes*

Each declares `required_roles=()` — an empty tuple. The matching rule in `presets_for_roles()` is extended:

```python
def presets_for_roles(roles, *, is_workspace_owner=False):
    return tuple(
        p for p in PRESETS
        if (
            (p.required_roles and held.intersection(...))     # legacy role branch
            or (not p.required_roles and is_workspace_owner)  # P1 branch
        )
    )
```

An empty-`required_roles` preset is **only** included when `is_workspace_owner` is true. Admin and client_admin keep seeing exactly the presets they saw in R1.0 + R1.1 — locked in by the `test_admin_sees_all_nine_presets_after_p1` and `test_client_admin_still_sees_only_client_presets_after_p1` regression tests.

### `from-preset` auto-resolve for `vendor_facing`

`CreateFromPresetRequest` already carried optional `client_id` / `vendor_id` from R1.1. P1 adds a branch in `post_from_preset`:

```python
elif preset.audience == ReportAudience.VENDOR_FACING:
    if vendor_id is None and actor.workspace_vendor_id is not None:
        vendor_id = actor.workspace_vendor_id
    if client_id is None and actor.workspace_client_id is not None:
        client_id = actor.workspace_client_id
```

The `_validate_scope` rule (audience ≠ `internal_only` requires at least one of `client_id`/`vendor_id`) is satisfied via the auto-fill. Internal staff using a provider preset must pass `vendor_id` explicitly in the body — they have no implicit anchor.

### Frontend

`apps/web/app/portal/reports/page.tsx` is collapsed from the V2.1 inline-create implementation to a thin `PortalAppShell` wrapper around `<ReportsListView role="portal">`. The provider gets for free:

- The 3 vendor-facing preset cards
- The R2 filter bar (search + Estado; Audiencia hidden — provider sees only one audience)
- The shared empty-state / filter-clear behavior
- Visual consistency with `/admin/reports` and `/client/reports`

The editor route `/portal/reports/[id]` is unchanged — it already used the shared `<ReportEditor>` from R1.0.1.

### Seed adjustment

`apps/api/scripts/dev_seed.py`:

- Adds an `Organization` (kind=`client`) tied to `BOSS_DEMO_CLIENT_NAME` so `_actor_from`'s workspace → owning-org resolution succeeds for boss.demo.
- Re-audiences the seeded vendor-scoped report from `client_facing` to `vendor_facing` and corrects its `organization_id` + `client_id` to match the boss-client tenant (the previous shape was cross-tenant).

### Tests

`apps/api/tests/test_reports_presets.py` adds **7 new tests** (total now 20):

| Test | Locks in |
|---|---|
| `test_workspace_actor_sees_three_provider_presets_only` | the workspace-owner branch returns exactly 3 vendor_facing presets |
| `test_workspace_actor_from_preset_auto_resolves_vendor_and_client` | auto-fill of vendor_id + client_id from the workspace |
| `test_workspace_actor_list_only_returns_own_vendor` | cross-vendor isolation — provider A cannot see vendor B's report even when sharing a client |
| `test_workspace_actor_cannot_read_client_facing` | audience boundary holds — same-vendor client_facing report still 404 for provider |
| `test_workspace_actor_admin_preset_forbidden` | provider asking for admin/client preset → 403 |
| `test_client_admin_still_sees_only_client_presets_after_p1` | regression guard |
| `test_admin_sees_all_nine_presets_after_p1` | regression guard — admin still sees exactly 6, not 9 |

### Three-role promise — fully closed

| Role | List | Editor | Filters | Presets |
|---|---|---|---|---|
| internal_admin / reviewer | ✅ /admin/reports | ✅ AdminShell | ✅ status + audience + search | ✅ 3 |
| client_admin | ✅ /client/reports | ✅ ClientShell | ✅ status + search | ✅ 3 |
| **role-less provider** | **✅ /portal/reports** | **✅ PortalAppShell** | **✅ status + search** | **✅ 3** |

### What P1 deliberately does NOT ship

- No new `MembershipRole`. Provider identity stays in `ProviderWorkspace`.
- No `external_signed` signed-link delivery for vendors without user accounts (R1.2).
- No PDF/DOCX export.
- No new block types.
- No new schema, migrations, or columns.
- No redesign.
- No changes to the upload / onboarding flow.

What it requires from the operator: re-run `scripts/dev_seed.py` once to pick up the seed changes (boss client gets an Organization; the seeded vendor report flips to `vendor_facing`).
