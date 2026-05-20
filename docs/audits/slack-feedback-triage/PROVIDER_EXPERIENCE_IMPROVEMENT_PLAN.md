# CheckWise — Provider Experience Improvement Plan

**Status:** planning only. No code changes, no commits.  
**Companion docs:**  
- [SLACK_FEEDBACK_TRIAGE_REPORT.md](SLACK_FEEDBACK_TRIAGE_REPORT.md) — the technical triage that preceded this plan.  
- [slack-feedback-backlog.json](slack-feedback-backlog.json) — machine-readable backlog (BL-001..BL-009).  
**Author of triage:** Claude (deeper UX strategy pass).  
**Review date:** 2026-05-20.  
**Tester:** `jluna@legalshelf.mx`, non-technical provider persona, desktop 1802×862.

---

## 1. Executive summary

The provider portal is functionally complete and visually disciplined, but the tester's seven Slack messages plus three follow-up notes describe a **product written for engineers, used by non-engineers**. Specific symptoms:

- The bug they noticed first (preset gallery empty) **fails silently** — they can't tell broken from "nothing for you."
- The upload surface speaks engineer dialect (`file_exists`, `allowed_file_type`, "Guided upload resolver" in English, canonical requirement codes).
- The provider can never look at their own registration data after onboarding.
- The provider can't recover from a forgotten password.
- There is no automatic logout, which on a compliance product is both a usability and a security gap.
- Two pages they trust (dashboard, calendar) don't carry the level of document-level detail that lets them self-serve.
- The "Cumplimiento al 78 %" number doesn't explain *why* it's 78.

This plan reframes the work as **a non-technical compliance assistant**, not a SaaS dashboard. It keeps every backend contract, every token, and every existing component — and removes engineer dialect from the surfaces a provider actually sees. It also introduces tasteful, compliance-focused progress motivation (no streaks, no badges that infantilize a legal product) and a real account/security layer.

Nothing here ships before approval.

---

## 2. What the feedback is really saying

Restated as user needs, not as bug tickets. Each item is mapped to the original Slack ref (F1–F7, RX-1) or the follow-up notes (N1–N3).

| Ref | What the user *literally* said | What they're *actually* asking for | Real category |
|---|---|---|---|
| F1 + F2 | "Pongan las partes de cada documento, una imagen de referencia." | "I don't know what this document is supposed to contain or look like before I upload it." | content / guidance |
| F3 | "Que `file_exists` o `allowed_file_type` sean lenguaje humano." | "Stop talking to me like a database." | content / copy |
| F4 | "Ver los documentos cargados ordenados por Institución, Mes, Año. Ajustar la gráfica para entender qué falta." | "Show me what I already submitted, and tell me *why* my score isn't 100." | information architecture |
| F5 | "Detalles sobre el expediente y por qué no está al 100 %. Juntar los 3 reportes en uno." | "Give me one report that explains where I stand and what to fix." | reports simplification |
| F6 | "No deja ver las plantillas." | "It looks broken and I can't tell if it's me or the product." | bug + error visibility |
| F7 | "Mostrar el día y nombre del documento cargado en el calendario." | "Use the calendar as my evidence timeline, not as a status grid." | feature gap |
| RX-1 | (console) `Cannot read properties of undefined (reading 'call')` on four portal routes. | "Why does the product flash and reload when I navigate?" | production runtime |
| N1 | "¿Puedo entrar a la información que registré al inicio? Si no, debería poder, o por soporte." | "I want a profile page where I can see and correct what I entered." | account management |
| N2 | "Que haya un botón de '¿olvidaste tu contraseña?' con código por correo." | "If I lose my password I'm locked out." | authentication |
| N3 | "Cierre de sesión automático tras inactividad, por seguridad." | "I'm uploading sensitive documents. Don't leave my session open on a shared computer." | security |

**Two cross-cutting truths:**

1. The provider does not understand the product through *features*. They understand it through *progress*: "what did I do, what's left, what's wrong, what's next." Every page they evaluated reflects that mental model.
2. They explicitly say the product is "interesante" and "excelente la forma en que se maneja." This is not a hostile audit. It is a non-technical compliance officer giving a competent product the missing 20 % that makes it feel **finished**.

---

## 3. Provider pain points (consolidated)

In order of how often the same complaint surfaced across feedback items:

1. **Engineer dialect leaking to non-engineers.** Validation rule codes (F3), an English "Guided upload resolver" eyebrow on `/portal/upload`, the word "Plantilla" used without context (F5/F6), `submission_id`-style codes in the URL — all surface to a user who explicitly says "no lo entenderá del todo." (F1, F2, F3, F5, F6.)
2. **Silent failure is indistinguishable from "nothing to do."** When the preset gallery is empty the user has no way to tell broken from intentional (F6).
3. **No document anatomy.** The first-time uploader has no idea what a Constancia de Situación Fiscal should contain or look like (F1, F2).
4. **No evidence history.** The dashboard tells you *how* you're doing but not *what* you've done (F4, F7).
5. **No causal explanation of progress.** "78 % cumplimiento" without a "porque te faltan X, Y, Z." (F4, F5.)
6. **No account self-service.** The provider can't view, much less correct, what they entered during onboarding (N1).
7. **No password recovery.** Forgotten password = blocked tester (N2).
8. **No session hygiene.** Shared/borrowed computer = security risk on a compliance product (N3).
9. **Calendar is a state grid, not a timeline.** It shows status but not "when did I do what" (F7).
10. **Production navigation reloads.** RSC chunk errors after deploys — looks broken even when it isn't (RX-1).

---

## 4. Page-by-page UX audit

Findings grounded in direct reads of:

- `frontend/app/portal/upload/page.tsx`
- `frontend/components/checkwise/intake-wizard.tsx`
- `frontend/components/checkwise/validation-summary.tsx`
- `frontend/app/portal/dashboard/page.tsx`
- `frontend/app/portal/calendar/page.tsx`
- `frontend/app/portal/reports/page.tsx`
- `frontend/components/checkwise/reports/list/reports-list-view.tsx`
- `backend/app/services/prevalidation.py`
- `backend/app/services/reports/templates.py`

### 4.1 `/portal/upload` — Guided upload resolver

**Purpose:** A provider resolves one obligation by uploading one document.

**What works:**
- Pre-fill from session + URL params keeps the user from re-typing client/proveedor/RFC.
- Field labels for the locked block are already in plain Spanish (`Cliente`, `Proveedor`, `RFC proveedor`, `Periodo`, `Tipo de carga`, etc.) per `intake-wizard.tsx:124-137`.
- Backend pre-validation already emits plain-Spanish `message` strings even when the `rule_code` is technical.
- Replacement-lineage flow (`?replaces=<id>`) is well thought out.

