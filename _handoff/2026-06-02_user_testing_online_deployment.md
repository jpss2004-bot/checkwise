# Handoff — Finish deploying the user-testing scenario to production

**Date:** 2026-06-02
**Author:** previous Claude session (Jose Pablo + Claude)
**Status:** infrastructure shipped to `main`; deployment to prod not yet executed; testers not yet invited.

---

## 30-second TL;DR

We built a complete machinery for spinning up a synthetic user-testing tenant
(3 providers — Alfa/green, Beta/yellow, Cobre/red — with 161 documents, 5 user
accounts, full status diversity). It works perfectly locally. **It has not yet
been deployed to production.** Your job is to finish that: fix one small bug,
run a UI walkthrough, send Paco the Slack message for sign-off, then run the
prep + SQL files against the prod Neon DB and R2 bucket.

---

## What's already done (committed to `main`)

Two commits pushed yesterday:

| SHA | What |
|---|---|
| `b281e43` | `feat(api): add local-only user-testing seed script` — Codex's original Python seeder at `apps/api/scripts/seed_user_testing_scenario.py` |
| `20f6392` | `feat(api): add SQL-driven user-testing prep for online deployment` — the prod-safe layer: `apps/api/scripts/sql/ut_2026_06_01_seed.sql`, `ut_2026_06_01_teardown.sql`, and `apps/api/scripts/ut_2026_06_01_prep.py`, plus `.gitignore` additions |

Both auto-deploy to Render (backend) and Vercel (frontend) on push.

**Local end-to-end verification yesterday confirmed:**
- All 3 testers authenticate via `/api/v1/auth/login`
- `/client/overview` returns 1 green / 1 yellow / 1 red semaphore, 161 submissions
- Status distribution: 151 aprobado, 3 pendiente_revision, 3 rechazado, 2 requiere_aclaracion, 1 posible_mismatch, 1 vencido
- PDFs round-trip through storage (downloaded one and confirmed valid PDF v1.4)
- Tenant isolation works (Anwar admin-wide; Mayela and Mina only their slice)

---

## What's left, in order

### 1. Fix the `ON CONFLICT` bug on `periods` (10 min)

**Bug:** both `apps/api/scripts/sql/ut_2026_06_01_seed.sql` and the SQL emitted
by `apps/api/scripts/ut_2026_06_01_prep.py` use `ON CONFLICT (id) DO NOTHING`
on the `periods` table. But the real-world unique constraint that collides
when another seeder has run is `(code, period_type)` — index name
`uq_periods_code_type`. Yesterday this forced a teardown-before-seed dance
that should not be necessary.

**Fix:** change two locations to `ON CONFLICT (code, period_type) DO NOTHING`.

- `apps/api/scripts/sql/ut_2026_06_01_seed.sql` — search for the periods
  INSERT block (around the 4 well-known periods: alta_inicial, 2026-M03,
  2026-M04, 2026-M05).
- `apps/api/scripts/ut_2026_06_01_prep.py` — find `emit_period_inserts()`
  and update the `ON CONFLICT (id) DO NOTHING` clause there.

After the fix, regenerate the submissions SQL locally to confirm the
emitted file uses the new clause:

```bash
cd "/Users/josepablosamano/Desktop/Work — LegalShelf/checkwise/CheckWise/apps/api"
.venv/bin/python scripts/ut_2026_06_01_prep.py --dry-run
grep -c "ON CONFLICT (code, period_type)" scripts/sql/ut_2026_06_01_submissions.generated.sql.dryrun
# Expect ≥ 18 (one per emitted period row)
```

Commit + push.

### 2. UI walkthrough as each role (20 min — needs human eyes)

Yesterday I verified via the API only. Before testers see this, click
through each role's actual UI:

```bash
# Kill the stale local Next dev server first
ps -ef | grep "next-server" | grep -v grep
# Find the long-running PID (it'll be the one running since "Tue 12PM" or whatever)
kill <PID>

cd "/Users/josepablosamano/Desktop/Work — LegalShelf/checkwise/CheckWise/apps/web"
npm run dev
# Then http://localhost:3000/login
```

Log in as each of the three. Hit:
- **Mayela** (`mayela.user-test@checkwise.local` / `MayelaLocal!2026`):
  dashboard portfolio with 3 providers, click into a vendor, click into a
  PDF.
- **Anwar** (`anwar.user-test@checkwise.local` / `AnwarLocal!2026`): admin
  views (clients, vendors, workspaces, audit log), review queue showing
  Beta's pendings + Cobre's mismatch.
- **Mina** (`mina.olaez.user-test@checkwise.local` / `MinaLocal!2026`):
  provider portal — onboarding gate complete, upcoming deadlines visible,
  some "needs action" items present.

If something looks ugly or confusing for testers, fix it before deploying
online.

### 3. Send Paco the Slack message (5 min)

