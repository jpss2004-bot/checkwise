# CheckWise Stabilization Audit — 2026-05-18

**Scope:** make every existing page and feature work end-to-end. No new
features, no redesigns, no new abstractions. Read-only Phase A report.

**Repo state at audit time**

- Branch / HEAD: `main` @ `2d38726` (Phase 5 — v2.1 close).
- Working tree: 1 modified file (`backend/scripts/dev_seed.py`,
  +519/-42, uncommitted) + 4 untracked artefacts under `docs/`.
- Local branches ahead of `origin`: none. `main` is in sync with
  `origin/main`.

**Baseline gauntlet (run for this audit, no edits applied)**

| Check | Result |
|---|---|
| `backend/.venv/bin/pytest -q` | **312 passed**, 2 deprecation warnings (anyio · `HTTP_422_UNPROCESSABLE_ENTITY`) |
| `backend/.venv/bin/ruff check .` | **All checks passed** |
| `frontend/node_modules/.bin/tsc --noEmit` | **0 errors** |
| `frontend/node_modules/.bin/next lint --quiet` | **0 errors, 3 warnings** (unused symbols) |
| `frontend/node_modules/.bin/next build` | **27/27 routes compile** |

Baseline is green. Stabilization here is therefore about **wiring gaps
and dead code**, not about a broken build.

---

## 1. Inventory

### 1.1 Frontend routes (31 page files, 27 routes)

Marketing / auth

- `app/page.tsx` — public hero (compliance cockpit reveal)
- `app/login/page.tsx` — unified login
- `app/activate/page.tsx` — first-login activation wizard
- `app/admin/login/page.tsx` — **stub**, redirects to `/login`

Provider portal (`/portal/*`) — all wrapped by `withOnboardingGate`
except `entra-a-tu-espacio` and `onboarding` themselves

- `portal/entra-a-tu-espacio/page.tsx`
- `portal/onboarding/page.tsx`
- `portal/dashboard/page.tsx`
- `portal/calendar/page.tsx`
- `portal/reports/page.tsx`
- `portal/reports/[id]/page.tsx`
- `portal/reports/[id]/print/page.tsx`
- `portal/upload/page.tsx`
- `portal/submissions/[submission_id]/page.tsx`
- `portal/layout.tsx`

Admin (`/admin/*`)

- `admin/page.tsx` (index → reviewer or dashboard by role)
- `admin/dashboard/page.tsx`
- `admin/reviewer/page.tsx`
- `admin/reviewer/[submission_id]/page.tsx`
- `admin/audit-log/page.tsx`
- `admin/calendar/page.tsx`
- `admin/clients/page.tsx`
- `admin/requirements/page.tsx`
- `admin/vendors/page.tsx`
- `admin/layout.tsx`

Client portfolio (`/client/*`)

- `client/page.tsx` (index → `/client/dashboard`)
- `client/dashboard/page.tsx`
- `client/activity/page.tsx`
- `client/calendar/page.tsx`
- `client/submissions/page.tsx`
- `client/vendors/page.tsx`
- `client/vendors/[vendor_id]/page.tsx`

All 27 statically/dynamically compile.

### 1.2 Backend routers (`backend/app/api/v1/`)

Wired in `router.py` in this order: `endpoints`, `compliance`,
`portal`, `auth`, `reviewer`, `admin`, `client`, `metadata_dry_run`,
`reports`.

| Module | `@router.<verb>` count |
|---|---|
| `admin.py` | 19 |
| `reports.py` | 13 |
| `portal.py` | 11 |
| `client.py` | 7 |
| `endpoints.py` | 4 |
| `auth.py` | 3 |
| `compliance.py` | 3 |
| `reviewer.py` | 3 |

`metadata_dry_run.py` is the in-house OCR/metadata staging surface;
also wired.

Migrations 0001 → **0008** (`0008_submission_supersedes`). No drift
between memory note and the migration tree.

---

## 2. Findings

### P0 — Breaks a user flow

**P0-1. `client_admin` users are routed to the wrong portal after login.**

`frontend/app/login/page.tsx:217-229` — `decideDestination` only
recognises two role classes:

```
internal_admin or reviewer  → /admin/reviewer
everything else             → /portal/entra-a-tu-espacio
```

