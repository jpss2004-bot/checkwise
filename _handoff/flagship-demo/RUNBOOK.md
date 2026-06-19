# Flagship Demo — Production Runbook & Login Matrix

How to put the flagship demo tenant on production (checkwise.com.mx) so a prospect can log into the live app, plus how to roll it back. Built + verified locally; this is the prod-promotion procedure.

> **You run the prod write.** Build/verify happened locally. The prod seed is a single command behind `--confirm-prod`; the only prerequisite is a Neon snapshot for a clean rollback anchor.

---

## Login matrix

| Role | URL | Email | Password | Lands on |
|---|---|---|---|---|
| **Client** | https://checkwise.com.mx/login | `demo.cliente@checkwise.mx` | `Cliente2026Demo!` | `/client/dashboard` (92%, 1 red) |
| **Provider** (Provider D) | https://checkwise.com.mx/login | `demo.proveedor@checkwise.mx` | `Proveedor2026Demo!` | `/portal` (calendar; 5 docs to upload) |

Both have legal consent pre-accepted → no consent wall. To **approve** a provider's freshly uploaded document live (the "watch it turn green" beat), use an existing internal reviewer/staff account in the global review queue (`/admin`); the flagship seeder intentionally does **not** create internal staff.

---

## Pre-flight

1. **Confirm target.** You are seeding the **production** Neon DB + the production R2/S3 bucket. Branded + real PDF bytes are uploaded to object storage under `flagship-demo/_blobs/`.
2. **Take a Neon snapshot** (named pre-deploy sibling branch) as the rollback anchor — e.g. `pre-flagship-demo-2026-06-17`. (See `reference_neon_snapshots`.)
3. **Check for email collisions.** The demo emails (`demo.cliente@checkwise.mx`, `demo.proveedor@checkwise.mx`) and RFC `CIA180115R30` must not already belong to a real account. They are namespaced specifically to avoid the `dev_seed` accounts; verify nothing live uses them.
4. **Env.** Have the prod `DATABASE_URL`, `STORAGE_BACKEND=s3`, `STORAGE_BUCKET`, and R2/S3 creds available (the same env Render uses).

---

## Seed production

```bash
cd apps/api

# Load prod env (however you normally source it), then:
CHECKWISE_ENV=production \
DATABASE_URL='postgresql+psycopg://…neon…/checkwise' \
STORAGE_BACKEND=s3 \
STORAGE_BUCKET='checkwise-prod' \
AWS_ACCESS_KEY_ID=… AWS_SECRET_ACCESS_KEY=… AWS_S3_ENDPOINT=… \
  .venv/bin/python scripts/seed_flagship_demo.py --apply --confirm-prod
```

Expected tail:
```
Seeded flagship tenant: client_id=…
Reports: 3   Blobs uploaded: 57
Client login:   demo.cliente@checkwise.mx / Cliente2026Demo!
Provider login: demo.proveedor@checkwise.mx / Proveedor2026Demo!  (Provider D)
Portfolio mean (simple): 92%   ·   red providers: 1
```

It auto-tears-down its own tenant first, so re-running is safe and idempotent.

---

## Smoke-test (live)

1. **Client login** → `/client/dashboard`: 92% donut, "Tienes 1 proveedor en riesgo", 5 workspaces, notifications bell shows a count.
2. **`/client/vendors`**: 1 al día / 3 en proceso / 1 en riesgo; Transportes del Golfo = En riesgo 83%.
3. **Open a document** on any provider → renders a real PDF (E's CSF shows the VENCIDO watermark). *This is the critical check — confirms R2 bytes serve.*
4. **`/client/reports`**: the 3 reports open with data.
5. **"Preparar paquete para auditoría"**: preview shows hundreds of files across the 5 providers.
6. **Provider login** → `/portal`: Provider D dashboard/calendar with the missing obligations visible.
7. **Read-only re-check** anytime: `… scripts/seed_flagship_demo.py --measure` (no writes).

---

## Rollback / teardown

**Clean teardown (preferred):**
```bash
CHECKWISE_ENV=production DATABASE_URL=… STORAGE_BACKEND=s3 STORAGE_BUCKET=… AWS_…=… \
  .venv/bin/python scripts/seed_flagship_demo.py --teardown --confirm-prod
```
Removes the flagship client tenant, its 2 demo users, and its unreferenced blobs only. Leaves every other tenant untouched.

**Hard rollback:** restore the `pre-flagship-demo-2026-06-17` Neon snapshot.

---

## Notes

- **No migration** required — uses existing tables.
- **Refresh dates:** the scenario is pinned to "today = 2026-06-15". If the demo runs much later and "última actividad" feels stale, bump `TODAY` in `seed_flagship_demo.py` and re-`--apply`.
- **Rotate credentials** if these passwords are shared widely; they are demo-grade by design.
- **Don't run the local `dev_seed`/`seed_demo_*` scripts against prod** — only the flagship seeder is intended for this tenant.
