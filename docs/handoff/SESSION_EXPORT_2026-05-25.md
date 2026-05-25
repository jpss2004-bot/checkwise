# Session export — 2026-05-24 → 2026-05-25

Chronological log of the multi-day session that:

1. Started as a Monday-readiness audit on Saturday 2026-05-24.
2. Spent the weekend shipping the Friday-meeting P0s, then the audit-package, onboarding, calendar, UserMenu, and audit-week prep.
3. Pivoted Monday 2026-05-25 into the four-pass sale-readiness audit, producing the buyer dossier + internal findings.
4. Ingested a parallel "BACKEND_HARDENING_PASS" PDF that another Claude session generated, reconciled findings, and shipped M0 (route policy manifest + CI gate).

Companion files:

- [docs/handoff/NEW_SESSION_HANDOFF_PROMPT.md](./NEW_SESSION_HANDOFF_PROMPT.md) — paste-ready prompt for a fresh Claude Code session.
- [docs/audits/SALE_READINESS_BUYER_DOSSIER_2026-05-25.md](../audits/SALE_READINESS_BUYER_DOSSIER_2026-05-25.md) — external-facing audit dossier.
- [docs/audits/SALE_READINESS_INTERNAL_FINDINGS_2026-05-25.md](../audits/SALE_READINESS_INTERNAL_FINDINGS_2026-05-25.md) — engineering-facing finding list.
- [docs/audits/SALE_READINESS_AUDIT_SCRATCH.md](../audits/SALE_READINESS_AUDIT_SCRATCH.md) — raw four-pass scratch findings.
- [docs/audits/security/BACKEND_HARDENING_PASS_2026-05-25.pdf](../audits/security/BACKEND_HARDENING_PASS_2026-05-25.pdf) — the parallel PDF audit.
- [docs/runbooks/PRODUCTION_ENV_SETUP_CHECKLIST.md](../runbooks/PRODUCTION_ENV_SETUP_CHECKLIST.md) — operator-side Render dashboard checklist.

---

## 0. Project context

- **Repo:** `https://github.com/jpss2004-bot/checkwise.git`
- **Branch:** `main` (direct-to-main commits, no PR workflow)
- **Local path:** `/Users/josepablosamano/Desktop/Work — LegalShelf/checkwise/CheckWise`
- **Frontend:** Next.js 15 / React 19 / Tailwind 3 at `apps/web`, version `2.5.0`
- **Backend:** FastAPI / Python 3.11 at `apps/api`
- **Prod URLs:** API `https://checkwise-api.onrender.com`, Web `https://checkwise-six.vercel.app`
- **DB:** Neon Postgres
- **Storage:** Cloudflare R2 (`STORAGE_BACKEND=s3`)
- **Renewal cron:** Render `checkwise-renewal-dispatch`, daily 14:00 UTC = 08:00 CDMX

## 1. Starting state (Saturday 2026-05-24)

- Friday meeting (2026-05-23) had produced a long action-item list.
- 922 backend pytests passing.
- Three `/legal/*` documents at version `v0-draft` with a BORRADOR banner.
- The Monday tester window was the deadline.

## 2. Work shipped

Chronological commit log of this session (newest at the top):

