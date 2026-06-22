# CheckWise system audit — remediation status (2026-06-21)

Branch: `chore/system-audit-cleanup` (worktree `~/checkwise-wt-audit`, off `origin/main` 28bb21d).
Audit source: `_handoff/system-audit-2026-06-21.md` (full report), `-findings.json` (254 verified),
`-worklist.txt` (every finding with file:line + fix, grouped into the 9 batches below).

## DONE — committed & verified (zero test regressions throughout: full suite held at the
24 pre-existing `requiere_aclaracion`/replacement baseline failures after every batch)

| Commit | Batch | What |
|--------|-------|------|
| `010a9e0` | 1 — cleanup | 17 dead files, in-file dead code, cron `requirements.lock`, gitignore/tsconfig de-machining (2,819 deletions) |
| `cea1c4e` | 2 — compliance correctness | notification commit + decision-event dual-write gating (`LEGACY_OWNS_DECISION_NOTIFICATIONS`); catalog-driven deadlines (annual SAT fixed); empty-password PDF; multi-doc metadata export; WhatsApp labels; reporting suppression; VENCIDO buckets; multi-client 404 |
| `1e69419` | 3 — tenant isolation | metadata export re-keyed on `client.id` (+ migration script); tenant-scoped sha256 dedup; 404-vs-403 leak; `assert_workspace_scope` wired; share audience redaction; `cookie_secure` + share-info title leak; FE `?client_id` |
| `3653a33` | 4 — security | target-privilege guards on user-lifecycle endpoints; 32-char JWT-secret floor; XFF rightmost-hop (deduped); rate limits on add-provider/upload/export/admin-ZIP; Wise owner-null; WhatsApp `phone_e164` gate; OTP log redaction; lockout enumeration |
| `05477ef` | 5 — resilience | true streaming ZIPs (bounded RAM); leak-free `open_stream`; zip-slip; uuid temp paths; build_entries dedup; FE fetch timeouts |
| `6c7faf3` | 7 — efficiency | `get_rollup`/radar/renewals bulk-prefetch; report-fetcher + `compute_renewal_actions` N+1; incremental metadata master; search floor + **migration 0055** (indexes) |
| `7350aa0` | 9 (HIGH only) | public-form whitespace 500 → 422; intake-wizard empty-select 422 |

Every batch verified: `ruff` at 44 baseline, `tsc` 0, backend import smoke, full pytest diffed
against `/tmp/cw-audit-baseline-fails.txt` (24 pre-existing). Two over-eager audit recommendations
were **rejected after they regressed tests**: RFC-mismatch escalation (intentional advisory design,
tested) and the VENCIDO `risk_level` bucket derivation (conflated missing vs lapsed).

## OPERATIONAL follow-ups before/at deploy
1. **Migration `0055`** (perf indexes, pg_trgm GIN + btree, CONCURRENTLY) is CODE-ONLY/unapplied.
   Snapshot Neon, confirm `idle_in_transaction_session_timeout` is set, then it auto-runs via the
   Render `preDeployCommand`. It cannot run inside a transaction.
2. **Metadata path migration**: `scripts/migrate_metadata_export_paths.py` (dark, dry-run default)
   moves existing `metadata_exports/<slug>/` trees to `<slug>-<client_id>/`. Run with `--apply`
   after deploying the Batch 3 re-keying, else existing exports orphan until next rebuild.
3. **Password-reset token invalidation** (Batch 4, MEDIUM) was DEFERRED — needs a
   `User.tokens_valid_after` column + migration + a check in `decode_access_token`. A stolen JWT
   currently survives a password reset until natural expiry (24h).
4. Spawned background task `task_caff8839` — admin renewals prefetch should pair (client_id,
   vendor_id) like the Batch 7B helper (a vendor under two clients can get the wrong anchor). Verify
   whether Batch 7A's renewals rewrite already covers it; the chip is the safety net.

## NOT YET DONE — medium/low, fully documented in the worklist (recommend the same
parallel-subagent-per-disjoint-file-cluster pattern, verify-vs-baseline, commit per batch)

### Batch 6 — Concurrency & races (medium/low; low urgency on the current single-worker deploy)
- TOCTOU reviewer-decision vs auto-approval double-terminalize → `SELECT … FOR UPDATE` on the
  submission row before the status transition (`submission_workflow.py`, `auto_approval.py`).
- `version_number` MAX+1 races the unique constraint → SAVEPOINT-and-reselect / retry on
  IntegrityError (`evidence_slots.py`).
- Concurrent master/latest rebuild races on fixed paths → write-to-temp + atomic rename
  (`metadata_export.py`).
- double-submit parallel leaves; first-time period/requirement create 500; duplicate-email race in
  `client_add_provider` → 500 instead of 409 (catch IntegrityError → 409).
- Non-deterministic workspace resolution when a vendor has multiple workspaces under one client.

### Batch 8 — Date/TZ + document-analysis hardening (low + 2 MEDIUM security)
- Introduce `today_mx()` / `utc_now()` helpers (America/Mexico_City, tz-aware) and replace
  `date.today()` (deadlines/calendars), the renewal anchor's UTC date, the activity-feed UTC-day
  grouping, and the naive `datetime.utcnow()`+manual-"Z" report/AI timestamps. FE `formatDateTime`
  renders bare `YYYY-MM-DD` a day early.
- **MEDIUM (security):** vendor-controlled PDF text and client-asserted Wise/conversation history are
  inlined into prompts with no untrusted-data delimiting → add fenced/neutralized delimiting in
  `document_analysis/expediente.py`, `wise/context.py`, `reports/copilot*`. Plus deep-tier
  truncation detection + shadow-runner redundant round-trips.

### Batch 9 — remaining LOW (infra + FE/UX polish)
- Alembic `env.py` single-transaction vs autocommit migrations; 0044 downgrade destroys operator
  platform_admin; empty `CORS_ORIGINS` boot guard.
- FE: client-metadata download / notification mark-read error handling; calendar error-retry no-op
  (sets year to itself); `DashboardActionType` missing "renewal"; `/seguridad` bare `<ul>`; blob
  revoke 1s-vs-60s; intake "Nueva carga" leaks preview blob URL.
- Slack mrkdwn injection + SSRF allowlist; SMTP header newline; misc rate-limit/consistency LOWs
  (see worklist "Batch 9" + the 96 unbatched tail items in `-findings.json`).
