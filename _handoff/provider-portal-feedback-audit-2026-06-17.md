# Provider Portal — Feedback vs. Production Code Audit

**Source feedback:** `Reporte_Pagina_Proveedor 17-6-2026.pdf` ("Reporte de Observaciones – Página Proveedor")
**Date:** 2026-06-17
**Scope:** Provider portal only (`/portal/*`). Frontend `apps/web`, backend `apps/api`. Findings are grounded in code read at current HEAD; every verdict cites `path:line`.

Each observation is rated against whether **production already satisfies the underlying ask**:

- ✅ **IMPLEMENTED** — the desired end-state already exists; little/no work remains.
- 🟡 **PARTIAL** — partially satisfied; specific gaps remain.
- 🔴 **OPEN** — the concern is valid and unaddressed (or by-design but worth revisiting).

---

## Executive summary

23 observations across 6 themes: **10 already implemented, 9 partial, 4 open.**

The portal is in good shape on **states/vocabulary, calendar→upload deep-linking, corporate-doc guidance, chatbot grounding, identity hardening, and guarded reversion** — most of which were built in prior sprints. The real gaps cluster around **(a) period/date literacy in the upload flow, (b) a blocking synchronous upload, (c) information-architecture overlap (Dashboard/Calendar/Submissions + the "Mi espacio" role), and (d) first-login routing through gates before the dashboard.**

