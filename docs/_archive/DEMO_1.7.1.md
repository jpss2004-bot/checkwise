# CheckWise 1.7.1 — Boss Demo Release

Stable build for handing CheckWise to a non-technical reviewer. Two
pre-seeded provider accounts cover the two paths a real provider can
walk: the first-login onboarding flow (Account A) and the returning,
already-set-up dashboard view (Account B).

---

## Demo accounts

| Account | Email | Password | What it shows |
|---|---|---|---|
| **A — First-login provider** | `proveedor.demo@checkwise.mx` | `(rotated 2026-05-18 · ask operator)` | Forced password change → guided initial expediente → manual dashboard activation. Demonstrates the gate. |
| **B — Returning provider** | `boss.demo@checkwise.mx` | `(rotated 2026-05-18 · ask operator)` | Login lands directly on the dashboard. Demonstrates the post-onboarding workspace. |
| Reviewer / admin | `ada@legalshelf.mx` | `(rotated 2026-05-18 · ask operator)` | Internal-staff login → reviewer queue. Optional, only needed to demo the back-office angle. |

Both provider accounts own independent workspaces so they never collide
during a side-by-side demo.

---

## Live URLs

- Frontend (Vercel): https://checkwise-six.vercel.app
- API (Render):    https://checkwise-api.onrender.com  (`/health` returns 200)
- Repo:           https://github.com/jpss2004-bot/checkwise (branch `main`)

---

## Walking the demo

### Account A — Initial Expediente flow

1. Open https://checkwise-six.vercel.app in **incognito** (no stale cookies).
2. Click **Iniciar sesión** in the top-right.
3. Log in with `proveedor.demo@checkwise.mx` / `(rotated 2026-05-18 · ask operator)`.
4. **Expected:** redirected to `/activate` with the heading
   *"Tu contraseña actual es temporal."* Set any 12+ character password
   (e.g. `MiNuevaPass2026!`).
5. **Expected:** lands on `/portal/entra-a-tu-espacio` showing
   *"Distribuidora Nogal · Demo"*. Confirm the contact info, click
   **Entrar a mi espacio**.
6. **Expected:** lands on `/portal/onboarding` (NOT the dashboard).
   Two clearly separated sections:
   - *"Obligatorios — desbloquean tu dashboard"* (5 cards, amber/warm)
   - *"Opcionales — puedes hacerlos después"* (5 cards, collapsible)
7. Click **Subir documento** on any obligatorio card. The wizard opens
   pre-filled for that requirement.
8. In wizard step 3 *"Sube el documento"*, click
   **Usar PDF de muestra**. A demo PDF is attached automatically. Step
   through Continuar → Continuar → Enviar.
9. **Expected on success:** primary CTA reads
   *"Continuar con tu expediente"* and routes back to the expediente.
   The card you just filled now shows the PDF filename in a blue chip
   with a checkmark.
10. To unlock the dashboard at any time: scroll to the bottom of the
    expediente and click **Activar mi dashboard de todos modos**
    (this is the demo escape hatch — production would require all
    obligatorios to be approved).
11. **Expected:** `/portal/dashboard` loads. Refresh — stays on
    dashboard. Logging out and back in goes straight to dashboard.

### Account B — Direct dashboard

1. Log out (top-right *Cerrar sesión*) or open another incognito tab.
2. Log in with `boss.demo@checkwise.mx` / `(rotated 2026-05-18 · ask operator)`.
3. **Expected:** redirected to `/portal/entra-a-tu-espacio` showing
   *"Servicios Especializados Aurora · Demo"*. No password change
   forced (`must_change_password = false`).
4. Click **Entrar a mi espacio**.
5. **Expected:** lands on `/portal/dashboard` directly. The expediente
   gate is satisfied because `onboarding_completed_at` was set during
   seeding.

### Verifying the gate from the URL bar (negative test)

While logged in as Account A *before* clicking "Activar mi dashboard":

