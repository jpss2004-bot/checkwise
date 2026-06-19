# CheckWise — Flagship Prospect Demo Tenant

**Status:** LIVE ON PRODUCTION (2026-06-17). Seeded to prod Neon + R2; both logins smoke-tested HTTP 200 against `checkwise-api.onrender.com`; documents serve from R2. Rollback = `--teardown --confirm-prod` (see `RUNBOOK.md`).
**Seeder:** `apps/api/scripts/seed_flagship_demo.py` · **Branded PDFs:** `apps/api/scripts/flagship_demo_assets.py`

A single, polished, lived-in client portfolio designed so a prospect can evaluate CheckWise exactly as a real customer would — from both the **Client** and **Provider** sides — and trust that the platform is production-ready.

One command stands it up: `python scripts/seed_flagship_demo.py --apply`. It is idempotent (wipe-then-reseed), prod-gated, and fully tearable-down.

---

## 0. Audit of the pre-existing demo capability

Before building, every existing seeding mechanism was audited. Summary of what we found, and why a new seeder was warranted:

| Seeder | What it does | Why it isn't the flagship |
|---|---|---|
| `dev_seed.py` | Local boot data: 3 orgs, 4 vendors, synthetic tiny PDFs | Local-only, synthetic PDFs, not a prospect portfolio |
| `seed_demo_sandbox.py` | One client, 5-provider **lifecycle ladder** (invited→fully compliant) using real sample PDFs | Ladder **starts at 0%** → portfolio mean ≈ 50%, not 90–95% |
| `seed_demo_clients.py` | 5 *named* client tenants, each the same ladder | Same ~50% shape; tenants are assigned to specific people |
| `seed_user_testing_scenario.py` | Synthetic local-only user-test scenario | Watermarked "NO USAR" PDFs |
| `seed_dtp_demo.py` | DTP-as-client + DTP-as-provider progression | Specific to the DTP engagement |

**What was strong and reused:** the real-PDF uploader (content-addressed, deduped), the full submission→document→inspection→history→validation graph (`_insert_submission`), deterministic UUID5 ids, the canonical deterministic report builder, prod-gating, and the battle-tested cascade-wipe helpers.

**What was missing / would break immersion for a prospect, and how the flagship fixes it:**

| Gap in existing demos | Flagship fix |
|---|---|
| Portfolio mean ~50% (ladder starts at 0%) — not the "strong portfolio" a prospect should see | Curated A–E distribution → **92% mean, one red provider** |
| Opening a document showed a **mismatched sample-vendor name** (3 fixed sample vendors) | **Hybrid docs**: branded synthetic PDFs (matching name/RFC/folio) for the high-touch onboarding expediente; real PDFs for the 139-item recurring calendar |
| No provider **login** wired to the portfolio (workspaces left ownerless) | Provider D's workspace owns a real **provider login** so the prospect can switch sides |
| Only one pre-seeded report | **Three** client-facing reports (executive, risk matrix, missing evidence) |
| Sparse notifications | Rich client notification feed (expired CSF, rejected REPSE, open corrective action, renewal) |
| Consent wall on first login | Legal consent **pre-accepted** for both demo logins → land straight on the dashboard |

**Automatic vs. curated:** the *volume* (139-item recurring calendar × 5 providers, status histories, validation events, timestamps) is generated automatically from the live catalog; the *story* (which provider is the model / problem, the exact A–E percentages, the branded expediente, company names) is curated.

---

## 1. Demo tenant architecture

```
Corporativo Industrial Anáhuac, S.A. de C.V.   (the CLIENT / prospect's company)
│   client_admin login: demo.cliente@checkwise.mx
│
├── A · Grupo Industrial Vallejo            100%  🟢  model
├── B · Servicios Logísticos Anáhuac         98%  🟡  strong  (CSF renewal due ~14d)
├── C · Mantenimiento y Limpieza Tlalpan     88%  🟡  average
├── D · Constructora y Edificaciones Bajío   91%  🟡  improving  ←★ PROVIDER LOGIN
│         provider login: demo.proveedor@checkwise.mx
└── E · Transportes y Distribución del Golfo 83%  🔴  problem

Portfolio compliance: 92%  ·  semáforo split: 1 al día / 3 en proceso / 1 en riesgo
```

- **Tenancy model:** `Client` (the company) → 5 `Vendor` rows (the providers) → one `ProviderWorkspace` each (client_id + vendor_id pairing). The `Organization` (kind=`client`) + `Membership` link the `client_admin` user. The provider login is a separate `User` set as `owner_user_id` on **only** Provider D's workspace.
- **Why only one workspace owner:** workspace ownership shadows org membership in report listing (`project_actor_from_precedence_risk`). The client_admin owns no workspace; the provider user is never a client_admin — cleanly separated, no shadowing.
- **Namespacing:** all ids are deterministic `uuid5(SCENARIO_NAMESPACE, "flagship-demo:v1:<key>")`. Re-running `--apply` reproduces identical ids → safe wipe-then-reseed.
- **Isolation:** the flagship tenant (RFC `CIA180115R30`) is independent of every other seeder. Teardown deletes only this tenant + its two demo users + its unreferenced blobs.

