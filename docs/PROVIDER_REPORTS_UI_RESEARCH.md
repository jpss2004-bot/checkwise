# Provider Reports — UI / Product Research (2026-05-18)

**Purpose.** Capture useful UI / product patterns from the SaaS compliance,
vendor-portal, and AI-report-builder space, plus the in-repo design
skills, to inform the Provider Reports redesign. No code. No commitments.
Patterns and judgement, with explicit "use this / skip this" calls.

Companion: [PROVIDER_REPORTS_REDESIGN_AUDIT.md](_archive/PROVIDER_REPORTS_REDESIGN_AUDIT.md).

---

## 1. Methodology

- Web research focused on what compliance platforms (Vanta, Drata,
  Secureframe, Sprinto) and vendor portals do for *the user who has to
  fix things*, not the auditor.
- Cross-referenced with the in-repo design skills under
  `.claude/skills/` to ground decisions in the project's own taste rails.
- Filtered everything against the audit's hard constraint: the
  dashboard read model already returns every signal the redesign needs
  — patterns that reinvent data flow are rejected.

I did **not** copy any screenshots, source code, or proprietary assets
into the repo. Inspiration only.

---

## 2. External patterns worth borrowing

### 2.1 Vanta — in-app compliance roadmap + AI remediation

What I saw:
- Vanta's product centers on a "roadmap" surface that guides each role
  from first login through audit-readiness via in-app checklists.
- Per-finding "remediation detail" answers *when, where, why, and how to
  fix* with the LLM generating the fix snippet inline.
- "Continuous monitoring" is the framing: the dashboard is alive, not a
  monthly export.
- Reviews note that vendor questionnaire UX is *the* friction point —
  out-of-the-box templates often miss vendor specifics, especially for
  non-SaaS suppliers.

What to borrow:
- The "guided roadmap + in-app checklist" framing for the provider's
  home view, which today is a static dashboard plus a separate Reports
  list. CheckWise's `attention_today` + `suggested_actions` from the
  dashboard read model already power this exactly — what's missing is
  the surface in the report.
- The AI-as-remediation-explainer pattern: when a doc is rejected, the
  LLM should explain *what to fix and how* in one sentence, grounded in
  `reviewer_note`. CheckWise already returns `reviewer_note` per
  submission (Phase 5).

What to skip:
- The "always-on certification" framing — CheckWise is about REPSE /
  SAT / IMSS / INFONAVIT, not SOC 2. The story is different. We are
  not telling the provider they're "97% SOC 2 ready"; we're telling
  them "you have one rejected RFC and one expired opinión de
  cumplimiento."
- Vanta's heavy "policy template library" — the provider is uploading
  evidence, not authoring policies.

### 2.2 Drata — engineer-grade visibility, control-state real-time

What I saw:
- Drata's strength is "this control is currently passing / failing,
  here's why, here's the last evidence captured." The state is the
  hero.
- Heavy use of green / amber / red status badges per control row,
  always with a *reason* chip the user can hover.
- A single status column anchors every row — no compositional
  ambiguity.

What to borrow:
- The "state chip + reason hover" pattern for every per-document row in
  a provider report. The CheckWise workflow state machine
  ([WORKFLOW_STATE_MACHINE.md](WORKFLOW_STATE_MACHINE.md)) already
  defines the states — render them as semantic chips, with the
  `reviewer_note` (Phase 5) as the reason on hover or expansion.
- A single canonical status column per row — don't make the user
  cross-reference two columns to know what's going on.

What to skip:
- Drata's "framework grid" multi-standard cross-mapping — irrelevant
  for a single provider's own compliance.
- The integration-heavy "auto-collect from your dev tools" — the
  provider's evidence is humans uploading PDFs, not API integrations.

### 2.3 Secureframe — guided onboarding + structured workflows

What I saw:
- Secureframe emphasizes step-by-step guided flows for non-technical
  users: "do this, then this, then this," with progress visible at all
  times.
- Onboarding has a strong "you are 3 of 7" affordance throughout.

What to borrow:
- Progress affordance on the provider report: at any moment, the
  provider should see *"you are X% complete this period, Y items
  remain."*
