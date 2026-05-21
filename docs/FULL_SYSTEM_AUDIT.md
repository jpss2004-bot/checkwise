# Full system audit — 2026-05-18

| Field | Value |
|---|---|
| Branch | `main` (1 commit ahead of `origin/main`) |
| Baseline | `5559e1c` "seed+docs: fix boss.demo routing, document role flow audit" |
| Working tree | clean before this session |
| App version | v2.1.1 — Phase 3 v1 closed, R1.0 (admin reports) shipped |

## 1. Scope of verification

| Surface | Verification method |
|---|---|
| Backend routes | static read + curl-based smoke per role |
| Frontend routes | static read (file existence + role-guard inspection) |
| Auth flows | curl login + JWT inspection per role |
| Reports AI pipeline | real Anthropic call via `POST /reports/{id}/generate` SSE |
| Per-button click behavior | **NOT browser-verified in this session** — flagged where assertions depend on it |
| Visual states (loading / error / empty) | **NOT browser-verified** — static checks only |

The session ran `ruff check`, `pytest`, `tsc --noEmit`, `next lint`, and curl probes. It did not open a browser; the user opens browsers themselves.

## 2. Frontend route inventory (31 routes)

| Path | File | Role | Source | Status |
|---|---|---|---|---|
| `/` | `app/page.tsx` | public | marketing | code-verified |
| `/login` | `app/login/page.tsx` | public | auth | code-verified, double-spinner fixed in `f294c31` |
| `/activate` | `app/activate/page.tsx` | public (with token) | mock email | code-verified |
| `/admin` | `app/admin/page.tsx` | internal_admin / reviewer | session | code-verified |
| `/admin/login` | `app/admin/login/page.tsx` | public | redirect | redirects to `/login` (legacy; see Issue B3) |
| `/admin/dashboard` | `app/admin/dashboard/page.tsx` | internal_admin¹ | `/api/v1/admin/overview` | code-verified, API 200 |
| `/admin/reviewer` | `app/admin/reviewer/page.tsx` | internal_admin¹ | `/api/v1/reviewer/queue` | code-verified, API 200 |
| `/admin/reviewer/[submission_id]` | dyn | internal_admin¹ | `/api/v1/reviewer/submissions/{id}` | code-verified |
| `/admin/clients` | `app/admin/clients/page.tsx` | internal_admin¹ | `/api/v1/admin/clients` | code-verified, API 200 |
| `/admin/vendors` | `app/admin/vendors/page.tsx` | internal_admin¹ | `/api/v1/admin/vendors` | code-verified, API 200 |
| `/admin/requirements` | `app/admin/requirements/page.tsx` | internal_admin¹ | `/api/v1/admin/requirements` | code-verified, API 200 |
| `/admin/calendar` | `app/admin/calendar/page.tsx` | internal_admin¹ | `/api/v1/admin/calendar` | code-verified, API 200 |
| `/admin/audit-log` | `app/admin/audit-log/page.tsx` | internal_admin¹ | `/api/v1/admin/audit-log` | code-verified, API 200 |
| `/admin/reports` *(R1.0)* | `app/admin/reports/page.tsx` | internal_admin¹ | `/api/v1/reports/_presets` + `/api/v1/reports` | code-verified, API 200 |
| `/admin/reports/[id]` *(R1.0)* | redirect | internal_admin¹ | n/a | redirects to `/portal/reports/[id]`; shared-editor lift deferred to R1.0.1 |
| `/client` | `app/client/page.tsx` | client_admin | redirect | redirects to `/client/dashboard` |
| `/client/dashboard` | `app/client/dashboard/page.tsx` | client_admin / internal_admin | `/api/v1/client/overview` | code-verified, API 200 |
| `/client/activity` | `app/client/activity/page.tsx` | client_admin / internal_admin | `/api/v1/client/activity` | code-verified, API 200 |
| `/client/calendar` | `app/client/calendar/page.tsx` | client_admin / internal_admin | `/api/v1/client/calendar` | code-verified, API 200 |
| `/client/submissions` | `app/client/submissions/page.tsx` | client_admin / internal_admin | `/api/v1/client/submissions` | code-verified, API 200 |
| `/client/vendors` | `app/client/vendors/page.tsx` | client_admin / internal_admin | `/api/v1/client/vendors` | code-verified, API 200 |
| `/client/vendors/[vendor_id]` | dyn | client_admin / internal_admin | `/api/v1/client/vendors/{id}` | code-verified |
| `/portal/entra-a-tu-espacio` | `app/portal/entra-a-tu-espacio/page.tsx` | role-less authenticated | session + mock resolver | uses mock invitations/expediente (TODO[backend-integration]) |
| `/portal/onboarding` | gated | provider with no `onboarding_completed_at` | `/api/v1/portal/workspaces/{id}/onboarding` | code-verified |
| `/portal/dashboard` | gated | onboarded provider | portal endpoints | code-verified |
| `/portal/calendar` | gated | provider | `/api/v1/portal/workspaces/{id}/calendar` | code-verified |
| `/portal/submissions/[submission_id]` | gated | provider | portal endpoints | code-verified |
| `/portal/upload` | gated | provider | portal endpoints | code-verified |
| `/portal/reports` | gated | any authenticated | `/api/v1/reports` | code-verified |
| `/portal/reports/[id]` | gated | any authenticated | `/api/v1/reports/{id}` | code-verified, R1.0 preset-prompt pre-fill wired |
| `/portal/reports/[id]/print` | gated | any authenticated | report data | code-verified |

