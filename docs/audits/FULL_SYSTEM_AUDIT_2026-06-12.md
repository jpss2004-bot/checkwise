# Full system + workspace audit — 2026-06-12

Scope: document delivery paths (download / preview / extract / audit package) across the
three portals, feature-surface consistency, repo hygiene, and full workspace-folder
hygiene. Findings below were produced by four parallel audit passes and the
highest-severity claims were hand-verified against the code before inclusion.

---

## 1. Document delivery — root cause confirmed

**One bug class explains the reported breakage: top-level navigations
(`<a href>` / `window.open`) pointed at endpoints whose only accepted auth is the
`Authorization: Bearer` header.** Browsers never attach custom headers to
navigations, so these requests arrive unauthenticated and the API returns 401.
`get_current_user` (apps/api/app/api/v1/auth.py:405-410) reads **only** the
Authorization header — there is no cookie or query-token fallback on the
admin/client side.

### Confirmed broken (P0)

| # | Surface | Call site | Endpoint | Why broken |
|---|---------|-----------|----------|------------|
| 1 | Admin — vendors list | apps/web/app/admin/vendors/page.tsx:281 `<a href={adminVendorExpedienteZipUrl(...)}>` | GET /api/v1/admin/vendors/{id}/expediente.zip (internal_admin, Bearer-only) | Navigation sends no Authorization header → 401 |
| 2 | Admin — vendor detail | apps/web/app/admin/vendors/[vendor_id]/page.tsx:153 same pattern | same endpoint | same → 401 |
| 3 | Client — vendor expediente | apps/web/app/client/vendors/[vendor_id]/page.tsx:126 `<a href={clientVendorExpedienteZipUrl(...)}>` | GET /api/v1/client/vendors/{id}/expediente.zip (ClientUser, Bearer-only) | same → 401 |
| 4 | Client — audit package ("todo seleccionado" path) | apps/web/app/client/auditoria/page.tsx:277 `window.open(downloadUrl)` | GET /api/v1/client/audit-package.zip (ClientUser, Bearer-only) | same → 401. The POST path (tree-picker selections) uses fetch+Bearer and works — so the same button works or fails depending on what the user selected. |

The docstring on `clientAuditPackageZipUrl` (apps/web/lib/api/client.ts:797-801)
claims "the bearer cookie carries" — **false**; there is no bearer cookie on the
client/admin portals. The comment encoded the wrong mental model and the pattern
was then copied.

### Fragile but probably working

- **Provider portal** expediente ZIP + document download navigations
  (portal/dashboard, portal/calendar) rely on the portal **session cookie**, which
  the portal endpoints do accept (cookie + JWT + legacy X-Workspace-Token). Cookie
  is SameSite=None;Secure in prod, which top-level navigations do send. Works, but
  it is a third auth model and breaks silently if cookie delivery ever changes.
- **Previews** in all three portals go through fetch→Blob helpers
  (`fetchSubmissionDocumentBlob`, `fetchClientSubmissionDocumentBlob`,
  `fetchReviewerSubmissionDocumentBlob`) with explicit Bearer headers → correct.
  In prod (R2 backend) the endpoint 307-redirects to a presigned URL → correct.

### Likely-broken under local dev / CWD drift (P1)