| Commit | Surface |
|---|---|
| `c4f96ff` | `feat(security)` — M0 route policy manifest + CI gate (5 tests, 122 routes classified) |
| `4d7336d` | `docs(runbooks)` — production env setup checklist (operator) |
| `88067c0` | `chore(fixtures)` — n8n token-shaped fallback removed |
| `85a05d3` | `docs(audit)` — sale-readiness 4-pass audit + buyer dossier + internal findings |
| `dcaaac2` | `feat(email)` — transactional outbound for reviewer decisions + renewals |
| `b46b3b2` | `feat(intake)` — multi-file upload (contract + anexo) enabled by default |
| `93bd354` | `fix(audit-package)` — date-range overlap replaces lexicographic period filter |
| `62dc8c0` | `docs(legal)` — references doc with laws + portals backing v1 |
| `b0c54db` | `feat(legal)` — promote consent set to v1 (Paco/Beko sign-off 2026-05-25) |
| `8e01a80` | `feat(shells)` — LinkedIn-style UserMenu + portal sidebar collapse |
| `fe56e4b` | `feat(client)` — `/client/calendar` institution icons + per-month drill-down |
| `ebaa821` | `feat(client)` — `/client/onboarding` page + dashboard prompt banner |
| `bf1b8fd` | `feat(client)` — self-service onboarding via `/client/profile` |
| `51a1850` | `feat(client)` — `/client/auditoria` audit-package page + vendors entry |
| `c0922e4` | `feat(audit-package)` — cross-vendor audit ZIP + `INDICE.pdf` cover |
| `1e2865d` | `feat(admin)` — bulk ZIP per vendor on `/admin/vendors` |
| `5de421d` | `feat(clients)` — require email on admin client alta + persist on the row |
| `07a4af5` | `feat(reviewer)` — inline PDF viewer + Spanish status copy on `/admin/reviewer/[id]` |
| `767afc8` | `fix(intake)` — render upload result status via `RequirementStatusBadge` |
| `c6625fe` | `fix(ui)` — unify `posible_mismatch` label as "Posible inconsistencia" |
| `da0f530` | `docs(audit)` — Monday readiness audit + Friday action matrix + P0 plan |

Test count rose **922 → 1001** across the session.

## 3. Key decisions made

| Topic | Decision | Reason |
|---|---|---|
| Sale bar | "First paying pilot bar" — not public launch, not acquirer-grade | User's explicit choice |
| Legal version label | `v1` (not `v2.5.0` matching the app); date stamp `25 de mayo de 2026` | User requested simple version + dated effective copy |
| Legal contact details | Deferred — kept `privacidad@legalshelf.mx` / `legal@legalshelf.mx` placeholders | User said defer |
| Multi-file upload | Default ON (`MULTI_FILE_UPLOAD_ENABLED=True` in code) | Pilot needs contract+anexo |
| Reviewer-decision emails | Provider workspace owner only | User answered scope question |
| Renewal-reminder emails | Provider + client_admin per threshold cross | User answered scope question |
| Email preference gate | Strict respect — only when `contact_preference in {"email","both"}` | User answered scope question |
| Email format | Plain text only for v1 | User answered scope question |
| Period range filter | Date-range overlap, not lexicographic | Bug — bimestral/cuatrimestral rows were silently dropped |
| Audit deliverable shape | Buyer dossier + internal findings | User explicit choice |
| Next step after M0 | `must_change_password` enforcement (recommended), not started yet | Last open question of session |

## 4. Personas + login credentials (DEV only; prod accounts rotated)

| Persona | Email | Password (dev only) | Use for |
|---|---|---|---|
| internal_admin + reviewer | `ada@legalshelf.mx` | `demo1234` | `/admin/*`, `/admin/reviewer` |
| client_admin | `cliente.demo@checkwise.mx` | `ClienteDemo!2026` | `/client/*` (3-vendor portfolio) |
| provider (full expediente) | `boss.demo@checkwise.mx` | `BossDemo!2026` | `/portal/*` |
| provider (first login) | `proveedor.demo@checkwise.mx` | `CheckWiseDemo!2026` | `/activate` → `/portal/onboarding` |

**Important:** All four passwords are confirmed dead on **prod** (login returns HTTP 401). Use them only against `localhost`. The docs that still list them are flagged as the P1 finding `P4-04` to clean up later.

## 5. The four-pass audit (Monday 2026-05-25)

