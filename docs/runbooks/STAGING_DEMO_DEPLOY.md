# Staging / Demo Deployment Runbook

This runbook creates an online CheckWise environment that mirrors production code and infrastructure while using a separate database, storage bucket, URLs, secrets, and synthetic test data.

Use this for guided user testing with Mayela, Anwar, Mina Olaez, Paco, or internal LegalShelf reviewers. Do not use real customer documents in this environment.

## Target Shape

| Layer | Production | Staging / demo |
| --- | --- | --- |
| Frontend | Vercel production project / domain | Separate Vercel project or preview domain |
| Backend | Render `checkwise-api` | Render `checkwise-api-demo` |
| Database | Production Neon project / branch | Separate Neon project or isolated staging branch |
| Storage | R2/S3 `checkwise-prod` | R2/S3 `checkwise-demo` |
| Secrets | Production-only | New staging-only values |
| Data | Real tenants and documents | Synthetic tenants and synthetic PDFs only |

The staging/demo environment should run the same Git commit as production, but should never share production database credentials, object storage credentials, or buckets.

## Naming Convention

Recommended names:

- Render backend: `checkwise-api-demo`
- Render renewal cron: `checkwise-renewal-dispatch-demo`
- Render reporting cron: `checkwise-reporting-dispatch-demo`
- Vercel frontend: `checkwise-web-demo`
- Neon database: `checkwise-demo`
- R2/S3 bucket: `checkwise-demo`
- Public frontend URL: `https://checkwise-demo.vercel.app`
- Public backend URL: `https://checkwise-api-demo.onrender.com`

## Step 1: Create Isolated Infrastructure

Create a new managed Postgres database. Neon is the easiest fit because the existing backend already expects pooled and direct connection strings.

Create:

- `DATABASE_URL`: pooled connection URL for runtime.
- `DIRECT_DATABASE_URL`: direct connection URL for Alembic migrations.

Create a new S3-compatible bucket, preferably Cloudflare R2:

- Bucket: `checkwise-demo`
- Access key: staging/demo only
- Secret key: staging/demo only
- Endpoint: `https://<account_id>.r2.cloudflarestorage.com`
- Region: `auto` for R2

Do not reuse the production bucket or production access keys.

## Step 2: Deploy Backend On Render

The existing `render.yaml` is production-named, so the safest demo setup is to create a second Render service manually using the same settings:

- Runtime: Python
- Root directory: `apps/api`
- Branch: `main`, or a dedicated branch such as `demo`
- Build command: `pip install -e . && playwright install --with-deps chromium`
- Pre-deploy command: `alembic upgrade head`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/health`

Set these required environment variables:

```bash
CHECKWISE_ENV=staging
PYTHON_VERSION=3.11
DATABASE_URL=<demo pooled postgres url>
DIRECT_DATABASE_URL=<demo direct postgres url>
CORS_ORIGINS=https://checkwise-demo.vercel.app
STORAGE_BACKEND=s3
STORAGE_BUCKET=checkwise-demo
AWS_S3_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com
AWS_ACCESS_KEY_ID=<demo key>
AWS_SECRET_ACCESS_KEY=<demo secret>
AWS_REGION=auto
AUTH_JWT_SECRET=<new demo secret from openssl rand -hex 32>
FRONTEND_BASE_URL=https://checkwise-demo.vercel.app
```

Recommended demo defaults:

```bash
CHECKWISE_LLM_BACKEND=mock
OCR_ENABLED=false
MESSAGING_ENABLED=false
TWILIO_ENABLED=false
WHATSAPP_ENABLED=false
WHATSAPP_NATIVE_TEMPLATES_ENABLED=false
NEXT_PUBLIC_DEMO_MODE=true
```

Optional feedback delivery:

```bash
SLACK_BOT_TOKEN=<staging Slack bot token>
SLACK_FEEDBACK_CHANNEL_ID=<channel id>
SLACK_CONTACT_WEBHOOK_URL=<optional webhook>
SLACK_CORRECTION_WEBHOOK_URL=<optional webhook>
```

## Step 3: Deploy Frontend On Vercel

Create a separate Vercel project for the demo frontend.

Use:

- Framework: Next.js
- Root directory: `apps/web`
- Build command: `npm run build`
- Install command: `npm install`

Set:

```bash
NEXT_PUBLIC_API_BASE_URL=https://checkwise-api-demo.onrender.com
NEXT_PUBLIC_DEMO_MODE=true
NEXT_PUBLIC_WHATSAPP_SUPPORT_URL=
NEXT_PUBLIC_SUPPORT_QR_PLACEHOLDER_URL=
```

After Vercel gives you the demo URL, update Render:

```bash
CORS_ORIGINS=https://checkwise-demo.vercel.app
FRONTEND_BASE_URL=https://checkwise-demo.vercel.app
```

If Vercel creates a different URL, use that exact origin. CORS must not include a trailing slash.

## Step 4: Commit Flow

Use a normal code commit. Do not commit `.env`, secrets, ZIP files, or real PDFs.

Recommended pre-commit verification:

```bash
cd apps/api
.venv/bin/ruff check .
.venv/bin/python -m pytest -q

