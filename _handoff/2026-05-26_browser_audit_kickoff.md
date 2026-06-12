# Kickoff prompt for the next session — live browser audit

**Copy everything between the triple-dashes below into the first message of your new Claude Code session.** The new session will load `MEMORY.md` automatically, which carries the full context of what shipped today (17 commits, 10 audit findings closed, admin portal split, migration repoint).

---

I shipped 17 commits to `main` today across the 8-item morning sprint, a 10-finding auth audit, an admin portal split into Operaciones + Plataforma, and a production hardening pass. The full disposition is in `project-sprint-2026-05-26` memory.

The work is verified at the HTTP / test / typecheck level (149 backend tests green, all production endpoints return correct status codes, every Vercel route serves 200, all 308 redirects land at the right destination). What's MISSING is a live browser walk-through of the new surfaces in production. The previous session got blocked by a stuck Claude-in-Chrome MCP tab-group; I'd like to finish that audit now.

**Production URL**: https://checkwise-six.vercel.app
**Backend API**: https://checkwise-api.onrender.com
**My credentials**: `jsamano@legalshelf.mx` / I'll paste the password when you ask for it (avoid echoing it in chat).

Please do the following live audit, capturing a screenshot after each step so you can flag anything off:

**1. Auth surfaces**
- Visit `/login`; confirm the empty-field guard disables the submit button (audit fix #7).
- Visit `/forgot-password`; submit with an invalid email; confirm the 422 copy is friendly.
- Visit `/reset-password` with no token; confirm only the alert renders (audit fix #4) — no disabled form below it.
- Log in with my creds; confirm you land on `/admin/dashboard`.

**2. Operaciones shell (`/admin/*`)**
- `/admin/dashboard` — verify the KPI strip + recent-activity widgets render with the trimmed nav (9 items, no Nuevo usuario / Audit log / Feedback).
- `/admin/clients` — verify the "Nuevo cliente" header CTA links to `/platform/users/new` (admin split). No more old "Solo alta" / "Onboarding nuevo cliente" buttons.
- `/admin/vendors` — verify the Proveedor cell is a `<VendorRef>` link to the client expediente.
- `/admin/reviewer` — verify the vendor name in each queue row is a `<VendorRef>` link.
- `/admin/correction-requests` — verify the same.

**3. Shell switcher**
- Open the UserMenu (top-right). Click "Cambiar a Plataforma". Confirm the URL changes to `/platform/dashboard`.
- In the Plataforma UserMenu, click "Cambiar a Operaciones". Confirm round-trip works.

**4. Plataforma shell (`/platform/*`)**
- `/platform/dashboard` — 3 action cards (Nuevo usuario, Audit log, Feedback reports).
- `/platform/users/new` — toggle the role selector between Cliente and Proveedor; verify the field sets swap correctly. Don't submit unless you want to actually create a test user.
- `/platform/audit-log` — confirm the explorer loads recent events.
- `/platform/feedback-reports` — confirm the triage queue loads.

**5. 308 redirects from old IT URLs**
- Open `/admin/users/new` in a new tab; confirm it 308s to `/platform/users/new`.
- Same for `/admin/audit-log` → `/platform/audit-log`.
- Same for `/admin/feedback-reports` → `/platform/feedback-reports`.

**6. Client portal samples** (use `?client_id=<id>` since I'm internal_admin)
- Pick any existing client_id from `/admin/clients` and visit `/client/vendors?client_id=<id>`.
- Click into a vendor. Verify the new **Contratos del proveedor** card renders at the top of the left column.
- If that vendor has any contract submission (`ONB-CONT-001/002/003`), click the View button and confirm the PDF opens in a new tab. Click Download and confirm the file downloads with the right name.
- `/client/auditoria?client_id=<id>` — verify the tree picker renders. If there are any contract submissions in scope, confirm they appear in a top-pinned "Contrato" group, NOT under "Interno cliente".
- `/client/onboarding?client_id=<id>` — confirm the "Mis proveedores" section appears below the profile form (only when `onboarding_completed_at` is set).
- `/client/calendar?client_id=<id>` — confirm the new vendor multi-select chips appear at the top.

**7. Console + network**
- Throughout, watch the browser console for any red errors.
- Watch the network panel for any 4xx/5xx unexpected responses on normal flows.

**Report format**: After the audit, give me a punch list — what works as designed, what's off, severity per item. Don't fix anything yet; we'll triage together. If you find a real bug, flag it but ask before changing code.

Open caveats to know:
- The parallel notifications session has uncommitted migrations 0024–0028. They're not on `main` yet. Don't be surprised if email/WhatsApp delivery looks unfinished.
- `/platform/users` (a listing of all users) is deliberately deferred — needs new `GET /api/v1/admin/users` endpoint that doesn't exist yet.
- Legal copy on `/legal/*` is `v0-draft` pending Paco/Beko sign-off. The T&C checkbox flow works but writes that version string in audit rows.

---

# How to start the new session

In Cursor / Claude Code, open a new chat (or hit `Cmd+N` if you're in the terminal). Then paste the block above as your first message. The memory system will autoload the sprint context. The new agent will pick up where this one stopped.
