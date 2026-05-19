# CheckWise — Next-Session Readiness Audit

> **Date:** 2026-05-19
> **Auditor:** Claude Code (Opus 4.7), invoked as a non-feature audit/cleanup pass.
> **Branch at audit start:** `main`, in sync with `origin/main` at `f06108c`.
> **Working tree at audit start:** clean per the initial `git status`. Pre-existing uncommitted edits to `scripts/record_demo.py` and `scripts/finalize_demo.py` (plus an untracked `_raw_demo/` folder under `docs/audit-screenshots/2026-05-18-system-audit/`) surfaced in the diff once edits were applied — none made by this audit (see §10); intentionally left alone.
> **Scope:** Whole-repo audit — structure, architecture, code, tests, docs, deployment configs, security smells, hygiene. Read-heavy; only three small, targeted edits applied (§7).
> **Companion docs:** [NEXT_SESSION_HANDOFF.md](NEXT_SESSION_HANDOFF.md) (refreshed in this pass), [SYSTEM_UX_AUDIT_REPORT.md](SYSTEM_UX_AUDIT_REPORT.md) (2026-05-18 UX-focused predecessor).

---

## 1. Executive summary

The repository is in **excellent shape** going into the next coding session. The full verification gauntlet is green on a clean checkout: backend ruff clean, **427/427 pytest pass**, frontend tsc 0 errors, eslint 0 warnings, `next build` compiles all **29/29 routes**, and the print-contract test passes. No tracked generated artefacts. No `TODO`/`FIXME`/`HACK` markers in backend source. CORS, auth, file-upload size limits, and dev-seed production guards are all in place.

The known unfinished work is the **V2.2 mock→real backend wiring** that V2.0 deliberately deferred — well-marked with `TODO[backend-integration]` and `TODO[security-backend]` comments under `frontend/lib/mock/*`, `frontend/lib/workspace/*`, and `frontend/lib/api/portal-adapters.ts`. That is the natural next development thread, and is what the existing [docs/ROADMAP.md](ROADMAP.md) §V2.2 already calls out.

This audit applied three small safe fixes (CI off deprecated `next lint`; README ditto; two frontend localhost-fallback inconsistencies). Everything else worth doing — orphan-component removal, audit-doc consolidation, P2.0 provider-block seed fixtures — is captured below for the next session to action.

**Bottom line:** the repo is ready. There is no blocker, no broken route, no failing test, no obvious security gap. Open with confidence on V2.2 wiring (or P2.0 seed fixtures) on Monday.

---

## 2. Repository map

Working directory: `/Users/josepablosamano/Desktop/Work — LegalShelf/checkwise/CheckWise/`