¹ R1.0 audit found that `AdminShell` rejected reviewer-only users. Fixed in this session (see B4 below).

## 3. Backend route inventory (~60 endpoints)

Grouped by router file. All counts verified via curl smoke for `ada@legalshelf.mx` (200) and `cliente.demo@checkwise.mx` (200 on own surfaces, 403 on `/admin/*` and `/reviewer/*`).

| Router file | Endpoints | Auth | Notes |
|---|---|---|---|
| `auth.py` | `POST /login`, `GET /me`, `POST /set-password` | mixed | core auth |
| `admin.py` | 19 routes (overview, clients, vendors, requirements, calendar, audit-log, workspaces, periods) | `internal_admin` | tested 200 for ada |
| `reviewer.py` | 3 routes (queue, submission detail, decisions) | `reviewer` OR `internal_admin` | tested 200 for ada |
| `client.py` | 8 routes (me, overview, activity, calendar, submissions, vendors) | `client_admin` OR `internal_admin` | tested 200 for cliente.demo |
| `portal.py` | 10 routes (enter, me, workspaces) | `X-Workspace-Token` | provider-portal auth, separate from JWT |
| `reports.py` | 16 routes (CRUD, presets, engine, plan, generate, regenerate, explain, conversations) | JWT + audience filter | tested 200 for ada |
| `compliance.py` | 3 routes (catalog, calendar, onboarding) | public/auth | public catalog data |
| `metadata_dry_run.py` | `POST /pdf` | auth | PDF inspection |
| `endpoints.py` | `/health`, `/health/db`, `/catalogs` | public | system check |

## 4. Buttons / actions — top tier

Verified by code-read, **not** by clicking:

| Surface | Action | Wires to | Verified |
|---|---|---|---|
| `/login` | Entrar | `POST /auth/login` → `decideDestination(roles)` | code+API |
| `/activate` | Set password | `POST /auth/set-password` | code |
| Admin shell — Reportes | nav | `/admin/reports` | code |
| `/admin/reports` | Usar plantilla | `POST /reports/from-preset` → editor | code |
| `/portal/reports` | Nuevo reporte | inline form → `POST /reports` | code |
| `/portal/reports/[id]` | Generar con IA | `POST /reports/{id}/generate` SSE | **end-to-end verified — 30 events ~11s** |
| `/portal/reports/[id]` | Save version | `POST /reports/{id}/versions` | code |
| `/portal/reports/[id]` | Print | `/portal/reports/[id]/print` | code |
| Any shell | Logout | clear session + `/login` | code |

## 5. Forms