Methodology:
- **Pass 4 (production reality)** — prod URL probes, render.yaml + config review, secret scan across source, demo-credential rotation confirmation against live prod, dev/internal route discoverability, docs hygiene sweep.
- **Pass 3 (backend hardening)** — delegated to an Explore agent that read every router under `apps/api/app/api/v1`, covering role gates, tenant isolation, audit-log completeness, Spanish errors, 422 edges, rate limits, file caps, secrets, misc smells.
- **Pass 1 (route walk per persona)** — static analysis against the 46-route inventory cross-referenced with the in-browser smoke tests already performed earlier in the session.
- **Pass 2 (end-to-end workflow)** — traced the sale story (client signup → admin precharge → onboarding → upload → reviewer decision → renewal cron → audit ZIP) directly from code.

**Verdict**: READY for first paying pilot **conditional on three Render env-var items**: `AUTH_JWT_SECRET` rotation, `SMTP_*` vars, `FRONTEND_BASE_URL`.

Additional 🔴 P0 from the parallel PDF: `must_change_password` enforcement (not yet shipped).

## 6. The parallel PDF audit ingested 2026-05-25 evening

`docs/audits/security/BACKEND_HARDENING_PASS_2026-05-25.pdf` — generated by another Claude Code session. Adds context my audit lacked:

- 122 routes total across 12 routers (precise count).
- Five-milestone plan: M0 (policy inventory) → M1 (role/tenant negative tests) → M2 (Spanish error catalog) → M3 (upload 413 + rate-limit expansion) → M4 (audit completeness) → M5 (CI secret/dependency scans).
- Per-finding action items mapped to specific routers.
- The two NEW 🔴 P0 findings my audit missed:
  - `must_change_password` users can currently read/mutate protected surfaces.
  - Reports + LLM snapshots need cross-tenant negative tests (Reports/Exports/Shares are high-risk because they combine cross-role access, signed redirects, and LLM-assembled context).

## 7. What's shipped vs. what's pending

### Shipped ✅

- 996+ → 1001 backend tests passing.
- Legal v1 across stack with archive copies in `docs/legal/` + references.
- Audit package (cross-vendor ZIP with INDICE.pdf) for client_admin.
- Onboarding self-service for client_admin.
- Calendar drill-down for client.
- UserMenu across all three shells + collapsible portal sidebar.
- Multi-file upload enabled.
- Transactional email outbound for reviewer decisions + renewals.
- Bimestre/cuatrimestral period range fix.
- M0 — route policy manifest (122 routes) + CI gate (5 tests).
- Operator env-setup checklist (`docs/runbooks/`).
- n8n fixture token cleanup.
- Two audit deliverables (buyer dossier + internal findings).

### Pending (in priority order)

**🔴 P0 — block sale**
1. Operator: three Render env vars (`AUTH_JWT_SECRET`, `SMTP_*`, `FRONTEND_BASE_URL`). Use the checklist.
2. Code: `must_change_password` enforcement. Recommended as the immediate next coding step.
3. Code: Reports/Exports/Shares cross-tenant negative tests (M1 from the PDF). Covers the LLM-snapshot concern.

**🟠 P1 — first 30 days of pilot**
4. Code: 4 manifest-flagged audit-log gaps (notification `mark-read` + `mark-all-read` × client + provider). Each adds 1 `add_audit_event` call.
5. Code: Login failure + share unlock failure sampled-audit (PDF M4).
6. Code: Spanish error normalization on auth/feedback/metadata-dry-run/reports/reviewer (PDF M2).
7. Code: In-app invitation flows (client → client_admin, client_admin → vendor, internal_admin → provider).
8. Docs: Stale demo-credential cleanup across 7 documents.

**🟡 P2 — quality / polish**
9. CORS tightening (`allow_methods=["*"]` → explicit list).
10. `/dev/calendar-preview` removal or env-gate.
11. `apps/web/.env.local.example` flip `NEXT_PUBLIC_DEMO_MODE` to `false`.
12. `docs/` archive cleanup (66 files → curated current set + `docs/_archive/`).
13. M3 upload 413 consistency + AI-heavy + share-unlock rate limits.
14. M5 CI secret scan (gitleaks) + dependency audit.