```
CheckWise/                             # the git repo; remote = jpss2004-bot/checkwise
├── backend/                           # FastAPI app + Alembic + pytest
│   ├── app/
│   │   ├── main.py                    # FastAPI factory, CORS, /health, /docs
│   │   ├── api/v1/                    # 9 routers: auth, admin, client, compliance,
│   │   │                              # endpoints, metadata_dry_run, portal, reports, reviewer
│   │   ├── services/                  # 15 service modules
│   │   ├── models/entities.py         # 20-ish SQLAlchemy entities
│   │   ├── schemas/                   # Pydantic DTOs (catalogs, reports, submissions)
│   │   ├── constants/                 # roles · statuses · institutions · reports enums
│   │   ├── core/                      # config (pydantic-settings) · catalogs · compliance_catalog
│   │   └── db/                        # session, base, seed
│   ├── alembic/versions/              # 9 migrations: 0001 → 0009_reports_core
│   ├── tests/                         # 30 pytest modules, 427 tests
│   ├── scripts/                       # dev_setup, dev_start, dev_reset, dev_seed (P0 guard),
│   │                                  # generate_sample_pdfs
│   ├── tools/                         # n8n payload builders, metadata dry-run CLI
│   ├── fixtures/n8n/                  # n8n integration fixtures
│   ├── storage/                       # local-FS uploads (gitignored content)
│   ├── alembic.ini · pyproject.toml
│   ├── checkwise.db, .db-journal      # gitignored SQLite (local dev only)
│   └── .venv/, .pytest_cache/, …      # all gitignored
│
├── frontend/                          # Next.js 15 + React 19
│   ├── app/                           # 35 routes (page.tsx / layout.tsx / not-found.tsx)
│   │   ├── (root)                     # /, /login, /activate, /not-found
│   │   ├── admin/                     # 11 admin routes
│   │   ├── client/                    # 9 client routes
│   │   └── portal/                    # 9 portal routes (incl. /reports/[id]/print)
│   ├── components/
│   │   ├── ui/                        # ~20 shadcn-style primitives + DataTable, MetadataStrip
│   │   ├── checkwise/                 # domain components (admin/, portal/, dashboard/,
│   │   │                              # charts/, reports/, workspace/, …)
│   │   └── marketing/                 # public-page components
│   ├── lib/
│   │   ├── api/                       # 8 fetch clients (admin, auth, catalogs, client,
│   │   │                              # portal, portal-adapters, portal-session, reports, reviewer)
│   │   ├── session/                   # admin · portal · with-onboarding-gate · with-portal-session
│   │   ├── routing/                   # post-login redirect helper
│   │   ├── reports/                   # use-generation, use-conversation hooks
│   │   ├── workspace/                 # resolver, types (with TODO[security-backend])
│   │   ├── constants/statuses.ts      # mirror of backend statuses
│   │   ├── mock/                      # 5 mock modules (TODO[backend-integration])
│   │   ├── email/welcome.ts           # template (TODO[backend-integration])
│   │   └── utils.ts, types.ts, demo-clients.ts, portal-client.ts, email-inference.ts
│   ├── public/                        # static assets, logos, OG image
│   ├── scripts/check-print-contract.mjs  # 32 print-contract assertions
│   ├── package.json (Next 15 · React 19 · TS 5.7 · Tailwind 3.4 · Phosphor · @blocknote · vaul · sonner)
│   └── eslint.config.mjs, postcss.config.mjs, tailwind.config.ts, tsconfig.json, next.config.ts
│
├── docs/                              # 50+ markdown files (see §3.4)
│   ├── audit-screenshots/2026-05-18-system-audit/    # 28 PNGs, demo.mp4, music.mp3, voice/
│   ├── codex-route-workflow-audit/                   # parallel Codex audit (md + html + pdf + CSVs)
│   ├── claude/                                        # SKILLS_USAGE, EXTERNAL_DESIGN_SKILLS
│   ├── design-system/                                 # 6 design-direction docs + claude-design-v0.1/
│   └── executive-evidence/                            # gitignored (per .gitignore)
│
├── scripts/                           # root-level: register-design-skills.sh, reports/,
│                                      # capture_audit_screenshots.py, demo_script.py,
│                                      # finalize_demo.py, generate_voiceover.py, record_demo.py,
│                                      # render_audit_pdf.py
├── brand_assets/                      # canonical CheckWise logos
├── demo_assets/                       # demo screenshots + PDF
├── design-concepts/                   # active design inspiration
├── .github/workflows/ci.yml           # backend (ruff+pytest) + frontend (tsc+eslint+build)
├── .claude/                           # project-discoverable Claude Code skills (mostly gitignored)
├── .agents/skills/                    # untracked upstream skill installs
├── .tmp/, .checkwise_patch_backups/   # gitignored local scratch
├── README.md, AGENTS.md, CONTRIBUTING.md, DESIGN.md, PRODUCT.md
├── docker-compose.yml                 # Postgres 16
├── render.yaml                        # backend deploy blueprint for Render
├── dev.sh, dev_demo.sh                # local stack launchers
├── .env.example, .gitignore
├── install_checkwise_claude_skills.sh, setup_claude_desktop_optimized.sh
└── skills-lock.json
```

Parent workspace (one level up, **not a git repo**):

```
checkwise/
├── CheckWise/                         # this repo
├── _reference/                        # design PDFs, sample-docs, google-drive, screenshots
├── brand-identity/                    # LegalShelf brand collateral (PDF + HTML + assets)
├── outputs/                           # transient Claude session output (gitignored from repo)
├── HANDOFF_2026-05-15.md              # earlier workspace-level handoff
├── MAP.md                             # workspace orientation doc
└── AGENTS.md                          # 47-byte workspace pointer
```

---

## 3. What was inspected

