# Checklist (Expediente / Requisitos) System Audit — 2026-06-09

Scope: full hardening / performance / resilience audit of the requirements-checklist
system across backend, database, frontend, permissions, and UX. Read-only audit; no
product behavior changed yet. Evidence is cited as `file:line`.

---

## 1. Current-state summary

The "checklist" is the **evidence-slot / obligation-state engine**. There is no stored
"checklist" table — the checklist is **computed dynamically** by projecting an in-code
compliance catalog (`app/core/compliance_catalog.py`) onto the provider's `submissions`.

- An *evidence slot* = `(client_id, vendor_id, requirement_code, period_key)`
  (onboarding slots drop `period_key`). See `services/evidence_slots.py:9-19`.
- The catalog (onboarding "Expediente Corporativo" + recurring REPSE calendar) is the
  source of *which* slots exist; `submissions` are the source of *what's in* each slot.
- Slot state is derived centrally by `classify_slot_state()` mapping `DocumentStatus`
  → coarse `SlotState` (`evidence_slots.py:196-221`). **Single source of truth on the
  backend** — good.
- The engine is **read-only**; replacement lineage (`supersedes_submission_id`) is set
  at intake and walked at read time by `_pick_current_submission()`
  (`evidence_slots.py:170-190`).
- Three portals consume it: **provider** (`/portal/*`), **client/contratante**
  (`/client/*`), **admin + reviewer** (`/admin/*`, `/reviewer/*`).
- Frontend: Next.js App Router, client-side `useEffect` fetches, no SWR/React Query.
  Status→UI mapping centralized in `lib/api/portal.ts:781-807` and
  `lib/constants/statuses.ts`.

Overall the design is **sound and should not be rewritten**. The issues are concentrated
in (a) **missing database indexes**, (b) a **per-vendor compute loop that scans the full
submissions table**, (c) a handful of **N+1s and frontend hardening gaps**. Tenant
isolation and permission gating were found **clean on the audited paths**.

---

## 2. Checklist data-flow map

```
in-code catalog (compliance_catalog.py)        submissions table (DB)
   onboarding reqs / recurring reqs                 one row per upload attempt,
        │                                           status + supersedes_submission_id
        ▼                                                  │
   build_workspace_onboarding_slots ───────────────────────┤  SELECT * FROM submissions
   build_workspace_calendar_slots(year) ────────────────────┤  WHERE client_id=? AND vendor_id=?
        │   (evidence_slots.py)                              │  (UNINDEXED → full scan)
        ▼                                                    ▼
   bucket submissions per slot in Python ◄──────────  _pick_current_submission (lineage leaf)
        │
        ▼
   SlotView{ state, current_submission, required, ... }   classify_slot_state()
        │
        ├─► provider dashboard      GET /portal/workspaces/{id}/dashboard|onboarding|calendar
        ├─► client overview/vendors GET /client/overview, /client/vendors   ← LOOPS per vendor
        ├─► client vendor detail    GET /client/vendors/{id}
        ├─► client calendar         GET /client/calendar
        └─► reports / audit package
                                              reviewer queue/decision mutate submission.status
                                              → next read recomputes slot state
```

Key property: **the checklist is recomputed on every request** from `submissions`. There
is no caching layer. Correctness is good (always live); cost is paid on every view, and
the underlying query is unindexed.

---

## 3. Main performance risks (ranked)

### P0-A — Missing indexes on the hot `submissions` / `documents` columns
Postgres does **not** auto-index foreign keys. On `submissions` the following are
unindexed: `client_id`, `vendor_id`, `period_id`, `institution_id`, `requirement_id`,
`status` (`entities.py:218-231`). Only `requirement_code`, `period_key`,
`supersedes_submission_id` are indexed (migrations 0004, 0008). On `documents`,
`submission_id` and `status` are unindexed; only `sha256` is (`entities.py:268-277`).

Every slot build runs `WHERE client_id=? AND vendor_id=?`
(`evidence_slots.py:148-151, 342-345, 415-421, 477-483`) → **full table scan of
`submissions`** every time. `documents.submission_id` is the most common join in the app
and is unindexed.

