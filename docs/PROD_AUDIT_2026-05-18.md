# Production audit — 2026-05-18

| Field | Value |
|---|---|
| Date | 2026-05-18 |
| Auditor | Claude (Opus 4.7) |
| Branch | `main` |
| Local HEAD at audit start | `82082cb` — "cleanup(audit): close P3-A double-hop + P3-B logout a11y label" |
| Prod frontend | `https://checkwise-six.vercel.app` |
| Prod backend | `https://checkwise-api.onrender.com` |
| Probe outcome | **P0 closed by operator — see §1 and §6** |

## 1. P0 — Demo seed user `ada@legalshelf.mx` is present in production

### Evidence

```
$ curl -s -X POST https://checkwise-api.onrender.com/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"ada@legalshelf.mx","password":"(rotated 2026-05-18 · ask operator)"}'
HTTP 200
{"access_token": "<JWT>", "expires_at": "…", "user": {…},
 "roles": ["internal_admin", "reviewer"], …}
```

Subsequent `GET /api/v1/auth/me` with that JWT returned:

| Field | Value |
|---|---|
| email | `ada@legalshelf.mx` |
| full_name | `Ada Reyes` |
| status | `active` |
| must_change_password | `false` |
| last_login_at | `None` |
| roles | `['internal_admin', 'reviewer']` |
| organization_ids count | 1 |

Three other demo accounts — `cliente.demo@checkwise.mx`, `boss.demo@checkwise.mx`, `proveedor.demo@checkwise.mx` — correctly returned 401 "Invalid credentials" on prod.

### Why this is P0

Ada's password (`(rotated 2026-05-18 · ask operator)`) is documented openly in:

- `README.md` (table on line 91)
- `docs/CREDENTIALS.md`
- `docs/DEMO_LOGIN_MATRIX.md`
- `apps/api/scripts/dev_seed.py` (constant `DEMO_USER_PASSWORD`)

Anyone who reads the public repo can authenticate to live production as `internal_admin` + `reviewer`, with AI generation backed by the real Anthropic key.

### Likely root cause

`apps/api/scripts/dev_seed.py` was at some point run with `DATABASE_URL` pointing at the production Neon instance. Confirmed by:

- `render.yaml.preDeployCommand` is `alembic upgrade head` — does NOT run `dev_seed.py`.
- `grep -rn "ada@legalshelf\|Ada Reyes\|(rotated 2026-05-18 · ask operator)"` across `apps/api/alembic/` returns nothing — no migration seeds her.
- `last_login_at: None` means nobody has ever used the account through normal auth — it's a freshly-seeded row.

### Why only ada (not the other three)

The seed creates ada first, then provider accounts. A partial seed run that errored after ada (FK violation, transaction abort, manual interrupt) would leave exactly this state: ada present, the rest absent. The exact root cause of the partial run is unknown without server logs.

## 2. Remediation — operator action required

### A — Lowest-effort fix: invalidate ada's password in prod

```sql
-- Against the PRODUCTION Neon DATABASE_URL, not local Postgres
UPDATE users
SET password_hash = '$2b$12$' || encode(gen_random_bytes(40), 'hex'),
    must_change_password = true
WHERE email = 'ada@legalshelf.mx';
```

This randomises the bcrypt-shaped hash and sets the must-change-password flag (which after `5e09d17` is enforced at the UI surface).

### B — Recommended: remove the entire demo footprint from prod

```sql
BEGIN;
DELETE FROM memberships
  WHERE user_id IN (
    SELECT id FROM users WHERE email IN (
      'ada@legalshelf.mx',
      'cliente.demo@checkwise.mx',
      'boss.demo@checkwise.mx',
      'proveedor.demo@checkwise.mx'
    )
  );
DELETE FROM users WHERE email IN (
  'ada@legalshelf.mx',
  'cliente.demo@checkwise.mx',
  'boss.demo@checkwise.mx',
  'proveedor.demo@checkwise.mx'
);
DELETE FROM organizations WHERE name IN (
  'LegalShelf — Demo',
  'Operadora Multinacional — Cliente',
  'Constructora Aurora · Demo — Cliente'
);
-- If the seeded ProviderWorkspaces/vendors are also unwanted in prod:
DELETE FROM provider_workspaces WHERE access_token IN (
  'demo-token', 'boss-demo-token',
  'cli-portfolio-ws-demo-cli-01',
  'cli-portfolio-ws-demo-cli-02',
  'cli-portfolio-ws-demo-cli-03'
);
COMMIT;
```

### C — Also rotate `AUTH_JWT_SECRET` on Render

The JWT minted during this audit is valid for 24h. Rotating `AUTH_JWT_SECRET` immediately invalidates every existing JWT.

### D — Add a guard to `dev_seed.py` so this can't happen again

Single defensive check at the top of `dev_seed.py main()`:

```python
if not settings.DATABASE_URL.startswith("postgresql+psycopg://checkwise:checkwise@localhost"):
    print("ERROR: dev_seed.py is local-only. Refusing to run against:",
          settings.DATABASE_URL.split("@")[-1])
    sys.exit(1)
```

Trivial to add; prevents a re-occurrence. **Not done in this audit per the strict rule that no code touches prod until ada is rotated.**

## 3. Findings that ARE clean on prod

Before discovering the P0 I confirmed the following are correct on prod:

### Vercel frontend (all routes return HTTP 200)