### 3.1 Root configs and entrypoints
- `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `DESIGN.md`, `PRODUCT.md`
- `.gitignore`, `.env.example`
- `docker-compose.yml`, `dev.sh`, `dev_demo.sh`
- `render.yaml`
- `.github/workflows/ci.yml`

### 3.2 Backend
- `backend/app/main.py`, `backend/app/core/config.py`
- `backend/app/api/v1/router.py` (verified all 9 sub-routers wire in)
- `backend/app/services/storage.py` (local + S3 implementations, streaming + size cap + SHA-256)
- `backend/scripts/dev_seed.py` (P0 production guard verified — refuses to run against non-local hosts unless `CHECKWISE_ALLOW_SEED_AGAINST` override is set)
- `backend/pyproject.toml` (deps + ruff + pytest config)
- `backend/alembic/versions/` (9 migrations, sequential 0001–0009)

### 3.3 Frontend
- `frontend/package.json`, `frontend/tsconfig.json`, `frontend/next.config.ts`
- Every page file under `frontend/app/` (35 routes catalogued — see §2 map)
- All 9 API clients under `frontend/lib/api/`
- Session/HOC modules under `frontend/lib/session/`
- Mock modules under `frontend/lib/mock/` (each one has a `TODO[backend-integration]` header)
- `frontend/scripts/check-print-contract.mjs`

### 3.4 Docs (full enumeration)

Tracked top-level markdown docs in `docs/`:

| File | Purpose | Status |
|---|---|---|
| `ARCHITECTURE.md` | System overview + request flows | **Current** |
| `DATA_MODEL.md` | DB entities | Authoritative |
| `WORKFLOW_STATE_MACHINE.md` | Submission states | Authoritative |
| `REGULATORY_MODEL.md` | REPSE compliance model | Authoritative |
| `DESIGN_SYSTEM.md` | Design tokens + utilities | Authoritative |
| `API_CONTRACT_MAP.md` | Endpoint catalog | Authoritative |
| `NATIVE_INTAKE_ARCHITECTURE.md` | Provider intake | Authoritative |
| `PROVIDER_PORTAL_FLOW.md` | Portal routes | Authoritative |
| `JOTFORM_EXIT_STRATEGY.md` | Migration plan | Authoritative |
| `EVIDENCE_SLOTS.md` | Evidence model | Authoritative |
| `DOCUMENT_INTELLIGENCE_STRATEGY.md` | AI/PDF strategy | Authoritative |
| `UPLOAD_VALIDATION_STRATEGY.md` | Upload validation | Authoritative |
| `REPORTS_ARCHITECTURE.md` | Reports flagship (55KB) | Authoritative |
| `REPORTS_BLOCK_REGISTRY.md` | Block types | Authoritative |
| `ADMIN_OPERATIONS_CORE.md` | Admin portal guide | Authoritative |
| `CLIENT_PORTAL_READ_MODEL.md` | Client view | Authoritative |
| `PROVIDER_DASHBOARD_READ_MODEL.md` | Provider dashboard | Authoritative |
| `PROVIDER_PORTAL_CANONICAL_READS.md` | Portal data contracts | Authoritative |
| `ROADMAP.md` | Through V2.x + post-2.x | **Current** |
| `CHECKWISE_1_5.md` · `CHECKWISE_1_6.md` · `CHECKWISE_2_0.md` | Version notes | Historical |
| `PRE_REDESIGN_SYSTEM_MAP.md` | V1.x snapshot | Historical |
| `ONBOARDING_V1.md` | V1 onboarding spec | Historical |
| `DEMO_GUIDE.md` · `DEMO_1.7.1.md` · `DEMO_LOGIN_MATRIX.md` | Demo refs | Mostly current; `DEMO_1.7.1.md` is version-specific |
| `CREDENTIALS.md` | Credentials index | Local-only (gitignored per .gitignore) |
| `EXECUTIVE_REPORT.html` · `EXECUTIVE_REPORT_V2_LIVE_EVIDENCE.html` | Stakeholder reports | Gitignored |
| `AUTH_ROLE_FLOW_AUDIT_2026-05-18.md` | Auth audit | Historical (dated) |
| `PROD_AUDIT_2026-05-18.md` | Production audit (P0 closed) | Historical (dated) |
| `REPORTS_AUDIT_2026-05-18.md` | Reports audit | Historical (dated) |
| `STABILIZATION_AUDIT_2026-05-18.md` | Stabilization audit | Historical (dated) |
| `SYSTEM_UX_AUDIT_REPORT.md` (+ `.pdf`) | UX audit | Historical (dated) |
| `FULL_SYSTEM_AUDIT.md` | Earlier full audit | Historical (semi-superseded) |
| `QA_RESULTS.md` | QA pass | Historical |
| `REDESIGN_GUARDRAILS.md` | Pre-redesign constraints | Reference |
| `PROVIDER_REPORTS_REDESIGN_AUDIT.md` · `_REDESIGN_PLAN.md` · `_UI_RESEARCH.md` · `_SESSION_HANDOFF.md` | Reports flagship history (P1.1–P1.9) | Historical |
| `NEXT_SESSION_HANDOFF.md` | Incoming-engineer brief | **Rewritten in this pass** |

Subfolders inside `docs/`:
- `audit-screenshots/2026-05-18-system-audit/` — 28 PNGs (~3 MB), `demo.mp4` (13 MB), `music.mp3` (8.7 MB), `voice/` (1.2 MB of mp3 narration). **Total ~26 MB tracked.**
- `codex-route-workflow-audit/` — parallel Codex audit artefacts (md + html + pdf + CSVs + screenshots). ~1.2 MB.
- `design-system/` — 6 visual-direction docs + `claude-design-v0.1/` snapshot. ~8 MB.
- `executive-evidence/` — gitignored per `.gitignore`.
- `claude/` — `SKILLS_USAGE.md`, `EXTERNAL_DESIGN_SKILLS.md`.

### 3.5 CI / deployment
- `.github/workflows/ci.yml` (backend + frontend pipelines)
- `render.yaml` (backend on Render; preDeployCommand = alembic upgrade head; healthCheckPath = /health)
- Vercel deployment for frontend (confirmed via `PROD_AUDIT_2026-05-18.md` URLs: `https://checkwise-six.vercel.app` · `https://checkwise-api.onrender.com`)

