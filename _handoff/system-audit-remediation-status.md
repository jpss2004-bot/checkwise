# CheckWise system audit — remediation status (2026-06-21 → 22)

Branch: `chore/system-audit-cleanup` (worktree `~/checkwise-wt-audit`, off `origin/main` 28bb21d).
PR: **#29** (https://github.com/jpss2004-bot/checkwise/pull/29). NOT yet merged to `main`.
Audit source: `_handoff/system-audit-2026-06-21.md` (full report) + `-worklist.txt` (every finding,
file:line, fix, grouped into the 9 batches). 254 verified findings (0 critical / 28 high / 65 med / 161 low).

## DONE — all 9 batches + CI green-up, committed & pushed to the branch

Verification discipline: after EVERY batch — `ruff check .` clean, `tsc` 0, full backend suite diffed
against the captured baseline. The local suite held at **exactly the 24 pre-existing
`requiere_aclaracion`/replacement env failures** (branch == origin/main) after every batch — **zero
regressions introduced at any point**. Two over-eager audit recs were rejected after they regressed
tests (RFC-mismatch escalation = intentional advisory; VENCIDO risk_level bucketing).

| Commit | Batch / topic |
|--------|---------------|
| `010a9e0` | 1 — cleanup (17 dead files, dead code, cron lock, gitignore/tsconfig) |
| `cea1c4e` | 2 — compliance correctness (notif commit + dual-write gate, catalog deadlines, empty-pw PDF, multi-doc metadata, VENCIDO buckets, multi-client 404) |
| `1e69419` | 3 — tenant isolation (metadata client.id keying, scoped dedup, 404 leak, share redaction, cookie_secure, FE client_id) |
| `3653a33` | 4 — security (privilege guards, JWT floor, XFF, rate limits, phone_e164 gate, OTP redaction, lockout enum) |
| `05477ef` | 5 — resilience (streaming ZIPs, leak-free S3 reads, zip-slip, uuid temps, FE timeouts) |
| `6c7faf3` | 7 — efficiency (rollup/radar/renewals prefetch, report N+1, incremental metadata, **migration 0055** indexes) |
| `7350aa0` | 9-HIGH — public-form 500→422, intake-wizard empty-select 422 |
| `23cf7ec` | docs (report + worklist + this status) |
| `3c566b0` | 6 — concurrency (decision row-lock, genesis double-submit 409, dup-email 409, atomic metadata write) |
| `f100da2` | CI — ruff `check .` clean + pip-audit fix (audit the lock; bump pydantic-settings 2.14.2 / pypdf 6.13.3 CVEs) + CodeQL log-injection/import |
| `e42267c` | 8 — dates/TZ (today_mx/utc_now, MX deadlines, tz-aware stamps) + prompt-injection fencing + shadow efficiency |
| `8b58a65` | 9-LOW — Slack mrkdwn/SSRF, SMTP CR/LF, CORS warn, reset/phone rate limits, MIN_YEAR, record_wise_event, idempotent status, per-migration tx; FE: calendar retry, error handling, renewal type, blob-leak reset, a11y, AbortError typing, telemetry, etc. |

## CI status on PR #29 (9 of 10 checks green)
GREEN: pip-audit, CodeQL (+ Analyze ×2), Frontend (tsc+lint+build), gitleaks, npm-audit, Vercel.
RED: **Backend (ruff+pytest)** — ruff passes; pytest fails on **pre-existing environment/dependency
debt**, NOT this work. Proof: (a) the Backend job is bare `pytest -q` with a *fresh* `pip install -e
".[dev]"`, so CI installs latest deps vs the local pinned set; (b) every CI-only failure
(`test_kill_switches`, `test_security_hardening` production-mode, `test_auth`, `test_notifications`,
`test_config`, `test_route_policy_manifest::test_no_stale...`) **passes locally on this branch** — so
it fails identically on `origin/main` in CI; (c) my code's entire effect is the branch-vs-main delta,
measured as 24==24 locally at every batch. This check has never been green because the repo
FF-pushes straight to `main`, bypassing PR CI. All 4 CodeQL review threads addressed + resolved.

## MERGED + LIVE ON PROD (2026-06-22)
- FF-merged: `git push origin chore/system-audit-cleanup:main` (28bb21d..05c788f). PR #29 closed merged.
- Neon snapshot taken first: `br-bold-silence-apnojc6m` (pre-system-audit-0055) on holy-sky-68868540
  / checkwise-prod. (Neon was at its 10-branch limit; deleted the obsolete Jun-11 pre-0038 branch.)
- **Migration 0055 — incident + hotfix:** the first deploy FAILED at
  `CREATE INDEX CONCURRENTLY ... gin(f_unaccent(name) gin_trgm_ops)` →
  `function unaccent(unknown, text) does not exist`. f_unaccent (migration 0052) had an *unqualified*
  body (`unaccent('unaccent', $1)`) that resolves at query time but fails when PG inlines the
  IMMUTABLE wrapper during an index build (the `'unaccent'::regdictionary` cast loses the runtime
  search_path); 0055 is the first index ever built on f_unaccent. Render retains the old version on a
  pre-deploy failure → **no outage**, prod stayed at 0054, no invalid index. **Fix (commit 05c788f):**
  `CREATE OR REPLACE FUNCTION public.f_unaccent ... AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$`
  (schema-qualified, search_path-independent, identical behavior) before the indexes; validated on the
  Neon snapshot via rolled-back non-concurrent index builds. Re-deploy succeeded:
  **alembic_version = 0055, all 5 indexes valid+ready, 0 invalid db-wide, API health 200.**
  LESSON: any IMMUTABLE-function expression index must schema-qualify unaccent/dictionary calls.
- **STILL PENDING (operator, needs prod R2 creds):** run
  `python -m scripts.migrate_metadata_export_paths --apply` (STORAGE_BACKEND=s3) or existing metadata
  exports orphan under the old `<slug>/` paths (batch-3 re-keyed to `<slug>-<client_id>/`). Non-urgent,
  no data loss.

## DEFERRED (medium/low, reported by the implementing agents; safe to leave)
- Password-reset JWT invalidation — needs a `User.tokens_valid_after` column + migration.
- version_number MAX+1 (reports executor/report_service) + non-genesis double-submit
  (portal._resolve_supersedes) + first-time get-or-create (requirement_service) race windows.
- Migration 0044 downgrade platform_admin preservation; cron DB-SSL/migration-head parity.
- Canonical entity-status enum (no agreed allowed set; `inactive` used freely today).
- Reviewer-detail `can_cancel`/`reviewer_note` backend field emission; vendor_id "Proveedor en
  pantalla" echo + history delimiting in wise/ai.py.
- spawned task_caff8839 — admin-renewals (client_id,vendor_id) pairing safety net.