---

## 2. Client demo account design

| Field | Value |
|---|---|
| Company | Corporativo Industrial Anáhuac, S.A. de C.V. |
| RFC | CIA180115R30 |
| Industry | Manufactura e infraestructura industrial |
| Admin login | `demo.cliente@checkwise.mx` / `Cliente2026Demo!` |
| Admin name | Daniela Robles Cárdenas (Compliance/Procurement lead) |
| Role | `client_admin` |
| Legal consent | Pre-accepted (v2) → lands on dashboard |

On login the client immediately sees: **92% compliance donut**, "**Tienes 1 proveedor en riesgo**", 5 active workspaces, portfolio signal buckets (faltantes / en revisión / por vencer), the Al día–En proceso–En riesgo distribution ring, 4 notifications, and recent activity stamped "12/06/2026".

---

## 3. Provider demo account design

| Field | Value |
|---|---|
| Provider | Constructora y Edificaciones del Bajío, S.A. de C.V. (**Provider D**) |
| Login | `demo.proveedor@checkwise.mx` / `Proveedor2026Demo!` |
| Contact | Daniel Quiroz Mena |
| Onboarding | Complete (recent — 42 days ago, "recently active") |
| Portal state | Lands on the provider dashboard/calendar (not the onboarding wizard) |

D is deliberately the **improving** provider: lots of recent approved uploads, a few items in review, and **5 genuinely missing recent obligations** the prospect uploads live. Uploading them moves those slots from **Faltante → En revisión** in the client view (visible risk reduction); once the compliance team approves them, D greens up further. This is the real provider action (uploading), so the loop is authentic.

The prospect switches between `demo.cliente@…` (client) and `demo.proveedor@…` (provider) to experience both sides of the same portfolio.

---

## 4. Company and provider profiles

| # | Legal name | RFC | Sector | City | Compliance | Semáforo | Demo role |
|---|---|---|---|---|---|---|---|
| A | Grupo Industrial Vallejo, S.A. de C.V. | GIV150218AB3 | Mantenimiento industrial | Monterrey | **100%** | 🟢 | Model — everything approved |
| B | Servicios Logísticos Anáhuac, S.A. de C.V. | SLA160712CD4 | Logística / transporte | Guadalajara | **98%** | 🟡 | Strong — 2 in review + CSF renewal due ~14d |
| C | Mantenimiento y Limpieza Corporativa Tlalpan, S. de R.L. de C.V. | MLC190503EF5 | Limpieza / facilities | CDMX | **88%** | 🟡 | Average — a few missing + pending |
| D | Constructora y Edificaciones del Bajío, S.A. de C.V. | CEB200911GH6 | Construcción / obra civil | Querétaro | **91%** | 🟡 | Improving — **login**, 5 to upload live |
| E | Transportes y Distribución del Golfo, S.A. de C.V. | TDG170820KK9 | Transporte / distribución | Veracruz | **83%** | 🔴 | Problem — see risk signals below |

**Provider E risk signals (the value-demonstration provider):** CSF **vencida** (expired, with a "VENCIDO" watermark on the PDF), REPSE registration **rechazado** (rejected, unresolved), **7** rejected monthly filings, **3** open `requiere_aclaración` corrective actions, **2** `posible_mismatch` (RFC mismatch), and ~13 missing recent obligations. Its semáforo is **red regardless of the 83%** because any blocking slot (rejected / needs-correction / mismatch) forces red — which is exactly how a real at-risk provider surfaces.

---

## 5. Document inventory plan (hybrid realism)

**~720 submissions across the 5 providers; 57 unique stored blobs (content-addressed dedup).** Every document opens as a valid PDF (verified 400/400).

- **High-touch onboarding expediente (branded synthetic):** for each provider, 5 documents generated with the provider's exact legal name / RFC / folio / dates and official-looking federal letterheads (SAT guinda, STPS guinda, IMSS verde):
  - Acta Constitutiva, Constancia de Situación Fiscal (CSF), Constancia de Registro REPSE, Contrato de servicios especializados, Tarjeta de identificación patronal IMSS.
  - Realistic filenames: `acta-constitutiva.pdf`, `constancia-situacion-fiscal.pdf`, `constancia-registro-repse.pdf`, `contrato-servicios-especializados.pdf`, `tarjeta-identificacion-patronal-imss.pdf`.
  - Provider E's CSF is the **expired** variant (red "VENCIDO" watermark); its REPSE is rejected.