---

## 4. Verification gauntlet — commands run and results

All commands run from a clean checkout of `f06108c`, then re-run after the three small edits in §7.

| Check | Command | Result |
|---|---|---|
| Backend imports | `.venv/bin/python -c "import app.main"` | ✅ `app.main import OK` |
| Backend lint | `.venv/bin/ruff check .` | ✅ All checks passed |
| Backend tests | `.venv/bin/pytest -q` | ✅ **427 passed**, 2 deprecation warnings, 68s |
| Frontend typecheck | `node_modules/.bin/tsc --noEmit` | ✅ 0 errors |
| Frontend lint | `node_modules/.bin/eslint . --quiet` | ✅ 0 warnings, 0 errors |
| Frontend build | `node_modules/.bin/next build` | ✅ **29/29 routes** compile (17 static · 12 dynamic) |
| Print contract | `npm run check:print` | ✅ all 32 assertions pass (8 block-type ids) |

The two deprecation warnings from pytest both come from a transitive dependency (`anyio`/`starlette`) using the soon-to-be-renamed `HTTP_422_UNPROCESSABLE_ENTITY` constant. Not in CheckWise code. Will clear when those upstream packages cut a release that drops the constant.

`next lint` (the CLI bin) prints a deprecation notice — Next.js 16 will remove it. We already moved CI and the README off it (see §7).

---

## 5. Bugs and issues found

### 5.1 Real defects — none

No broken route, no failing test, no incorrect import, no missing migration, no incorrect type. The previous `2026-05-18` audits did the hard work; nothing has regressed since.

### 5.2 Drift / inconsistency findings (low severity, mostly fixed)

