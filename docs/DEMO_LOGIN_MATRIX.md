# Demo login matrix

**Synthetic local-dev credentials only.** These accounts are seeded by
`apps/api/scripts/dev_seed.py` against your local Postgres. Production
(Vercel + Render + Neon) has none of them — see
`docs/CREDENTIALS.md` for the rationale.

The login form at `/login` routes every user via the same
`decideDestination(session, mustChangePassword)` logic in
`apps/web/app/login/page.tsx`:

```
must_change_password=true                       → /activate
roles ∋ internal_admin OR reviewer              → /admin/reviewer
roles ∋ client_admin                            → /client/dashboard
otherwise (empty roles)                         → /portal/entra-a-tu-espacio
```

## The four seeded accounts

| User type | Email | Password | Roles (Membership.role) | Landing route | What to test |
|---|---|---|---|---|---|
| **Admin / reviewer** | `ada@legalshelf.mx` | `(rotated 2026-05-18 · ask operator)` | `internal_admin`, `reviewer` | `/admin/reviewer` | review queue, audit log, clients, vendors, requirements, calendar, **all R1.0 reports presets** at `/admin/reports` |
| **Client admin** | `cliente.demo@checkwise.mx` | `(rotated 2026-05-18 · ask operator)` | `client_admin` | `/client/dashboard` | client portfolio view, 3 seeded vendors, vendor risk surface, seeded `client_facing` reports at `/portal/reports` |
| **Provider — onboarded** | `boss.demo@checkwise.mx` | `(rotated 2026-05-18 · ask operator)` | *(none)* | `/portal/entra-a-tu-espacio` → `/portal/dashboard` | post-onboarding provider workspace, seeded submissions, calendar |
| **Provider — first login** | `proveedor.demo@checkwise.mx` | `(rotated 2026-05-18 · ask operator)` | *(none)* | `/activate` (forced password change) | activation flow, `/portal/onboarding` gate |

## Notes per account

### `ada@legalshelf.mx`
- Holds **both** `internal_admin` and `reviewer` roles in the `LegalShelf — Demo` org.
- Only account that can use the R1.0 admin preset gallery at `/admin/reports`.
- Sees all four `ReportAudience` values via `visible_audiences()`.

### `cliente.demo@checkwise.mx`
- Single `client_admin` membership in `Operadora Multinacional — Cliente`.
- Portfolio has 3 seeded vendors with mixed compliance states.
- Sees only `client_facing` reports per `visible_audiences()`.
- **No preset cards yet** at `/portal/reports` — client-targeted presets land in slice R1.1.

### `boss.demo@checkwise.mx`
- Has a `ProviderWorkspace` row (`ws-demo-0002`) with `onboarding_completed_at` already set, so the `withOnboardingGate` HOC lets her through to `/portal/dashboard` immediately.
- **No memberships** by design — gives her empty roles so the login router sends her to the provider flow. (An earlier seed version granted `client_admin` to populate `/portal/reports`; that was the wrong fix and was reverted on 2026-05-18 because it broke her primary route.)

### `proveedor.demo@checkwise.mx`
- Has `must_change_password=true` and **no memberships**.
- Login lands on `/activate` (forced password rotation).
- After activation, `withOnboardingGate` requires completing `/portal/onboarding` before the dashboard unlocks.

## Re-seeding

The script wipes its own demo rows and re-inserts them deterministically:

```bash
cd backend
.venv/bin/python scripts/dev_seed.py
```

If `compliance_snapshots` rows from prior AI-generation tests block the wipe with FK errors, clear them first:

```bash
docker exec checkwise-postgres psql -U checkwise -d checkwise -c "
UPDATE report_versions SET source_snapshot_id = NULL WHERE source_snapshot_id IS NOT NULL;
DELETE FROM compliance_snapshots;"
```

## Production login

Production does not have any of these accounts. Do not paste these credentials into the deployed Vercel UI — they will return 401, which is correct.