**What hurts the user:**
- `frontend/app/portal/upload/page.tsx:108` ships an **English** eyebrow: `eyebrow="Guided upload resolver"`. On a Spanish-first product that targets non-technical Mexican providers, this is the worst possible first impression.
- `frontend/components/checkwise/validation-summary.tsx:29` renders `validation.rule_code` directly. The user reads `file_exists`, `allowed_file_type`, `pdf_magic_header`, `pdf_encrypted`, `pdf_readable_text`, `max_file_size`, `sha256_hash`, `duplicate_hash`, `vendor_match`. F3 verbatim.
- The wizard exposes "Tipo de carga" + "Código canónico" / "Periodo canónico" as state. The codes themselves don't render as labels (per the comment at `intake-wizard.tsx:134-136`) but the URL contains `requirement_code=...&period_key=...&load_type=...` which a screen-recording-aware user can absolutely see.
- Each requirement has **no anatomy text and no sample image**. A first-time provider doesn't know what a CSF or REPSE registration should look like before uploading. F1/F2 verbatim.
- The "back" links in the page header are labeled "Expediente" and "Calendario" — but they both point to `/portal/onboarding` and `/portal/dashboard` respectively. The second label is wrong: it says "Calendario" but routes to the dashboard (`page.tsx:124-127`).

### 4.2 `/portal/dashboard` — Semaphore + suggested actions + KPIs

**Purpose:** Tell the provider where they stand and what to do next.

**What works:**
- `SemaphoreHero` and `KPIStrip` use proper Spanish: "Aprobados", "En revisión", "Por atender", "Pendientes", "Vencidos" (`page.tsx:261-265`).
- `NextActionRail` empty state already reads "Estás al día" with a non-judgmental subtitle.
- `EvidenceSlotGrid` empty state: "Nada por atender hoy" — exactly the tone a compliance product needs.
- `loadError` branch shows a "No pudimos cargar tu dashboard" warning instead of a blank crash — F6's pattern (silent fail) does not apply here.

**What hurts the user:**
- The compliance gauge shows the **percentage** but no causal subtitle. F4: "ajustar la gráfica para entender qué falta." There is no "Te faltan 3 documentos para llegar al 100 %" line.
- There is no **history of what was submitted**. F4 explicitly asks for documents grouped by `Institución × Mes × Año`. The closest current surface is the calendar, which is a separate page and is itself state-only (see 4.3).
- The `CalendarTeaser` and `UpcomingCard` are good but do not tell the user "you uploaded *this file* on *this day*."
- Internal nav uses the word "workspace" (`emptyState.description: "No hay acciones urgentes para tu workspace en este momento."`). Non-engineer providers don't think of their own company as a "workspace."

### 4.3 `/portal/calendar` — REPSE obligations grid

**Purpose:** Visualize 12 months × 4 instituciones to scan compliance state.

**What works:**
- Drawer at `page.tsx:421+` is a strong pattern: status badge, frequency label, required document, due date, institution, suggested action, "Subir documento" CTA.
- `INSTITUTION_LABELS`, `MONTH_LABELS_ES`, status pill labels are all canonical Spanish.
- `DocStateBadge` uses semantic tokens (no raw hex).

**What hurts the user:**
- Grid cells show only status; not the upload date, not the filename, not the reviewer. F7.
- There is no per-month progress indicator ("4/5 obligaciones del mes en orden").
- No filter rail (by institution, by status, by period). User must scan visually.
- The drawer reads document data but does not link to the submission detail page when the document is approved — only the "Subir documento" CTA appears when not approved.
- Calendar has no "today" affordance to anchor the user's eye.

### 4.4 `/portal/reports` — Compliance pulse + plantillas + recent reports

**Purpose:** Generate executive reports about the expediente.

**What works:**
- Preset titles already read well in Spanish: "Mi estado de cumplimiento", "Documentos faltantes", "Rechazos recientes" (`backend/app/services/reports/templates.py:196,224,248`).
- Featured first card (F4 visual audit) gives a clear "empieza aquí" without explicit copy.

**What hurts the user:**
- The Plantillas section was empty in the tester's session (F6 — bug, see BL-001).
- The silent fallback in `reports-list-view.tsx:112-120` collapses non-401 errors to `[]`. The empty-state copy "Tu rol todavía no tiene plantillas asignadas" is identical whether the role is genuinely empty or the endpoint failed (F6 root cause amplifier — see BL-008).
- The `CompliancePulseStrip` shows the percentage but doesn't say *why* (F5).
- Three vendor-facing presets is one more than most providers feel they need (F5 second half) — but this is strategic.
- Section header reads "Plantillas" — a non-technical user may not connect "plantilla" to "reporte ejecutivo." Consider "Empieza desde una plantilla" or "Genera un reporte" as a verb-led header.

### 4.5 Account & security (no current dedicated surface)

The provider has no:
- read-only profile page (N1)
- editable profile page with self-service fields (or escalation-to-support path)
- "olvidé mi contraseña" recovery flow (N2)
- idle logout (N3)
- last-login indicator
- list of active sessions

This is the **biggest single gap** in the product as the tester sees it, because it's not one missing button — it's an entire region of the product they expected to exist.

---

## 5. Provider experience model (the eleven questions)

Every provider page should answer at least one of these eleven questions explicitly. Today, some are answered, some are not.

| # | Question | Best surface today | Gap |
|---|---|---|---|
| 1 | What do I need to upload? | `/portal/onboarding` checklist + `/portal/calendar` cells | Not enough document detail per item |
| 2 | What does this document look like? | — | Missing (F1, F2) |
| 3 | Why is this document required? | Sparse hover text on some cards | Missing for most requirements |
| 4 | What have I already uploaded? | `/portal/submissions/[id]` per submission | No grouped history (F4) |
| 5 | What is approved? | `/portal/dashboard` semaphore segment | Approval count visible; *which* documents not always |
| 6 | What is pending? | Dashboard + calendar | OK |
| 7 | What was rejected and why? | Per-submission detail page | The "why" is sometimes plain Spanish, sometimes `rule_code`-shaped (F3) |
| 8 | What is missing? | Calendar empty cells + dashboard count | No grouped "missing list" with explanations (F4) |
| 9 | What is urgent? | Suggested actions rail + upcoming deadlines | Reasonable today |
| 10 | What should I do next? | Suggested actions rail | OK |
| 11 | How close am I to being complete? | Semaphore + percentage | Percentage shown without explanation (F4, F5) |