| Form | Source | Submit behavior | Validation | Status |
|---|---|---|---|---|
| `/login` | `app/login/page.tsx` | `POST /auth/login` | inline error per status | code-verified |
| `/activate` | `app/activate/page.tsx` | `POST /auth/set-password` | min length, confirm match | code-verified |
| Onboarding wizard | `app/portal/onboarding/page.tsx` | multi-step state-machine + portal upload | per-step | code-verified |
| Upload | `app/portal/upload/page.tsx` | portal upload endpoint | mime/size from `ALLOWED_FILE_EXTENSIONS` + `MAX_UPLOAD_SIZE_BYTES` | code-verified |
| Inline "Nuevo reporte" | `app/portal/reports/page.tsx` | `POST /reports` | title length | code-verified |
| AI prompt textarea | `app/portal/reports/[id]/page.tsx` | SSE stream | non-empty | end-to-end verified |
| Correction request | `components/checkwise/workspace/correction-request-form.tsx` | mock — `apps/web/lib/mock/corrections.ts` | client-side only | **mock; TODO marker** |
| Marketing contact | `components/marketing/contact-form.tsx` | mock — `apps/web/lib/mock/contact-requests.ts` | client-side only | **mock; TODO marker** |

## 6. Reports system status

| Surface | Status |
|---|---|
| `/admin/reports` list + preset gallery | R1.0 live; 3 admin presets render; preset-from creates report with audience filter |
| `/portal/reports` list | works (uses same backend) |
| `/portal/reports/[id]` editor | works; loads content, mounts Canvas + ChatCopilot |
| AI planner | live; verified end-to-end with real Anthropic key |
| AI block streaming | live; verified end-to-end (30 SSE events including `ai_summary_delta`, `block_complete`, `version_saved`) |
| Per-block regenerate | code-verified; endpoint exists; calls work in unit tests |
| Per-block explain | code-verified |
| Copilot chat | code-verified; backend test passes |
| Save version | code-verified |
| Print mode | route exists; not browser-tested this session |
| Audience-based redaction | tested via unit tests (`test_reports_ai_safety.py`) |

## 7. Upload / document flow status

Static audit only. Not browser-tested this session.

- Provider upload flow exists at `/portal/upload`.
- 4 sample submissions seeded per provider workspace (pendiente_revision, posible_mismatch, aprobado, rechazado).
- Reviewer queue at `/admin/reviewer` consumes them.
- Decision flow exposed via `POST /reviewer/submissions/{id}/decisions`.

## 8. Auth / role status

Verified end-to-end via curl:

| Account | Roles | Routes to | Tenant access |
|---|---|---|---|
| `ada@legalshelf.mx` | internal_admin, reviewer | `/admin/reviewer` | all orgs |
| `cliente.demo@checkwise.mx` | client_admin | `/client/dashboard` | own org; admin endpoints return 403 |
| `boss.demo@checkwise.mx` | *(none)* | `/portal/entra-a-tu-espacio` | own workspace only |
| `proveedor.demo@checkwise.mx` | *(none)* + must_change_password | `/activate` | own workspace after activation |

`visible_audiences()` / `writable_audiences()` ship correctly: client_admin sees only `client_facing` reports, ada sees all 4 audiences.

## 9. Mock vs real data wiring

5 modules in `apps/web/lib/mock/` with `TODO[backend-integration]` markers — these are **intentionally documented mocks**, not bugs:

| Module | Consumer | What's mocked |
|---|---|---|
| `invitations.ts` | `/portal/entra-a-tu-espacio` | invitation tokens |
| `calendar.ts` | older calendar surfaces | calendar events (some surfaces use the real `/portal/*/calendar`) |
| `corrections.ts` | correction-request form | correction submissions |
| `contact-requests.ts` | marketing contact form | inbound contact requests |
| `expediente.ts` | resolver | expediente synthesis |

13 TODO/FIXME comments total across the entire codebase, all in mock modules. Honest scaffolding.

## 10. Code hygiene

| Check | Result |
|---|---|
| `: any` / `any[]` escapes in FE | **0** |
| `@ts-ignore` / `@ts-expect-error` | **0** |
| `eslint-disable` comments | 3 (all intentional) |
| `.bak` / `.old` / `.tmp` files | **0** |
| TODO/FIXME comments | 13 (all in mock modules, marked) |
| Hardcoded URLs | 1 (a defensive fallback default in `portal-session.ts:24`) |
| Dead routes | none found |
| Duplicate components | none found |

## 11. Test baseline

| Check | Result |
|---|---|
| `ruff check app tests` | clean |
| `tsc --noEmit` | clean |
| `next lint --quiet` | clean |
| `pytest -q` (with B5 fix in conftest) | **320 passed** |
| Real Anthropic AI generation (smoke) | **30 SSE events, ~11s, full sequence** |
| API smoke — admin role | 12/12 endpoints 200 |
| API smoke — client role | 9/9 own endpoints 200, 2/2 forbidden endpoints 403 |
| `next build` | last green at `6ba0d33` — not re-run this session |

