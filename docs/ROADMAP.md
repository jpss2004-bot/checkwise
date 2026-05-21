# Roadmap

## Done

### V1.0 — Foundation

- Monorepo: frontend, backend, local DB, docs.
- Versioned regulatory model.
- Initial document-intake form.
- Receive-document endpoint with hash + storage-key persistence.
- Objective prevalidations.
- Audit log.

### V1.1 — Native Intake Foundation

- Native upload wizard.
- PDF-only intake with technical inspection.
- Deterministic document signals.
- Traceable validation events.
- Documented JotForm exit strategy.

### V1.2 — Provider Portal

- `/` provider access page (demo, opaque workspace token).
- `/portal/onboarding` — Expediente Corporativo gated by `persona_moral` / `persona_fisica`.
- `/portal/dashboard` — REPSE 2026 calendar (monthly · bimonthly · four-monthly · annual).
- `/portal/upload` — guided 5-step wizard with file preview, SHA-256 duplicate pre-check, and plain-language confirmation.
- `/portal/submissions/[id]` — correction flow for `posible_mismatch` / `requiere_aclaracion`.
- Compliance catalog API (`/api/v1/compliance/*`, `/api/v1/portal/*`).
- `provider_workspaces` table + migration 0003.

### V1.2.1 — Canonical Keys + Catalog Seed

- `requirement_code` and `period_key` end-to-end across submissions, documents, and the wizard.
- Idempotent compliance-catalog seed migration (0005).
- Reconciled bimestral / cuatrimestral / anual periods (fixes a previous 422 on those frequencies).

### V1.2.2 — State & Polish Layer

- Skeleton, empty, error, and not-found surfaces across the portal.

### V1.3 — Real Auth + RBAC

- `User`, `Organization`, `Membership` tables + migration 0006.
- bcrypt + JWT (HS256).
- `require_role`, `require_org_role`, `require_any_role` dependencies.
- Internal-admin / reviewer / (future) client-admin roles.

### V1.4 — Reviewer Queue + Decision Workflow

- `/admin/reviewer` queue ordered by attention.
- `/admin/reviewer/[submission_id]` decision detail.
- 4 decision actions: `approve`, `reject`, `request_clarification`, `mark_exception`.

### V1.4.1 — Brand Application

- Official IMPI palette (`#013557` · `#02558a` · `#09c1b0` · `#4b90a4`).
- Open Sans typography.
- `BrandLogo` component across every shipped surface.

### V1.4.2 — Motion + Plain-Language Polish

- CSS-only motion utilities (`cw-fade-up`, `cw-stagger`, `cw-pulse-soft`, `cw-hover-lift`, `cw-success-ring`, `cw-draw-check`), all guarded by `prefers-reduced-motion`.
- `AnimatedCheck` in the success step of the wizard.
- Plain-language status labels: `Esperando revisión` · `Posible inconsistencia` · `Necesita aclaración`.

### V1.5 — Client Overview ("Patch 8")

Out-of-tenant read-only view for `client_admin`. Shipped.

- `/api/v1/clients/{org_id}/...` endpoints, guarded by `require_org_role("client_admin")`.
- Per-vendor aggregation of `ReviewerDecision` + risk signals.
- `/admin/clients/[organization_id]` route.
- Client dashboard surfaces under `/client/*`.
- Correction-flow links per vendor.

### V1.6 — Workspace Confirmation + Security Hardening

- `/portal/entra-a-tu-espacio` workspace-confirmation gate between auth-success and the rest of the portal.
- `ProtectedFieldNotice` + `CorrectionRequestForm` for locked tenant identifiers.
- `WorkspaceIdentityCard` on the vendor dashboard.
- `blocked` + `unavailable` states added to `/portal/reports`.
- Tenant-isolation rules tightened: backend is the source of truth for every protected field; client-side display values are hints only.
- Full detail: [CHECKWISE_1_6.md](CHECKWISE_1_6.md).

### V2.0 — Unified visual language across portals

Frontend redesign pass that lifts vendor, client, and admin portals onto one component spine. Backend contracts unchanged.

- Shared dashboard primitive family (`StatCard`, `Surface`, `EmptyState`) replaces three drifted `Tile` implementations.
- Inline-SVG chart primitives (`RadialGauge`, `Donut`, `Sparkline`, `MiniBars`, `StackedBars`, `TrendArrow`) — zero external deps, token-bound.
- `PortalAppShell` — sidebar-driven vendor portal chrome.
- `lib/routing/post-login.ts` — centralized post-auth routing decision.
- `lib/api/portal-adapters.ts` — bridge from real backend payloads to UX-curated UI shapes.
- 20 routes redesigned across `/admin/*`, `/client/*`, `/portal/*`.
- Removed: orphan `access-decision-banner.tsx` (referenced a deleted type, zero consumers).
- Full detail: [CHECKWISE_2_0.md](CHECKWISE_2_0.md).

### V2.x — Visual rework + Reports flagship (in progress)

The 2.x track unifies the rework into one release. Five phases.

**Phase 1 — Audit + inspo map** (done, `384177f`)

- Surface-by-surface audit of 12 routes; 7 cross-cutting findings.
- 13 Pinterest inspos tagged ADOPT / TRANSLATE / REJECT.
- 4 public-route current-state PNGs.
- Full detail: [design-system/AUDIT_2_X.md](design-system/AUDIT_2_X.md), [design-system/INSPO_MAP.md](design-system/INSPO_MAP.md).

