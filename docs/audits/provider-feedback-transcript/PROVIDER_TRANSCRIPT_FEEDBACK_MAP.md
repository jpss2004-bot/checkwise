# Provider Feedback Transcript — Feedback Map (Stage 2.5)

**Status:** planning only. No code changes, no commits.  
**Companion docs:**  
- [../slack-feedback-triage/SLACK_FEEDBACK_TRIAGE_REPORT.md](../slack-feedback-triage/SLACK_FEEDBACK_TRIAGE_REPORT.md)  
- [../slack-feedback-triage/slack-feedback-backlog.json](../slack-feedback-triage/slack-feedback-backlog.json)  
- [../slack-feedback-triage/PROVIDER_EXPERIENCE_IMPROVEMENT_PLAN.md](../slack-feedback-triage/PROVIDER_EXPERIENCE_IMPROVEMENT_PLAN.md) (updated with revised roadmap)  
**Review date:** 2026-05-20.  
**Prior shipped work:** Stage 1 (commits `ed7d7a6`, `1e4c20a`, `88263a1`) + Stage 2 (commits `05947cb`, `03e8285`).

---

## 1. Source / context

This map turns a longer-form provider-side feedback transcript (Jose Pablo's notes after a deeper walkthrough with the tester team, 2026-05-20) into a structured, code-aware roadmap update. Where the Slack-channel triage covered seven messages from a single session, this transcript expands to ten themes spanning privacy, data correction, period validation, multi-document upload, rejection reasons, XML acceptance, classifier accuracy, technical language in the timeline, REPSE date hardcoding, and a closing positive evaluation.

**Hard rules locked before this map was written:**
- Do not write final legal copy without Paco/Beko/legal approval.
- Do not enable XML uploads without an explicit security decision.
- Do not build a full AI classifier now.
- Do not implement multi-file upload, full correction workflow, or any complex item without its own design pass.
- Preserve existing architecture, tokens, and roadmap discipline.

---

## 2. Summary

| Metric | Count |
|---|---:|
| Distinct themes | 10 |
| P0 (safety/correctness blockers) | 4 |
| P1 (provider clarity / user-test blockers) | 4 |
| P2 (product polish) | 1 |
| P3 (strategic differentiators) | 1 |
| Items implementable safely now (code only) | 3 |
| Items needing legal/security/product approval before code | 4 |
| Items needing a separate design pass before code | 3 |
| Routes most affected | `/portal/upload`, `/portal/onboarding`, `/portal/dashboard`, `/portal/calendar`, `/portal/entra-a-tu-espacio` |

**The transcript is validating, not destructive.** Theme 10 explicitly says the design is intuitive and the next work is polish + clarity, not a rebuild. The roadmap shifts only the *order* of stages, not the strategic direction.

---

## 3. Theme-by-theme map

### T1 — Privacy / legal process before credentials are shared

- **What the user said:** Platform may expose provider/client info before the end user is authenticated/identified. Need a clear privacy notice + legal authorization flow before credentials are issued. Coordinate with Paco and Beko on the privacy notice and how the client authorizes sharing supplier/provider information.
- **Affected pages/routes:** `/portal/entra-a-tu-espacio` (post-auth confirmation), `/activate` (credential setup), `/login`. Possibly also the public landing `/`.
- **User role:** Provider during onboarding; client/admin during invite creation.
- **Code state today:** A `grep` for `privacy / privacidad / aviso de privacidad / consentimiento / consent` returns **zero matches** anywhere in the repo (frontend + backend). There is no privacy-notice surface at all.
- **Severity:** P0 (legal/safety blocker).
- **Implementation complexity:** Medium frontend; needs **legal copy from Paco/Beko before any text is written**. The plumbing (a notice banner + an `accepted_privacy_notice_at` timestamp on the user / workspace row) is straightforward; the words are the gating item.
- **Legal/security dependency:** YES — final wording requires Paco / Beko / legal.
- **Safe to implement now?:** Skeleton (route + acceptance timestamp + audit log entry) — yes. Final copy — no. Do not invent legal language.
- **Recommended next action:** Plan the data model + acceptance UI behind a "needs legal copy" placeholder. Defer ship until legal returns the wording.

### T2 — Provider data correction flow ("Solicitar corrección")

- **What the user said:** Provider general info (RFC, razón social, provider name) should have a clear clickable action like "Solicitar corrección". Should not let the provider directly edit legally-sensitive data; should route to an admin/support workflow.
- **Affected pages/routes:** `/portal/entra-a-tu-espacio` (workspace confirmation card), `/portal/dashboard` (provider context bar), provider profile surface (does not exist yet — locked Tier B from §18 of the experience plan).
- **User role:** Provider.
- **Code state today:**  
  - **`apps/web/components/checkwise/workspace/correction-request-form.tsx` already exists.** It is a fully built React component with a Field/Input/Select/Textarea form, an `isProtectedField` gate, and a `submitCorrection` call.  
  - **It is currently NOT mounted on any provider-facing route.** A `grep` for `CorrectionRequestForm` returns only the definition file itself.  
  - The backing API at `submitCorrection` lives in `apps/web/lib/mock/corrections.ts` — **mock only**, no real backend endpoint.
- **Severity:** P1 (provider clarity blocker; Slack-feedback note N1 also raised this).
- **Implementation complexity:** Low frontend (mount existing component, link from provider context bar). Medium backend (replace mock with a real endpoint + audit log row + admin notification).
- **Legal/security dependency:** Light. RFC/razón social/contract-reference edits must remain support-only (Tier B locked decision). Audit every request.
- **Safe to implement now?:** Yes — surface the existing component on the provider profile area + add an entry point on the provider context bar. Backing endpoint can be added in the same PR or a follow-up.
- **Recommended next action:** Inventory the protected fields, ship a real `POST /api/v1/portal/workspaces/{id}/correction-requests` endpoint, mount the existing form, add an entry-point button on the relevant provider surface.

### T3 — REPSE 2026 hardcoded date

- **What the user said:** Review every "REPSE 2026" / hardcoded date. Decide whether to remove, dynamically calculate, or legally validate. Avoid hardcoded future years that may become wrong or confusing.
- **Affected pages/routes (verified by grep):**
  - `apps/web/components/marketing/features-section.tsx:46` — `title: "Calendario REPSE 2026"` (marketing)
  - `apps/web/components/marketing/hero-section.tsx:61` — `México · 2026`
  - `apps/web/components/marketing/hero-section.tsx:151` — `label: "REPSE 2026"`
  - `apps/web/components/marketing/legal-shelf-section.tsx:21` — `Estándar REPSE 2026`
  - `apps/web/app/portal/entra-a-tu-espacio/page.tsx:267` — `"Calendario REPSE 2026: SAT mensual..."` (provider-facing)
  - `apps/api/app/api/v1/portal.py:883` — `year: int = 2026` (calendar endpoint default)
  - Test files (`tests/test_portal_dashboard.py`, etc.) — fixtures, ignore.
- **User role:** Provider (entra-a-tu-espacio), public visitor (marketing).
- **Severity:** P2 (polish; not a safety blocker, but ages badly).
- **Implementation complexity:** Low. Each string can read from `new Date().getFullYear()` (frontend) or a config constant. The backend default can stay at 2026 with a `Query(ge=2021, le=now().year+1)` constraint added (folds into T7).
- **Legal/security dependency:** None.
- **Safe to implement now?:** Yes.
- **Recommended next action:** A single small PR replacing every hardcoded year with the current year (or a `CHECKWISE_DEFAULT_YEAR` config constant). Treat the provider-facing one on `entra-a-tu-espacio` as the priority.

### T4 — Multi-document upload for one requirement

- **What the user said:** Current upload appears to be one document at a time. Providers may need to upload multiple files for one requirement (contract + annex, RFC + actualizaciones). Evaluate whether the data model already supports it; if so, improve the UI; if not, document the safest path.
- **Code state today:**
  - **`Submission` has a 1:N relationship to `Document`** (`apps/api/app/models/entities.py:222`: `documents: Mapped[list[Document]] = relationship(back_populates="submission")`). **The data model already supports multiple documents per submission.**
  - The endpoint `POST /api/v1/portal/workspaces/{id}/submissions` (line 1453) accepts **one** `UploadFile`, runs `assert_pdf_upload(file)`, then stores one Document.
  - The prevalidation pipeline is per-document and per-submission.
  - The replacement lineage (`supersedes_submission_id`) is for re-uploads after rejection — **NOT** for grouping multiple documents under one submission.
- **Affected pages/routes:** `/portal/upload` (the wizard's file dropzone).
- **User role:** Provider.
- **Severity:** P1 (provider clarity blocker, also matches the Stage 2.7 plan goal).
- **Implementation complexity:** Medium. Backend endpoint moves from `file: UploadFile` → `files: list[UploadFile]`, loops the storage + per-doc prevalidation. Frontend wizard accepts multi-file selection (`<input type="file" multiple>`) and displays a per-file progress list. Reviewer + reports surfaces already handle multi-document submissions (the relationship was always 1:N) so the read path doesn't need to change.
- **Legal/security dependency:** None directly; but multi-file enables larger overall uploads → confirm the size limit applies *per file* AND in aggregate.
- **Safe to implement now?:** Not in Stage 2.5. Needs its own design pass (UI design for the file list, error handling per file, atomic vs partial submission semantics).
- **Recommended next action:** Plan only; ship in Stage 2.7 as a dedicated PR after period filters + language + correction request are stable.

### T5 — Full rejection cause catalog

- **What the user said:** Current guidance shows common rejection causes. Providers may need the full set of possible rejection causes because they're the lowest in the legal chain. Use plain Spanish. Use progressive disclosure to avoid overwhelming.
- **Code state today:** Stage 2 (commit `05947cb`) added `common_errors: tuple[str, ...] = ()` on `OnboardingRequirement`, with per-institution fallbacks (2 bullets) and per-item content for the 5 priority requirements (3 bullets each). There is **no** "complete causes" catalog separate from "common causes."
- **Affected pages/routes:** `/portal/onboarding` (the disclosure shipped in Stage 2), `/portal/upload` (could mirror the disclosure), submission detail pages.
- **User role:** Provider.
- **Severity:** P1.
- **Implementation complexity:** Low–medium. Two options:
  1. Expand `common_errors` per priority requirement from 3 bullets to 5–7, keeping the same field. Cheapest.
  2. Add a separate `all_rejection_reasons: tuple[str, ...]` field with the comprehensive list, render in a second disclosure level inside the existing "Acerca de este documento" component. Cleaner taxonomically.
- **Legal/security dependency:** None — copy only. Optional: review with Legal Shelf for accuracy of legal reasons.
- **Safe to implement now?:** Yes (option 1). Option 2 needs the content authored first.
- **Recommended next action:** Phase A (Stage 2.5): expand the priority items' `common_errors` to 5 bullets each. Phase B (Stage 3+): add a second-level "Todas las causas de rechazo" disclosure when content is curated.

### T6 — XML file security

- **What the user said:** Evaluate whether XML uploads are required. Do not enable just because users mention it. Produce a security recommendation: allow / block / allow only in specific types / quarantine-then-process / parse with hardened parser.
- **Code state today (verified):**
  - `apps/api/app/core/config.py:37` — `ALLOWED_FILE_EXTENSIONS: str = ".pdf"` — **PDF-only by default.**
  - `apps/api/app/services/submission_service.py:57` — `if not filename.lower().endswith(".pdf")` — hard reject for non-PDF.
  - `apps/api/app/api/v1/metadata_dry_run.py:41` — same PDF-only check.
  - `apps/api/app/services/prevalidation.py:30` — `allowed_file_type` rule fails on non-PDF.
  - **XML is currently rejected at three layers.** The system is safe today.
- **Affected pages/routes:** `/portal/upload`.
- **User role:** Provider; reviewer/admin if XML ever enters the pipeline.
- **Severity:** P0 *as a decision*, not as a fix — the safe answer needs a written security decision so future PRs don't accidentally enable XML.
- **Implementation complexity:** Decision: one-paragraph security recommendation. If we later allow XML for SAT XML CFDIs specifically: medium effort — `defusedxml` parser, schema validation, no DTD/entity expansion, quarantine + scan-then-process, scoped to specific requirement codes only.
- **Legal/security dependency:** YES. Decision needs Jose Pablo's product sign-off; if "allow under restrictions" is chosen, security review is required.
- **Safe to implement now?:** Yes — *document the decision to KEEP XML blocked* in the security recommendation file. No code change needed.
- **Recommended next action:** Write `docs/security/XML_UPLOAD_SECURITY_RECOMMENDATION.md` recommending "Block by default. Re-evaluate only with a specific requirement (e.g. SAT CFDI XML) and a defusedxml-based parser, entity-expansion disabled, schema-validated, file-scope-limited."

### T7 — Period filter limits (must reject anything before 2021)

- **What the user said:** Period filters currently accept impossible dates like 1945. Since REPSE began in 2021, period selectors / filters should not accept dates before 2021.
- **Code state today (verified):**
  - `apps/api/app/api/v1/portal.py:883` — `year: int = 2026` (no `Query(ge=..., le=...)`). **Accepts `?year=1945` and `?year=9999`.**
  - `apps/api/app/api/v1/portal.py:1993` — `period_key`-based deadline lookup reads `int(period_key[:4])` with no min/max check.
  - Frontend calendar page (`apps/web/app/portal/calendar/page.tsx:109`) sets the year from `new Date().getFullYear() || 2026` — **already dynamic**, only the fallback is hardcoded.
- **Affected pages/routes:** `/portal/calendar`, `/portal/dashboard` (via period query), `/portal/reports` (period filter), `/portal/upload` (period_key form field), admin/client calendars.
- **User role:** Provider; admin/client read-only.
- **Severity:** P0 (correctness blocker — accepts impossible inputs).
- **Implementation complexity:** Low. Add `Query(ge=2021, le=<current_year + 1>)` to every period-bearing endpoint. Add a helper `validate_period_key(period_key: str) -> None` that parses the year and validates the range. Frontend: cap the year selector at `[2021, currentYear + 1]`.
- **Legal/security dependency:** Light — confirm 2021 is the canonical REPSE start year (it is, per the catalog comment).
- **Safe to implement now?:** Yes.
- **Recommended next action:** Single-PR backend validation + frontend cap on every period selector. Plain-Spanish error: "Las obligaciones REPSE inician en 2021. Selecciona un año entre 2021 y {currentYear+1}."

### T8 — Automatic document identification accuracy

- **What the user said:** The product correctly flagged a mismatch in some cases (valuable), but misidentified a manual as a possible CFDI (reduces trust). Product must prevent "upload anything → 100% compliance." Continue improving identification but don't overclaim AI if it's rule-based.
- **Code state today (verified):**
  - `apps/api/app/services/dashboard_compute.py:40-47` — `ACTIONABLE_SLOT_STATES = {REJECTED, NEEDS_CORRECTION, POSSIBLE_MISMATCH}` blocks the semaphore to red. `RESOLVED_SLOT_STATES = {APPROVED, EXCEPTION, NOT_APPLICABLE}` are the only states that count toward `compliance_pct`. **The "100% with mismatched document" path is structurally prevented.** A document in `POSSIBLE_MISMATCH` cannot reach `APPROVED` without explicit reviewer action.
  - `apps/api/app/services/prevalidation.py:120-136` — `requirement_match` rule fires `result="warning"` and `requires_human_review=True` when `document_signals.mismatch_reason` is set.
  - The manual-vs-CFDI misclassification suggests `document_signals.mismatch_reason` *did not fire* for that file. The bug is in the upstream classifier (probably `apps/api/app/services/document_intelligence/`), not in the safety net.
- **Affected pages/routes:** `/portal/upload` (validation summary), `/portal/submissions/[id]` (timeline), `/portal/dashboard` (semaphore).
- **User role:** Provider; reviewer for diagnosis.
- **Severity:** P3 (strategic differentiator) for the classifier itself; P1 for the UI honesty around it.
- **Implementation complexity:** Classifier accuracy: out-of-scope for Stage 2.5. UI honesty: low — copy fixes only.
- **Legal/security dependency:** None.
- **Safe to implement now?:** UI honesty (T8b) yes — rewrite the validation summary copy so it never overclaims and always says "el documento parece…" / "no podemos confirmar que sea el documento solicitado." Classifier work: hold.
- **Recommended next action:** Stage 2.6 owns the UI honesty rewrite. Classifier accuracy lives in a separate plan (Stage 3+ or a dedicated track).

### T9 — Technical language in timeline / flow

- **What the user said:** Provider users don't understand "hash," "OCR," "extraction," internal process labels. Rewrite provider-facing timeline / status language for non-technical users. Keep valuable messages like "posible discrepancia detectada" and "el documento parece…". Hide technical details under an advanced/debug area only if useful for QA/admin.
- **Code state today (verified):**
  - `apps/api/app/services/prevalidation.py:86` — message contains `"Hash SHA-256 calculado: {sha256}"`. Surfaced to providers.
  - `apps/api/app/services/prevalidation.py:106` — `"Pendiente de extracción/OCR para confirmar RFC..."`.
  - `apps/api/app/services/prevalidation.py:115` — `"Pendiente de extracción/OCR para confirmar que el documento corresponde al periodo."`.
  - `apps/api/app/services/prevalidation.py:94-97` — `"Ya existe un documento con el mismo hash..."`.
  - `apps/web/components/checkwise/intake-wizard.tsx:1104` — `"Calculamos hash SHA-256, inspeccionamos la estructura PDF..."` (provider-facing helper text).
  - `apps/web/components/checkwise/intake-wizard.tsx:1232` — `"Hash SHA-256, estructura PDF, texto legible, señales documentales."`.
  - `apps/web/components/marketing/features-section.tsx:70` — `"Validación lista para OCR/IA"` (marketing — acceptable).
  - **Stage 1 BL-003 fixed the `rule_code` labels but left the message bodies and the wizard helper text untouched.**
- **Affected pages/routes:** `/portal/upload` (validation summary + intake wizard), `/portal/submissions/[id]`.
- **User role:** Provider.
- **Severity:** P1.
- **Implementation complexity:** Low. Rewrite the backend `message` strings to be technology-agnostic; tuck the SHA-256 / extraction details under an "Acerca de la validación técnica" disclosure available only on the admin/reviewer surface.
- **Legal/security dependency:** None.
- **Safe to implement now?:** Yes.
- **Recommended next action:** Stage 2.6. Single small PR rewriting the backend `message` strings + the intake wizard helper text; add a `font-mono` admin-only details block for QA reproducibility.

### T10 — Overall positive evaluation

- **What the user said:** Provider-level design is generally intuitive and strong. Next work should polish and clarify, not rebuild.
- **Code state today:** N/A — directional input.
- **Severity:** N/A.
- **Recommended next action:** Honor the direction — keep changes scoped, additive, and reversible. No tear-downs. Use the existing token system, the existing motion utilities, the existing component library. The roadmap revision below is order-of-stages only.

---

## 4. Affected pages × theme matrix

| Route | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 | T9 |
|---|---|---|---|---|---|---|---|---|---|
| `/` (landing) | | | ✓ | | | | | | |
| `/login`, `/activate` | ✓ | | | | | | | | |
| `/portal/entra-a-tu-espacio` | ✓ | ✓ | ✓ | | | | | | |
| `/portal/onboarding` | | | | | ✓ | | | | |
| `/portal/upload` | | | | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `/portal/dashboard` | | ✓ | | | | | ✓ | ✓ | |
| `/portal/calendar` | | | ✓ | | | | ✓ | | |
| `/portal/reports` | | | | | | | ✓ | | |
| `/portal/submissions/[id]` | | | | | | | | ✓ | ✓ |

---

## 5. Priority distribution

| Priority | Themes |
|---|---|
| **P0** — safety / correctness blockers | T1 (privacy notice — gated on legal), T6 (XML decision), T7 (period validation), and the **structural compliance-% safety net is already in place from T8** (verified) |
| **P1** — provider clarity / user-test blockers | T2 (correction request mount), T5 (expanded rejection causes), T8b (UI honesty copy), T9 (timeline language) |
| **P2** — product polish | T3 (REPSE 2026 hardcoded) |
| **P3** — strategic differentiators | T8a (classifier accuracy improvements) |
| **Direction** | T10 (validating, not destructive) |

---

## 6. Implementable-now vs. needs-approval breakdown

| Item | Can ship in Stage 2.5? | Why |
|---|---|---|
| T1 — privacy notice **placeholder + acceptance timestamp** | Skeleton only | Legal copy gated on Paco/Beko |
| T2 — mount existing `CorrectionRequestForm` + minimal entry point | Yes | Component already built; mock backend acceptable for Phase A; real endpoint in Phase B |
| T3 — replace hardcoded REPSE 2026 with dynamic year | Yes | Pure copy/code change |
| T4 — multi-file upload (UI + API) | No | Needs own design pass; ship in Stage 2.7 |
| T5 — expand `common_errors` per priority requirement to 5 bullets | Yes | Content-only |
| T6 — write "XML stays blocked" security recommendation doc | Yes | Documentation-only; locks decision |
| T7 — `year ≥ 2021` validation everywhere | Yes | Bounded change with tests |
| T8a — classifier accuracy improvements | No | Separate plan; AI work |
| T8b — UI honesty copy ("el documento parece…") | Yes | Copy-only |
| T9 — rewrite technical timeline language | Yes | Copy-only |
| Full multi-file UI, real correction-request endpoint, legal privacy text | No | Each is its own PR with its own approval |

---

## 7. Recommended order for Stage 2.5+

See the revised roadmap in `../slack-feedback-triage/PROVIDER_EXPERIENCE_IMPROVEMENT_PLAN.md` §20 ("Transcript-Based Provider Feedback Update"). The short version:

1. **Stage 2.5 — Provider trust and safety corrections.** T7 (period limits), T3 (REPSE 2026 → dynamic), T6 (XML stays-blocked doc), confirmation of T8 safety net.
2. **Stage 2.6 — Provider language simplification.** T9 (timeline copy), T8b (UI honesty), T5 (expand common_errors to 5 bullets).
3. **Stage 2.7 — Provider upload usability.** T2 (correction request mount), T4 (multi-file plan + scoped implementation).
4. **Stage 3 — Dashboard data-viz rework** as previously planned, now unblocked because Stage 2.5 fixed the trust foundation.
5. **Stages 4–6** unchanged from the prior plan.
6. **Stage 2.8 (parallel track) — Privacy notice + correction-request real endpoint.** Gated on legal/Paco/Beko sign-off.

---

## 8. Outstanding clarifications

1. **T1** — Paco / Beko / legal: please return the canonical privacy-notice wording for both provider activation and client-side authorization-to-share before Stage 2.8 begins.
2. **T6** — Jose Pablo: confirm "block XML" as the standing default; explicit go to revisit only when a specific requirement (SAT CFDI XML?) needs it.
3. **T4** — Jose Pablo: confirm the multi-file UX expectation. Does "contrato + anexos" arrive as one logical submission (1 Submission → N Documents) OR as separate submissions per file? Both are valid; the chosen shape changes the wizard design.
4. **T5** — Legal Shelf: optionally review the expanded rejection-cause copy for the 5 priority requirements before it ships.
5. **T8a (classifier)** — Jose Pablo: confirm whether the manual-vs-CFDI confusion warrants a dedicated track now, or stays in the strategic backlog until more telltale examples accumulate.

---

*End of transcript feedback map.*