1. Paste `https://checkwise-six.vercel.app/portal/dashboard` directly.
2. **Expected:** flashes the dashboard skeleton, then redirects back
   to `/portal/onboarding`. The HOC `withOnboardingGate` enforces this
   client-side, and `/portal/me` returns
   `expediente_status: "in_progress"` server-side as the source of truth.

---

## Sample PDF helper

The intake wizard's step 3 *"Sube el documento"* exposes a button:

> **Usar PDF de muestra** — adjunta un PDF de prueba etiquetado como
> demostración para recorrer el flujo sin tu archivo real.

It fetches `/samples/checkwise-demo-document.pdf` (committed at
`apps/web/public/samples/`) and attaches it to the upload form. The
PDF carries a visible *"DOCUMENTO DE MUESTRA · CHECKWISE 1.7.1 DEMO"*
ribbon so a reviewer who opens the file outside CheckWise immediately
sees it is demo data.

The button is gated behind `NEXT_PUBLIC_DEMO_MODE=true` (set in both
`.env.local` and Vercel) so it disappears automatically in any
non-demo environment.

To regenerate the sample PDF:

```bash
cd backend
.venv/bin/python scripts/generate_sample_pdfs.py
```

---

## Running locally

```bash
# 1. Backend
cd backend
.venv/bin/python -m uvicorn app.main:app --reload --port 8000

# 2. Database seed (idempotent — safe to re-run)
.venv/bin/python scripts/dev_seed.py

# 3. Frontend
cd ../frontend
npm install   # only if you haven't yet
npm run dev   # http://localhost:3000
```

`.env.local` for the frontend should contain:

```
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_DEMO_MODE=true
```

---

## Re-seeding the live (Render) database

If demo accounts get into a weird state, run this in
**Render → checkwise-api → Shell**:

```bash
python scripts/dev_seed.py
```

The script is idempotent — it deletes the demo rows it owns and
recreates them deterministically. It does not touch any non-demo data.

---

## Architectural notes for reviewers (optional reading)

- **Auth:** email + password → JWT (Bearer in `Authorization`). Portal
  endpoints accept both the JWT and the legacy `checkwise_portal_session`
  httpOnly cookie. JWT path is the cross-origin-safe primary; the
  cookie is kept as a transparent fallback. See
  `apps/api/app/api/v1/portal.py::current_portal_workspace`.
- **Expediente gate:** centralised in
  `apps/web/lib/session/with-onboarding-gate.tsx`. Single rule:
  `expediente_status === "complete"` unlocks `/portal/dashboard`,
  `/portal/calendar`, `/portal/reports`. Anything else redirects to
  `/portal/onboarding`. Backend computes the status in
  `_expediente_status(db, workspace)` and exposes it on every
  workspace response.
- **Workspace ownership:** `ProviderWorkspace.owner_user_id` ties a
  user to exactly one workspace. `current_portal_workspace` enforces
  the JWT user matches the requested workspace_id; cross-workspace
  reads return 403/404.

---

## Known limitations (demo scope)

- Reports center renders sample data; PDF generation and
  send-to-client are not wired. The page is informational for
  this release.
- Dashboard widgets (compliance semaphore, attention queue, suggested
  actions) render against demo fixtures alongside the real workspace
  identity. The expediente + calendar surfaces use live backend data.
- Invitation-by-email flow is not in this build; new users are
  created by `dev_seed.py` and the temporary password drives the
  forced first-login flow.

---

## Final verification checklist

Run before sharing the URL with the reviewer:

- [ ] `cd backend && .venv/bin/pytest tests/test_auth.py tests/test_portal.py` → all pass
- [ ] `cd frontend && npm run typecheck` → no errors
- [ ] `cd frontend && npm run build` → no errors
- [ ] Account A login redirects to `/activate` (must_change_password)
- [ ] After password change, Account A lands on `/portal/onboarding`
- [ ] Direct hit on `/portal/dashboard` redirects to `/portal/onboarding`
- [ ] Sample PDF button attaches a file in the wizard
- [ ] Account B login lands on dashboard with no detour
- [ ] `/health` on Render returns `{"status":"ok"}`