A `client_admin` user (the V2.1 persona, `cliente.demo@checkwise.mx`)
therefore lands on `/portal/entra-a-tu-espacio`, a workspace-confirmation
page that requires a `ProviderWorkspace` membership the client does not
have. The client cannot reach `/client/*` from `/login` at all. README
explicitly bills `/login` as the entry for *both* "Login (provider /
cliente)" rows and lists `cliente.demo` as reaching `/client/*`. This
worked in V1.x (no `client_admin` role existed) and silently regressed
when the persona shipped in V2.1.

Same routing bug repeats on the boot-check at `frontend/app/login/page.tsx:49`
(authenticated visitor hits `/` then `/login`) and in the post-submit
redirect at `:69`.

**Minimum fix:** add a `client_admin` branch to `decideDestination`
returning `/client/dashboard`. ~5 LOC, single file.

### P1 — Visible defect or wrong data

**P1-1. Uncommitted `dev_seed.py` (+519/-42) is the working refactor that
makes the seed idempotent for the V2.1 multi-workspace client portfolio.**

`backend/tests/test_seed.py` passes against this version. The previous
seed (HEAD) deletes orgs *before* it deletes the Client rows that FK
into them, which is the bug the diff fixes. If anyone runs `git reset
--hard` or pulls in a teammate, the working-tree-only fix is lost and
`bash backend/scripts/dev_reset.sh` will fail on re-seed against a
populated DB. This is a producer/consumer split waiting to happen
(exactly the failure mode of the May 15 incident captured in memory).

**Minimum fix:** stage and commit the file as-is. No source changes.

**P1-2. Untracked secrets-grade docs sitting in the working tree.**

`docs/CREDENTIALS.md` (demo passwords in plaintext),
`docs/EXECUTIVE_REPORT.html`,
`docs/EXECUTIVE_REPORT_V2_LIVE_EVIDENCE.html`,
`docs/executive-evidence/` (DEMO_ACCOUNTS.md, screenshots, …).
`.gitignore` does *not* exclude them, so an inadvertent `git add .`
puts the demo password list and a 33-file evidence bundle into git
history.

The README already documents the same demo accounts on its own. The
`docs/executive-evidence/` directory is a parallel ad-hoc QA artefact
set; nothing in the repo references it.

**Minimum fix:** add a narrow `.gitignore` entry covering
`docs/CREDENTIALS.md`, `docs/EXECUTIVE_REPORT*.html`,
`docs/executive-evidence/`. Decide separately whether to delete or
keep the local files. No source changes.

### P2 — Hygiene (dead code, lint warnings, type escapes)

**P2-1. Orphaned mock files (no source consumers).**

| File | Consumers in `app/`, `components/`, `lib/` (excluding the file itself and the .next cache) |
|---|---|
| `frontend/lib/mock/activation.ts` | 0 |
| `frontend/lib/mock/reports.ts` | 0 |

Both files document themselves as `TODO[backend-integration]` bridges
but no code imports them today. Safe to delete.

**P2-2. Orphaned portal components.**

| File | Consumers |
|---|---|
| `frontend/components/checkwise/portal/compliance-calendar.tsx` | 0 |
| `frontend/components/checkwise/portal/onboarding-checklist.tsx` | 0 |
| `frontend/components/checkwise/portal/provider-access-form.tsx` | 0 |
| `frontend/components/checkwise/portal/semaphore-card.tsx` | 0 (also the sole reason `lib/mock/dashboard.ts` is kept in tree — its only consumer is type-only) |

These were superseded by the V2 primitives (`StatCard`,
`EvidenceSlotGrid`, the new `PortalAppShell`) but never removed. Safe
to delete; if `semaphore-card` goes, `lib/mock/dashboard.ts` becomes
removable too.

**P2-3. Dead helper: `lib/routing/post-login.ts`.**

`decidePostLoginRoute` has **zero callers** in the codebase. `/login`
uses an inline `decideDestination` (see P0-1); `/activate` uses its own
inline logic. The exported `isWorkspaceConfirmed` likewise has no
callers. The file's only inbound dependency is `lib/mock/expediente`.
Safe to delete.

If we delete `post-login.ts` + the four orphan components + the two
orphan mocks, `lib/mock/expediente.ts` and `lib/mock/dashboard.ts`
become removable too — and the README's "Several 2.0 dashboards still
consume `lib/mock/*` …" warning shrinks to: `corrections`,
`contact-requests`, `invitations` (type-only via
`lib/workspace/resolver.ts`), plus `calendar` + `expediente` consumed
*only* by `lib/api/portal-adapters.ts` (legitimate documented bridge).

**P2-4. ESLint warnings (3, all unused symbols).**

