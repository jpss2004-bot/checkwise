# Handoff prompt for the next Claude Code session

Copy everything inside the triple-tilde block below into a fresh Claude Code session at the repo root
`/Users/josepablosamano/Desktop/Work — LegalShelf/checkwise/CheckWise`. The prompt is self-contained
and will orient the new agent without losing the directives from the previous session.

---

~~~markdown
You are picking up the CheckWise project mid-stream. CheckWise is a Mexican REPSE compliance SaaS
operated by LegalShelf, S.A. de C.V. The repo root is the working directory you've been spawned in.
The previous session's full log + final state lives at
`docs/handoff/SESSION_EXPORT_2026-05-25.md` — open it first so you don't repeat decisions or rediscover
state already captured there.

## Stack + endpoints

- Frontend: Next.js 15 / React 19 / Tailwind 3 at `apps/web` (version 2.5.0).
- Backend: FastAPI / Python 3.11 at `apps/api`.
- DB: Neon Postgres. Storage: Cloudflare R2.
- Prod: API `https://checkwise-api.onrender.com`, Web `https://checkwise-six.vercel.app`.
- Render auto-deploys from `main`. Renewal cron: daily 14:00 UTC.

## Current state at the moment of handoff

- HEAD: `c4f96ff` (`feat(security): M0 — route policy manifest + CI gate`).
- 1001 backend tests pass (`apps/api/.venv/bin/python -m pytest tests -q`).
- Frontend `typecheck`, `lint`, `build` all green.
- Legal documents at `v1`, vigente 25-mayo-2026.
- Multi-file upload enabled by default.
- Transactional email outbound is shipped in code (reviewer decisions + renewal threshold crosses),
  but silently no-ops on prod because the SMTP env vars are not set on Render yet (see env checklist
  below).

## Canonical reference documents (READ THESE BEFORE ACTING)