## 12. Prioritized issue list

### P0 — app-breaking
**None found.** All routes resolve, all role redirects route correctly, backend never 500s on probed surfaces, pytest passes, AI pipeline works end-to-end.

### P1 — core flow broken or misleading
**Fixed in this session:**

- **B4 — `AdminShell` rejected reviewer-only users.** Line 74 of `apps/web/app/admin/_shell.tsx` was `if (!current.roles.includes("internal_admin"))`. A user with only `reviewer` (no `internal_admin`) would be bounced to `/admin` even though `/admin/reviewer` is the reviewer's primary route. No seeded account triggers it because `ada` holds both roles, but the gate is wrong. Now accepts either role.
- **B5 — pytest fails when a real Anthropic key is present in env.** 4 tests assume the deterministic mock LLM. When the developer has a real key in `.env`, the factory builds the real client and these tests fail on shape mismatch. Fixed via session-level `tests/conftest.py` that pops `ANTHROPIC_API_KEY` and forces `CHECKWISE_LLM_BACKEND=mock` at import time. Confirmed: 320/320 pass.

**Filed but not fixed:**

- **B3 — `/admin/login` legacy double-hop.** `apps/web/app/admin/login/page.tsx` redirects to `/login`. `AdminShell` and `ClientShell` redirect to `/admin/login` on unauthorized, causing a double hop. Cosmetic only — works functionally. Recommended fix: change both shells to redirect directly to `/login`.

### P2 — visible quality issue
Static audit did not surface any P2s with confidence. Per-page loading/error/empty states need browser verification.

### P3 — cleanup / hygiene
- 5 mock modules in `apps/web/lib/mock/` with `TODO[backend-integration]` markers. Real backend integration for invitations / corrections / contact-requests / expediente / calendar is deferred. These are honest scaffolds today.
- `/admin/reports/[id]` is currently a redirect to `/portal/reports/[id]` (deliberate; the shared-editor extraction is R1.0.1).

### Deferred — product feature gap
- **R1.0.1** — extract editor into a shell-agnostic component so `/admin/reports/[id]` mounts in `AdminShell`.
- **R1.1** — `/client/reports` surface with `client_admin` preset gallery.
- **R1.2** — `external_signed` audience delivery via `/share/r/[token]`.
- **R2** — interactive filters (date range, status, vendor selector).
- Production seed accounts — currently none on Vercel/Render/Neon (security/intent).
- Vercel/Render `ANTHROPIC_API_KEY` — needs to be set on Render to lift the mock-LLM banner in production.
- Production observability — no Sentry/log shipping configured.

## 13. What this session did

| Change | File | Commit candidate |
|---|---|---|
| Force mock LLM at pytest session start | `apps/api/tests/conftest.py` (new, 17 lines) | yes |
| Admin shell accepts reviewer-only users | `apps/web/app/admin/_shell.tsx` (12 lines changed) | yes |
| Full system audit doc | `docs/FULL_SYSTEM_AUDIT.md` (this file) | yes |
| QA results doc | `docs/QA_RESULTS.md` | yes |

Total: 4 files, ~250 net added lines (mostly docs).

## 14. What this session deliberately did NOT do

- No browser clicking. Per-button visual + interaction verification still needs the user.
- No fix for B3 (cosmetic redirect) — out of session scope.
- No new features.
- No removal of the mock modules (TODO[backend-integration] markers stay).
- No production deploy.
- No changes to `next build` (last verified green at `6ba0d33`).

## 15. Recommendation for the next session

Pick one:

1. **Browser smoke** — open localhost:3000 as each of the 4 demo accounts, click through the major flows on each shell, and report any P1s I cannot see from code.
2. **R1.1** — client preset gallery + 3 client-facing presets.
3. **B3 cleanup** — change `AdminShell`/`ClientShell` to redirect directly to `/login`.
4. **Production AI key** — set `ANTHROPIC_API_KEY` on Render so the production `/admin/reports` banner disappears.

If you push `5559e1c` (already on local `main`) and the new conftest + shell fix that lands in the next commit, prod immediately gets the boss.demo seed fix + admin shell fix.