| File:line | Symbol |
|---|---|
| `frontend/app/client/vendors/page.tsx:9` | `Storefront` import |
| `frontend/app/portal/dashboard/page.tsx:3` | `useMemo` import |
| `frontend/lib/mock/invitations.ts:71` | `_demo` constant |

If P2-1/P2-2 ship, the third disappears with the file.

**P2-5. `react-hooks/exhaustive-deps` disables (3 sites).**

`frontend/app/admin/audit-log/page.tsx:51`,
`frontend/app/client/vendors/page.tsx:64`,
`frontend/app/client/submissions/page.tsx:69`.

Each guards a `useEffect(() => { refresh(); }, [])` pattern where
`refresh` is declared in the same component. The disable is the
idiomatic "run once on mount, don't loop" form. Not a defect; logging
here so we don't re-flag them later.

**P2-6. Type-safety escapes (9 sites total, all legitimate).**

| File:line | Escape | Notes |
|---|---|---|
| `lib/api/admin.ts:38` | `undefined as unknown as T` | Sentinel for `204 No Content` in a typed `fetch` wrapper. Same pattern in `client.ts:40`, `reports.ts:46`. |
| `lib/api/client.ts:40` | same | as above |
| `lib/api/reports.ts:46` | same | as above |
| `lib/reports/registry.ts:104` | `Component as unknown as ComponentType<BlockProps>` | Bridging the block-registry's narrowed prop union to the generic React component type. |
| `components/checkwise/reports/chat-copilot.tsx:151` | `e as unknown as FormEvent` | Keyboard handler → form-submit shim. |
| 3 × `eslint-disable-next-line react-hooks/exhaustive-deps` | — | See P2-5. |

No `any`, no `@ts-ignore`, no `@ts-nocheck`, no `@ts-expect-error` in
app code. Type-safety floor is clean.

**P2-7. API base fallback hardcoded to localhost (12 sites).**

```
process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"
```

…appears in `lib/portal-client.ts`, `lib/api/{portal-session, admin,
reviewer, client, reports, portal, auth}.ts`,
`lib/reports/{use-conversation, use-generation}.ts`, plus
`components/checkwise/{intake-wizard, document-submission-form}.tsx`
(the last two use `http://localhost:8000`, an inconsistency in
addition to the fallback). Pre-existing deferred risk — handoff §6
item 3 already flagged this. Local dev works; production behaviour
hinges on Vercel env-var hygiene. **Out of scope for this
stabilization pass** unless explicitly authorised, since the fix is a
hardening change, not a stabilization fix.

**P2-8. Documentation / memory drift.**

- `docs/CHECKWISE_2_0.md` claims `lib/api/portal-adapters.ts` and the
  mocks `calendar`, `expediente` were removed; they are still in tree
  (re-introduced or never removed; either way the doc lies).
- `~/.claude/projects/-Users-josepablosamano-Desktop-Personal-legalshelf-checkwise/memory/project_state.md`
  pins HEAD at `5a51733`; real HEAD is `2d38726` (11 commits ahead,
  including the entire Phase 3 Reports flagship and Phase 5 V2.1
  close). Memory still reads "182 → 269 passing"; actual count is
  **312**.
- The active memory path implied by the current working directory
  (`-Users-...-Work---LegalShelf-checkwise`) has no memory files; all
  memory still lives at the older `-Personal-legalshelf-` path. Future
  sessions opened here will start cold unless the memory is migrated
  or symlinked.

Memory updates are a meta-task — flagging, not fixing as part of
stabilization unless asked.

---

## 3. Contract / wiring spot-checks

- `withOnboardingGate` (`frontend/lib/session/with-onboarding-gate.tsx`):
  role-aware bypass for `internal_admin` / `reviewer` is present and
  reads from `readAdminSession()`. Behaves as documented.
- `lib/api/portal-adapters.ts`: maps backend `OnboardingSummary` →
  `ExpedienteRequirement[]` and `CalendarPayload` →
  `CalendarEvent[]`. Status mapping is exhaustive over
  `RequirementStatus`. `no_aplica` / `excepcion_legal` collapse to
  `approved` for UI display — intentional, documented.
- `IntakeWizard` accepts `supersedesSubmissionId?: string` and forwards
  it as `supersedes_submission_id` in the form body
  (`components/checkwise/intake-wizard.tsx:423`). Matches backend
  migration `0008_submission_supersedes`.