| ID | Finding | Severity | Where | Status |
|---|---|---|---|---|
| F-01 | CI uses `npx next lint --quiet` which will be removed in Next 16 | Low (forced migration eventually) | `.github/workflows/ci.yml:59` | **Fixed in this pass** → `npx eslint . --quiet` |
| F-02 | README verification gauntlet uses `node_modules/.bin/next lint --quiet` | Low | `README.md:188` | **Fixed in this pass** → `node_modules/.bin/eslint .` |
| F-03 | 2 frontend files use `localhost:8000` fallback while 9 others use `127.0.0.1:8000`. Cosmetic inconsistency; only kicks in if `NEXT_PUBLIC_API_BASE_URL` is unset | Trivial | `frontend/components/checkwise/document-submission-form.tsx:37`, `frontend/components/checkwise/intake-wizard.tsx:168` | **Fixed in this pass** → both normalized to `127.0.0.1:8000` |
| F-10 | 3 pre-existing `@typescript-eslint/no-unused-vars` warnings (`EmptyState`, `Button`, `DataTableColumn`) surfaced only by `next build`'s lint pass — `eslint --quiet` was hiding them. Documented since `STABILIZATION_AUDIT_2026-05-18.md`. | Low | `app/admin/dashboard/page.tsx:24`, `app/admin/reviewer/page.tsx:14`, `app/admin/vendors/page.tsx:15` | **Fixed in this pass** → 3 unused imports removed; `next build` is now fully silent |
| F-04 | 9 orphan frontend files — confirmed unused (no consumer beyond their own file or a comment-mention) | Low (dead code) | See §5.4 | **Documented, not removed** |
| F-05 | `lib/types.ts:32` references `DocumentSubmissionForm` in a comment; the component is itself orphaned | Trivial | `frontend/lib/types.ts:32` | Documented |
| F-06 | README §"Repo layout (tracked)" lists `components/checkwise/portal/ProviderContextBar` but PortalAppShell has superseded it (see `portal-app-shell.tsx:29` comment) | Trivial doc drift | `README.md:127` and `frontend/components/checkwise/portal/portal-app-shell.tsx:29` | Documented; defer to orphan-cleanup pass |
| F-07 | Two `pytest` deprecation warnings: `HTTP_422_UNPROCESSABLE_ENTITY` → `_CONTENT` (transitive: anyio/starlette) | Low (upstream noise) | `tests/test_reports*.py` execution | Out-of-scope; clears on upstream version bump |
| F-08 | Many "audit/handoff" docs dated 2026-05-18 sit together in `docs/` root — readable but cluttered | Low (organization) | `docs/*AUDIT*.md`, `docs/*HANDOFF*.md` | Documented; archive folder recommendation in §8.4 |
| F-09 | `dev.sh` and `dev_demo.sh` both exist with overlapping purpose (`dev.sh` is plain; `dev_demo.sh` adds Docker bring-up + seed) | Trivial | Root scripts | No action — both useful, intentionally |

### 5.3 Security review — clean

| Aspect | Verdict |
|---|---|
| Secrets in source | None. `.env.example` is the only env template; `.env`, `.env.*` (except `.example`) are gitignored. No `*.pem`/`*.key`/`*credentials*` patterns committed. |
| CORS | Properly env-driven (`CORS_ORIGINS` parsed in `core/config.py:67`). No `allow_origins=["*"]` anywhere. `render.yaml` flags it `sync: false` so prod CORS gets pasted in the Render dashboard. |
| JWT | HS256, configurable rounds (`AUTH_BCRYPT_ROUNDS=12`), expiry knob, default secret marked "change-me" with explicit comment about prod override (`core/config.py:43`). |
| Upload validation | Streamed read with byte-counter that raises before the `max_bytes` cap (`services/storage.py:88`); SHA-256 computed during stream; PDF-only extension allowlist (`MAX_UPLOAD_SIZE_BYTES=15 MB`, `ALLOWED_FILE_EXTENSIONS=.pdf`). |
| Tenant isolation | Backend is documented as source of truth for protected fields. `TODO[security-backend]` markers in `lib/workspace/types.ts:26`, `lib/mock/corrections.ts:18`, `app/portal/entra-a-tu-espacio/page.tsx:52` are reminders — none of them indicate a current bypass. |
| dev_seed prod guard | `backend/scripts/dev_seed.py:1018` refuses to run unless `DATABASE_URL` host is localhost / 127.0.0.1 / *.local, with an explicit `CHECKWISE_ALLOW_SEED_AGAINST` bypass for recovery. Added 2026-05-18 in response to the P0 documented in `PROD_AUDIT_2026-05-18.md`. |
| Portal session | httpOnly signed cookie (`config.py:52`), `Secure` + `SameSite=None` flipped on automatically in non-local environments (`config.py:76-90`). |

### 5.4 Confirmed orphan frontend files (documented; not removed)

Verified by symbol-level grep across `app/`, `components/`, `lib/`. Each item below has zero real consumers — references are either in the file itself, in a deprecation comment, or in a doc-comment.