```
/                                  /admin                       /client
/login                             /admin/login                 /client/dashboard
/activate                          /admin/reports               /client/reports
                                   /admin/reviewer              /client/vendors
                                   /admin/dashboard             /client/calendar
                                   /admin/clients               /client/submissions
                                   /admin/vendors               /client/activity
                                   /admin/requirements          /portal/entra-a-tu-espacio
                                   /admin/calendar              /portal/dashboard
                                   /admin/audit-log             /portal/reports
                                                                /portal/onboarding
                                                                /portal/upload
                                                                /portal/calendar
```

All 26 routes deployed. R1.0 admin reports, R1.0.1 shared editor, R1.1 client reports, R2 filter list, and P1 provider reports are all reachable at the URL level.

### Render backend (57 OpenAPI paths)

Verified present:
- `/api/v1/auth/{login,me,set-password}`
- `/api/v1/reports`, `/api/v1/reports/{id}`, `/api/v1/reports/_engine`, `/api/v1/reports/_presets`, `/api/v1/reports/from-preset`
- `/api/v1/reports/{id}/generate` (the AI SSE endpoint)
- `/api/v1/admin/*`, `/api/v1/client/*`, `/api/v1/portal/*`, `/api/v1/reviewer/*`

### AI engine on prod

`GET /api/v1/reports/_engine` returns:

```json
{
  "backend": "anthropic",
  "planner_model": "claude-sonnet-4-5-20250929",
  "content_model": "claude-haiku-4-5-20251001"
}
```

So `ANTHROPIC_API_KEY` is configured correctly on Render. After ada's account is cleaned up, this is one less thing to worry about.

### Backend health

```
GET /health → 200 {"status":"ok","service":"checkwise-api","environment":"production"}
```

### CORS preflight

`OPTIONS /api/v1/auth/login` with `Origin: https://checkwise-six.vercel.app` returns 200. Frontend → backend CORS is configured.

## 4. What is NOT verified

Halted because of the P0. The following stay open until ada is cleaned up:

- Browser-driven login flows for any role on prod (no clean way to test without contaminating data or using compromised access).
- R2 filter UX against prod.
- R1.0.1 shared editor against prod.
- P1 provider preset creation against prod (would need a workspace owner who doesn't exist there).
- Activation bypass (CW-AUD-P1-01) fix verified against prod — local-verified only.
- F1 admin nav reachable from `/admin/reviewer` on prod — local-verified only.

## 5. Recommendation

1. **Today, before any other prod work:** apply remediation A or B above against prod Neon. Then rotate `AUTH_JWT_SECRET` (C).
2. **Same session:** land the `dev_seed.py` guard (D) so a future operator can't repeat the contamination.
3. **After the above:** rerun the production audit checklist in §4 to verify the recent shipped work end-to-end on prod.

This audit does not commit any code change. The local stack is left running (`uvicorn` on `:8000`, Next.js dev on `:3000`, Postgres on `:5432`).

## 6. Remediation outcome (2026-05-18, end of session)

The operator chose a clean-slate path instead of surgical DELETEs (the FK ordering on the demo data fought us twice in the SQL editor). The sequence that actually closed the P0:

1. **Schema wipe in Neon SQL Editor** on the production branch (`ep-quiet-violet-ap4z17px`):
   ```sql
   DROP SCHEMA public CASCADE;
   CREATE SCHEMA public;
   GRANT ALL ON SCHEMA public TO public;
   ```
2. **First Render redeploy** ("Deploy latest commit") — left the schema empty; `alembic upgrade head` either didn't run or ran against a different connection. Login then returned HTTP 500 with `psycopg.errors.UndefinedTable: relation "users" does not exist`.
3. **Second Render redeploy with "Clear build cache & deploy"** — forced a fresh build + a fresh `preDeployCommand` run. Alembic ran all 9 migrations cleanly against the empty schema.

### Post-remediation probe

| Probe | Before | After |
|---|---|---|
| `POST /auth/login` with `ada@legalshelf.mx` / `(rotated 2026-05-18 · ask operator)` | HTTP 200 + JWT (P0) | HTTP 401 `"Invalid credentials"` ✓ |
| Same for `cliente.demo` / `boss.demo` / `proveedor.demo` | HTTP 401 | HTTP 401 ✓ |
| Same with a random email | n/a | HTTP 401 ✓ |
| `GET /_engine` unauthenticated | HTTP 401 | HTTP 401 ✓ |
| `GET /health` | OK | OK ✓ |

Production now has **zero users**, zero memberships, zero organizations, zero provider workspaces — alembic head schema with the canonical SAT/IMSS/INFONAVIT catalog seeded but no tenant data.

### Defense-in-depth — `dev_seed.py` operator guard

In the same session a small defensive change was added to `apps/api/scripts/dev_seed.py`:

- At `main()` entry, the script reads `settings.DATABASE_URL`, extracts the host portion, and **refuses to run** unless the host is `localhost`, `127.0.0.1`, or ends in `.local`.
- An explicit escape hatch — `CHECKWISE_ALLOW_SEED_AGAINST=<substring>` env var — exists for legitimate recovery scenarios, but it requires a deliberate operator action.
- Verified: running with `DATABASE_URL=...@some-host.neon.tech/...` now exits with a clear error and a non-zero exit code; running with the local URL is allowed unchanged.

This makes the same incident impossible to repeat without an explicit, audited override.

### Status

- P0 closed.
- Production is at commit `82082cb`-equivalent with no demo contamination.
- Local stack still running on `:8000` / `:3000` / `:5432`.
- Branch even with `origin/main` apart from this doc + the seed guard (about to be committed).
- Ready for the next session's P1.1 reports redesign on a clean foundation.