Codex drafted the Spanish message yesterday. It's in the previous Codex
conversation transcript, starting "Hola Paco, ¿cómo estás?" — paste it
into Slack and wait for his green light. He's gating production access.

### 4. Once Paco approves: deploy to prod (15 min)

This is the actual deployment. Pre-flight checklist:

- [ ] Snapshot the prod Neon DB first: log into Neon → branch the prod DB
      OR `pg_dump` to a local file. Insurance against anything sideways.
- [ ] Have prod env values ready: `DATABASE_URL`, `STORAGE_BUCKET`,
      `AWS_S3_ENDPOINT`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`,
      `AWS_SECRET_ACCESS_KEY`. Pull them from Render → backend service →
      Environment, OR from `apps/api/.env.production` if it exists locally.

Run sequence:

```bash
cd "/Users/josepablosamano/Desktop/Work — LegalShelf/checkwise/CheckWise/apps/api"

# Set up prod env in this shell only (do NOT export to .env)
export CHECKWISE_ENV=production
export DATABASE_URL='<prod psycopg URL from Render>'
export STORAGE_BUCKET='<prod bucket from Render>'
export AWS_S3_ENDPOINT='<prod R2 endpoint>'
export AWS_REGION='auto'
export AWS_ACCESS_KEY_ID='<from Render>'
export AWS_SECRET_ACCESS_KEY='<from Render>'

# Step A — generate hashes, PDFs, upload to prod R2, emit submissions SQL.
# The --confirm-prod flag is REQUIRED — prep.py refuses otherwise.
.venv/bin/python scripts/ut_2026_06_01_prep.py --apply --confirm-prod

# Step B — psql URL needs the +psycopg stripped
PSQL_URL=$(echo "$DATABASE_URL" | sed 's/postgresql+psycopg/postgresql/')

# Step C — load the bcrypt hashes
set -a; source out/ut_2026_06_01_hashes.env; set +a

# Step D — run the static seed
psql "$PSQL_URL" \
  -v mayela_hash="$MAYELA_HASH" -v anwar_hash="$ANWAR_HASH" \
  -v alfa_hash="$ALFA_HASH" -v mina_hash="$MINA_HASH" -v cobre_hash="$COBRE_HASH" \
  -f scripts/sql/ut_2026_06_01_seed.sql

# Step E — run the generated submissions
psql "$PSQL_URL" -f scripts/sql/ut_2026_06_01_submissions.generated.sql
```

**Verification:** log into the deployed app (Vercel URL, not localhost) as
each of the three users. Confirm the same things you saw locally in step 2.

### 5. Set up feedback capture (30 min)

Testers need somewhere structured to log findings. Options in order of
ease:

1. **Notion database** with columns: tester / role / page / what happened /
   expected / severity / screenshot / notes. Quickest to set up; Paco and
   Beko already use Notion.
2. **Google Form** mirrored to a Sheet. Lower friction for non-Notion users.
3. **Recorded sessions** (Loom or zoom) — highest signal but highest
   coordination cost.

Recommendation: do **Notion + recorded session for Mayela**. Mayela's
flow is the highest-stakes one (executive-style portfolio view); seeing
her react in real time is more valuable than a form. Mina and Anwar can
use the Notion form async.

Drop the link to the form in the Slack thread with Paco so he sees the
feedback flow.

### 6. Teardown when done

When the testing round is complete:

```bash
cd "/Users/josepablosamano/Desktop/Work — LegalShelf/checkwise/CheckWise/apps/api"

# Same env exports as step 4

PSQL_URL=$(echo "$DATABASE_URL" | sed 's/postgresql+psycopg/postgresql/')

# Database teardown — drops all 161 submissions, 3 vendors, 5 users, etc.
psql "$PSQL_URL" -f scripts/sql/ut_2026_06_01_teardown.sql