The two unanswered questions (#2, #11-with-context) drive the majority of the feedback. The plan below addresses them as Stage 2 and Stage 3.

---

## 6. Technical-clutter decluttering plan

Per-item rules for every engineer-dialect leak. The default action is **rename or hide under "Detalles técnicos," never silently drop** — backend identifiers stay useful for support tickets.

| Leak | Where | Action | Replacement |
|---|---|---|---|
| `eyebrow="Guided upload resolver"` | `frontend/app/portal/upload/page.tsx:108` | Rename | `"Carga guiada"` (eyebrow) |
| `validation.rule_code` rendered as primary label | `frontend/components/checkwise/validation-summary.tsx:29` | Rename via map + keep raw as tooltip | `RULE_CODE_LABELS_ES[code]` with code in `title=""` |
| `file_exists`, `allowed_file_type`, `pdf_magic_header`, `pdf_encrypted`, `pdf_readable_text`, `max_file_size`, `sha256_hash`, `duplicate_hash`, `vendor_match` | Backend `prevalidation.py` rule_code values | Wrap with frontend label map; keep backend codes intact | "Archivo recibido", "Tipo de archivo permitido", "PDF válido", "PDF protegido", "Texto legible", "Tamaño dentro del límite", "Hash de integridad", "Posible duplicado", "RFC del proveedor coincide" |
| `requirement_code`, `period_key`, `load_type` in URL | `/portal/upload?requirement_code=...&period_key=...` | Hide via `useEffect → router.replace(...)` after read, OR move to a session-store. Acceptable to leave for now but document. | Same params, but stripped from URL after hydration |
| "Workspace" in copy ("acciones urgentes para tu workspace") | `dashboard/page.tsx:168` | Rename | `"tu empresa"` or `"tu expediente"` |
| "Plantilla" without verb | `reports-list-view.tsx` section header | Rename | `"Empieza desde una plantilla"` or `"Genera un reporte"` |
| Wrong back-link label ("Calendario" → `/portal/dashboard`) | `upload/page.tsx:124-127` | Fix label OR fix route | Whichever matches intended UX; presumably the route is wrong |
| `submission_id` / `S-2826`-style codes shown without context | Various surfaces | Move under "Detalles técnicos" disclosure | Keep visible only inside submission detail's metadata block |
| Empty-state message that doesn't distinguish "role empty" vs "endpoint failed" | `reports-list-view.tsx:244-247` + `.catch(...)` | Add `presetsError` state + Alert | Two distinct empty messages |
| `font-mono` overuse on labels meant for casual reading | Multiple | Audit; reserve mono for codes, dates, file sizes | Plain sans for content labels |

**Never expose to providers, even after these fixes:**
- Raw SQLAlchemy/Pydantic field names
- Database PK UUIDs
- Internal feature-flag names
- Backend service names
- Stack-trace messages
- HTTP status numbers (the user sees "no pudimos cargar X", not "Error 500")

---

## 7. Plain-language Spanish copy recommendations

Curated set of replacements. Treat as the canonical first batch; the full map lives in `frontend/lib/constants/validation.ts` (new) + extends `frontend/lib/constants/statuses.ts`.

### Validation rule codes

| Backend code | Plain-Spanish label | One-line description (already in backend `message`) |
|---|---|---|
| `file_exists` | Archivo recibido | "Archivo recibido y almacenado fuera de la base de datos." |
| `allowed_file_type` | Tipo de archivo permitido | "Extensión detectada: PDF. En esta versión solo aceptamos PDFs." |
| `pdf_magic_header` | Estructura PDF válida | "El archivo tiene cabecera PDF válida." |
| `pdf_encrypted` | PDF sin contraseña | "No se detectó bloqueo por contraseña." |
| `pdf_readable_text` | Texto legible | "Se detectó texto legible para análisis posterior." |
| `max_file_size` | Tamaño dentro del límite | "Tamaño registrado: N bytes." |
| `sha256_hash` | Huella de integridad | "Hash SHA-256 calculado." |
| `duplicate_hash` | Sin duplicados | "No se detectó duplicado por hash." |
| `vendor_match` | RFC del proveedor coincide | (backend message) |

### Page-level eyebrow / nav

| Today | Tomorrow |
|---|---|
| "Guided upload resolver" (en `/portal/upload`) | "Carga guiada" |
| "Centro de cumplimiento personal: estado del expediente, obligaciones pendientes y rechazos por corregir." | Keep — already user-friendly |
| "Tu rol todavía no tiene plantillas asignadas." | "Aún no hay reportes disponibles para tu cuenta. Si crees que es un error, contáctanos." |
| "No pudimos cargar el dashboard" | "No pudimos cargar tu información en este momento. Volveremos a intentarlo." |

### Empty states (specific)

- Calendar empty month: "No hay obligaciones registradas para este mes."
- Reports empty after filter: "No encontramos reportes con esos filtros. Limpia los filtros para ver todos tus reportes."
- Profile not editable yet: "Para corregir un dato, escríbenos a soporte@checkwise.mx o usa el chat."

---

## 8. Upload guidance plan (Stage 2)

The upload page becomes the first place a provider learns what a document *is*, not just how to send it.

**Per-requirement metadata to add** (backend `catalogs.py`, optional fields):

- `anatomy_es: str | None` — 2-4 sentence description of what the document should contain. Example for CSF:  
  > "La Constancia de Situación Fiscal vigente la emite el SAT. Debe estar a nombre de la empresa proveedora, vigente al día de hoy, y mostrar el RFC, el régimen fiscal y el domicilio actualizados. Solo aceptamos la versión emitida en los últimos 30 días."
- `sample_image: string | null` — relative path to a redacted sample. Lives under `frontend/public/marketing/requirement-samples/`.
- `where_to_obtain_es: string | null` — short instruction with link (e.g. SAT portal URL).
- `common_errors_es: string[]` — 1-3 bullets: "El documento debe estar a nombre de la empresa, no de un representante." / "Verifica que el RFC coincida con el del contrato."

**UX surfaces** (`document-submission-form.tsx`, `intake-wizard.tsx`):

- An "Acerca de este documento" disclosure (collapsed by default) opens to show the four fields above.
- Sample image renders inline above the file dropzone (≤ 220 px wide, with `alt` and redaction note).
- A "Tips antes de subir" mini-checklist appears between the file selector and the submit button. Two-to-three bullets, plain Spanish.

**Validation summary upgrade (BL-003 visual):**

```text
✓ Archivo recibido                       Archivo recibido y almacenado.
✓ Tipo de archivo permitido              PDF. En esta versión solo aceptamos PDFs.
✓ Estructura PDF válida                  El archivo tiene cabecera PDF válida.
! PDF sin contraseña                     Bloqueado por contraseña — revisa con quien lo emitió.
✓ Texto legible                          Texto detectado correctamente.
```

The mono `rule_code` becomes a small `title="file_exists"` tooltip for QA reproducibility.

**Out of scope (do not ship in Stage 2):** OCR-based per-page guidance, AI-assisted document recommendations.

---

## 9. Dashboard guidance plan (Stage 3)

Two changes, both additive — do not remove existing surfaces.

### 9.1 Gauge causality subtitle

Below the percentage on `SemaphoreHero`:

```
78 % de cumplimiento
Te faltan 3 documentos para completar mayo · IMSS prioritario
```

Source: the same `dashboard.document_state_counts` already feeding the segments. The "IMSS prioritario" chip uses the highest-weight pending requirement from `dashboard.attention_today`.

### 9.2 "Mis documentos cargados" history block

A new read-only block under `EvidenceSlotGrid`, grouped by **Institución → Año → Mes**, with rows showing:

- Document name (Spanish, from catalog title)
- Period it covers
- Upload date in `DD MMM YYYY` Spanish
- Filename, truncated
- Status pill (the existing `DocStateBadge`)
- A "Ver" button → submission detail

No edit affordance. F4 explicitly warns about edit risk; respect that.

Behind a `<details>` or a "Ver historial" expand by default, so the dashboard first viewport stays calm.

**Data source:** existing `GET /api/v1/portal/workspaces/{id}/submissions` — verify the response already includes `uploaded_at`, `filename`, `institution_code`, `period_code`. If not, extend.

---

## 10. Reports simplification plan (Stage 4)

Two additive moves; the strategic "collapse three presets into one" is held back as BL-009.

### 10.1 Surface the "why" on Compliance Pulse

The strip gets a one-line subtitle that uses the same blocker source as the dashboard subtitle:

```
Tu expediente está al 78 %
Te faltan 2 documentos críticos: Constancia REPSE y Opinión IMSS.
```

### 10.2 Visible error vs. empty in the preset gallery

- Empty (legitimate): "Aún no hay reportes disponibles para tu cuenta. Si crees que es un error, contáctanos."
- 500 / network / other: a small Alert above the gallery: "No pudimos cargar las plantillas. Vuelve a intentarlo en unos segundos." + retry button.

This is BL-008 verbatim. It's listed here too because it is the **product-side** half of the BL-001 bug; both must ship together.

---

## 11. Interactive calendar plan (Stage 5)

Today's calendar is a state grid. The plan is to turn it into an **evidence timeline** without losing the at-a-glance grid.

### 11.1 Cell view (additive)

Each populated cell shows:

```
─────────────
IMSS · MAY 2026
Aprobado · 18 may
opinion_imss.pdf
─────────────
```

Truncate the filename with ellipsis. Hide upload date and filename on cells whose state is `empty`/`pending`. F7 verbatim.

### 11.2 Filter rail

A single row above the grid, only on desktop:

- Institución: chips (SAT · IMSS · INFONAVIT · STPS — multi-select, default all)
- Estado: chips (Aprobado · En revisión · Por atender · Pendiente · Vencido)
- Periodo: small year selector (default current year)

Empty result: "No encontramos obligaciones con esos filtros."

### 11.3 "Hoy" affordance

A subtle column accent (border + faint background tint) on the current month column. Mobile: a `↓ Hoy` button anchored above the grid that scrolls to the current month.

### 11.4 Per-month progress indicator

A small mono caption above each column:

```
MAYO 2026
4 / 5 al día
```

Color-coded by completion: green ≥ 80 %, amber 50–79 %, red < 50 %.

### 11.5 Drawer upgrades

The drawer already has the right scaffold. Additions:

- When the slot has a submission, show its **upload date + filename** at the top of the drawer (mirroring the cell preview).
- When the document is approved, replace "Subir documento" with **"Ver documento"** routing to the submission detail.
- When the document is rejected, the CTA becomes **"Corregir rechazo"** with a one-line reason summary above it.
- Add a "Comentarios del revisor" disclosure when there is a `reviewer_comment` available.

### 11.6 Out of scope for Stage 5

- Drag-and-drop on cells (risky — accidental submissions).
- Multi-year navigation beyond a year selector.
- Public/external sharing of the calendar.

---

## 12. Professional gamification & guided-progress plan (Stage 6)

This is **the** axis where CheckWise can become memorable for a provider without becoming a children's app. The rule is: motivation tied to compliance, not to consumption.

| Idea | Verdict | Why |
|---|---|---|
| Progress ring on dashboard + per-month progress on calendar | **Useful now.** | The user already asked for this implicitly (F4, F5). Already partly built. |
| "Te faltan N documentos para completar mayo" mini-checklist | **Useful now.** | Direct restatement of the F4 ask in product copy. |
| Next-best-action rail | **Useful now — already exists**, slightly polished. | Keep; tighten the empty-state copy. |
| "Expediente completo del mes" celebration banner | **Useful now.** Brief, dismissible, restrained ("Mayo terminado al 100 %. Te lo confirmamos."). | Tasteful; pairs with the per-month progress indicator. |
| Mini-milestones: "Primer documento", "Mes completo", "Trimestre sin rechazos" | **Useful later.** | Could become a "Hitos" disclosure on the dashboard. Behind a feature flag; opt-in. |
| Streaks ("3 meses al hilo") | **Risky.** Don't ship. | Streaks penalize legitimate one-month gaps for legal reasons. |
| Trust score / risk score visible to the provider | **Risky — needs legal approval.** | A score that materially affects how Legal Shelf treats them must not be a one-line "you're at 72". Hold. |
| Badges with cute names | **Not recommended.** | Compliance product, not Duolingo. |
| Confetti / celebratory animation on upload success | **Borderline.** | A 600 ms checkmark draw (already in `globals.css`) is enough. No confetti. |
| Step-by-step first-time onboarding tutorial overlay | **Useful later.** | Real value, but it's its own design problem — schedule after Stage 3. |
| "Antes de subir" mini-checklist (Stage 2) | **Useful now.** | Already in the plan. |
| Document anatomy + sample image (Stage 2) | **Useful now.** | F1, F2. |
| Per-section "¿Te sirvió esta vista?" thumbs-up/down | **Useful later.** | Powerful product feedback signal; build after Stage 4. |

**Visual treatment:** all progress indicators use the existing tokens — navy for primary, teal for "Wise" / intelligence moments, green for completion, amber for warning, red for risk. No new colors.

**Copy treatment:** never imperative or scolding. Never humorous. "Te faltan 3 documentos" not "¡Te falta poco!". "Mayo cerrado al 100 %" not "¡Lo lograste!".

---

## 13. Account & security plan (Stage 6.5 — new because of N1/N2/N3)

This region of the product does not exist today and needs its own stage. It is **not** gamification; it is table-stakes for a compliance product.

### 13.1 Profile read view (`/portal/mi-espacio` or `/portal/perfil`)

Shows, read-only:

- Empresa / razón social
- RFC del proveedor
- Cliente vinculado
- Contrato de referencia
- Correo de la persona contacto
- Última sesión iniciada (fecha + zona horaria)
- "Si necesitas corregir alguno de estos datos, escríbenos a soporte@checkwise.mx."

### 13.2 Self-service profile edit (controlled)

Three escalating tiers — pick **Tier B** for the first ship:

- Tier A: read-only only. Lowest risk. Use this if Legal Shelf prefers full control of provider master data.
- **Tier B: edit `contact_email`, `contact_phone`, `contact_name` only.** Everything else (RFC, razón social, contract reference) stays support-only. This matches the tester's exact ask: "modificar dato erróneo" without exposing tenancy-altering fields.
- Tier C: full self-service with a one-edit limit. Higher risk; needs explicit approval.

Audit log every change to `audit_events` with `actor=provider`.

### 13.3 Forgot password flow

- Add a `"¿Olvidaste tu contraseña?"` link on `/login` and `/portal/entra-a-tu-espacio`.
- Click → email entry → backend mints a single-use recovery token (TTL 15 min) → user receives email with a link to `/login/reset?token=...` → user sets new password (existing change-password component reused).
- Rate-limit by email + IP. Audit every request.

### 13.4 Idle logout

- Default: **20 minutes** of inactivity → session ends → user is shown a "Por seguridad cerramos tu sesión." screen at `/login` with their email pre-filled.
- A "Mantén mi sesión" interstitial appears at 18 minutes giving the user 60 seconds to extend.
- Token lifetime stays at its current value; only the **idle** timer is new.
- Configurable via `NEXT_PUBLIC_PORTAL_IDLE_MINUTES` for staging vs production.

### 13.5 Out of scope for this stage

- 2FA — schedule for a later legal pass.
- Active session listing — nice to have, not urgent.

---

## 14. Production runtime hardening plan (Stage 7)

This is the BL-005 work from the triage, but framed for the new staged plan:

1. Audit `next.config.ts` — the recently added `distDir` override is keyed on non-ASCII cwd; verify Vercel cwd is ASCII so the override is inert in production. (Quick check: log `process.cwd()` during a one-time Vercel preview build.)
2. Add `frontend/app/portal/error.tsx` or wrap the portal layout with a small client component that listens for `ChunkLoadError` and triggers `window.location.reload()` after a 500 ms grace period.
3. Investigate Vercel's deploy-preserve behavior. If chunks get pruned aggressively, switch to `experimental.optimisticClientCache: false` for the portal segment.
4. Smoke-test by deploying a no-op to a preview, leaving a portal tab open, deploying again, and navigating.

---

## 15. Revised staged roadmap

Each stage is one PR. Each stage is independently shippable.

| Stage | Title | Items | Why now | Risk |
|---|---|---|---|---|
| **Stage 0** | Understanding (this document) | — | We are here. | n/a |
| **Stage 1** | Provider clarity + safe failure | BL-008 (Alert in reports list) → BL-001 (presets bug repro + fix) → BL-003 (Spanish validation labels) → fix English eyebrow on `/portal/upload` → fix wrong back-link label → audit "workspace" → "empresa" copy | Closes the only declared bug, removes the loudest engineer-dialect leak, fixes a misleading nav label. ½–1 day. | low |
| **Stage 2** | Upload guidance | BL-002 (document anatomy + sample image + "antes de subir" mini-checklist) | The single biggest first-time-uploader pain. Five priority requirements first. 2 days. | medium (content curation) |
| **Stage 3** | Dashboard guidance | BL-004 (history block + gauge causal subtitle) | Direct restatement of F4; the second loudest pain. 2 days. | medium (layout balance) |
| **Stage 4** | Reports simplification | BL-007 (Compliance Pulse "why" chip) + the visible error state shipped in Stage 1 finalized + "Plantillas" header verb rewrite | Closes F5 first half. 1 day. | low |
| **Stage 5** | Interactive calendar | BL-006 (cell metadata) + filter rail + "Hoy" + per-month progress + drawer upgrades | Closes F7 and elevates the calendar from grid to timeline. 3 days. | medium (component complexity) |
| **Stage 6** | Professional gamification | per-month progress on calendar + "Mes completo" banner + tightened next-action rail copy + "Te faltan N documentos" subtitle reused | All cumulative — does not introduce new screens; refines what Stages 3 and 5 ship. 1 day. | low |
| **Stage 6.5** | Account & security | N1 (profile read view), Tier-B profile edit, N2 (forgot password), N3 (idle logout) | Three feedback items, table-stakes for a compliance product. 3 days. | medium-high (auth + audit log) |
| **Stage 7** | Production runtime hardening | BL-005 (ChunkLoadError fallback + Vercel audit) | Cosmetically loud (chunk errors on four routes), benefits from a Vercel preview. ½ day. | medium (preview-only smoke) |
| **Stage 8 (strategic)** | Collapse three vendor presets into one | BL-009 | Hold. Needs more signal than one tester. | high |

**Total before Stage 8:** ≈12 working days of implementation. Realistic to ship Stages 1–4 in the first week and 5–7 in the second.

---

## 16. Recommended first implementation batch

After approval, the very first PR is **Stage 1**, in this order inside the PR:

1. `frontend/components/checkwise/reports/list/reports-list-view.tsx` — add `presetsError` state and a visible `Alert` for non-401/403 errors (BL-008).
2. Reproduce BL-001 on staging with jluna's account. Capture the actual `/api/v1/reports/_presets` response. If `200 { items: [] }`, decide between (a) seed-data fix or (b) loosening `ReportActor.is_workspace_owner`. Ship the chosen fix.
3. `frontend/lib/constants/validation.ts` (new) + `frontend/components/checkwise/validation-summary.tsx` — BL-003. Keep raw codes as `title=""` tooltips.
4. `frontend/app/portal/upload/page.tsx:108` — replace `"Guided upload resolver"` with `"Carga guiada"`.
5. `frontend/app/portal/upload/page.tsx:124-127` — fix the back-link mislabel (either change "Calendario" to "Dashboard" or change the route to `/portal/calendar` per UX preference).
6. Audit & rename `"workspace"` in user-facing strings.

Single PR, single review surface. Then ship Stages 2–7 sequentially.

---

## 17. Acceptance criteria for the future implementation phase

Apply uniformly to every stage:

- **No raw engineer dialect** anywhere on `/portal/*` outside of explicit "Detalles técnicos" disclosures.
- **No silent failure** — every error has either a retry path or a "contáctanos" path.
- **No backend-name leaks** — words like "workspace", "preset", "submission_id", "vendor_id" do not appear in user-facing copy.
- **Plain Spanish** — every label and helper is written for a non-technical Mexican compliance officer.
- **Token discipline** — every color, shadow, and radius continues to flow from `globals.css` tokens.
- **Reduced-motion respected** everywhere new motion is added.
- **Mobile parity** — every new surface ships responsive at 390 / 768 / 1366 / 1440 (the matrix already in the recent landing-redesign QA).
- **`npx tsc --noEmit` clean. `npm run lint` clean. `npm run build` clean.** Two consecutive builds must succeed.
- **Every PR ships with a verification line** in the commit body (per the user's standing commit-workflow preference).

---

## 18. Risks & open questions

### Risks

- **Stage 1 — BL-001 root cause may be seed data, not code.** If `jluna@legalshelf.mx` was seeded with any non-empty `roles` tuple AND a `workspace_vendor_id`, the `is_workspace_owner` property correctly returns `False`. The fix is then a one-row UPDATE, not a code change. Confirm in staging before patching `report_service.py`.
- **Stage 2 — sample image sourcing.** Requirement-by-requirement sample images may need legal review (PII risk in real samples). Mitigation: redact via Photoshop / use SAT public examples.
- **Stage 3 — dashboard length growth.** Adding the history block under the existing surfaces pushes the first viewport down. Mitigate with a "Ver historial" expand and keep the hero block above.
- **Stage 5 — calendar density.** Adding upload-date + filename per cell may overcrowd on 1366×768. Truncate aggressively and only show on populated cells.
- **Stage 6.5 — auth surface.** Forgot password + idle logout touch session, audit, and rate-limit code. Ship with backend tests covering token TTL, rate-limit, and audit-log writes. Stage independently from anything UX-only.
- **Stage 7 — Vercel chunk behavior is hard to repro locally.** Preview deploy + manual repro before promotion to production.

### Decisions locked with Jose Pablo (2026-05-20)

- **N1 — profile edit tier:** **Tier B.** Provider may edit `contact_email`, `contact_phone`, `contact_name` only. RFC, razón social and contract reference stay support-only. Audit every change.
- **N2 — recovery channel:** **Email link AND live-chat escalation.** Email path ships first (single-use token, 15 min TTL, rate-limited, audited); chat-with-support entry point ships alongside as the v1 escalation route. Schedule the chat integration scope as a sub-task inside Stage 6.5.
- **N3 — idle timeout:** **20 minutes idle, 18-minute warning interstitial** with a 60-second "Mantén mi sesión" extend. Configurable via `NEXT_PUBLIC_PORTAL_IDLE_MINUTES` for staging.
- **Stage 2 — sample images:** **Ship anatomy text and "antes de subir" mini-checklist first. Images later.** No content-curation blocker on Stage 2. Once images are produced (Legal Shelf or curated from public SAT/IMSS), add them in a follow-up PR keyed off the same `sample_image` field in `catalogs.py`.
- **Stage 5 — calendar PR scope:** **Thin slice first.** PR #1 ships cell metadata (upload date + filename) plus drawer upgrades (Ver / Corregir CTA + reviewer-comment disclosure). Filters, "Hoy" affordance, and per-month progress land in PR #2. Keeps each review surface small and closes F7 quickly.
- **Stage 6 — milestones default:** **Default ON for all providers, no toggle.** If Legal Shelf later wants to disable for a specific client, we ship the per-org flag at that point. Less code now, more motivation for the testers.
- **Stage 8 — BL-009 (collapse 3 presets):** **Hold.** Single-tester signal. Re-evaluate when (a) a second tester says the same, or (b) sales/ops requests it. Existing three presets remain canonical until then.

### BL-001 — Resolved direction (2026-05-20)

Jose Pablo provided the staging row for `jluna@legalshelf.mx`:

```json
{
  "email": "jluna@legalshelf.mx",
  "full_name": "Jorge Luna",
  "must_change_password": true,
  "user_status": "active",
  "vendor_name": "LegalShelf - CheckwiseDEMO",
  "vendor_rfc": "SNM070412PT7",
  "vendor_persona_type": "persona_moral",
  "client_name": "Cliente Piloto CheckWise",
  "workspace_id": "afbcffca-cd8c-4bc5-8120-55fbc2227584",
  "token_prefix": "1cfc525c…",
  "workspace_status": "active"
}
```

**Reading:**

- Jorge has a vendor (`SNM070412PT7`, persona moral) bound to an active workspace (`afbcffca-…`). By data, he is a workspace owner.
- The query did not surface a `roles` field. If the row truly has no role assignments (the standard "provider invite" path), then `ReportActor.is_workspace_owner = not self.roles and self.workspace_vendor_id is not None` should resolve to `True`, and the three vendor-facing presets should render.
- `must_change_password: true` plus the `token_prefix: 1cfc525c…` suggest Jorge is operating on the **temporary activation token** (he hasn't completed credential rotation yet). This is the path most likely to mis-thread `workspace_vendor_id` into the `ReportActor` dependency.

**Stage 1 backend investigation step (revised):** before touching `ReportActor.is_workspace_owner`, the implementation session must inspect `backend/app/api/v1/reports.py` — specifically the dependency that constructs `actor` for the `_presets` endpoint — and verify that `workspace_vendor_id` is populated when the session is authenticated with a portal activation token. If it is **not** populated for that token shape, the fix lives in the dependency (correctly thread the workspace into `ReportActor`), not in the property. If it **is** populated, then the `roles` tuple must contain something unexpected for Jorge's seed and the fix lives in seed data (or the property loosens to "has workspace_vendor_id, regardless of roles" — the safer change).

The order of checks:
1. Reproduce on staging as Jorge. Capture the response body of `GET /api/v1/reports/_presets`.
2. Add structured logging on the dependency: `actor.user_id`, `actor.roles`, `actor.workspace_vendor_id`. One-line debug.
3. If `workspace_vendor_id` is `None`, fix the dependency.
4. If `workspace_vendor_id` is set and `roles` is empty but the function still returns `[]`, fix the property (unlikely — the property is correct).
5. If `roles` has unexpected content (e.g. an accidental `internal_admin` from a seed script), fix the seed and add a backend assertion.

This investigation is bounded — it fits inside Stage 1.

### F4 mandate — Holistic data-viz redesign on `/portal/dashboard` (revised Stage 3 scope)

Jose Pablo confirmed: "use the design skills to rework that section to be more intuitive and clear." This raises Stage 3 from a subtitle tweak to a **holistic visual redesign of the dashboard's gauge and chart composition**, with the explicit goal that a non-technical provider can answer "qué me falta para completar mi expediente" in one glance.

**Stage 3 — revised scope:**

- Use `ui-ux-pro-max`, `impeccable`, `design-taste-frontend`, `high-end-visual-design`, and `redesign-existing-projects` as the visual engine.
- Re-compose the dashboard's data-visualization region (`SemaphoreHero`, the donut, the stacked bars, the KPI strip) so it answers, in priority order:
  1. **Where am I?** (compliance %)
  2. **What is keeping me from 100 %?** (causal subtitle + top blocker chip)
  3. **What did I submit?** (history block grouped by Institución × Mes × Año — already planned in §9.2)
  4. **What should I do next?** (existing NextActionRail, kept)
- The radial gauge stays as the focal point; the surrounding charts get reorganized so each one answers a distinct question instead of restating the same totals in different shapes.
- Stage 3 is **not** "delete the existing charts." It is "make them tell a story together." Tokens, motion utilities, and component primitives all stay.

**Stage 3 acceptance criteria (updated):**

- A new provider lands on `/portal/dashboard` and can articulate "X documentos me faltan" + "el más importante es Y" within 5 seconds of looking at the gauge region.
- Every chart that remains explains its own purpose in a one-line eyebrow ("Distribución por estado", "Documentos por institución", etc.).
- No raw counts or technical labels appear without a verbal subtitle.
- History block (read-only) ships alongside the chart redesign — F4's two halves are one PR.
- Responsive matrix 360 / 768 / 1366 / 1440 holds.

Implementation note for the next session: spawn the design skills via the `Skill` tool early in Stage 3 to lock the composition direction before writing components.

---

### Still needs a quick clarification from Jose Pablo before Stage 1 ships

None. Both blocking questions are resolved. Stage 1 can begin as soon as Jose Pablo says "go."

---

## 19. Final words

The product is good. The tester literally says so. What's missing is the last 20 % that makes it feel like a **compliance assistant** instead of a **compliance database** — plain language, visible history, causal explanations, account self-service, and a calendar that remembers what you did, not just what you owe.

Every recommendation here keeps the existing CheckWise architecture, the existing tokens, the existing component library. Nothing is destructive. Nothing should be implemented until you've approved this plan.

---

## 20. Transcript-Based Provider Feedback Update (2026-05-20)

After Stages 1 and 2 shipped, a longer-form transcript review surfaced ten provider-side themes that re-order the roadmap. The themes are catalogued in detail in [../provider-feedback-transcript/PROVIDER_TRANSCRIPT_FEEDBACK_MAP.md](../provider-feedback-transcript/PROVIDER_TRANSCRIPT_FEEDBACK_MAP.md); this section is the part that affects the staged plan.

### 20.1 What the transcript changes

- **Priority shift.** Four items become P0 (one already-mitigated, three actionable): privacy notice (T1, gated on legal), XML decision (T6, document-only), period filter validation (T7), and confirmation that the compliance-% safety net (T8) already structurally prevents "upload anything → 100 %". This bumps the dashboard data-viz rework (former Stage 3) **behind** trust/safety/language polish.
- **Existing assets discovered.** The `CorrectionRequestForm` component is already built (`frontend/components/checkwise/workspace/correction-request-form.tsx`) but unmounted; T2's lift is mostly wiring + a real backend endpoint, not a green-field build. Stage 2.5/2.7 can land it quickly.
- **Multi-file is a UI/API problem, not a schema problem.** `Submission` already has `documents: list[Document]`. T4 becomes a Stage 2.7 implementation question, not an architectural one.
- **Stage 1 BL-003 was the labels only.** The transcript exposes that the *messages* (the second sentence under each rule_code) still carry "Hash SHA-256", "extracción/OCR", "anomaly_codes". Stage 2.6 finishes that work.

### 20.2 Revised staged roadmap

The roadmap below supersedes the §15 sequence for anything not already shipped. Stages already on `main` (1 + 2) stay as-is.

#### **Stage 2.5 — Provider trust and safety corrections** (NEW, P0 batch)

- **Objective:** Close the safety/correctness gaps the transcript flagged before any new visual work begins.
- **Why it matters:** Period filters today accept impossible inputs (e.g. `?year=1945`). REPSE 2026 is hardcoded on the provider-facing `entra-a-tu-espacio` route. XML acceptance is not documented as a decision. Each is small to fix; together they harden the trust baseline.
- **Affected pages:** `/portal/calendar`, `/portal/dashboard`, `/portal/reports`, `/portal/upload`, `/portal/entra-a-tu-espacio`. Backend `portal.py` calendar + period endpoints.
- **Likely files:**
  - `backend/app/api/v1/portal.py` (add `Query(ge=2021, le=...)` on every `year` param; helper `validate_period_key`)
  - `frontend/app/portal/calendar/page.tsx` (cap year selector)
  - `frontend/app/portal/entra-a-tu-espacio/page.tsx` (replace literal "REPSE 2026")
  - `frontend/components/marketing/*-section.tsx` (replace marketing literals — non-blocking)
  - `docs/security/XML_UPLOAD_SECURITY_RECOMMENDATION.md` (new — documents the "block by default" decision)
- **Backend impact:** Add a min/max `Query` constraint on every year-bearing endpoint + a `validate_period_key` helper called wherever a `period_key` arrives from user input. Add backend tests for the boundary cases (`?year=2020`, `?year=2021`, `?year=current+1`, `?year=current+2`).
- **Frontend impact:** Year selectors cap at `[2021, currentYear + 1]`. Marketing + activation strings derive from `new Date().getFullYear()` or a `CHECKWISE_DEFAULT_YEAR` constant.
- **Legal/security dependencies:** None code-side. The XML doc records a decision that needs Jose Pablo's go.
- **Acceptance criteria:**
  - Every period-bearing endpoint rejects `year < 2021` and `year > currentYear + 1` with a 422 + plain Spanish detail.
  - No string `"REPSE 2026"` or `"2026"` literal remains in `/portal/*` user-facing copy.
  - `XML_UPLOAD_SECURITY_RECOMMENDATION.md` lands in `docs/security/` recording the current PDF-only stance + the conditions under which XML would be reconsidered.
  - Compliance-% safety net (T8) is verified with a regression test: a slot in `POSSIBLE_MISMATCH` is excluded from `RESOLVED_SLOT_STATES`; `compliance_pct` cannot reach 100 while any required slot is in an actionable-blocking state.
- **Test plan:** Backend pytest on the period validators (4 boundary cases × N endpoints). Frontend snapshot of the year selector at the new lower bound. Manual verification that the activation route no longer shows a hardcoded year.
- **Implementation risk:** Low. Each item is a bounded change with a clear test.

#### **Stage 2.6 — Provider language simplification** (NEW, P1 batch)

- **Objective:** Finish the BL-003 work by removing engineer dialect from the *messages* (not just the labels) and tightening the UI honesty around the classifier.
- **Why it matters:** Providers still read "Hash SHA-256", "extracción/OCR", "anomaly_codes" inside the validation summary's second sentence and inside the intake wizard's helper text. The transcript also asks for explicit "el documento parece…" / "no podemos confirmar que sea el documento solicitado" framing when the classifier flags a possible mismatch.
- **Affected pages:** `/portal/upload` (intake wizard + validation summary), `/portal/submissions/[id]` (timeline), admin/reviewer detail.
- **Likely files:**
  - `backend/app/services/prevalidation.py` (rewrite the `message` strings; surface a separate `technical_detail` field for admin-only consumption)
  - `frontend/components/checkwise/validation-summary.tsx` (render the friendly message; hide the technical detail behind an admin-visible / QA-visible `<details>`)
  - `frontend/components/checkwise/intake-wizard.tsx:1100-1240` (rewrite the "Calculamos hash SHA-256…" helper lines)
  - `frontend/components/checkwise/confidence-badge.tsx` (audit copy)
  - Possibly expand `frontend/lib/constants/validation.ts` with a `message_es` override map keyed by `rule_code`.
- **Backend impact:** Modify validation message strings; optionally add a `technical_detail: str | None` field on `ValidationSignal` that frontend admin paths render and provider paths skip. Or keep the technical bits under a backend-only logger and just send the friendly version to the API.
- **Frontend impact:** Update the validation summary to render `messageFor(ruleCode, signal)` (a small helper) and tuck the SHA-256 / anomaly-code details under an admin-only or reviewer-only disclosure. Rewrite the wizard helper text in plain Spanish.
- **Legal/security dependencies:** None.
- **Acceptance criteria:**
  - The strings `"SHA-256"`, `"hash"`, `"OCR"`, `"extracción"`, `"pipeline"`, `"parser"`, `"anomaly"` never appear on the provider portal viewport.
  - When the classifier flags `document_signals.mismatch_reason`, the provider UI surfaces "Posible discrepancia detectada · el documento parece…" with the mismatch reason as supporting copy.
  - The reviewer / admin surfaces retain the technical detail (under a disclosure) so QA reproducibility is not lost.
- **Test plan:** Frontend unit test asserts no banned string in the rendered validation summary. Backend snapshot of `prevalidate(...).message` for each rule. Visual QA on a seeded mismatched-document submission.
- **Implementation risk:** Low (copy + a small `<details>` reorganization).

#### **Stage 2.7 — Provider upload usability** (NEW, P1 batch — independent of Stage 2.5/2.6)

- **Objective:** Cover the "multi-file per requirement" and "Solicitar corrección entry point" asks. Also expand `common_errors` to 5 bullets per priority requirement.
- **Why it matters:** Today the wizard accepts one file; contract + annex requires two separate submissions. The existing `CorrectionRequestForm` is unmounted, so providers have no way to ask for an RFC / razón social fix without leaving the product.
- **Affected pages:** `/portal/upload`, `/portal/entra-a-tu-espacio`, provider context bar (sitewide).
- **Likely files (multi-file):**
  - `backend/app/api/v1/portal.py:1453` (endpoint `files: list[UploadFile]` instead of `file: UploadFile`; loop storage + prevalidation per document)
  - `backend/app/services/submission_service.py` (multi-doc submission write path)
  - `frontend/components/checkwise/intake-wizard.tsx` (multi-file dropzone, per-file progress + status)
- **Likely files (correction request):**
  - Existing `frontend/components/checkwise/workspace/correction-request-form.tsx` mounted on the workspace identity card / provider profile area
  - `frontend/lib/mock/corrections.ts` → real `frontend/lib/api/corrections.ts` + `POST /api/v1/portal/workspaces/{id}/correction-requests` backend endpoint
  - New `correction_requests` table or `audit_events` row with admin notification
- **Likely files (expanded rejection causes):**
  - `backend/app/core/compliance_catalog.py` (expand each priority requirement's `common_errors` from 3 to 5)
- **Backend impact:** New endpoint for correction requests; multi-file endpoint changes; multi-doc transaction discipline (atomic vs partial submit semantics — recommend atomic: all-or-nothing per submission).
- **Frontend impact:** Multi-file UI redesign; small profile / context bar surface for the correction-request entry point.
- **Legal/security dependencies:** Multi-file aggregate size limit must be enforced. Correction-request workflow needs an admin path to act on the request — confirm whether admin notification goes via Slack (existing pattern, see Stage 1 BL-008) or via a new admin tray.
- **Acceptance criteria:**
  - One requirement upload can include `[1, N]` files where N is bounded (recommend N ≤ 5) and total ≤ a per-submission cap (recommend 30 MB).
  - A failed file fails the entire submission (atomic) and surfaces a per-file error list.
  - The `CorrectionRequestForm` is reachable from the provider context bar with one click; a real submission persists to `audit_events` and produces an admin notification.
  - The 5 priority onboarding requirements each show ≥ 5 plain-Spanish rejection-cause bullets in their "Antes de subir" list.
- **Test plan:** Backend pytest for the multi-doc submission write path (success, partial-fail rollback, size limit). Frontend integration test mocking the multi-file dropzone. Visual QA on the correction-request flow.
- **Implementation risk:** Medium. Multi-file changes the API contract; ship behind a `multi_file_upload` feature flag so we can roll back if needed.

#### **Stage 2.8 — Privacy notice + correction-request backend (parallel track, gated on legal)**

- **Objective:** Land the privacy notice acceptance UI + the real correction-request endpoint once Paco/Beko return the legal copy.
- **Why it matters:** Privacy notice is a regulatory requirement before sharing provider/client info. Cannot ship without final copy.
- **Affected pages:** `/activate`, `/login`, `/portal/entra-a-tu-espacio`, possibly `/`.
- **Likely files:** New `frontend/components/marketing/privacy-notice-modal.tsx`; new `backend/app/api/v1/auth.py` accept-privacy endpoint; `accepted_privacy_notice_at` column on `users` or `provider_workspaces`.
- **Legal/security dependency:** **Blocking** — Paco/Beko/legal copy.
- **Acceptance criteria:** The user cannot proceed past activation without explicit acceptance; the acceptance is timestamped and audited.
- **Implementation risk:** Low code-wise; high process-wise (legal copy).

#### **Stage 3 — Dashboard clarity and data-viz rework** (unchanged in scope; reordered later)

- **Objective:** F4 holistic data-viz redesign using the design-skill stack. (See §14 of this plan, untouched.)
- **Why it matters:** The dashboard gauge does not explain *why* the user isn't at 100 %.
- **Stage discipline:** Stage 3 begins only after Stages 2.5 + 2.6 are on `main`. The dashboard redesign benefits from a clean trust/language baseline.

#### **Stage 4 — Reports simplification** (unchanged)

#### **Stage 5 — Interactive calendar** (unchanged; thin slice first per the locked decision)

#### **Stage 6 — Professional guided progress / gamification** (unchanged)

### 20.3 Recommended first implementation batch after this update

**Option A — Stage 2.5 first.** Pure safety/correctness/documentation work, no legal blockers, no design pass needed. Closes the four P0 items and produces a written security decision on XML. Highest trust gain per unit of effort.

**Option B — Continue with Stage 3 dashboard.** Defensible only if you decide that the verified compliance-% safety net (T8) plus the existing dynamic-year frontend on the calendar already meet "safe enough." Even then, the period validation gap and the REPSE 2026 leak on `entra-a-tu-espacio` argue against jumping to Stage 3.

**Option C — Split Stage 2.5 + Stage 2.6 into two PRs.**  
- PR 1: period validation + REPSE 2026 cleanup + XML security doc (Stage 2.5).  
- PR 2: timeline language rewrite + "el documento parece…" honesty pass (Stage 2.6).  
Same total work, two cleanly reviewable surfaces.

**Recommendation:** Option C. The two stages are conceptually independent (safety vs language), each PR is short enough to review in one sitting, and Option C lets us deploy Stage 2.5 immediately while Stage 2.6 is in review.

### 20.4 What still needs your sign-off before any of this codes

| Item | Decision needed |
|---|---|
| T1 — privacy notice | Final copy from Paco / Beko / legal. Plumbing can wait. |
| T6 — XML | Confirm "block by default; reopen only with a specific need" — Stage 2.5 ships the doc recording your decision. |
| T4 — multi-file UX | Confirm: contrato + anexo arrives as one Submission with N Documents, OR as N separate submissions? Recommendation: 1 Submission → N Documents. |
| T5 — expanded rejection-cause copy | Optional: have Legal Shelf review the 5-bullet lists for the priority items before they ship. |
| T8a — classifier accuracy | Confirm whether the manual-vs-CFDI misclassification warrants a dedicated track now, or stays strategic backlog. |

---

*End of provider experience improvement plan.*