## 8. Operational rules + preferences locked during the session

- **Direct-to-main commits, no PRs.** Split per logical surface. Push at end of work block.
- **Multi-paragraph commit body** with explicit verification line ("npm run typecheck && lint && build … green" / "pytest tests -q — N passed").
- **Spanish UX, no English leaks, no raw enum labels** in user-facing surfaces.
- **Browser smoke** any change observable in the preview before reporting done. Use `mcp__Claude_Preview__*` tools, login as the right persona, take a screenshot.
- **Test suite must stay green** before push. Frontend: `typecheck && lint && build`. Backend: `pytest tests -q`.
- **No feature enablement until the audit tells us what is safe** — directive issued Monday. M0 closed enough of the audit that defensive M1-M5 work is permitted; new product features still are not.
- **PDF audit + internal audit findings** are the canonical to-do list. No new findings should be invented outside this scope without explicit user direction.
- **Multi-file flag** is ON by default (`MULTI_FILE_UPLOAD_ENABLED=True` in code).
- **Legal v1** is the canonical version string. Don't touch `apps/web/app/legal/*` or `CURRENT_LEGAL_CONSENT_VERSION` without explicit instruction.
- **Local DB** points at a dev Postgres; `alembic upgrade head` was run locally for migrations 0022 + 0023. Prod runs `alembic upgrade head` automatically on Render deploy.
- **Two artifacts in the working tree** that the operator generated (`docs/audits/security/BACKEND_HARDENING_PASS_2026-05-25.pdf` was added by an external Claude session; `docs/legal/checkwise-paquete-legal-simple-v1-2026-05-25.pdf` was a hand-export). Some marketing-related working-tree changes (`apps/web/components/marketing/*`, `apps/web/public/marketing/*`) are user work — leave them alone.

## 9. Last open question of the session

> **User:** "what is the best next logical step?"
> **Claude:** Recommended `must_change_password` enforcement next (single best step). Reasoning in the chat. Awaiting confirmation when this export was generated.

The next session should start by either:
- Confirming with the user and proceeding with the `must_change_password` work; OR
- If the user has since asked for a different direction, pick that up.

If no answer arrives, default to `must_change_password` per the explicit recommendation — it's a real security gap, isolated, ~1-2 h, and uses the M0 manifest as the testing substrate.

## 10. What NOT to do in the next session

- Don't open new feature work outside the audit findings list.
- Don't touch the legal documents (they're at `v1`, signed off).
- Don't push to `main` without running pytest + frontend typecheck/lint/build first.
- Don't commit user-generated PDFs without asking.
- Don't regenerate the route policy manifest with `seed_route_policy_manifest.py` — manual edits live in `route_policy_manifest.json` now.
- Don't change `MULTI_FILE_UPLOAD_ENABLED` default without explicit instruction.
- Don't add WhatsApp UI surfacing — the `SupportCard` component is intentionally orphan until the actual phone number lands.
- Don't run `dev_seed.py` against prod (it has a guard but don't try).

## 11. Operator outstanding action

The user has NOT yet executed `docs/runbooks/PRODUCTION_ENV_SETUP_CHECKLIST.md`. The new session should either:

1. Confirm with the user that env work is done before relying on transactional email in prod, OR
2. Mention at the end of each work block that the env checklist is still the blocker for the email path being live.

## 12. Quick-start verification commands

After cloning + setup, the next session can verify the working tree state:

```bash
cd "/Users/josepablosamano/Desktop/Work — LegalShelf/checkwise/CheckWise"
git log --oneline -n 5
# Expect c4f96ff at HEAD (M0 manifest commit).

cd apps/api && ./.venv/bin/python -m pytest tests -q
# Expect 1001 passed.

cd ../web && npm run typecheck && npm run lint
# Expect both green.

cd ../api && ./.venv/bin/python -m pytest tests/test_route_policy_manifest.py -q
# Expect 5 passed (M0 gate is live).
```

End of session export.