### P0-B — Client overview & vendors-list are O(vendors) × full-table-scan
`client_overview` (`client.py:990`) and `client_vendors` (`client.py:1066`) loop over
every workspace and call `_vendor_compliance` (`client.py:279-330`), which runs **two**
full-scan `select(Submission)` per vendor (onboarding + calendar). For *N* vendors that's
**2N full scans of the entire submissions table**. As both submissions and vendor counts
grow this degrades super-linearly and will be the first surface to fall over under load.
(The team already fixed a smaller 2N activity-timestamp N+1 at `client.py:333`; the
costlier slot-build loop was missed.)

If `RECURRING_CATALOG_V2` is ever enabled (`config.py:180`, currently `False`), each
vendor additionally triggers a full `select(Institution)` scan
(`evidence_slots.py:473-475`) → 3N scans.

### P1-A — N+1 in submission-detail "previous attempts"
- `portal.py:1932-1943` and `reviewer.py:418-421` — loop ≤10 prior attempts, one
  `Document` query each.
- `client.py:1165-1173` (`_recent_submissions_for_workspace`) — 2 queries/row.
- `client.py:1225-1228` (`_contracts_for_workspace`) — 1 query/row.

### P1-B — Frontend: no virtualization / true pagination on large lists
- Client vendors `DataTable` renders **all** rows ("no sorting, no pagination, no row
  selection" — `data-table.tsx:37`).
- Reviewer queue renders all items, no `limit` param (`admin/reviewer/page.tsx`).
- Submissions page uses a limit selector (25–500) with **no offset paging** — user can't
  reach row 101 without raising the limit. Fine < 500 rows, risky beyond.

### P2 — Frontend per-render recomputation
Provider dashboard derives `attentionRows` / `inReviewRows` / `primaryAction` fresh each
render without `useMemo` (`portal/dashboard/page.tsx:172-181`). Negligible at current
slice sizes (lists sliced to 5) but worth memoizing for safety.

---

## 4. Main reliability risks

1. **No DB guard against duplicate submissions in a slot.** `submissions` has no unique
   constraint on `(client_id, vendor_id, requirement_code, period_key)`
   (`entities.py:214-261`). Two concurrent uploads create two un-superseded leaves. The
   **read path is safe** (`_pick_current_submission` picks the latest leaf,
   `evidence_slots.py:170-190`), but row-summing aggregates can double-count and the
   audit trail shows phantom duplicates. Uploads are **not idempotent / not retry-safe**
   at the DB layer (there's a SHA-256 pre-flight check endpoint, but no enforcement).
2. **No CHECK constraint on `status`** (`entities.py:229, 274`). Invalid status strings
   are possible from legacy or buggy writes; `classify_slot_state` falls back to
   `MISSING` (safe-ish, but masks bad data).
3. **Frontend crash risk:** `a.vendor_name.localeCompare(...)` with no null guard
   (`client/submissions/page.tsx:128`). A null `vendor_name` from the API crashes the
   page.
4. **No request timeout** in `fetchJson` (`portal.ts:192-201`) → a hung endpoint shows
   an infinite spinner.
5. **Silent error swallow** on the onboarding fetch (`portal/dashboard/page.tsx:112`,
   `.catch(() => null)`) — degraded UI, no telemetry.
6. **Duplicated status logic on the frontend:** `statusToCode` (`portal-adapters.ts:31-55`)
   duplicates `statusToDocumentStateCode` (`portal.ts:781-807`); status→color variant
   maps are re-declared per page (dashboard / submissions / calendar) → drift risk.

---

## 5. Main security & permission risks

**No tenant-isolation or permission defects were found on the audited endpoints.** The
framework is consistent:
- Provider: `current_portal_workspace` validates workspace ownership (`portal.py:655`).
- Client: `_resolve_client_id` / `_resolve_client_id_for_vendor` scope every read to the
  caller's memberships (`client.py:153`, re-checked on nested reads e.g. `:2010, :2376`).
- Reviewer: intentionally cross-tenant, gated by `require_any_role(reviewer,
  internal_admin)` (`reviewer.py:13, 46-48`).
- Admin: `internal_admin`-gated at the router.
- Input validation present on `period_key`, institution codes, status enums, load types
  (`portal.py:2508-2529`, `client.py:2005`).

Caveats to harden, not defects:
- This is a *clean-on-inspection* result, not a proof. There are **no tenant-isolation
  regression tests** asserting that vendor B's `submission_id`/`vendor_id` returns 404
  for client A. Recommend adding them so it stays clean.
- Known precedence subtlety (from project memory): workspace `owner_user_id` can shadow
  org membership in report visibility (`_actor_from`). Worth a regression test in the
  same pass.
- Some client-portal action buttons (e.g. "Generar reporte") aren't role-gated in the UI
  and rely on the backend rejecting — acceptable, but add a UI guard for clarity.

---

## 6. UX problems found

- **Status→color inconsistency:** labels are centralized (`statuses.ts`, with soft
  Spanish like "rechazado" → "Requiere corrección"), but each page re-declares its own
  status→variant color map → colors can drift across portals.
- **Pagination ergonomics:** limit-selector with no "next page" hides rows beyond the
  limit.
- **Audit-package selection** silently clears when filters change
  (`client/auditoria/page.tsx:193`) with no toast — feels like data loss.
- Loading / empty / error states are otherwise **well covered** on both portals (skeletons,
  warning alerts, empty hints) — confirmed across dashboard, vendors, submissions,
  calendar, reviewer.
- Plain-Spanish next-action copy exists (`suggested-actions.tsx`, `next-action-rail.tsx`,
  `state-surfaces.tsx`) and is good.

---

## 7. Backend changes needed

| # | Change | File(s) | Risk |
|---|--------|---------|------|
| B1 | Batch the per-vendor slot compute: fetch all client submissions once, bucket by vendor, pass buckets into `build_workspace_*`. Turns 2N queries → ~2. | `evidence_slots.py`, `client.py:279-330, 962-1037, 1045-1110` | Med (refactor, behavior-preserving) |
| B2 | Batch "previous attempts" Document lookups into one `IN` query / `selectinload`. | `portal.py:1932`, `reviewer.py:418`, `client.py:1165, 1225` | Low |
| B3 | Hoist the v2 `select(Institution)` map out of the per-vendor path (only matters if V2 flips on). | `evidence_slots.py:473` | Low |
| B4 | Add a request-id-keyed idempotency / dedup guard on upload finalize (pairs with D3). | `submission_service.py` | Med (behavior) |

## 8. Frontend changes needed

| # | Change | File(s) | Risk |
|---|--------|---------|------|
| F1 | Null-guard `vendor_name.localeCompare`. | `client/submissions/page.tsx:128` | Low (bugfix) |
| F2 | Centralize status→color variant map into `lib/constants/statuses.ts`; delete duplicate `statusToCode`. | `portal-adapters.ts`, page maps | Low |
| F3 | Add `AbortController` timeout to `fetchJson`. | `portal.ts:192`, `client.ts` | Low |
| F4 | Log (don't swallow) the onboarding fetch error. | `portal/dashboard/page.tsx:112` | Low |
| F5 | Virtualize or paginate vendor list + reviewer queue when row count is large. | `data-table.tsx`, vendors/reviewer pages | Med |
| F6 | `useMemo` the dashboard row derivations. | `portal/dashboard/page.tsx:172` | Low |
| F7 | Toast when audit-package filter clears the selection. | `client/auditoria/page.tsx:193` | Low |

## 9. Database / indexing changes needed (migration 0034)

```sql
-- submissions: the hot path
CREATE INDEX CONCURRENTLY ix_submissions_client_vendor   ON submissions (client_id, vendor_id);
CREATE INDEX CONCURRENTLY ix_submissions_client_status   ON submissions (client_id, status);
CREATE INDEX CONCURRENTLY ix_submissions_period_id       ON submissions (period_id);
CREATE INDEX CONCURRENTLY ix_submissions_requirement_id  ON submissions (requirement_id);
-- documents: most common join + status filter
CREATE INDEX CONCURRENTLY ix_documents_submission_id     ON documents (submission_id);
CREATE INDEX CONCURRENTLY ix_documents_status            ON documents (status);
-- audit / history (P2)
CREATE INDEX CONCURRENTLY ix_doc_status_history_document ON document_status_history (document_id, created_at);
CREATE INDEX CONCURRENTLY ix_audit_log_entity            ON audit_log (entity_type, entity_id);
```
- Use `CONCURRENTLY` (non-blocking) on prod Neon; Alembic op with `autocommit_block()`.
- **D-decision:** unique partial index to stop duplicate slots (needs data de-dup first):
  `CREATE UNIQUE INDEX ... ON submissions (client_id, vendor_id, requirement_code,
  period_key) WHERE supersedes_submission_id IS NULL` — see Question Q2.
- Optional: `CHECK (status IN (...))` on `submissions`/`documents` (D5).

---

## 10. Testing plan

**Backend** (pytest; strong existing base — `test_evidence_slots.py`,
`test_catalog_v2_slots.py`, `test_portal_dashboard.py`, `test_client_portal.py`):
- Slot generation: onboarding + recurring, persona moral/fisica, each `SlotState`.
- Requirement matching: canonical vs legacy, v1 vs v2 compatibility join.
- Upload status transitions: missing→uploaded→in_review→approved/rejected/expired,
  replacement lineage picks the right leaf.
- Duplicate handling: two un-superseded leaves → read path returns latest; aggregates
  don't double-count (regression for the row-summing risk).
- **Tenant isolation (new):** client A cannot read vendor B's submission / vendor detail
  / expediente.zip (expect 404); provider token can't read another workspace.
- **Permission boundaries (new):** non-reviewer 403 on decision; non-admin 403 on
  requirement CRUD.
- Empty data: zero vendors, zero submissions → 100% / empty, no crash.
- Large data: seed N vendors × M submissions; assert query **count** stays ~constant
  after B1 (guard against N+1 regressions — assert via SQL counter).
- Malformed: unknown status string → `MISSING`, not a 500.

**Frontend** (Vitest/RTL — currently thin, 5 files):
- `statusToDocumentStateCode` exhaustive mapping (extend existing `statuses.test.ts`).
- Components render with null/missing/duplicated API fields without crashing
  (vendor_name null, requirements undefined).
- Loading / empty / error / success state snapshots for dashboard + vendors + submissions.
- Mobile/responsive: table overflow at 360px.

## 11. Prioritized implementation plan

**Wave 1 — safe, high-impact, no behavior change (do first):**
1. D-indexes migration 0034 (P0-A) — biggest win per unit risk.
2. B1 batch per-vendor slot compute (P0-B) + a query-count test.
3. B2 N+1 batch fixes (P1-A).
4. F1 null-guard, F3 timeout, F4 error logging (reliability quick wins).

**Wave 2 — clarity & consistency:**
5. F2 centralize status→color; remove duplicate mapping.
6. F6 memoization; F7 audit-package toast.
7. CHECK constraints (D5) + status backfill audit.

**Wave 3 — scale & behavior (needs product input):**
8. F5 virtualization/pagination for large lists.
9. B4 + unique partial index (D) — idempotent uploads / duplicate prevention.
10. Tenant-isolation + permission regression test suite.

## 12. Questions before changing product behavior

1. **Scope now:** proceed with Wave 1 (indexes + batch + N+1 + FE hardening — all
   behavior-preserving), or audit-only for this pass?
2. **Duplicate submissions:** enforce a DB unique partial index (requires de-duping
   existing prod rows and may reject a re-upload if lineage isn't set), keep app-level
   only, or leave the read-path dedup as-is + add monitoring?
3. **Index deploy on prod Neon:** OK to run `CREATE INDEX CONCURRENTLY` against prod, and
   should I take a named Neon snapshot first per the usual rollback procedure?
4. **Realistic scale:** what's the target ceiling for vendors-per-client and submissions
   total? That decides how hard to push virtualization/pagination (Wave 3) now vs later.

---

## 13. Wave 1 — shipped 2026-06-09 (behavior-preserving)

All verified: **backend `pytest` 1389 passed**, **frontend `tsc` clean + 48 tests**,
ruff clean.

- **Indexes (migration 0034 + model `__table_args__`).** `submissions(client_id,
  vendor_id)`, `(client_id, status)`, `period_id`, `requirement_id`;
  `documents(submission_id)`, `(status)`; `document_status_history` + `audit_log`. Built
  `CONCURRENTLY` on Postgres via `autocommit_block`; plain `CREATE INDEX` on SQLite tests.
  *Deploy step (yours): take a named Neon snapshot, then `alembic upgrade head`.*
- **Batched per-vendor slot compute (P0-B).** `evidence_slots.build_workspace_*` and
  `current_onboarding_submission_for_workspace` gained an optional
  `prefetched_submissions` (and v2 `institutions_by_id`); `_portfolio_slot_inputs` in
  `client.py` fetches a client's submissions once and buckets by vendor.
  `/client/overview` and `/client/vendors` are now constant-query in the vendor count
  (was ~5N). New regression test asserts the submissions-scan count doesn't grow with N.
- **N+1 fixes (P1-A).** Batched the previous-attempts document lookups
  (`portal.py`, `reviewer.py`) and the `_recent_submissions_for_workspace` /
  `_contracts_for_workspace` per-row doc+lineage lookups (`client.py`), plus
  `selectinload(Submission.requirement)` to kill a lazy per-row hit.
- **Frontend hardening.** Null-guarded the submissions sort; added a 30 s request
  timeout to both `fetchJson`s (`portal.ts`, `client.ts`); log the onboarding-fetch
  error instead of swallowing it.

### Auto-supersede + unique-slot constraint — shipped (approved behavior change)

Tracing the write path (`_resolve_supersedes_submission`, `portal.py`) showed the upload
flow previously **did not auto-link** a new upload to an existing slot occupant, and only
`{rechazado, requiere_aclaracion, posible_mismatch, vencido}` were replacement-eligible.
So re-uploading for a slot that already held an **approved**/in-review submission created
a second genesis row (`supersedes_submission_id IS NULL`) — the read engine resolved
"current" by recency. A hard unique constraint would have *rejected* those legitimate
re-uploads, so it needed an upload-semantics change. **Decision (approved): auto-supersede,
then enforce.**

- **Auto-supersede** (`portal._auto_supersede_target` + `_resolve_supersedes_submission`).
  When no explicit `supersedes_submission_id` is passed and the canonical slot is already
  occupied, the new upload automatically supersedes the current occupant **regardless of
  its status** (approved/in-review included). The prior row is kept as linked history; the
  slot returns to review. Codeless legacy uploads (no `requirement_code`) can't be slotted
  and still stand alone. The explicit-replace path (and its 404/409 guards) is unchanged.
- **Migration 0035** — a read-result-preserving de-dup backfill (chains any pre-existing
  parallel-genesis rows by recency; oldest stays genesis, newest stays the leaf) then a
  `CONCURRENTLY`-built unique partial index `ux_submissions_active_slot` on
  `(client_id, vendor_id, requirement_code, coalesce(period_key,''))`
  `WHERE supersedes_submission_id IS NULL AND requirement_code IS NOT NULL`. `coalesce`
  folds the onboarding NULL-period case so its duplicates collide; codeless rows are
  exempt. The index is **migration-only** (Postgres) — the SQLite test schema omits it so
  it can still seed parallel-genesis rows that exercise the read engine's defensive
  recency-tiebreak for legacy data; the invariant is upheld by the auto-supersede write
  path, which is covered by endpoint tests.
- **Tests:** `test_workspace_submissions.py` (auto-supersede over approved → links, slot
  back to review, one genesis; first-upload-is-genesis) and
  `test_unique_active_slot_migration.py` (runs the exact `_DEDUP_SQL` + index DDL: chaining,
  codeless exemption, onboarding/recurring rejection, supersede/different-period accepted).

*Deploy step (yours):* take a named Neon snapshot, then `alembic upgrade head` runs 0034
(indexes) then 0035 (backfill + unique index), all `CONCURRENTLY`. Auto-supersede ships
with the API deploy. If 0035's `CONCURRENTLY` build ever aborts on a straggler duplicate,
it's re-runnable (drops the invalid index first).