- **Recurring calendar (real sample PDFs):** the full 139-item 2026 SAT/IMSS/INFONAVIT/STPS catalog per provider, backed by the real `_reference/sample-docs/` corpus (CFDIs, declaraciones, cuotas, acuses ICSOE/SISUB) — picked deterministically per (provider, requirement, period).
- **Metadata realism:** each document carries `DocumentInspection` (page count, detected RFC, detected institution, match confidence, mismatch reason), `Validation` rows, `DocumentStatusHistory` (recibido → final), and reviewer `ValidationEvent`s for rejections/clarifications.
- **Upload-date realism:** timestamps are derived from each period's close date (filed ~12 days after the period), anchored to a pinned "today" of 2026-06-15, so the library reads as months of continuous activity.

---

## 6. Compliance status distribution

CheckWise computes a provider's compliance as `round(resolved_slots / required_slots × 100)` over the full required-slot universe (onboarding + the 2026 recurring catalog), where *resolved* = approved / exception / not-applicable. The portfolio number is the mean of the providers. Semáforo: **green = 100%**, **yellow = 1–99% with no blocking slot**, **red = any blocking slot (rejected / needs-correction / mismatch) regardless of %**.

The flagship dials each provider's non-resolved count to hit its target:

```
A 100  +  B 98  +  C 88  +  D 91  +  E 83   →  mean 92%   ·   reds: 1 (E)
```

This is the deliberate insight that makes the brief work: E can be a **vivid red "en riesgo"** (expired cert, rejected REPSE, open corrective actions) while sitting at 83% raw — so the portfolio stays in the 90–95% band *and* there is exactly one clearly-flagged problem provider.

---

## 7. Report inventory