**Phase 2 — Visual direction lock** (done, `67993aa`)

- Three density tiers (`comfortable` / `dense` / `compact`).
- 8-step type scale, four new utility classes (`.cw-eyebrow`, `.cw-metadata-strip`, `.cw-prose`, `.cw-display`).
- 14 codified anti-patterns; peer-reference set (Vanta / Drata / Mercury / Ramp / Linear / Stripe).
- Anchor spike: `/portal/dashboard` 4-up KPI grid → horizontal metadata strip.
- Full detail: [design-system/VISUAL_DIRECTION_2_X.md](design-system/VISUAL_DIRECTION_2_X.md).

**Phase 3 — Reports flagship** (v1 closed)

Reports evolved into a living, AI-orchestrated compliance-intelligence workspace. Not a PDF exporter.

- 3.0 — Architecture lock (`02fa193`)
- 3.1 — Backend foundation: 6 tables, 7 CRUD endpoints, tenant isolation (`8295024`)
- 3.2 — Canvas + 5 base blocks: text, divider, executive_summary, vendor_risk_matrix, kpi_strip (`79ca440`)
- 3.3a — AI planner + tenant-safe context orchestrator + 6 explicit safety tests (`a27c97a`)
- 3.3b — Streaming generation pipeline + AI-aware blocks + ai_recommendation (`330b5e2`)
- 3.3c — Embedded conversational copilot + per-block Regenerate/Explain + print mode (this PR)

**Phase 3 v1 closes after 3.3c merges.** Six working block types, two AI endpoints (plan + generate), one chat endpoint, two per-block actions, print mode. Backend gauntlet: 320+ tests including the AI safety suite. Architecture spec carries §21 listing what's deferred to 2.2 production polish (server-rendered DOCX/PDF, signed-link sharing, autosave, Inspector panel, 8 remaining block types).

See [REPORTS_ARCHITECTURE.md](REPORTS_ARCHITECTURE.md) + [REPORTS_BLOCK_REGISTRY.md](REPORTS_BLOCK_REGISTRY.md).

**Phase 4 — Hero + marketing visual rework**

`/`, `/login`, `/activate`, `/portal/entra-a-tu-espacio` lifted into the V2.x visual register.

**Phase 5 — Internal polish + roll-out** (closed at `v2.1.0`)

Locked visual direction applied across the remaining ~20 admin / client / portal surfaces. Foundation work first: role-aware `withOnboardingGate` (internal staff bypass the expediente check), `cliente.demo@checkwise.mx` client_admin seed with a 3-vendor portfolio, shared `<DataTable>` and `<MetadataStrip>` primitives. Shells run at `data-density="dense"` with a drawer fallback below 1024px. Identical-card grids killed everywhere (admin + client 4-up KPI strips → asymmetric bordered lists, `/portal/onboarding` 2×2 → vertical bordered list). All `bg-gradient-to-br` ornaments dropped in product surfaces. State coverage normalised: loading skeleton + error state with retry + empty state on every changed surface. README bumped to V2.1.

The full 2.x track is complete at this tag.

## Next (post-2.x)

### V2.2 — Mock → real backend wiring

Finish the backend-integration TODOs that 2.0 carried forward through `portal-adapters.ts`.

- Enrich `/portal/workspaces/{id}/onboarding` with `why` / `format` / `next_action` / `reviewer_note` fields so the adapter can be dropped.
- Wire the admin + client dashboards to real `/api/v1/clients/*` payloads (today they still consume `lib/mock/*`).
- Replace the V1.2 opaque `X-Workspace-Token` with the JWT/RBAC stack already used by `/admin/*`.

### V2.3 — Importers + Source-of-Truth Migration

- Audit JotForm / Google Sheets schemas.
- Build a field dictionary.
- Map each field to canonical entities.
- Idempotent importer into PostgreSQL.
- Report unmappable rows, duplicates, divergences.

### V2.4 — Document Intelligence + Structured Metadata

Turn every uploaded PDF into reviewed, exportable document intelligence. PostgreSQL remains the canonical source of truth; Google Sheets / Excel are export bridges.

- Add async extraction jobs (`document_extraction_requested` → `running` → `completed` / `failed`).
- Add persistent extraction tables for runs, extracted fields, evidence, review status, and export batches.
- Run OCR only when native PDF text is insufficient.
- Extract structured fields per document rule in `metadata_rules.py`.
- Compare extracted values against expected client, vendor, institution, requirement, period, and contract context.
- Write confidence-scored `validation_events` and set `posible_mismatch` / `requiere_aclaracion` when objective mismatches appear.
- Add reviewer UI for accepting, correcting, or rejecting extracted metadata before legal approval.
- Export reviewed/pending metadata to CSV/XLSX first, then Google Sheets with idempotent row updates.

### V2.5 — Notifications

- Vendor alerts (overdue, rejected, action-required).
- Reviewer alerts (queue depth, SLA risk).
- Push reports (from Phase 3) as scheduled Slack / WhatsApp / email digests.

### Production readiness (parallel track)

- S3-compatible storage path (currently `LocalStorageService` writes to `./storage`).
- Managed Postgres (Neon or equivalent).
- Frontend → Vercel; backend → Render/Railway/Fly/Cloud Run.

## Guiding constraint

Every phase must ship a piece that's operable and verifiable. Future integrations hang off the canonical model; regulation never lives in form-only logic.
