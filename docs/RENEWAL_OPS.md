# Renewal reminder ops

Operational runbook for the Phase 6 renewal engine. Covers the daily
Render Cron job, what to do when it misses a day, and the manual
escape hatches.

## What ships today

Phase 6 lands in three slices:

| Slice | What lands |
|-------|------------|
| 6A    | Rule layer: `OnboardingRequirement.renewal_frequency_days` (CSF 90d, REPSE 1095d, patronal 1095d), pure helpers in `evidence_slots`, read-only audit CLI. |
| 6B    | `renewal_reminders` dedupe table + per-cycle/per-threshold idempotency, client + provider notification emit-site, dispatcher orchestrator, manual write CLI. |
| 6C    | Daily Render Cron Job that invokes the dispatch CLI. |

## The cron job

Defined in [`render.yaml`](../render.yaml) under the
`checkwise-renewal-dispatch` service:

- **Schedule**: `0 14 * * *` (14:00 UTC = 08:00 America/Mexico_City
  year-round; Mexico City dropped DST in 2022).
- **Command**: `python -m scripts.run_renewal_dispatch`
- **Env**: only `DATABASE_URL` is required, sourced from the existing
  `checkwise-api` web service via `fromService`.

Each run:

1. Walks every `ProviderWorkspace`.
2. For each renewal-bearing onboarding requirement (CSF, REPSE,
   registro patronal), resolves the current approved submission, the
   cycle anchor date, and the days until the next renewal due date.
3. For each threshold that has crossed since the last successful
   run, inserts a `renewal_reminders` row and emits one client +
   one provider notification.
4. Commits per workspace so a failure on one provider doesn't
   abort the rest of the batch.

The unique constraint on `renewal_reminders(workspace_id,
requirement_code, cycle_anchor_date, threshold_days)` is the entire
dedupe mechanism. A repeat run on the same day is a no-op for
already-emitted thresholds.

## Cadence the cron implements

| `days_remaining` | Severity | Notification type |
|------------------|----------|-------------------|
| `30`             | yellow   | `renewal_due_soon` |
| `14`             | yellow   | `renewal_due_soon` |
| `7`              | yellow   | `renewal_due_soon` |
| `0`              | **red**  | `renewal_overdue`  |
| `-7`             | red      | `renewal_overdue`  |
| `-14`            | red      | `renewal_overdue`  |
| `-21`            | red      | `renewal_overdue`  |
| `-28`            | red      | `renewal_overdue`  |
| past `-28`       | (silent) | —                  |

Each crossing fires exactly once per cycle. A new approved upload
shifts the cycle anchor, resets all eight slots, and the cadence
walks again under the new anchor.

## What to do if the cron fails

Render emails the project owner on non-zero exit. The CLI exits 0 on
success.

**Catch-up is automatic.** The `thresholds_crossed(days_remaining)`
function emits every threshold that has crossed since the last
successful run. If the cron misses 3 days and 2 thresholds crossed
in that window, the next run emits both — no notifications get
silently dropped.

**To rerun manually after a failed cron**:

```bash
# From a Render shell (easiest):
python -m scripts.run_renewal_dispatch

# Or from a local checkout against the prod DATABASE_URL:
DATABASE_URL='postgres://...' .venv/bin/python -m scripts.run_renewal_dispatch
```

**To audit what WOULD fire without writing anything** (use this
before flipping the cron on for the first time, or before a
production rerun):

```bash
python -m scripts.run_renewal_dispatch --dry-run
```

Dry-run rolls back the session — no `renewal_reminders` rows are
inserted, no notifications are written. Output shows the intended
emit set.

**To preview a future or past date** (cadence math runs against the
override, not the system clock):

```bash
python -m scripts.run_renewal_dispatch --today 2026-12-01 --dry-run
```

**To dispatch a single workspace** (incident scoped to one provider):

```bash
python -m scripts.run_renewal_dispatch --workspace-id <uuid>
```

## Read-only diagnostics

The Slice 6A audit CLI is the read-only counterpart — never writes,
useful for "what should the dashboard be showing for this provider?"

```bash
python -m scripts.run_renewal_audit
python -m scripts.run_renewal_audit --only-due
python -m scripts.run_renewal_audit --today 2026-12-01
```

## Verifying a delivery in the DB

After a cron run, the audit trail lives in three places:

| Table                         | What you'll see                          |
|-------------------------------|------------------------------------------|
| `renewal_reminders`           | One row per (workspace, requirement, cycle, threshold) — the dedupe record. |
| `client_notifications`        | Yellow / red rows with `notification_type` ∈ {`renewal_due_soon`, `renewal_overdue`}. |
| `provider_notifications`      | Same shape on the portal side, scoped by `workspace_id`. |

To check what the cron fired on its most recent run:

```sql
SELECT created_at, workspace_id, requirement_code, threshold_days, severity
FROM renewal_reminders
ORDER BY created_at DESC
LIMIT 50;
```

## Out of scope (will land later)

- **Frontend renewal pill / dashboard surface**. Notifications surface
  in the existing client + portal inboxes today via the same
  `notification_type` discriminator other notifications use; a
  dedicated renewal widget is a separate frontend slice.
- **Email / WhatsApp delivery**. Per the locked Phase 6 roadmap,
  in-app first. Email and WhatsApp emit-sites consume the same
  dispatcher when they ship.
- **Recurring-calendar renewals** (monthly IMSS, etc.). The dashboard's
  suggested-actions list already drives "due soon" for the recurring
  calendar; the renewal dispatcher is onboarding-only.