**Three client-facing reports** pre-seeded (built via the canonical `build_deterministic_blocks` registry — the same path the product's pick-template→generate flow uses — so the demo and the real templates can never drift). Each has 6 data blocks over the live portfolio:

1. **Resumen ejecutivo mensual · Junio 2026** (`client-monthly-executive`) — global compliance, by institution, radar, risk matrix, recommendations.
2. **Matriz de riesgo de proveedores · 2.º trimestre 2026** (`client-vendor-risk-matrix`) — providers ranked by risk.
3. **Evidencia faltante del portafolio · Junio 2026** (`client-missing-evidence`) — missing obligations by provider, prioritized.

**Audit / evidence packages** are live, not seeded text: the client's "Preparar paquete para auditoría" builds a real ZIP — verified to assemble **662 files / 88 MB across 5 vendors and 6 institution folders** (contrato, corporativo, sat, imss, infonavit, stps_repse) with an INDICE manifest. **Metadata export** (XLSX) and **provider-performance / corrective-action** views are all driven by the same seeded submissions, so they render with real data. The reports editor also supports generating *new* reports live (mock LLM if no API key, so it never needs network for the demo).

---

## 8. Activity-history generation plan

The environment is engineered to feel "alive for months," not freshly created:
- **Timestamps** span Jan→Jun 2026, derived from each obligation's period close; "última actividad" reads ~3 days ago.
- **Status histories**: every document has a `recibido → <final>` transition with actor + reason.
- **Reviewer trail**: approvals, rejections, and clarification requests are written as `ValidationEvent` rows (the audit-visible timeline the detail view renders).
- **Renewal engine**: Provider B's CSF is approved 76 days ago → due in ~14 days, so `RenewalReminder` rows + client/provider notifications fire (shows "the system watches expiries").
- **Notifications**: 4+ client notifications (expired CSF, rejected REPSE, open corrective action, renewal due).
- **Supersession-ready**: rejected items are left unresolved so the provider-side re-upload flow is demonstrable.

---

## 9. Realistic seed-data strategy

- **Deterministic** (UUID5) → idempotent, re-runnable, safe to teardown.
- **Hybrid documents** (branded synthetic for high-touch + real PDFs for volume) → opens look authentic *and* there's depth.
- **Content-addressed blob dedup** → 720 submissions, only 57 uploaded blobs.
- **Live-engine tuned**: the per-provider percentages are not hard-coded display values — they are computed by the real `dashboard_compute`/slot engine from seeded statuses. `--measure` reads them back. This guarantees the demo's numbers are *real product output*, not faked.
- **Honest**: every branded PDF carries a small grey footer — "documento generado para demostración… ficticio y sin validez oficial." Demo RFCs/folios are fictional.

---

## 10. Demo walkthrough script

The full clickable script (with routes) is in `WALKTHROUGH.md`. The arc, mapped to the brief's 14 beats:

1. **Log in** as `demo.cliente@checkwise.mx` → `/client/dashboard`.
2. **Strong compliance**: 92% donut, 5 workspaces, recent activity.
3. **Provider portfolio**: `/client/vendors` → 1 al día, 3 en proceso, 1 en riesgo, with % bars.
4. **Notice the problem**: Transportes del Golfo, **En riesgo 83%**.
5. **Investigate**: open E's detail → expired CSF, rejected REPSE, open aclaraciones, mismatches.
6. **Open documents**: any document opens as a real PDF (branded CSF/REPSE/contrato; the expired CSF shows the VENCIDO watermark).
7. **Reports**: `/client/reports` → open the executive summary, risk matrix, missing-evidence.
8. **Audit package**: "Preparar paquete para auditoría" → real ZIP across 5 vendors.
9. **Risk visibility**: the dashboard buckets + E's red semáforo make the risk legible at a glance.
10. **Switch to provider**: log in as `demo.proveedor@checkwise.mx` (Provider D) → `/portal`.
11. **Upload documents**: D has 5 missing recent obligations → upload one (real provider action).
12. **Respond to observations**: view in-review items + reviewer notes; re-upload to supersede.
13. **Back to client**: those obligations now read **En revisión** (no longer Faltante) — risk reduced.
14. **See improvement**: faltantes count drops; once the compliance team approves, D greens up.

---

## 11. Technical implementation plan

| File | Change |
|---|---|
| `apps/api/scripts/flagship_demo_assets.py` | **New.** reportlab branded-PDF generator (acta / CSF / REPSE / contrato / patronal) with federal letterheads + expired watermark + honest footer. |
| `apps/api/scripts/seed_flagship_demo.py` | **New.** The flagship seeder: client + 2 logins, A–E roster + profiles, profile-driven document distribution, renewal + notifications, 3 reports, `--apply` / `--teardown` / `--measure`. |
| `apps/api/scripts/seed_demo_sandbox.py` | **1 backwards-compatible change**: optional `override_doc=(bytes, filename)` on `_insert_submission` so branded PDFs can be injected. Default `None` = unchanged behavior. |

Reuse boundary: the flagship seeder imports `seed_demo_sandbox` (submission graph, uploader, report builder, env-gating) and `seed_demo_clients` (cascade-wipe helpers), and sets the shared module globals (`_INSTANCE_KEY`, `SCENARIO_TAG`, `TODAY`, `PROVIDERS`) to the flagship namespace — the same composition pattern `seed_demo_clients` already uses.

---

## 12. Database seeding strategy

```bash
cd apps/api

# Local (CHECKWISE_ENV=local): wipe-then-reseed, idempotent
.venv/bin/python scripts/seed_flagship_demo.py --apply

# Read back the live-computed compliance (no writes)
.venv/bin/python scripts/seed_flagship_demo.py --measure

# Remove everything (DB rows + storage blobs)
.venv/bin/python scripts/seed_flagship_demo.py --teardown

# Production: snapshot Neon FIRST, then (see RUNBOOK.md)
CHECKWISE_ENV=production DATABASE_URL=... STORAGE_BUCKET=... \
  .venv/bin/python scripts/seed_flagship_demo.py --apply --confirm-prod
```

- **Prod-gated**: refuses to run outside local without `--confirm-prod`.
- **Idempotent**: `--apply` tears down its own tenant first, so re-runs are safe.
- **Storage**: writes branded + real PDF bytes to the configured backend (local FS or R2/S3 with SSE) under `flagship-demo/_blobs/`.
- **No migration required** — uses existing tables only.

---

## 13. Success criteria — and verification results (local, 2026-06-17)

| Criterion | Target | Result |
|---|---|---|
| Portfolio compliance | 90–95% | **92%** ✅ |
| Provider distribution | A100 / B95-98 / C85-90 / D improving / E problem | **100 / 98 / 88 / 91 / 83** ✅ |
| Exactly one red provider | 1 | **1 (E)** ✅ |
| Documents open (return bytes) | 100% | **400/400 valid PDFs** ✅ |
| Branded high-touch docs present | yes | acta, CSF, REPSE, contrato, patronal ✅ |
| Audit package non-empty | yes | **662 files / 88 MB / 5 vendors / 6 institutions** ✅ |
| Reports render with data | ≥3, non-empty | **3 reports × 6 blocks** ✅ |
| Provider login + live-upload loop | yes | owner set, onboarding complete, **5 missing slots** ✅ |
| Notifications feed | populated | **4** ✅ |
| Idempotent re-run | identical | wipe (2 users/57 blobs) → identical reseed ✅ |
| No regressions | seed tests + base seeder | **test_seed 7/7**, sandbox apply/teardown clean, ruff clean ✅ |
| Verified through the real UI | dashboard + portfolio | 92% donut, "1 en riesgo", A–E semáforos ✅ |

The flagship tenant is indistinguishable from a real client that has been operating in CheckWise for months, and demonstrates the full value of the platform from both the Client and Provider perspectives.