- Step-numbered prioritization in the action surface: don't just list
  what's wrong; list it in order with explicit "first / next / then"
  framing.

What to skip:
- The heavy hand-holding wizard chrome — providers are repeat users
  (monthly), they need density after the first month, not a wizard.

### 2.4 Linear — keyboard density + status fluency

What I saw:
- Linear treats every row as a structured object: priority chip,
  status chip, owner avatar, due date, in *one* line, scannable.
- The list is the product. The detail view exists, but the list is
  where work happens.

What to borrow:
- Density target: a single provider report row should fit institution
  + state + period + due-in-days + CTA in one scannable line.
- Keyboard shortcut to open the first rejected item — for repeat
  users.

What to skip:
- Linear's full ticket model (assignees, projects, cycles) — overkill
  for a per-period compliance checklist.

### 2.5 Notion / Claude Artifacts / ChatGPT Canvas — editable AI canvas

What I saw:
- The "AI streams structured content into an editable canvas; user
  refines via chat" pattern is the same one CheckWise already
  committed to in REPORTS_ARCHITECTURE.md.
- The differentiator that lands: the AI's output is *not the artifact*
  — it's a starting point the user manipulates.

What to borrow (already committed):
- Keep the canvas + right-rail copilot. The redesign adds
  provider-aware blocks; it does not throw out the canvas.

What to skip:
- Going further into "live multi-user cursors" — out of scope for v1
  (already excluded in §17 of the architecture doc).

### 2.6 Stripe Dashboard — document-quality exports

What I saw:
- Stripe's dashboard renders a report that looks the same on screen
  and printed. No "switch to print mode" surprise — the on-screen
  layout *is* the document.

What to borrow:
- Make the on-screen provider report identical to its print mode in
  visual identity. The CheckWise print route at
  `/portal/reports/[id]/print` already enforces this; the redesign
  must not break that parity by adding interactive-only chrome inside
  blocks.