cd ../web
npm run typecheck
npm run lint -- --quiet
npm run build
```

Commit only the files needed for the deployment or test setup:

```bash
git status --short
git add <specific files>
git commit -m "docs: add staging demo deploy runbook"
git push origin main
```

If using a dedicated demo branch:

```bash
git checkout -b demo/user-testing
git add <specific files>
git commit -m "chore: prepare user testing demo environment"
git push origin demo/user-testing
```

Point Render and Vercel at that branch while the test is active.

## Step 5: Seed Synthetic Test Data

The current `apps/api/scripts/seed_user_testing_scenario.py` is intentionally local-only. Do not bypass that guard against production.

For online staging/demo, first confirm all three are true:

1. `CHECKWISE_ENV` is `staging` or `demo`, not `production`.
2. `DATABASE_URL` points to the isolated demo database.
3. `STORAGE_BUCKET` points to the isolated demo bucket.

Then create a staging-safe seeder or update the local seeder with:

- An explicit `ALLOW_USER_TESTING_SEED=1` guard.
- A refusal when `CHECKWISE_ENV=production`.
- A refusal unless the database hostname or project name is the demo database.
- A refusal unless `STORAGE_BUCKET` contains `demo`, `staging`, or `user-testing`.
- Deletes limited to records tagged with `user_testing_2026_06_01`.
- No access to the original ZIP or any real PDFs.
- No passwords printed in deploy logs.

Run it from a Render shell or one-off job only after migrations pass.

## Step 6: Smoke Test

Verify backend:

```bash
curl https://checkwise-api-demo.onrender.com/health
```

Verify frontend:

- Open the Vercel demo URL.
- Log in as Mayela and confirm three providers: Alfa green, Beta yellow, Cobre red.
- Log in as Anwar and confirm the reviewer queue loads.
- Log in as Mina Olaez and confirm the provider workspace, calendar, upload, and documents pages load.

Verify storage:

- Upload one synthetic PDF.
- Confirm the object appears in the demo R2/S3 bucket.
- Confirm download or preview works from the UI.

Verify feedback:

- Use the in-app `Reportar` button.
- Confirm a row appears in `/admin/feedback-reports`.
- If Slack is configured, confirm the message arrives in the selected channel.

## Step 7: Tester Access

Share credentials privately, not in PDFs or Slack channels.

Send testers:

- Demo URL.
- Their assigned role.
- Their testing guide PDF.
- Reminder: only synthetic PDFs, no real documents.
- Feedback channel: in-app `Reportar`, session recording, or the shared issue CSV.

## Step 8: Teardown Or Reset

After the testing cycle:

- Export feedback reports.
- Export or snapshot relevant logs.
- Rotate demo passwords.
- Either keep the environment for the next pilot or disable public tester accounts.
- Do not copy demo data into production.

If resetting, rerun only the staging-safe seeder against the isolated demo database and bucket.

## Deployment Gate

Do not invite testers until all are true:

- Backend health check is green.
- Frontend points to the demo backend, not localhost or production.
- Migrations completed on the demo database.
- Storage writes to the demo bucket.
- Synthetic seed data is visible in all three roles.
- Feedback capture has a clear owner.
- No real documents are present in the demo bucket.