### The 4 genuinely open items
1. **🔴 Upload blocks on the full validation pipeline (§1.5).** Submit runs OCR + mismatch analysis + forensics + QR/folio + the metadata XLSX export **synchronously before the response returns** — the provider stares at "Enviando…" the whole time. Highest-impact UX fix.
2. **🔴 Calendar doesn't say which period a document covers (§2.2).** The backend computes the covered-period label (`period_label`, e.g. "IMSS Mayo") but `flattenCalendarPayload` **drops it** before render. No current-vs-next-period framing reaches the provider.
3. **🔴 "Mi espacio" is an identity/consent gate, not a work hub (§3.3).** It's filed under "Cuenta" next to "Mi perfil" and routes *away* to the dashboard — the inverse of the feedback's ask.
4. **🔴 Upload as a standalone nav item is a dead-end pass-through (§3.2).** `/portal/upload` with no `requirement_code` renders an empty state that bounces the user elsewhere. (Arguably by-design — it's a wizard *target* — but the nav still surfaces it as a primary destination.)

### Highest-value quick wins
- Surface `period_label` on calendar cell/popover/drawer (§2.2) — data already exists server-side; pure frontend plumbing.
- Make the upload submit return fast and finish validation in the background (§1.5) — the LLM tier is already deferred to `background_tasks`; extend that to the heavy pipeline.
- Add `router.refresh()` / refetch on upload success so an already-open dashboard/calendar updates (§1.6).
- Add period/vigencia helper copy + disambiguate "Vence" (delivery deadline) from document vigencia (§1.1, §1.4).

---

## Scorecard

| # | Observation | Verdict |
|---|---|---|
| **1. Gestión de documentos y cumplimiento** | | |
| 1.1 | Clarify period logic (single month vs. longer periods) | 🟡 PARTIAL |
| 1.2 | Explain which docs require anexos & when mandatory | 🟡 PARTIAL |
| 1.3 | Clearer instructions for corporate docs (Acta Constitutiva, etc.) | ✅ IMPLEMENTED |
| 1.4 | Reduce confusion around fechas / vigencias / periodos de entrega | 🟡 PARTIAL |
| 1.5 | Don't make users wait on unnecessary validations to continue | 🔴 OPEN |
| 1.6 | On upload finish, immediately reflect in Dashboard & Calendar | 🟡 PARTIAL |
| **2. Calendario y seguimiento de obligaciones** | | |
| 2.1 | Calendar as the primary source of dates/vencimientos | ✅ IMPLEMENTED |
| 2.2 | Each date shows which doc is current period vs. next | 🔴 OPEN |
| 2.3 | Visibly show pendientes / vencidos / en revisión / aprobados | ✅ IMPLEMENTED |
| 2.4 | Intuitive calendar → upload relationship | ✅ IMPLEMENTED |
| **3. Navegación y arquitectura de información** | | |
| 3.1 | Functional duplication between Dashboard / Calendar / Submissions | 🟡 PARTIAL |
| 3.2 | Upload section adds little value (same action available elsewhere) | 🔴 OPEN (by-design) |
| 3.3 | "Mi espacio" should be the central work hub, tied to Dashboard | 🔴 OPEN |
| 3.4 | Reduce steps / eliminate redundant routes | 🟡 PARTIAL |
| **4. Dashboard y experiencia inicial** | | |
| 4.5 | Dashboard shows ALL faltantes needing immediate attention | 🟡 PARTIAL |
| 4.6 | Reminders appear only when relevant | ✅ IMPLEMENTED |
| 4.7 | Critical info visible from first login, no multi-screen hunt | 🟡 PARTIAL |
| **5. Chatbot y soporte** | | |
| 5.1 | "Report a problem" button location is invasive | 🟡 PARTIAL |
| 5.2 | Chatbot answers more specific & contextualized | ✅ IMPLEMENTED |
| 5.3 | Avoid ambiguous/generic answers in compliance scenarios | ✅ IMPLEMENTED |
| **6. Observaciones generales** | | |
| 6.4 | Remove confusing actions / unclear reversion options | ✅ IMPLEMENTED |
| 6.5 | Consistency of states/dates/results across views | ✅ IMPLEMENTED |
| 6.6 | Reinforce validation & identity verification | ✅ IMPLEMENTED (MFA gap) |

---

## Detailed findings

### 1. Gestión de documentos y cumplimiento

**1.1 — Period logic (month vs. longer periods) · 🟡 PARTIAL**
Frequency/period are shown as passive chips (**Frecuencia** Mensual/Bimestral/…, **Periodo**) in the upload summary — `intake-wizard.tsx:1508-1512`, `:1494-1496` — but only when the user arrives from the calendar, which threads `period_human` (`calendar/page.tsx:925-936` → `upload/page.tsx:74`). On manual/unlocked entry the period is a bare free-text input with placeholder `"2026-05 / Ene-Abr 2026"` and no helper copy (`intake-wizard.tsx:1211-1222`); the frequency dropdown lists raw labels with no descriptions (`catalogs.ts:1-9`). **Gap:** nothing explains that e.g. an IMSS payment covers one month while ICSOE covers a cuatrimestre.

**1.2 — Annex requirements · 🟡 PARTIAL**
A generic multi-file "anexos" picker exists (flag-gated, default on) framed for "contrato + anexos" — `intake-wizard.tsx:1885-1957` — and a static checklist appears only when the requirement name matches `/contrato|anexo/i` (`:1673-1704`). The v2 `minimum_documents` "one vs all" signal (`:1556,1564-1566`) is the closest thing to "when mandatory," but it's about alternatives, not annexes. **Gap:** no per-requirement "anexos obligatorios" flag, no validation requiring an annex, no general explanation of which doc types need them.

**1.3 — Corporate-doc instructions · ✅ IMPLEMENTED**
Best-covered item. Catalog-driven guidance renders "Qué debe contener este documento" with anatomy, dónde obtenerlo, and "Evita estos errores comunes" — `intake-wizard.tsx:1618-1655` (fetch at `upload/page.tsx:206-226`). A moral-only Acta Constitutiva cross-reference with a deep link shows on the contract requirement — `intake-wizard.tsx:1656-1668`, gated by `showActaNote` (`upload/page.tsx:403-407`). Onboarding splits Obligatorios vs. Sugeridos with per-item guidance (`onboarding/page.tsx:200-237`).

**1.4 — Dates / vigencias / delivery periods · 🟡 PARTIAL**
The upload summary shows a **"Vence"** chip (long Spanish date) + **Periodo** — `intake-wizard.tsx:1509-1512`, formatter `:1459-1470` — but "Vence" here is the *delivery* deadline, easily misread as document expiry. Document **vigencia/validity** is not surfaced on the upload or detail surfaces; the submission detail is period-centric ("Periodo cubierto/capturado", `submissions/[submission_id]/page.tsx:539-541`) with no rendered `valid_until`. **Gap:** fecha de emisión / vigencia / periodo de entrega are never disambiguated side-by-side.

**1.5 — Blocking validations · 🔴 OPEN**
The submit is fully synchronous. `create_workspace_submission` runs `finalize_intake_submission` via `run_in_threadpool` and **awaits it before returning** — `portal.py:2840-2858`. That function runs inline: `inspect_pdf_with_ocr_fallback`, `analyze_document_text`, forensics + QR, status derivation, and `export_metadata_table_after_upload` (XLSX → R2) — `submission_service.py:661-721`. The button shows "Enviando…" the entire time (`intake-wizard.tsx:746-826, 1022-1031`). Only the LLM shadow tier is backgrounded (`submission_service.py:976-997`). The advisory *duplicate pre-check* is correctly non-blocking (`intake-wizard.tsx:463-464,531-547`), but the actual submit is not. **No "upload now, validate in background" path exists.**

**1.6 — Immediate reflection in Dashboard/Calendar · 🟡 PARTIAL**
New state shows up on the *next* mount because there's no client cache to fight (dashboard/calendar fetch fresh via `useEffect`; `fetchJson` has no `next.revalidate` — `portal.ts:173-211`). But the success screen only renders **links** ("Ver mi calendario", "Ver detalle") — `intake-wizard.tsx:2315-2338` — with no `router.refresh()`, refetch, or optimistic update. **Gap:** reflection is lazy (next navigation), not active; an already-open dashboard/calendar tab won't update.

### 2. Calendario y seguimiento de obligaciones

**2.1 — Primary source of dates · ✅ IMPLEMENTED (caveat)**
Backend builds the full year from the canonical catalog (`recurring_for_year_v2`, `portal.py:1611-1700`); each item carries a computed deadline (`_calendar_deadline_iso`, `:1629`, day-17 / day-30 SAT-annual). Renders 4 institutions × 12 months (`page.tsx:416-459`) + mobile list; a zero-item response is treated as a bug (`page.tsx:323`). **Caveat:** scope is the *recurring* catalog; one-off corporate docs (acta, ID) aren't placed on the calendar.

**2.2 — Current vs next period per date · 🔴 OPEN**
The document is named per entry, but the **covered-period and current-vs-next distinction never reaches the UI**. Backend emits `period_label` (e.g. "IMSS Mayo", `compliance_catalog.py:763`) with previous-month semantics (`_previous_month_label`, `:510-514`), but `flattenCalendarPayload` **drops `period_label`/`period_key`** (`page.tsx:74-96`); they're absent from the `CalendarEntry` type (`types.ts:13-39`). The provider sees obligation name + deadline *day* only (`cell-popover.tsx:182`; drawer "Vence" `page.tsx:723-727`). The only renderers of `period_label` (`obligation-block.tsx`, `provider-review-card.tsx`) belong to the **client** calendar, not this one. **Fix is cheap:** stop dropping the field, render it.

**2.3 — Show states · ✅ IMPLEMENTED**
All four states + more are encoded with color/icon/badge/filter. `statusToDocumentStateCode` resolves pending/expired/in_review/approved/uploaded/rejected/needs_review/empty (`portal.ts:951-977`); colored segment bar + icon per cell (`month-cell.tsx:23-65,186-208`), state dots in popover (`cell-popover.tsx`), Spanish badges in mobile list (`mobile-month-list.tsx:182-196`), an 8-state legend (`page.tsx:953-981`), and a "Pendientes" filter (`page.tsx:188-194`).

**2.4 — Calendar → upload · ✅ IMPLEMENTED**
`_calendar_upload_href` mints a fully-parameterized `/portal/upload?…` per item (`portal.py:521-577`), threading requirement_code, period_key, period_label, institution, load_type, period_human, deadline, v2. State-aware CTAs ("Subir documento" / "…actualizado" / "Revisar rechazo y corregir" / "Ver documento aprobado", `page.tsx:839-895`), and the upload page consumes every param (`upload/page.tsx:65-81`) → lands on a pre-filled wizard.

### 3. Navegación y arquitectura de información

**Nav map** (`portal-app-shell.tsx`, `PRIMARY_NAV` L63-101 / `SECONDARY_NAV` L103-116):
Operación → Dashboard `/portal/dashboard`, Expediente `/portal/onboarding`, Calendario `/portal/calendar`, Subir documento `/portal/upload`, Documentos `/portal/submissions`, Reportes `/portal/reports`, Notificaciones `/portal/notifications`. Cuenta → Mi espacio `/portal/entra-a-tu-espacio`, Mi perfil `/portal/perfil`. Plus top-bar search → `/portal/buscar`.

**3.1 — Dashboard/Calendar/Submissions duplication · 🟡 PARTIAL**
Purposes are distinguishable (aggregate command-center vs. annual grid vs. flat history) but content overlaps materially: the dashboard's "Vence pronto" links to the calendar (`dashboard/page.tsx:1253`) and "Cargas recientes" renders the same upload list as Submissions and links to it (`:1288`). The feedback's core claim — the same pendientes/uploads restated across all three — holds.

**3.2 — Upload section redundant · 🔴 OPEN (by-design)**
`/portal/upload` deliberately refuses to work without context: no `requirement_code` → dead-end empty state that bounces to calendar/expediente (`upload/page.tsx:287-361`). Every real upload deep-links in from calendar/dashboard/expediente. So "Subir documento" as a standalone nav item adds little — it's a wizard target, not a usable destination. The header's bare "Subir documento" button (`dashboard/page.tsx:216-225`) lands on the same dead-end.

**3.3 — "Mi espacio" as central hub · 🔴 OPEN**
"Mi espacio" exists but is an **identity/consent entry gate**, not a work hub: it shows tenant identity, expediente summary, legal-consent checkbox, correction-request dialog, and an "Entrar a mi espacio" CTA that routes *away* to dashboard/onboarding (`entra-a-tu-espacio/page.tsx:92-95`). It's filed under "Cuenta" next to "Mi perfil." The actual central surface is the Dashboard — the inverse of the feedback's ask.

**3.4 — Reduce steps / redundant routes · 🟡 PARTIAL**
Clean single sidebar with active states + collapsible rail, but redundancy persists: upload is a non-standalone pass-through (3.2); two "documents" routes (`/portal/onboarding` "Expediente" + `/portal/submissions` "Documentos") plus the calendar all surface obligation state; account is split across espacio + perfil; and post-login adds a hop (provider → entra-a-tu-espacio → dashboard, `login/page.tsx:307`).

### 4. Dashboard y experiencia inicial

**4.5 — Show ALL faltantes · 🟡 PARTIAL**
Attention logic is sound (all actionable states + calendar items due ≤14 days, `dashboard_compute.py:419-477`) but **capped**: `attention_today` truncates to 10 (`:485`), `suggested_actions` to 5 (`:991`), and queues slice to 5 rows with "Ver todo" only when overflow (`dashboard/page.tsx:1237/1254/1289/1347`). A provider with >10 faltantes won't see all on the dashboard.

**4.6 — Reminders only when relevant · ✅ IMPLEMENTED**
Banners are state-gated: `LockedDashboardBanner` only when `gateBlocked` (`dashboard/page.tsx:173`), `ProvisionalAccessBanner` only when all uploaded but not marked complete (`:174-175`); the hero collapses to "Estás al día" when no actions (`:664-690`); notif badge only when unread>0 (`:216-218`); renewal reminders fire only when a threshold is crossed (`renewal_dispatch.py:99-209`).

**4.7 — Critical info on first login · 🟡 PARTIAL**
Once on the dashboard, critical info is consolidated above the fold (semaphore + reason, single next action, KPI strip, metadata strip; `EmptyExpedienteHero` for new users). **But first ingress isn't the dashboard:** login → `/portal/entra-a-tu-espacio` (`login/page.tsx:299-308`) → click "Entrar a mi espacio" → dashboard; incomplete expedientes get redirected to `/portal/onboarding` (`with-onboarding-gate.tsx:42-49`). The gate hops are the gap.

### 5. Chatbot y soporte

**5.1 — Report-problem button invasive · 🟡 PARTIAL**
`FeedbackLauncher` is a **fixed floating FAB pinned bottom-right** at `z-50` on every portal page — `feedback-launcher.tsx:418`, mounted `portal-app-shell.tsx:401`. Mitigations exist (collapses to icon-only below `sm`, `:438`; auto-hides when the Wise drawer owns the right gutter; a redundant in-sidebar "Reportar problema" entry exists at `portal-app-shell.tsx:592-599`). **Gap:** the FAB is still permanently pinned over content and not user-dismissible.

**5.2 — Chatbot specific/contextualized · ✅ IMPLEMENTED**
`build_workspace_context` (`wise/context.py:233`) ships compliance %, bucket counts, every onboarding+calendar slot (state/period/deadline/reviewer-note), and last 10 uploads — from the same evidence-slot service the dashboard uses. Plus page context (`ai.py:123`) and a tenant-guarded on-screen document focus (`context.py:346`). System prompt grounds dates/deadlines and "this document" (`ai.py:187-188`).

**5.3 — Avoid generic compliance answers · ✅ IMPLEMENTED**
`build_static_context` (`context.py:310`) injects a glossary + per-document REPSE catalog guidance grouped by institution (`render_static_block`, `:430`). Rules forbid invented data ("no tengo ese dato a la mano", `ai.py:189`), require validated `cta_id`s (invented CTAs dropped, `:541`), and mandate human-readable status labels (`context.py:867-869`). **Note:** model is Haiku capped at ~3 sentences (`ai.py:54`) — grounding is rich, depth is deliberately short.

### 6. Observaciones generales

**6.4 — Confusing reversion options · ✅ IMPLEMENTED**
One reversion action ("Cancelar envío"), well-guarded: confirm dialog explains the consequence and steers to "Reemplazar archivo" (`submissions/[submission_id]/page.tsx:107`); backend allows cancel only for pre-review states (`_CANCELABLE_STATUSES`, `portal.py:1838-1843`) and 409s otherwise ("usa el flujo de reemplazo", `:1856`). Replace/supersede path is visually distinct (LineageStrip, `:770-800`). **Minor:** cancel is a hard-delete with no undo, but clearly disclosed.

**6.5 — Consistency across views · ✅ IMPLEMENTED**
Single canonical vocabulary in `lib/constants/statuses.ts` (frontend mirror of `constants/statuses.py`): labels (`STATUS_LABELS_ES`), variants (`STATUS_VARIANT`), explainers, and unified SlotState/Semáforo/Bucket vocabularies. Header documents the 2026-06-10 pass that collapsed five vocabularies into one; regression-locked by `statuses.test.ts` + `doc-state-labels.test.ts`.

**6.6 — Identity verification · ✅ IMPLEMENTED (MFA gap)**
Layered: account lockout (429 at `AUTH_LOCKOUT_THRESHOLD=5`/15 min, `auth.py:673`, `config.py:252-253`), login rate-limiting + constant-time bcrypt + generic 401 (`auth.py:664,682-684`), WhatsApp OTP phone verification (`me.py`, OTP model `entities.py:1487`), and a full document-authenticity stack (QR/folio allowlist `document_verification.py`, container + ELA/copy-move forensics, tiered LLM). **Gap:** no login MFA/TOTP (the only OTP is phone verification, not a sign-in second factor).

---

## Suggested priorities

**P0 — UX friction with the clearest payoff**
- §1.5 Non-blocking upload: return on receipt, run OCR/forensics/metadata in `background_tasks`, surface result async (reuse the existing deferred-tier pattern). Pair with §1.6 (`router.refresh()`/refetch on success).
- §2.2 Render `period_label` on the provider calendar (cell/popover/drawer) + current-vs-next framing — data already exists, frontend-only.

**P1 — Information architecture**
- §3.1/§3.2/§3.3/§3.4: decide the role split. Either (a) promote "Mi espacio" into the real hub the feedback wants, or (b) drop it into the dashboard and remove the gate hop (§4.7); demote standalone "Subir documento" from primary nav to a contextual action; clarify Expediente vs. Documentos vs. Calendario purposes.

**P2 — Document literacy**
- §1.1 period helper copy + frequency descriptions; §1.4 disambiguate "Vence" (delivery) from vigencia (validity) and surface document vigencia; §1.2 per-requirement annex-required flag + copy.

**P3 — Polish**
- §4.5 raise/relax the 10/5 caps or make "Ver todo" always reachable; §5.1 make the feedback FAB dismissible or relocate it.

**Backlog**
- §6.6 login MFA/TOTP (already tracked as a known gap in prior security audits).
