# Reports Block Registry — Catalog

Status: **Phase 3.0 deliverable.** Companion to [REPORTS_ARCHITECTURE.md](REPORTS_ARCHITECTURE.md).
Locked: 2026-05-17.

Each block is a typed JSON object the LLM planner can compose into a report. This doc is the source of truth for what's available, what each block contains, and what the LLM is told about it.

## Conventions

- **`type`** is the discriminant. Stable. Adding a block = appending a new type. Removing a block requires a migration plan.
- **`config`** is user-editable. Survives version-to-version.
- **`data`** is server-fetched. Refreshed when config changes or on explicit refresh.
- **`ai_summary`** is LLM-generated. Optional per block; some blocks are data-only.
- **`audience`** governs which fields render: every PII-tagged field is dropped in `client_facing` / `vendor_facing` / `external_signed`.

Each entry below names:
- **Purpose** — one-line intent
- **Config** — user-editable shape
- **Data** — server-returned shape
- **AI summary** — does this block carry LLM commentary?
- **Audiences** — where it's allowed to render
- **LLM hint** — the description the planner sees
- **Example configs** — few-shot for the planner

---

## Layout primitives

### `text`

**Purpose** — Free-form intro paragraphs, transitions, commentary written by the user or the LLM.

**Config**
```typescript
{ heading?: string; }
```

**Data** — none (`null`).

**AI summary** — yes, this is where the LLM puts standalone commentary that doesn't belong to any data block.

**Audiences** — all.

**LLM hint** — *"Free-form paragraph block. Use sparingly between data blocks to set up context or close with takeaways."*

---

### `divider`

**Purpose** — Visual section break.

**Config** — `{ label?: string }` (optional eyebrow above the line).

**Data** — none.

**AI summary** — no.

**Audiences** — all.

---

## Executive layer

### `executive_summary`

**Purpose** — The cover paragraph. Sets context for the entire report in 3-4 sentences. First block by convention.

**Config**
```typescript
{
  focus: 'compliance' | 'risk' | 'expediente' | 'audit' | 'custom';
  custom_prompt?: string;          // when focus = 'custom'
  include_metrics: boolean;        // render a compact metric strip below the paragraph
}
```

**Data**
```typescript
{
  period_label: string;            // "Mayo 2026"
  scope_label: string;             // "Distribuidora Nogal · 4 obligaciones"
  headline_metrics: {              // shown if include_metrics
    completion_pct: number;
    vendors_at_risk: number;
    submissions_in_review: number;
    next_critical_deadline: string | null;
  };
}
```

**AI summary** — yes (the body paragraph itself).

**Audiences** — all (PII fields scrubbed for external).

**LLM hint** — *"Open the report. State period + scope. Name the headline number. Name what's at risk. Three to four sentences, executive-grade, Spanish."*

**Example configs**
- `{ focus: 'compliance', include_metrics: true }` — for "monthly summary"
- `{ focus: 'risk', include_metrics: true }` — for "providers at risk"
- `{ focus: 'audit', include_metrics: false }` — for "audit trail" deep-dives

---

### `ai_recommendation`

**Purpose** — A standalone "next 3 actions" block. Reads other blocks in the same report and proposes prioritized actions.

**Config**
```typescript
{
  based_on: string[];              // block IDs this recommendation should reason from
  priority_count: number;          // default 3
  audience_tone: 'internal' | 'client' | 'vendor';
}
```

**Data**
```typescript
{
  upstream_block_summaries: Array<{ block_id: string; type: string; key_metric: unknown }>;
}
```

**AI summary** — yes — the entire content is LLM-generated.

**Audiences** — all. The `audience_tone` modulates the language: internal is direct, client is consultative, vendor is instructive.

**LLM hint** — *"Read the upstream block summaries. Propose N prioritized actions, each with: (1) who should act (2) what they should do (3) by when (4) why it matters. Spanish. No filler."*

---

## Vendor / portfolio layer

### `vendor_risk_matrix`

**Purpose** — The flagship matrix: rows are vendors, columns are institutions/requirements, cells are status + age. The most common block in any portfolio report.