# Storage teardown — deletes all PDFs under user-testing/2026-06-01/ in R2
.venv/bin/python scripts/ut_2026_06_01_prep.py --teardown-storage --confirm-prod
```

Verification block at the end of teardown.sql prints residual counts —
must all be 0.

---

## Critical context for the new session

### File locations

- **Repo root:** `/Users/josepablosamano/Desktop/Work — LegalShelf/checkwise/CheckWise`
  (note the em-dash and the doubled `checkwise/CheckWise` — both literal)
- **API:** `apps/api/` — FastAPI + SQLAlchemy + Alembic
- **Web:** `apps/web/` — Next.js 15
- **Python venv:** `apps/api/.venv/bin/python` — must use this; `python3` from
  PATH doesn't have project deps installed
- **Docker:** local Postgres lives in container `checkwise-postgres`
  (db/user/password all `checkwise`)

### The synthetic tenant — what gets created

| Entity | Count | Tag |
|---|---|---|
| Client | 1 | `name LIKE '%User Testing%'`, `rfc = 'CUT260601AA1'` |
| Users | 5 | `email LIKE '%@checkwise.local'` |
| Organizations | 2 | `name LIKE '%User Testing%'` |
| Memberships | 3 | (Mayela client_admin; Anwar internal_admin + reviewer) |
| Vendors | 3 | `rfc IN ('SAS260601AA1','SBS260601BB2','SCS260601CC3')` |
| Workspaces | 3 | `id LIKE 'ut-20260601-%'` |
| Periods | ~22 | `code LIKE 'user_testing_2026_06_01-%'` |
| Submissions | 161 | `comments LIKE '%user_testing_2026_06_01%'` |
| Documents | 161 | `storage_key LIKE 'user-testing/2026-06-01/%'` |
| Audit | 1 | `action = 'user_testing.scenario_seeded'` |

### Tester credentials

| Tester | Email | Password | Role |
|---|---|---|---|
| Mayela | `mayela.user-test@checkwise.local` | `MayelaLocal!2026` | client_admin |
| Anwar | `anwar.user-test@checkwise.local` | `AnwarLocal!2026` | internal_admin + reviewer |
| Mina | `mina.olaez.user-test@checkwise.local` | `MinaLocal!2026` | provider_admin (workspace `ut-20260601-provider-b`) |
| Alfa owner | `provider.alfa.user-test@checkwise.local` | `ProviderAlfa!2026` | provider_admin (workspace `ut-20260601-provider-a`) |
| Cobre owner | `provider.cobre.user-test@checkwise.local` | `ProviderCobre!2026` | provider_admin (workspace `ut-20260601-provider-c`) |

Passwords are bcrypt-hashed per `AUTH_BCRYPT_ROUNDS` (default 12). `prep.py`
regenerates hashes each run; running step D again rotates the passwords.

### Known gotchas

1. **`DATABASE_URL` uses `postgresql+psycopg://`** — that's the SQLAlchemy
   dialect prefix. psql doesn't understand it; always strip `+psycopg` for
   psql commands (the snippet above uses `sed`).
2. **zsh + bcrypt hashes** — bcrypt strings contain `$` which expand in
   double-quoted shell. The `out/ut_2026_06_01_hashes.env` file uses single
   quotes to wrap them — preserve that quoting.
3. **`out/` and `*.generated.sql` are gitignored** — the hashes file and the
   generated SQL should never be committed. Verified.
4. **`_actor_from` precedence risk** (from memory) — `provider_workspaces.owner_user_id`
   silently shadows org memberships in `list_reports`. After seeding, spot-check
   that Mina sees only her workspace's reports, not anything else.
5. **The local-only seeder (`seed_user_testing_scenario.py`) is destructive.**
   It calls `_wipe_existing()` and refuses any non-local env. Do not use it
   online — use `ut_2026_06_01_prep.py --apply --confirm-prod` + the SQL
   files instead.

### Deployment infra (from memory)

- Backend: Render service `checkwise-api`, auto-deploys from `main` on
  `jpss2004-bot/checkwise`
- Frontend: Vercel project, auto-deploys from `main`
- Database: Neon Postgres
- Storage: Cloudflare R2 (S3-compatible)
- Per memory `project_render_env_state`: all required Render env vars are
  populated as of 2026-05-25.

### One ambiguity to confirm with the user before deploying online

**Where does the "synthetic tenant in prod" actually live?**

Yesterday's design conversation went back and forth between three options:

- **A**: separate staging/demo Render + Vercel + Neon + R2 stack (the
  STAGING_DEMO_DEPLOY.md runbook covers this — file is in
  `docs/runbooks/`, untracked, not yet committed)
- **B**: synthetic tenant inside production (this is what the SQL files were
  built for, since prod still has no real paying customers — Phase 1 consent
  gate is DRAFT per memory `project_phase1_consent`)
- **C**: enhanced local with ngrok

Jose Pablo leaned toward B at the end of the design pass. Confirm before
running step 4 — the env values you point at are the only thing that
distinguishes B from A.

---

## Bootstrap prompt for the new session

Copy-paste this into a fresh Claude session to get started:

> Read `_handoff/2026-06-02_user_testing_online_deployment.md` in the
> CheckWise repo at `/Users/josepablosamano/Desktop/Work — LegalShelf/checkwise/CheckWise/`.
> That document is the full handoff from the previous session. We need to
> finish deploying the synthetic user-testing tenant to production.
>
> Start with step 1 (the `ON CONFLICT` bug fix on periods). Then walk
> through steps 2–6 in order, asking me to confirm each step before moving
> on. Be especially careful before step 4 — that's the irreversible one
> that touches prod, and we need Paco's green light first.
>
> The repo already has commits `b281e43` and `20f6392` on `main` with all
> the seed/teardown SQL and prep.py. Don't re-create those — read them,
> fix what's broken, then run them.