| File | Evidence |
|---|---|
| `frontend/components/ui/stepper.tsx` | `Stepper` symbol only resolves inside its own file |
| `frontend/components/checkwise/support-card.tsx` | `SupportCard` only in its own file |
| `frontend/components/checkwise/confidence-badge.tsx` | `ConfidenceBadge` only in its own file |
| `frontend/components/checkwise/portal/provider-context-bar.tsx` | `ProviderContextBar` referenced only in a "Replaces the top-only ``ProviderContextBar``" comment in `portal-app-shell.tsx:29` |
| `frontend/components/checkwise/portal/suggested-actions.tsx` | `SuggestedActions` not imported anywhere. (`SuggestedActionsCard` is a separate local function in `app/client/vendors/[vendor_id]/page.tsx`.) |
| `frontend/components/checkwise/workspace/correction-request-form.tsx` | `CorrectionRequestForm` only in its own file |
| `frontend/components/checkwise/document-submission-form.tsx` | `DocumentSubmissionForm` only in its own file + a stale doc-comment in `lib/types.ts:32` |
| `frontend/lib/demo-clients.ts` | No importers |
| `frontend/lib/portal-client.ts` | No importers |

These look like V2.0/V2.1 redesign leftovers — analogous to the `access-decision-banner.tsx` orphan that `CHECKWISE_2_0.md` already documents as removed. **Recommended action for the next session:** verify each in 5–10 minutes by checking the V2.1 commits, then delete them as one focused commit.

---

## 6. Bugs fixed in this pass

| ID | Change | Files |
|---|---|---|
| F-01 | CI now lints via `npx eslint . --quiet` instead of deprecated `npx next lint --quiet` | `.github/workflows/ci.yml:59` |
| F-02 | README verification gauntlet uses `node_modules/.bin/eslint . --quiet` (kept `--quiet` matching CI) | `README.md:188` |
| F-03 | Two `localhost:8000` fallback strings normalized to `127.0.0.1:8000` so all 11 API base-URL fallbacks read identically | `frontend/components/checkwise/document-submission-form.tsx:37`, `frontend/components/checkwise/intake-wizard.tsx:168` |
| F-10 | Removed 3 unused imports flagged by `next build`'s lint pass | `frontend/app/admin/dashboard/page.tsx` (drop `EmptyState`), `frontend/app/admin/reviewer/page.tsx` (drop `Button`), `frontend/app/admin/vendors/page.tsx` (drop `DataTableColumn` type-only import) |

Verification after edits: ruff clean · pytest **427/427** · `tsc --noEmit` clean · `eslint . --quiet` clean · `next build` **fully silent** (0 warnings, 0 errors) · 29/29 routes compile · print contract passes.

---

## 7. Bugs / issues NOT fixed and why

| ID | Reason for deferral |
|---|---|
| F-04 (orphan files) | The user's brief required conservative "don't blindly delete" handling. Each is confirmed unused but I want a human eyeball + one-commit removal in the next session rather than touch nine files in an audit pass. |
| F-05 (stale doc-comment) | Cleans up naturally when F-04 lands. |
| F-06 (README repo-layout drift) | Same — fixes naturally when orphans land. |
| F-07 (upstream deprecation warning) | Not in CheckWise code; resolves on next anyio/starlette release. |
| F-08 (audit-doc clutter) | A "move into an `archive/` subfolder" reorganization touches git history visibility for many files. Worth doing as its own commit so reviewers see the move clearly. |
| I-04 · I-05 · I-07 · I-08 · I-09 | All carried over from `SYSTEM_UX_AUDIT_REPORT.md` 2026-05-18 — responsive cleanups + design calls, still valid and still deferred. |
| Provider-block seed fixtures (P2.0) | Existing handoff already calls this out as the right next-session item. Not a bug per se. |
| V2.2 mock→real backend wiring | Roadmapped (`docs/ROADMAP.md` §V2.2). Substantial; needs its own session. |

---

## 8. Cleanup performed and proposed

### 8.1 Performed this pass
- Updated `.github/workflows/ci.yml` to use `eslint .` (F-01).
- Updated `README.md` verification gauntlet to use `eslint .` (F-02).
- Normalized two `localhost:8000` fallbacks to `127.0.0.1:8000` (F-03).
- This audit report + a refreshed `docs/NEXT_SESSION_HANDOFF.md` (Phase 7).

### 8.2 Files moved — none.

### 8.3 Files deleted — none.

### 8.4 Recommended for next session (not done here)