**Config**
```typescript
{
  filter: {
    missing_institution?: 'sat' | 'imss' | 'infonavit' | 'stps_repse';
    status?: DocumentStateCode[];
    min_risk_score?: number;
  };
  columns: Array<'sat' | 'imss' | 'infonavit' | 'stps_repse' | 'risk_score' | 'last_event'>;
  sort: 'risk_desc' | 'risk_asc' | 'name';
  max_rows: number;
}
```

**Data**
```typescript
{
  rows: Array<{
    vendor_id: string;
    vendor_name: string;
    vendor_rfc: string;            // PII — scrubbed for external
    risk_score: number;            // 0-100, derived
    cells: Record<string, { state: DocumentStateCode; age_days: number; period: string }>;
    last_event_at: string;
  }>;
  totals: Record<string, Record<DocumentStateCode, number>>;  // column → state → count
}
```

**AI summary** — optional. When present: "3 vendors carry SAT risk; Distribuidora Nogal is the worst at 84 days overdue."

**Audiences** — all. PII scrubbed for non-internal.

**LLM hint** — *"Cross-vendor portfolio view. Use when the request mentions multiple vendors or 'todos los proveedores'. Filter by institution if specified. Default columns: sat, imss, infonavit, stps_repse, risk_score."*

**Example configs**
- *"providers missing SAT"* → `{ filter: { missing_institution: 'sat' }, columns: ['sat', 'imss', 'infonavit', 'risk_score'], sort: 'risk_desc', max_rows: 50 }`
- *"high-risk this quarter"* → `{ filter: { min_risk_score: 60 }, columns: ['sat','imss','infonavit','stps_repse','risk_score'], sort: 'risk_desc', max_rows: 25 }`

---

### `vendor_comparison_table`

**Purpose** — Side-by-side comparison of a *small* set of named vendors. Used when the request names specific vendors.

**Config**
```typescript
{
  vendor_ids: string[];            // exactly 2–5
  dimensions: Array<'completion_pct'|'overdue_count'|'days_since_last_submission'|'in_review_count'|'rejection_rate'|'avg_review_time'>;
}
```

**Data**
```typescript
{
  vendors: Array<{ vendor_id: string; vendor_name: string; dimensions: Record<string, number> }>;
}
```

**AI summary** — optional.