- Interactive affordances (Subir / Reemplazar buttons) should sit on
  the *outer* block frame and print as static text ("Acción: subir
  RFC actualizado"), not as broken buttons.

### 2.7 Power BI / Looker Studio — block-based dashboards

What I saw:
- Composable blocks (KPI cards, charts, tables, narratives) with a
  shared registry; users drag-and-drop to compose.
- Heavy use of "small multiples" — the same metric rendered four
  times for four entities.

What to borrow:
- The block registry shape (already committed).
- Small-multiples idea for a single-provider, multi-institution view:
  one mini-card per institution (SAT / IMSS / INFONAVIT / STPS-REPSE)
  showing its current state at a glance.

What to skip:
- Heavy charting — providers don't need pie charts of their own
  compliance. They need to know what to upload.

### 2.8 Airtable Interfaces — view configurability

What I saw:
- A single data model rendered as multiple "views" (gallery, grid,
  kanban) the user picks per task.

What to borrow:
- For *internal* (admin) provider reports, offer a "by institution"
  vs. "by deadline" toggle on the same dataset. Not v1 — but the
  block contract should support it.

What to skip:
- Letting providers pick views — too many choices for a non-technical
  user.

---

## 3. Anti-patterns to actively avoid

| Anti-pattern | Why it hurts the provider | What to do instead |
|---|---|---|
| AI-generated prose as the only output | Provider has to read paragraphs to find the one document they need to upload | Lead with a structured action list; AI prose is the bottom section, not the top |
| Generic "compliance score" with no breakdown | Provider sees "78%" and doesn't know what's wrong | Show the semaphore + the failing slots inline with click-to-fix |
| Per-block AI regenerate as the primary affordance | Providers don't think in blocks; they think in documents | Per-block regenerate stays available, but each provider block should also offer "open in upload flow" |
| Wizard with forced steps | Repeat users get punished | Step affordance exists, but every step is independently click-targetable |
| Cross-vendor matrix on a provider's own report | Confuses the provider; tempts cross-tenant data | Provider reports never show other vendors. Period |
| Hidden "click here to see details" — single canonical row + expansion | Forcing modal navigation breaks scanning | Inline-expand or open in a side drawer; never modals on a per-row action |
| Empty-state pep talk "Great, no rejections!" with no follow-up | Provider has nothing to *do* | Empty state still suggests what's next (upcoming deadlines, optional uploads) |

---

## 4. In-repo skills relevant to this redesign

Inventory of `.claude/skills/` entries that map cleanly to the work
ahead:

| Skill | Relevance |
|---|---|
| `checkwise-report-designer` | Direct match. Already specifies that a CheckWise report explains compliance status, missing docs, risk, responsibility, deadline, evidence, next action, auditability. Sections list matches my redesign target almost 1:1 (exec summary, supplier overview, period filters, critical missing, rejected, validation notes, evidence, actions, appendix). Use as the canonical taste reference. |
| `checkwise-ui-designer` | Use for the editor surface and the new provider blocks. |
| `checkwise-frontend` | Use for component implementation, shared list view edits. |
| `checkwise-redesign-prep` | Use to pre-flight the redesign — guardrails, what to leave alone. |
| `checkwise-audit` | Use to verify post-change that we haven't broken admin / client surfaces. |
| `checkwise-security` | Critical — every new block fetcher must pass through a tenant-scope review. |
| `checkwise-qa-release` | Use before merging the first slice. |
| `checkwise-git-safe` | Use for branch / commit hygiene. |
| `design-taste-frontend`, `impeccable`, `impeccable-ui`, `taste`, `gpt-taste` | Visual-taste references for the new blocks. |
| `high-end-visual-design`, `hero-redesign` | Useful if we add a "compliance pulse" hero strip to `/portal/reports`. |
| `emil-kowalski-design` | Motion + micro-interaction taste reference for streaming block fade-ins. |
| `redesign-existing-projects` | Process discipline — work in slices, validate per slice. |

The skill that most directly aligns with the audit's findings is
`checkwise-report-designer`. Its 9-section template is essentially the
provider-report shape we want — except today's blocks only realize ~4
of the 9 sections, and none in a provider-aware way.

---

## 5. Recommended design direction

Synthesizing the above into a single direction for the redesign plan:

### 5.1 The big shift

Move provider Reports from **"a list of past AI generations"** to
**"a living compliance brief that lets me act."**

The list page should answer "where do I stand right now?" without
clicking. The editor should answer "what do I need to fix, in what
order, with one click to do it." AI prose stays — but as one section
of the report, not the whole report.

### 5.2 Five concrete moves

1. **Compliance pulse on `/portal/reports`** — a hero strip above the
   preset gallery rendering `semaphore.level + reason + compliance_pct`
   from the dashboard payload. Same widget the dashboard hero uses,
   no new endpoint.

2. **Three provider-aware block types** added to the registry:
   - `compliance_state` — semaphore + counts. Static, no AI.
   - `attention_list` — table of rejected / mismatch / clarification
     items, each row with institution chip + state chip + reviewer note
     preview + "Subir documento" / "Reemplazar" CTA linked to
     `/portal/upload?…&replaces=…`.
   - `upcoming_deadlines` — next ≤5 deadlines as small-multiples cards,
     each with countdown.

3. **Grounded AI context for workspace-owner generates.** Inject the
   full dashboard payload into the planner system prompt for vendor
   audience. The LLM stops guessing.

4. **Structured action surface.** Replace the generic
   `ai_recommendation` block with a `prioritized_actions` block whose
   data model is `{priority, title, body, href, source_slot_id}`. The
   AI fills in `body`; everything else comes from
   `suggested_actions[]`. Each action is a click-through, not just
   prose.

5. **Print parity.** Every new block renders identically on print.
   Buttons degrade to plain text ("Acción: subir RFC actualizado");
   chips degrade to bracketed labels ("[Rechazado]"). The on-screen
   report and the printed one are the same artifact.

### 5.3 What stays

- The shared `<ReportsListView>` (no fork — extend it).
- The shared `<ReportEditor>` (no fork — extend its block registry).
- The Context Assembler + trust boundary.
- The preset registry shape.
- The 6 existing block types (legacy, available to admin/client).
- The print mode, mock-engine banner, AI-generated pill, version
  history rules.
- Every permission helper as-is.
- The 7 P1 tests as regression locks.

### 5.4 What deliberately does NOT change

- No new auth model. Provider identity stays in `ProviderWorkspace`.
- No schema change. New blocks live in `content_json`; new data
  fetchers read from existing tables.
- No new MCP, no new external dep.
- No PDF/DOCX server export (still deferred).
- No share-link delivery for vendors without accounts (R1.2, still
  deferred).
- No multi-vendor matrix on provider reports. Ever.

---

## 6. Risks to flag in the plan

| Risk | Likelihood | Where to mitigate |
|---|---|---|
| New block fetcher leaks across vendors | Medium | `assert_workspace_scope()` helper, mandatory on every vendor-only block. Plus a vendor-isolation test per new block. |
| AI hallucinates remediation that contradicts `reviewer_note` | Medium | Inject the full attention payload (with reviewer notes) verbatim into the planner; cite the slot id in the `prioritized_actions` rows. |
| Click-through URLs go stale (`replaces=` ids drift) | Low | Resolve the href at render time from the canonical dashboard payload, not from the persisted snapshot. |
| Print mode breaks when buttons appear in blocks | Low | Print stylesheet covers existing components; new ones add `print:` modifiers from day one. |
| Confusion: "is this report current or last week's?" | Medium | Every new block carries a `data.fetched_at` timestamp the block frame displays subtly above the content. |
| Dual-workspace owner edge case | Low (no seed coverage) | Add a test in the first slice where one user owns two workspaces; assert the report scopes to the workspace whose `vendor_id` matches the report. |
| Performance: dashboard payload is ~5 KB; injecting into planner system prompt costs tokens every generate | Low | Acceptable. Prompt-caching the catalog + workspace context once per session keeps the marginal cost bounded. |
| Block registry symmetry drift (FE def vs BE fetcher) | Medium | Add a CI check that every block in `apps/web/lib/reports/registry.ts` has a matching `apps/api/app/services/reports/blocks/<type>.py`. |

---

## 7. Sources

The web research that informed §2:

- [Compliance & Audit Automation MCP Servers — Vanta, Drata, Secureframe overview (ChatForest, 2026)](https://chatforest.com/reviews/compliance-audit-automation-mcp-servers/)
- [Secureframe vs Vanta vs Drata (Drata blog, 2026)](https://drata.com/blog/secureframe-vs-vanta-vs-drata)
- [Vanta — Compliance Automation](https://www.vanta.com/products/automated-compliance)
- [Vanta — Compliance Agent (AI remediation)](https://www.vanta.com/resources/vanta-delivers-compliance-agent)
- [Vanta — Continuous Control Monitoring](https://www.vanta.com/collection/grc/continuous-control-monitoring)
- [Compliance Automation Tools Comparison (InventiveHQ, 2026)](https://inventivehq.com/blog/compliance-automation-tools-comparison)
- [AWS — Building an AI-powered system for compliance evidence collection](https://aws.amazon.com/blogs/machine-learning/building-an-ai-powered-system-for-compliance-evidence-collection/)
- [SaaSCity — SaaS Compliance Checklist 2026](https://saascity.io/blog/saas-compliance-checklist-2026-soc2-gdpr-ai-act)

And in-repo:

- `.claude/skills/checkwise-report-designer/SKILL.md`
- [REPORTS_ARCHITECTURE.md](REPORTS_ARCHITECTURE.md) (esp. §15 deferred
  block list, §22 R1.0, §25 P1)
- [PROVIDER_DASHBOARD_READ_MODEL.md](PROVIDER_DASHBOARD_READ_MODEL.md)
- [PROVIDER_PORTAL_CANONICAL_READS.md](PROVIDER_PORTAL_CANONICAL_READS.md)
- [EVIDENCE_SLOTS.md](EVIDENCE_SLOTS.md)
- [WORKFLOW_STATE_MACHINE.md](WORKFLOW_STATE_MACHINE.md)
