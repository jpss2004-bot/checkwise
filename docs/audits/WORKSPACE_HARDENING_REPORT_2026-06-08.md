# CheckWise workspace hardening report - 2026-06-08

Scope: `/Users/josepablosamano/Desktop/Work - LegalShelf/checkwise`, including the active `CheckWise` monorepo, collateral/workshop folders, generated outputs, local storage folders, dependency trees, and deployment/config artifacts.

## 1. Workspace inventory

- Active Git repo: `CheckWise/` (`main...origin/main`). Parent workspace is not a Git repo.
- Source apps: `CheckWise/apps/api` (FastAPI/Python), `CheckWise/apps/web` (Next.js/TypeScript).
- Infrastructure/config: `CheckWise/render.yaml`, `CheckWise/docker-compose.yml`, `.env.example`, `.gitleaks.toml`, `.github/workflows`.
- Product/docs/assets: `CheckWise/docs`, `demo_assets`, `brand_assets`, `design-concepts`, parent `_reference`, `_handoff`, `brand-identity`, `outputs`.
- Local generated/runtime areas: `CheckWise/apps/api/.venv` (~585 MB), `CheckWise/apps/web/node_modules` (~718 MB), `CheckWise/.tmp` (~24 MB), `checkwise-workshops/video-production/remotion/node_modules` (~573 MB), `checkwise-workshops/system-workflow-v2/node_modules` (~196 MB), `outputs` (~122 MB).
- Project-owned files excluding major dependency trees: about 10,067 files inside `CheckWise`.
- Empty source files found: `apps/api/app/services/reports/__init__.py`, `apps/api/app/services/wise/__init__.py`; both are valid package markers.

## 2. Security findings

| Class | Finding | Confidence | Impact | Action |
| --- | --- | ---: | --- | --- |
| SAFE_AUTOFIX | Deprecated/prototyping upload routes defaulted registered unless explicitly disabled, despite docs saying local-only outside production. Routes were auth-gated, but still present in schema/attack surface. | 0.95 | Reduces production route exposure and fuzzing surface. | Fixed: unset now means local-only; explicit true is required outside local. |
| SAFE_AUTOFIX | Route policy manifest drift: three live routes lacked policy rows and one stale `/admin/ocr-config` row remained. | 0.99 | CI route gate failed; endpoint policy review could drift. | Fixed manifest entries for client Wise + report export download URL; removed stale row. |
| SAFE_AUTOFIX | Python dependency audit flagged `aiohttp`, `pyjwt`, and stale local `pip` metadata. | 0.99 | Known CVEs in runtime/transitive dependencies. | Fixed floors in `apps/api/pyproject.toml`, upgraded local venv, archived stale dist-info. |
| SAFE_AUTOFIX | Remotion workshop dependency audit flagged moderate `ws` advisory via Remotion renderer chain. | 0.99 | Local video tooling vulnerability; lower production blast radius but still workspace risk. | Fixed by upgrading Remotion packages to `^4.0.474`. |
| REVIEW_REQUIRED | Populated local env files exist (`apps/api/.env`, `.env.production`, `apps/web/.env.local`) and are correctly ignored. | 0.8 | Secret exposure risk if copied into docs, archives, or manual commits. | Do not print or move; keep ignored. Rotate if any value may have left local machine. |
| REVIEW_REQUIRED | Large sample docs, generated demos, screenshots, and duplicated assets exist across `_reference`, `_handoff`, `docs`, `outputs`, and workshop folders. | 0.85 | Workspace clutter and possible accidental sharing of sample/vendor-like artifacts. | Keep for now; approve a staged archive pass before removing. |

## 3. Architecture findings

- Strong existing controls: docs disabled outside local, explicit CORS allowlist, security headers, JWT placeholder boot refusal, portal CSRF origin checks, upload size/type gates, tenant-scoped portal/client routes, route-policy manifest gate, Redis-capable rate limits.
- Route registration is now more consistent with production posture: deprecated legacy upload and metadata dry-run surfaces are local-only unless explicitly opted in.
- Route-policy manifest now matches live FastAPI routes.
- Remaining architectural debt: FastAPI startup still uses deprecated `on_event`; API tests emit warnings for deprecated FastAPI/Starlette status constants and TestClient cookie usage.

## 4. Folder cleanup report

- No permanent deletion performed.
- Moved stale local venv metadata from active site-packages to `_archive_candidate/2026-06-08-hardening/stale-venv-metadata/pip-26.1.dist-info`.
- Moved the empty top-level workspace scaffold `apps/` to `_archive_candidate/2026-06-08-workspace-cleanup/empty-root-scaffolds/apps`.
- Added parent-level workspace organization docs: `WORKSPACE_INDEX.md` and `_review_required/2026-06-08-workspace-cleanup/CLEANUP_MANIFEST.md`.
- High-noise/generated areas to keep out of commits: `.venv`, `node_modules`, `.cw-next-*`, `.tmp`, workshop render caches, generated PDFs/videos, storage/report exports.
- Confirmed `.gitignore` already ignores populated env files, local storage/upload areas, outputs, build caches, generated PDFs, `.cw-next-*`, and local session artifacts.

## 5. File deletion candidates

Review before permanent deletion:

- `_archive_candidate/2026-06-08-hardening/stale-venv-metadata/pip-26.1.dist-info` - stale pip metadata, already removed from active venv.
- `CheckWise/docs/audit-screenshots/2026-05-18-system-audit/_raw_demo/page@c7d96217c663cdbca1965acd30be0a48.webm` (~20 MB) - raw recording; `.gitignore` says raw demo intermediates are local-only.
- `CheckWise/apps/web/node_modules/@typescript-eslint/.DS_Store` - generated OS clutter inside dependency tree.
- Duplicate sample/reference PDFs under `_reference/sample-docs`, `_handoff/checkwise-video-drive/06_sample_documents`, `CheckWise/apps/api/tests/fixtures/prevalidation`, and `CheckWise/apps/api/storage/demo-sandbox/_blobs` - keep fixtures, but review whether every mirrored copy is still needed.
- Generated workshop/browser caches under `checkwise-workshops/*/node_modules`, `outputs/deck-2026-06-05/cap/node_modules`, and Remotion `.cache`/Chromium folders - regenerate from package locks when possible.

## 6. Changed files list

This pass changed:

- `.env.example`
- `apps/api/app/api/v1/endpoints.py`
- `apps/api/app/api/v1/router.py`
- `apps/api/app/core/config.py`
- `apps/api/app/security/route_policy_manifest.json`
- `apps/api/pyproject.toml`
- `apps/api/tests/test_kill_switches.py`
- `apps/api/tests/test_rate_limit_redis_backend.py`
- `apps/web/components/checkwise/wise/client-wise-dock.tsx`
- `docs/audits/WORKSPACE_HARDENING_REPORT_2026-06-08.md`
- Parent workspace: `checkwise-workshops/video-production/remotion/package.json`
- Parent workspace: `checkwise-workshops/video-production/remotion/package-lock.json`
- Parent workspace: `WORKSPACE_INDEX.md`
- Parent workspace: `_review_required/2026-06-08-workspace-cleanup/CLEANUP_MANIFEST.md`
- Parent workspace: `_archive_candidate/2026-06-08-workspace-cleanup/empty-root-scaffolds/apps`
- Parent workspace archive: `_archive_candidate/2026-06-08-hardening/stale-venv-metadata/pip-26.1.dist-info`

Pre-existing unrelated repo modifications were left intact, including WhatsApp fanout/runbook/render changes, onboarding changes, seed script changes, and untracked storage/handoff/design files.

## 7. Hardening summary

- Made deprecated upload/prototyping route registration local-only by default.
- Added env-template documentation for the route exposure controls.
- Updated route-policy manifest for live report export and client Wise endpoints.
- Removed stale manifest entry for a route no longer registered.
- Raised vulnerable Python dependency floors: `pyjwt>=2.13`, `aiohttp>=3.14.0`.
- Upgraded local venv packages: `pip 26.1.2`, `aiohttp 3.14.1`, `pyjwt 2.13.0`.
- Upgraded Remotion video tooling from `4.0.463` to `^4.0.474`, clearing the `ws` advisory.
- Removed unused frontend `Sparkle` import.
- Stabilized Redis limiter test window so it verifies limiter semantics, not first-call Lua/fakeredis latency.

## 8. Remaining risks

- Full backend Ruff still has existing debt in report-rendering/prompt modules and scripts; touched-file Ruff is clean.
- Local env files are ignored but present; they should never be copied into outputs, handoffs, or review bundles.
- Workspace has large duplicated media/sample-document sets. Cleanup should be staged with explicit approval because some copies are fixtures, demo assets, or sales collateral.
- FastAPI deprecation warnings remain for `on_event` and deprecated HTTP status aliases.
- Some local generated folders are outside the active Git repo, so they are operational workspace hygiene rather than commit-scoped source cleanup.

## 9. Future backlog

1. Add a repo-level hygiene script that inventories dependency trees, generated outputs, raw recordings, stale dist-info, `.DS_Store`, and duplicate hashes without printing secrets.
2. Migrate FastAPI startup from `@app.on_event("startup")` to lifespan.
3. Pay down backend Ruff debt or add documented per-file ignores for intentionally long HTML/prompt files.
4. Replace `vite-tsconfig-paths` with Vite native `resolve.tsconfigPaths: true`.
5. Build a formal asset retention map: fixtures vs. sample docs vs. sales/video artifacts vs. archive candidates.
6. Add a periodic dependency audit job for API, web, and workshop tooling.
7. Review whether ignored `metadata_exports/` and `storage/` should be archived outside the repo workspace after demos.

## 10. Hardening score

- Before: 82/100. The product code already had strong tenant/auth/security foundations, but route exposure defaults, manifest drift, vulnerable dependencies, and generated workspace clutter reduced operational confidence.
- After: 90/100. Production route exposure is tighter, route policy drift is fixed, dependency audits are clean, frontend/backend validation is green, and cleanup candidates are staged rather than deleted.

## Validation evidence

- `apps/api/.venv/bin/python -m pytest apps/api/tests -q` - 1,387 passed, 32 warnings.
- `apps/api/.venv/bin/python -m pytest apps/api/tests/test_rate_limit_redis_backend.py apps/api/tests/test_route_policy_manifest.py apps/api/tests/test_kill_switches.py -q` - 30 passed.
- `apps/api/.venv/bin/python -m ruff check` on touched Python files - passed.
- `apps/api/.venv/bin/python -m pip_audit --skip-editable` - no known vulnerabilities found.
- `npm run lint` in `CheckWise/apps/web` - passed.
- `npm run typecheck` in `CheckWise/apps/web` - passed.
- `npm run test` in `CheckWise/apps/web` - 48 passed.
- `npm run build` in `CheckWise/apps/web` - passed.
- `npm audit --audit-level=moderate` in `CheckWise/apps/web` - 0 vulnerabilities.
- `npm audit --audit-level=moderate` in `checkwise-workshops/system-workflow-v2` - 0 vulnerabilities.
- `npm audit --audit-level=moderate` in `checkwise-workshops/video-production/remotion` - 0 vulnerabilities after upgrade.