**Audiences** — internal_only, client_facing (for vendors in the client's scope).

---

### `compliance_heatmap`

**Purpose** — Time-by-institution heatmap. Rows are institutions, columns are months/periods, cells are aggregate compliance %.

**Config**
```typescript
{
  vendor_ids?: string[];           // omit = all in scope
  institutions: string[];
  periods: string[];               // e.g., ['2026-M01' ... '2026-M05']
  metric: 'completion_pct' | 'on_time_pct' | 'submission_count';
}
```

**Data**
```typescript
{
  cells: Array<{ institution: string; period: string; value: number; sample_size: number }>;
}
```

**AI summary** — optional ("STPS coverage dropped from 92% to 71% between March and May").

**Audiences** — all.

---

## Period-by-period layer

### `missing_documents`

**Purpose** — Explicit list of what's missing, by period and institution. Operationally the most actionable block.

**Config**
```typescript
{
  period: string;
  institutions?: string[];
  vendor_ids?: string[];
  include_optional: boolean;        // include non-mandatory items
  group_by: 'vendor' | 'institution' | 'requirement';
}
```

**Data**
```typescript
{
  groups: Array<{
    label: string;
    items: Array<{
      vendor_id: string;
      vendor_name: string;
      institution: string;
      requirement_code: string;
      requirement_label: string;
      mandatory: boolean;
      days_overdue: number;
      assignee_user_id: string | null;
      last_event: string | null;
    }>;
  }>;
  total_missing: number;
}
```

**AI summary** — optional ("14 mandatory documents missing across 3 vendors. Critical: 2 SAT acuses for Distribuidora Nogal.").

**Audiences** — all.

**LLM hint** — *"List of mandatory documents not yet submitted for the period. Use when the request mentions 'falta', 'pendiente', 'missing'. Default group_by to 'vendor' unless request implies otherwise."*

---

### `timeline`

**Purpose** — Chronological event log for a single vendor or a small set. Useful for incident reports and audit trails.

**Config**
```typescript
{
  vendor_ids?: string[];
  event_types?: Array<'submission'|'review'|'approval'|'rejection'|'correction'|'exception'|'reminder'|'login'>;
  since: string;                    // ISO
  until: string;
  max_events: number;
}
```

**Data**
```typescript
{
  events: Array<{
    timestamp: string;
    vendor_id: string | null;
    actor: string;                  // "Ada Lovelace · Reviewer" or "Sistema" 
    event_type: string;
    summary: string;
    details_href: string | null;
  }>;
}
```

**AI summary** — optional ("Three corrections requested within 48 hours signal review fatigue on this vendor").

**Audiences** — internal_only (default); client_facing if vendor_ids belong to client's scope.

---

## Regulatory / audit layer

### `regulatory_status`

**Purpose** — Top-level "are we compliant?" panel per institution.

**Config**
```typescript
{
  vendor_ids?: string[];            // omit = portfolio-level
  institutions: string[];
  reference_period: string;
}
```

**Data**
```typescript
{
  institutions: Array<{
    code: string;
    label: string;                  // "SAT", "IMSS"
    status: 'compliant' | 'partial' | 'at_risk' | 'non_compliant';
    completion_pct: number;
    next_obligation: { code: string; label: string; due_date: string } | null;
    blocking_items: number;
  }>;
}
```

**AI summary** — optional.

**Audiences** — all.

---

### `exception_list`

**Purpose** — Documents in `requiere_aclaracion` or `posible_mismatch` state — the "things that need a human decision" list.

**Config**
```typescript
{
  vendor_ids?: string[];
  include_states: Array<'requiere_aclaracion'|'posible_mismatch'|'rechazado'>;
  since: string;
}
```

**Data**
```typescript
{
  exceptions: Array<{
    submission_id: string;
    vendor_id: string;
    vendor_name: string;
    requirement_label: string;
    period: string;
    state: string;
    reviewer_note: string | null;
    raised_at: string;
    age_days: number;
  }>;
}
```

**AI summary** — optional.

**Audiences** — internal_only; vendor_facing if filtered to the vendor's own submissions.

---

### `audit_trail`

**Purpose** — Append-only event log scoped to a vendor + period. The "what happened, when, by whom" surface required for regulatory audits.

**Config**
```typescript
{
  vendor_id: string;
  period: string;
  include_internal_events: boolean;  // login, system housekeeping
}
```

**Data**
```typescript
{
  events: Array<{
    timestamp: string;
    actor: string;
    action: string;
    target_kind: string;
    target_id: string;
    diff_json: object | null;
  }>;
  hash_chain_anchor: string;          // tamper-evident anchor for the period
}
```

**AI summary** — no. Audit trails must not be paraphrased — paraphrased compliance evidence is worthless.

**Audiences** — internal_only, external_signed (for regulator-facing reports). Never `client_facing` by default — internal events leak.

**LLM hint** — *"Tamper-evident event log. The LLM never summarizes this content. Include when the request mentions 'auditoría', 'auditable', 'eventos', 'historial completo'. Pair with executive_summary that explains why an audit was conducted."*

---

## Data viz layer

### `kpi_strip`

**Purpose** — A horizontal strip of 4–6 metrics. The metadata strip pattern from VISUAL_DIRECTION_2_X.md, in block form.

**Config**
```typescript
{
  metrics: Array<{
    label: string;                  // user-editable label
    metric_key: 'completion_pct'|'vendors_total'|'vendors_at_risk'|'submissions_period'|'overdue_count'|'in_review_count'|'approved_pct'|'avg_review_hours'|'days_to_next_deadline';
    format: 'percent'|'number'|'duration_days'|'duration_hours';
  }>;
  period?: string;
}
```

**Data**
```typescript
{
  resolved: Array<{ metric_key: string; value: number; trend_pct_vs_prior: number | null }>;
}
```

**AI summary** — no — the values speak.

**Audiences** — all.

---

### `chart`

**Purpose** — A configurable chart using the existing inline-SVG primitives (`Donut`, `StackedBars`, `Sparkline`, `MiniBars`, `RadialGauge`).

**Config**
```typescript
{
  kind: 'donut' | 'stacked_bars' | 'sparkline' | 'mini_bars' | 'radial_gauge';
  title: string;
  query: {                          // structured query into compliance data
    metric: string;
    group_by?: string;
    filter?: object;
    period?: string;
  };
}
```

**Data**
```typescript
{
  series: Array<{ label: string; value: number; tone: ChartTone }>;
  total?: number;
}
```

**AI summary** — optional.

**Audiences** — all.

**LLM hint** — *"Use for visual emphasis. donut for proportions, stacked_bars for category breakdowns, sparkline for trend, radial_gauge for a single percentage anchor."*

---

## Evidence layer

### `evidence_attachment`

**Purpose** — Link to (or embedded thumbnail of) a specific document submission. Used in audit reports and evidence packages.

**Config**
```typescript
{
  submission_id: string;
  show_thumbnail: boolean;
  show_metadata: boolean;          // hash, page count, MIME, size
}
```

**Data**
```typescript
{
  vendor_name: string;
  requirement_label: string;
  period: string;
  uploaded_at: string;
  reviewed_at: string | null;
  state: string;
  storage_thumbnail_url: string | null;
  storage_metadata: {
    sha256: string;
    mime_type: string;
    bytes: number;
    page_count: number | null;
  };
  download_href: string;            // signed URL valid for the audience
}
```

**AI summary** — no.

**Audiences** — all that have access to the underlying submission.

---

## Block summary table

| Type | AI summary | Default audiences | Phase introduced |
|---|---|---|---|
| `text` | yes | all | 3.2 |
| `divider` | no | all | 3.2 |
| `executive_summary` | yes | all | 3.2 |
| `vendor_risk_matrix` | optional | all | 3.2 |
| `ai_recommendation` | yes (whole block) | all | 3.3 |
| `vendor_comparison_table` | optional | internal/client | 3.3 |
| `compliance_heatmap` | optional | all | 3.3 |
| `missing_documents` | optional | all | 3.3 |
| `timeline` | optional | internal/client | 3.6 |
| `regulatory_status` | optional | all | 3.6 |
| `exception_list` | optional | internal/vendor | 3.6 |
| `audit_trail` | **no** | internal/external | 3.6 |
| `kpi_strip` | no | all | 3.2 |
| `chart` | optional | all | 3.6 |
| `evidence_attachment` | no | all | 3.6 |

**v1 launch set (Phase 3.2):** `text`, `divider`, `executive_summary`, `vendor_risk_matrix`, `kpi_strip`. Five blocks. Enough to demonstrate the architecture and ship the canvas.

**v2 set (Phase 3.3):** add `ai_recommendation`, `vendor_comparison_table`, `compliance_heatmap`, `missing_documents`. Nine total. First version with full AI orchestration.

**v3 set (Phase 3.6):** add `timeline`, `regulatory_status`, `exception_list`, `audit_trail`, `chart`, `evidence_attachment`. Fourteen total. Catalog complete for the 2.x scope.

## Adding a new block

1. Declare the type, config schema, data schema in this doc.
2. Add the backend module under `apps/api/app/services/reports/blocks/<type>.py` with `fetch_data` + `render_docx` + `render_ai_summary` (or none).
3. Add the frontend module under `apps/web/components/checkwise/reports/blocks/<type>.tsx` exporting the `BlockDefinition`.
4. Register in `apps/web/lib/reports/registry.ts` and `apps/api/app/services/reports/registry.py`.
5. Add at least one example config + one few-shot prompt example.
6. Write tenant-isolation tests for the new data_fetcher.
7. Ship behind a feature flag if the block is experimental.