1. `docs/handoff/SESSION_EXPORT_2026-05-25.md` — chronological log of the previous session.
2. `docs/audits/SALE_READINESS_BUYER_DOSSIER_2026-05-25.md` — external-facing audit dossier (this is what the buyer's CTO will read).
3. `docs/audits/SALE_READINESS_INTERNAL_FINDINGS_2026-05-25.md` — engineering-facing finding list (4 🔴 P0, 5 🟠 P1, 9 🟡 P2, 14 📘 NOTE). This is your to-do list.
4. `docs/audits/security/BACKEND_HARDENING_PASS_2026-05-25.pdf` — parallel audit by another Claude session. Has the M0-M5 milestone plan and 122-route classification.
5. `docs/runbooks/PRODUCTION_ENV_SETUP_CHECKLIST.md` — operator-side Render dashboard work. Confirm whether Jose Pablo has executed this before relying on prod email.
6. `apps/api/app/security/route_policy_manifest.json` — M0 manifest, 122 routes classified. The pytest at `apps/api/tests/test_route_policy_manifest.py` gates CI on its completeness.

## Standing rules (locked across the previous session)

1. **No new feature enablement** outside the audit findings list until the user explicitly approves. The audit week reframed work from "ship features" to "harden". Defensive work (tests, error normalization, audit-log fills, rate limits, security tightening) is allowed; new product features are not.
2. **Direct-to-main commits, no PRs.** Split per logical surface (one commit per shipped surface). Multi-paragraph commit body with explicit verification line. Push at end of work block, not after each commit.
3. **Test suite must stay green before push.** Frontend: `npm run typecheck && npm run lint && npm run build` (from `apps/web`). Backend: `apps/api/.venv/bin/python -m pytest tests -q`.
4. **Browser smoke** any change observable in the preview before reporting done. Use `mcp__Claude_Preview__*` tools, log in as the right persona, take a screenshot for visual changes.
5. **Spanish UX everywhere.** No English leaks, no raw enum labels exposed to users, no DRAFT banners. The canonical labels live in `apps/web/components/checkwise/portal/requirement-status-badge.tsx`.
6. **Don't touch legal documents** at `apps/web/app/legal/*` or the `CURRENT_LEGAL_CONSENT_VERSION` backend constant. The legal package is at `v1` and signed off.
7. **Don't change `MULTI_FILE_UPLOAD_ENABLED` default.** It's intentionally `True`.
8. **Don't surface WhatsApp UI** — the `SupportCard` component is intentionally orphan until the real phone number lands.
9. **Don't regenerate `route_policy_manifest.json` with the seeder.** It carries manual edits now; only hand-edit it. The pytest fails CI if a new route lacks a manifest entry, so adding a new route correctly is: add route → fail → add entry → pass.
10. **Don't commit user-generated PDFs** sitting in the working tree (`docs/audits/security/BACKEND_HARDENING_PASS_*.pdf`, `docs/legal/checkwise-paquete-legal-simple-v1-*.pdf`) and don't touch the marketing-related files in the working tree (`apps/web/components/marketing/*`, `apps/web/public/marketing/*`) — those are user/external work.
11. **Don't run `dev_seed.py` against prod.** It has a host guard but stay clear.

## Personas + dev credentials

These work against `localhost` only. All four are confirmed dead on prod.

- `ada@legalshelf.mx` / `(rotated 2026-05-18 · ask operator)` — internal_admin + reviewer → `/admin/*`.
- `cliente.demo@checkwise.mx` / `(rotated 2026-05-18 · ask operator)` — client_admin → `/client/*`.
- `boss.demo@checkwise.mx` / `(rotated 2026-05-18 · ask operator)` — provider (full expediente) → `/portal/*`.
- `proveedor.demo@checkwise.mx` / `(rotated 2026-05-18 · ask operator)` — provider (first login) → `/activate` → `/portal/onboarding`.

## What the previous session left as the next single best step

**Enforce `must_change_password`.**

Real security finding from the parallel PDF audit (🔴 P0). Today, a user whose `User.must_change_password == True` (e.g. a freshly-activated provider before setting their own password) can read/mutate any route they have a role for. The fix is small and isolated.

Acceptance criteria for the next step:

- Add a dependency (e.g. `enforce_password_set`) layered into or after `get_current_user` in `apps/api/app/api/v1/auth.py`. When `current.user.must_change_password is True`, return HTTP 403 (Spanish message) unless the request route is in an explicit allow-list of `{/api/v1/auth/me, /api/v1/auth/set-password}` (and `/api/v1/auth/logout` if it exists).
- Update `apps/api/app/security/route_policy_manifest.json` to add a `must_change_password_allowed: bool` field per route. Default `false`; the 2-3 allow-listed routes set `true`. Update `apps/api/tests/test_route_policy_manifest.py` to enforce the new required field.
- New pytest cases (in a new file `tests/test_must_change_password_gate.py` ideally):
  - A user with `must_change_password=True` gets 403 on a sample of admin/client/portal/reviewer endpoints.
  - The same user gets 200 on `/auth/me` and 200 on `/auth/set-password`.
  - After hitting `/auth/set-password` and the flag clears, the same user gets 200 on previously-blocked endpoints.
- Run full backend pytest (expect 1004+ passing, +3 vs current 1001).
- Commit per surface (likely two commits: one for the gate + tests, one for the manifest schema change + manifest entries).
- Push.

If the user has already moved on from this recommendation, follow whatever they actually said. Don't restart this work if it's stale.

## After `must_change_password`, the priority order is

1. **M4 partial — close the 4 manifest-flagged audit-log gaps** (notification mark-read × client + provider). ~30 min. The manifest entries are already tagged with `audit_rule = "not_logged (P1 GAP — Pass 3 finding P3-01; ...)"` so the next maintainer cannot miss them.
2. **M1 — cross-tenant negative tests for reports / exports / shares.** Covers the high-severity LLM-snapshot concern flagged in the parallel PDF audit. ~2-3 hours.
3. **M2 — Spanish error normalization** on auth/feedback/metadata-dry-run/reports/reviewer routes. ~1-2 hours.
4. **M3 — Upload 413 consistency + share-unlock + AI-heavy rate limiters.** ~half a day.
5. **M5 — CI secret scan (gitleaks) + dependency audit.** ~1 hour.

Beyond M5, the polish items in `SALE_READINESS_INTERNAL_FINDINGS_2026-05-25.md` (CORS tightening, `/dev/*` removal, `.env.example` flip, stale-demo-doc cleanup, archive bloated docs, in-app invitation flows).

## Operator outstanding action (blocking but not your work)

The user has not yet executed `docs/runbooks/PRODUCTION_ENV_SETUP_CHECKLIST.md`. Three Render env vars are unset:

- `AUTH_JWT_SECRET` — confirm not the in-code placeholder.
- `SMTP_HOST`/`SMTP_USERNAME`/`SMTP_PASSWORD`/`SMTP_FROM_EMAIL` — outbound email no-ops without these.
- `FRONTEND_BASE_URL` — email CTA links default to localhost without this.

Confirm with the user whether this is done before assuming prod email works. Mention it at the end of work blocks until cleared.

## Start of session — your first move

1. Open `docs/handoff/SESSION_EXPORT_2026-05-25.md` and read it end to end.
2. Open the internal findings list at `docs/audits/SALE_READINESS_INTERNAL_FINDINGS_2026-05-25.md`.
3. Open the route policy manifest at `apps/api/app/security/route_policy_manifest.json`.
4. Run the quick-start verification block from §12 of the session export to confirm the repo is in the expected state.
5. Then: confirm with the user whether to proceed with `must_change_password` enforcement (the previous session's recommended next step) or pivot to something else. If the user is silent or says "continue", proceed with `must_change_password`.

Don't restart the audit week. Don't re-read the legal documents. Don't generate new finding lists. The audits are done; you are now in execution mode.

When you finish a work block, end with a 4-5 line status: what shipped, test counts, what's next.
~~~

---

## How to use this file

1. Open a brand-new Claude Code session at the repo root.
2. Copy everything between the `~~~markdown` and the closing `~~~` above (or just the body inside).
3. Paste as the first user message.
4. The new session is now caught up.

Do not include this surrounding wrapper text — only the content between the tildes.