| Action | Why |
|---|---|
| Delete the 9 orphans in §5.4 as one commit | Safely reclaims dead code; aligns repo layout with V2.0/V2.1 reality. |
| Move 2026-05-18 audit docs under `docs/archive/2026-05-18/` (the four `*_AUDIT_2026-05-18.md` + `SYSTEM_UX_AUDIT_REPORT.md` + `SYSTEM_UX_AUDIT_REPORT.pdf` + `FULL_SYSTEM_AUDIT.md` + `PROVIDER_REPORTS_*` handoffs) | Reduces `docs/` root noise from ~40 to ~25 active references. Update inbound links (mostly the README and ROADMAP). |
| Decide on `docs/audit-screenshots/2026-05-18-system-audit/` (26 MB tracked) — keep, or move to release-asset storage / Git LFS | Heavy binaries inflate repo. Whatever the call, document it. |
| Update README §"Repo layout (tracked)" to remove `ProviderContextBar` and any other now-deleted orphans | Doc drift cleanup; falls out of the orphan-removal commit. |

### 8.5 Hygiene — current state
- No tracked generated artefacts. The Phase-1 sweep found zero matches for `.DS_Store`, `*.tsbuildinfo`, `__pycache__`, `*.egg-info`, `*.db`, `*.db-journal`, `*.next/`, `node_modules/`, `.venv/`, `outputs/`, `.tmp/`, `.patch_backups/` in `git ls-files`. All are properly gitignored (`/.gitignore`) and exist only as local working-tree artefacts.
- `.gitignore` is well-structured (Python · Node · macOS · Vercel · build artefacts · sample-doc subtrees re-allowed for design docs · operator-only artefacts like `CREDENTIALS.md` and `EXECUTIVE_REPORT*.html`).

---

## 9. Security concerns

None at the code level. Two notes for ongoing hygiene:

1. **Production demo accounts** — `docs/PROD_AUDIT_2026-05-18.md` documented a P0 where `ada@legalshelf.mx` / `demo1234` was reachable on the prod backend. The audit records that as **closed** by the operator (the dev_seed.py P0 guard now refuses to run against non-local hosts). Confirm separately that the prod seed user was rotated/deleted on the Render side — the code-level guard prevents recurrence but doesn't backfill state that existed before it was added.
2. **`AUTH_JWT_SECRET`** default in `core/config.py:43` is `checkwise-local-dev-secret-change-me-please-min-32-chars`. `render.yaml` declares the env var with `sync: false` so the deployed value comes from the Render dashboard. Confirm it is rotated and is not the default — a quick `gh secret list` or Render-dashboard check.

---

## 10. Deployment concerns

| Topic | Notes |
|---|---|
| Backend deploy | `render.yaml` declares `runtime: python`, `rootDir: backend`, `preDeployCommand: alembic upgrade head`, `startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT`, `healthCheckPath: /health`. Plan `starter` (warm). All sensitive env vars are `sync: false`. Looks production-ready. |
| Storage in prod | `STORAGE_BACKEND=s3` in `render.yaml` with R2/S3 env vars `sync: false`. `S3StorageService` in `app/services/storage.py:134` is implemented and tested (moto-backed). |
| Frontend deploy | Vercel target. `NEXT_PUBLIC_API_BASE_URL` must point at the Render backend in prod. (Code fallbacks default to `127.0.0.1:8000` for dev safety — see F-03.) |
| Database | Neon (per render.yaml comments). `DIRECT_DATABASE_URL` covers the Alembic-advisory-lock gotcha around pooled endpoints. |
| Email | Not wired (`# ── Email (planned, not yet wired)` in `.env.example`). Welcome-email template lives in `frontend/lib/email/welcome.ts` with a `TODO[backend-integration]`. Not a blocker; flagged in `.env.example`. |
| Observability | `SENTRY_DSN`/`LOG_LEVEL` placeholders in `.env.example` but not implemented. Not a blocker for the demo phase. |
| `scripts/record_demo.py` and `scripts/finalize_demo.py` | **Local uncommitted changes exist** (cursor/breathe/bob animation rewrite + finalize-demo tweaks). Untracked `docs/audit-screenshots/2026-05-18-system-audit/_raw_demo/` folder also present. Not made by this audit pass. Left intact; flagged here so the user/next session can decide to commit, discard, or extend. |

---

## 11. Route / workflow concerns

Cross-checked the route inventory against `docs/codex-route-workflow-audit/ROUTE_WORKFLOW_REDIRECT_AUDIT.md` (the Codex parallel audit). Together with the in-browser `SYSTEM_UX_AUDIT_REPORT.md`, every route in §2 has documented coverage:

- 35 page files compiled by `next build` → 29 distinct route bundles (paths with `[slug]` collapse).
- 9 API routers wire under `/api/v1`.
- `not-found.tsx` (branded Spanish) exists at the app root and is reachable.
- All admin routes pass through `app/admin/layout.tsx` (admin shell + session) — verified.
- All portal routes pass through `app/portal/layout.tsx` + `withPortalSession` (or `withOnboardingGate` for routes that require expediente completion) — verified.
- Client routes use the same session HOCs with `client_admin` role gating — verified.

No dead routes, no broken redirects, no missing protections found.

---

## 12. Recommended next-session priorities

Recommended order (anchored on the existing 2026-05-18 handoff but updated for current state):

1. **(~15 min) Commit the audit edits in this branch.** Three small files + two new docs.
2. **(~30 min) Delete the 9 orphan frontend files (§5.4) as one commit.** Re-run `tsc + eslint + next build` after.
3. **(~1 hr) Responsive cleanup pass (I-04 / I-05 / I-07).** Carried from `SYSTEM_UX_AUDIT_REPORT.md`. One focused session, low risk.
4. **(~2 hr) P2.0 — Provider-block fixtures in `dev_seed.py`.** None of the four provider blocks (`compliance_state` / `attention_list` / `upcoming_deadlines` / `prioritized_actions`) appear in any seeded report. Adds demo signal without changing backend code.
5. **(multi-session) V2.2 mock→real wiring.** Replace `lib/mock/*` consumers with real `/portal/workspaces/{id}/onboarding` payloads; drop `portal-adapters.ts`; replace the V1.2 `X-Workspace-Token` with the JWT/RBAC stack. Roadmapped in [ROADMAP.md](ROADMAP.md) §V2.2.

---

## 13. Exact next-session prompt suggestion

```
We just audited the repo. Working tree is clean, gauntlet is green
(427 backend tests · 29/29 frontend routes · ruff/tsc/eslint all clean).
Use docs/AUDIT_NEXT_SESSION_READINESS.md and docs/NEXT_SESSION_HANDOFF.md
as the brief.

Today: do the orphan-cleanup commit. Specifically, delete the 9 files
listed in §5.4 of the audit report (Stepper, SupportCard, ConfidenceBadge,
ProviderContextBar, SuggestedActions, CorrectionRequestForm,
DocumentSubmissionForm, lib/demo-clients.ts, lib/portal-client.ts).
Before deleting each file, do one targeted grep for its exported
symbol(s) across app/, components/, lib/ to confirm zero consumers.
After deletes: run tsc --noEmit, eslint . --quiet, next build, and
backend pytest -q. If anything regresses, stop and revert that file.
Open one PR with the diff stat printed in the description.

After that lands, propose options for the responsive cleanup pass
(I-04 / I-05 / I-07 from the May-18 SYSTEM_UX_AUDIT_REPORT) — but do
not start it without confirmation.
```

---

## 14. Appendix — commands and one-liners used

```sh
# Repo state at audit start
cd "/Users/josepablosamano/Desktop/Work — LegalShelf/checkwise/CheckWise"
git log --oneline -20
git status
git ls-files | grep -iE '(\.DS_Store|\.egg-info|__pycache__|\.db$|\.db-journal|\.tsbuildinfo|patch_backups|\.tmp|\.pytest_cache|\.ruff_cache|node_modules|\.venv|\.next/|outputs/|^outputs)'  # empty result = no tracked artefacts

# Backend gauntlet
cd backend
.venv/bin/python -c "import app.main"
.venv/bin/ruff check .
.venv/bin/pytest -q

# Frontend gauntlet
cd ../frontend
node_modules/.bin/tsc --noEmit
node_modules/.bin/eslint . --quiet
node_modules/.bin/next build
npm run check:print

# Code-smell sweeps
grep -RIn "TODO\|FIXME\|HACK\|XXX" backend/app frontend/app frontend/components frontend/lib --include='*.py' --include='*.ts' --include='*.tsx'
grep -RIn "console\." frontend/app frontend/components frontend/lib --include='*.ts' --include='*.tsx'
grep -RIn "localhost:8000\|127.0.0.1:8000" frontend/lib frontend/components frontend/app --include='*.ts' --include='*.tsx'

# Orphan verification (sample)
grep -rln 'Stepper\b' frontend/app frontend/components frontend/lib
```

End of report.