- State coverage: 18 of the 27 routes have at least one of
  `Skeleton` / `loading` / `Error` / `EmptyState` markers — non-trivial
  surfaces are covered. Marketing landing, `admin/login` redirect stub,
  `client/page.tsx` index redirect, `portal/reports/[id]/print/page.tsx`
  do not need them.

No contract mismatches, no missing `response_model` against frontend
consumers, no cross-tenant leak path found in this pass.

---

## 4. Suggested prioritized fix list

| ID | Severity | Title | Fix size |
|---|---|---|---|
| P0-1 | P0 | `client_admin` routed away from `/client/*` in `app/login/page.tsx:217` | 1 file, ~5 LOC |
| P1-1 | P1 | Commit `backend/scripts/dev_seed.py` working-tree refactor | 0 source LOC, 1 commit |
| P1-2 | P1 | Add `.gitignore` entries for `docs/CREDENTIALS.md`, `docs/EXECUTIVE_REPORT*.html`, `docs/executive-evidence/` | 1 file, ~3 lines |
| P2-1 | P2 | Delete orphaned mocks: `lib/mock/activation.ts`, `lib/mock/reports.ts` | 2 files |
| P2-2 | P2 | Delete 4 orphaned portal components (and `lib/mock/dashboard.ts` when `semaphore-card` goes) | 4–5 files |
| P2-3 | P2 | Delete dead helper `lib/routing/post-login.ts` (also enables dropping `lib/mock/expediente.ts` after it ceases to back `portal-adapters.ts` — but adapters still need it, so leave `expediente.ts` alone) | 1 file |
| P2-4 | P2 | Remove 3 unused imports (`Storefront`, `useMemo`, `_demo`) — `_demo` deletion subsumed by P2-1/P2-2 if `invitations.ts` is judged orphan; today it's still type-imported by `resolver.ts` | 2 files |
| P2-5 | P2 | (Noted, no action) — `react-hooks/exhaustive-deps` disables are legitimate | — |
| P2-6 | P2 | (Noted, no action) — type-safety escapes are legitimate | — |
| P2-7 | Deferred | API-base fallback hardening (12 sites) — hardening, not stabilization | — |
| P2-8 | Deferred | Memory + `CHECKWISE_2_0.md` doc drift | — |

---

## 5. Resolution log

All P0 / P1 / actionable P2 items closed on branch
`stabilization/2026-05-18`. Verification gauntlet re-run after every
commit; final results captured in §6.

| ID | Status | Commit | Notes |
|---|---|---|---|
| P0-1 | Resolved | `f536329` | `decideDestination` gains a `client_admin` branch returning `/client/dashboard`. Browser-verified: `cliente.demo` logs in and lands on the V2.1 client shell with no console errors. |
| P1-1 | Resolved | `748d3a8` | `dev_seed.py` working-tree refactor staged as-is; `test_seed.py` (7 tests) green against the new version. |
| P1-2 | Resolved | `43a9511` | `.gitignore` adds narrow rules for `docs/CREDENTIALS.md`, `docs/EXECUTIVE_REPORT*.html`, `docs/executive-evidence/`. Local files left in place; `git status` is clean of them. |
| P2-1 | Resolved | `66634da` | Deleted `lib/mock/activation.ts`, `lib/mock/reports.ts`. |
| P2-2 | Resolved | `66634da` | Deleted 4 orphan portal components + `lib/mock/dashboard.ts` (last consumer was the `semaphore-card` deleted alongside). |
| P2-3 | Resolved | `66634da` | Deleted `lib/routing/post-login.ts` (the entire `lib/routing/` directory collapsed cleanly with no remaining files). |
| P2-4 | Resolved | `66634da` | Removed `Storefront` and `useMemo` unused imports; renamed `_demo` destructure to `_demoIgnored` + explicit void. `next lint` warnings: 3 → 0. |

## 6. Post-stabilization gauntlet

Re-run on `stabilization/2026-05-18` after the final commit.

| Check | Result |
|---|---|
| `backend/.venv/bin/pytest -q` | **312 passed** (unchanged) |
| `backend/.venv/bin/ruff check .` | **All checks passed** |
| `frontend/node_modules/.bin/tsc --noEmit` | **0 errors** |
| `frontend/node_modules/.bin/next lint --quiet` | **0 errors, 0 warnings** (was 0 errors, 3 warnings) |
| `frontend/node_modules/.bin/next build` | **27/27 routes compile** |

Branch is 5 commits ahead of `origin/main`. Not pushed.

End of stabilization session.