- `LOCAL_STORAGE_PATH: str = "./storage"` (apps/api/app/core/config.py:27) is
  CWD-relative. The workspace currently contains **three** storage dirs
  (workspace-root `storage/`, `CheckWise/storage/`, `CheckWise/apps/api/storage/`)
  — physical evidence that the process has been launched from different CWDs and
  scattered files. Local downloads/previews 404 ("Documento no disponible en
  almacenamiento") whenever the reading process's CWD differs from the writing
  process's. `METADATA_EXPORT_PATH: "./metadata_exports"` has the same flaw
  (repo-root `metadata_exports/` vs `apps/api/metadata_exports/` both exist).
  Prod (R2) is unaffected for documents but metadata XLSX exports still hit local
  disk — which on Render is **ephemeral**, so metadata download links die on each
  deploy/restart.
- Admin/client metadata download endpoints (admin.py:2849, 2919; client.py:2606)
  return `FileResponse(path)` **without an existence check** (portal.py:2146 does
  check) → unhandled error instead of a clean 404 + log line.

### Inconsistencies (P2)

- Audit-package INDICE.pdf manifest render failures are swallowed
  (client.py:3054-3076): the ZIP downloads "successfully" but silently lacks its
  legally-significant cover page.
- Three different auth models for the same action across the three portals
  (cookie+JWT+legacy-token vs Bearer-only vs Bearer-only).

---

## 2. Feature-surface findings

| Severity | Finding | Location |
|----------|---------|----------|
| BUG | Backend `STATUS_LABELS_ES` still ships pre-unification labels ("Recibido", "Prevalidado", "Pendiente de revisión", "Excepción legal") while the frontend glossary (apps/web/lib/constants/statuses.ts:77-86) collapsed them to "En revisión" / "Aprobado con nota legal" (2026-06-10 vocabulary unification). Consumed by core/catalogs.py → /api/v1/catalogs. Any surface rendering backend-provided labels contradicts the UI glossary. | apps/api/app/constants/statuses.py:60-72 |
| INCONSISTENCY | ~20 config vars / feature flags missing from .env.example (AUTO_APPROVE_*, RECURRING_CATALOG_V2, MULTI_FILE_UPLOAD_ENABLED, SLACK_CORRECTION_WEBHOOK_URL, NEXT_PUBLIC_MULTI_FILE_UPLOAD_ENABLED, …). MULTI_FILE_UPLOAD also undocumented in render.yaml → no prod kill switch documented. | .env.example, render.yaml |
| LIKELY-BUG (verify) | `TODO[security-backend]` on `ProtectedWorkspaceFields` — confirm backend re-validates workspace/tenant/role ids against session everywhere. | apps/web/lib/workspace/types.ts:26 |
| SMELL | Mock modules still flagged "replace with real endpoint" (lib/mock/invitations.ts, calendar.ts, contact-requests.ts) — verify none are live in prod surfaces. | apps/web/lib/mock/* |
| SMELL | console.warn/error leftovers (portal/dashboard/page.tsx, feedback-launcher.tsx); silent localhost:8000 fallback when NEXT_PUBLIC_API_BASE_URL unset. | apps/web |

Known open risk (pre-existing): `_actor_from` workspace-ownership precedence
shadowing org memberships in list_reports.

---

## 3. Repo hygiene (CheckWise/)

- **Untracked now**: commit `_handoff/2026-05-26_browser_audit_kickoff.md`; gitignore
  `metadata_exports/` + `storage/` (root-level — the apps/api variants are already
  ignored); decide track-vs-ignore for `seed_dtp_demo.py` + `verify_dtp.py`;
  normalize the lone untracked GOV.UK inspo PDF.
- **Docs**: ~34 root docs; archive NATIVE_INTAKE_ARCHITECTURE, JOTFORM_EXIT_STRATEGY,
  ONBOARDING_V1, UPLOAD_VALIDATION_STRATEGY; refresh-or-archive REPO_CLEANUP_PLAN,
  DATA_MODEL; review docs/codex-route-workflow-audit/ (13 files) for archive.
- **Scripts**: ~6 one-off demo/video production scripts in scripts/ (capture_audit_screenshots,
  record_demo, render_audit_pdf, demo_script, generate_voiceover, finalize_demo)
  → archive; delete ut_2026_06_01 seed + SQL fixtures once that UT cycle is closed.
- **Secrets**: clean. No tracked env files; gitleaks config sound.
- **Tests**: backend healthy (~1,387 passing, active); frontend coverage is
  constants-only (acceptable, note for later).

## 4. Workspace hygiene (parent folder, ~4 GB)

Existing CLEANUP_MANIFEST (2026-06-08) is partially executed. Recommended batches:

- **Batch 1 — immediate, low risk (~92 MB)**: delete `_handoff/checkwise-video-drive.zip`
  (uncompressed sibling kept), `CheckWise/.tmp/` (May-25 captures, superseded),
  `.ruff_cache/`; archive `CheckWise/metadata_exports/` stale snapshots; delete
  `outputs/checkwise-capturas-2026-06-10.zip` after confirming the folder is final.
- **Batch 2 — verify then act (~11 MB)**: `_reference/sample-docs 2.zip`,
  workspace-root `storage/report-exports/`, `_reference/screenshots/` (May-13,
  superseded by captures-2026-06-10).
- **Batch 3 — post-video-finalization (~793 MB)**: remotion node_modules (577 MB),
  system-workflow-v2 node_modules (196 MB), raw `.webm` demo recordings (20 MB).
- **Stale top-level docs**: archive HANDOFF_2026-05-15.md and MAP.md (superseded by
  WORKSPACE_INDEX.md).
- **Sensitive**: `.demo.env` holds a live Neon connection string (outside the repo,
  fine, keep untracked); `_reference/sample-docs/` + fixtures contain real-looking
  CFDI/IMSS/SAT documents — never publish.
- Total potential reclaim: **~885 MB (~22%)**, most gated on video work being done.

---

## 5. Proposed fix scope (in order)

1. **P0 — unify download delivery (fixes the reported bugs).** One shared
   `downloadAuthenticatedFile(url, filename)` helper (fetch + Bearer → Blob →
   object-URL anchor click), already the pattern used by the working POST
   audit-package path. Replace the four broken call sites; optionally migrate the
   provider-portal navigations onto it too, retiring the cookie dependency.
   Alternative considered: short-lived signed download tokens appended to GET URLs
   — better for very large ZIPs (no blob buffering), more backend work. Recommend
   the fetch→blob helper now (ZIPs are capped at 500 MB but realistically far
   smaller), signed tokens later if memory becomes an issue.
2. **P0 — backend label sync.** Update STATUS_LABELS_ES to the unified glossary (or
   better: make the frontend glossary the single source and have /catalogs serve it).
3. **P1 — storage path hardening.** Make LOCAL_STORAGE_PATH and
   METADATA_EXPORT_PATH absolute (anchored to the api app root); add existence
   checks + logging to the three metadata FileResponse endpoints; consolidate the
   three storage dirs into the canonical apps/api/storage. Decide what to do about
   metadata exports living on Render's ephemeral disk (move to R2?).
4. **P1 — surface manifest failure.** If INDICE.pdf rendering fails, either fail the
   download with a clear error or visibly mark the ZIP as missing its index.
5. **P2 — config documentation.** Backfill .env.example + render.yaml comments for
   all flags; verify the workspace-fields TODO against backend behavior; remove
   console leftovers; decide mock-module fates.
6. **Hygiene** — repo batch (gitignore, untracked dispositions, docs/scripts
   archive) and workspace Batches 1–3 above, staged through `_archive_candidate/`
   per workspace policy.

No code was changed during this audit.
