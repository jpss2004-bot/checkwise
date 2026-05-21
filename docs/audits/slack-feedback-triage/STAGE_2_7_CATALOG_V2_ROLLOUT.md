# Catalog v2 — production rollout plan

**Status:** authored 2026-05-21 at end of Session 3.
**Companion docs:** [STAGE_2_7_SHIP_NOTES.md](./STAGE_2_7_SHIP_NOTES.md) · [HANDOFF_2026-05-20.md](./HANDOFF_2026-05-20.md).
**Owners:** Jose Pablo (product + decision authority), Render ops (backend env), Vercel ops (frontend env).

The catalog v2 work ships across three sessions:

- **Session 1** — Foundation: dataclass fields + `recurring_for_year_v2` generator. Backend only, no consumers.
- **Session 2** — Read path: slot resolver flag-aware, calendar/onboarding endpoints flag-aware, seed loads both catalogs, compatibility join.
- **Session 3** — Frontend: `?v2=1` URL signal, calendar drawer fans out into N stacked disclosures, intake wizard renders the alternatives radio picker, migration plan (this doc).

All of the above lives behind two feature flags that default off; production behavior is unchanged until ops flips them. This document is the playbook for flipping them safely.

---

## 1. The flags

| Flag | Layer | Effect when off (default) | Effect when on |
|---|---|---|---|
| `RECURRING_CATALOG_V2` | Backend env (Render) | `recurring_for_year` is authoritative. API emits ~139 calendar rows/year/persona. `accepts_documents` is `[]` on every item. | `recurring_for_year_v2` is authoritative. API emits ~34 calendar rows/year/persona. Each row carries `accepts_documents` (rich per-doc list) + `minimum_documents`. Slot resolver uses the compatibility-join branch. Calendar items' `href` includes `&v2=1`. |
| `NEXT_PUBLIC_MULTI_FILE_UPLOAD_ENABLED` | Frontend env (Vercel) | Wizard's annex picker hidden. Single-file path is the only one available. | Wizard shows the "Adjuntar archivos adicionales" block when **not** in alternatives mode. Auto-hidden when wizard is in v2 alternatives mode (peer-evidence semantics make the primary+annex framing unnecessary). |

There's no `NEXT_PUBLIC_RECURRING_CATALOG_V2` flag — the frontend reads the v2 signal from the calendar item's URL (`?v2=1` appended by the backend), so flipping the backend flag alone activates the v2 frontend UX. That's deliberate: it lets us canary the backend without coordinating a frontend redeploy.

---

## 2. Rollback guarantees

The v2 design assumes the flag can be flipped off at any time without data loss. The guarantees:

1. **Seed populates both code namespaces every run.** v1 codes (`REC-IMSS-2026-01-cuotas-obrero-patronales`) and v2 codes (`REC-IMSS-2026-01`) live in the `requirement` table side by side. `test_seed_populates_both_v1_and_v2_requirement_codes` pins this. Flipping the flag never touches the DB.

2. **Compatibility join in `build_workspace_calendar_slots`.** When v2 is on, the slot resolver matches candidates by `(institution_code, period_key)` — so a v1-coded submission still satisfies the v2 collapsed row sharing that (institution, period). Pinned by `test_legacy_v1_submission_satisfies_v2_slot_after_flag_flip` (mid-test flag flip, legacy submission shows as satisfied on the v2 calendar).

3. **`lookup_recurring_by_code` is permanent v1 fallback.** Even with the v2 flag on, v1 codes continue to resolve (`test_lookup_still_resolves_v1_codes_when_flag_on`). Audit-log entries, lineage references, and historical submission timelines keep working forever.

4. **Frontend graceful degradation.** With the backend flag off, every calendar item ships `accepts_documents: []` and no `v2=1` in `href`. The frontend's v2 branches all gate on `accepts_documents.length > 0` or `params.get("v2") === "1"`, so v1 behavior is byte-for-byte identical.

---

## 3. Pre-flip checklist (do all of this in staging first)

1. **Deploy `cbb36d6` (Session 2) + the Session 3 commit to staging.** Confirm green CI, ruff clean, 586+ backend pytest passing, frontend tsc/lint clean.

2. **Verify v1 mode is unchanged on staging.**
   - Calendar route returns ~139 items.
   - Wizard loads from a calendar row without showing the radio picker.
   - Submissions resolve cleanly.
   - `compliance_pct` math is identical to pre-deploy.

3. **Flip `RECURRING_CATALOG_V2=true` on the staging backend only.** No frontend env change.

4. **Verify v2 mode end-to-end on staging:**
   - `GET /api/v1/portal/workspaces/{id}/calendar` returns 34 items/year, each with a non-empty `accepts_documents` and `href` containing `v2=1`.
   - `GET /api/v1/compliance/calendar` returns the same 34-item shape (public catalog read).
   - `GET /api/v1/admin/calendar` shows the reduced expected totals per month.
   - Calendar drawer shows N stacked disclosures (one per accepted doc).
   - Wizard radio picker renders when opened from a v2 calendar row.
   - Submitting a CFDI via the wizard creates a Submission with `requirement_code="REC-IMSS-2026-01"` and `requirement_name="CFDI de pago de cuotas"`.
   - That submission satisfies the v2 calendar row immediately on reload.

5. **Verify legacy data survives:** seed a v1-coded submission (or use an existing one), then flip the flag and confirm it still shows on the v2 calendar via the compatibility join.

6. **Verify rollback:** flip the flag back to false. Confirm:
   - Calendar returns to 139 items.
   - The v2-coded submission written in step 4 above continues to exist in the DB but no longer surfaces on the v1 calendar (it has a v2 code which doesn't match any v1 row). Its submission detail page still loads via `/portal/submissions/{id}` because the lookup falls back through v1.
   - Other v1 submissions unchanged.

7. **Tester pass:** have jluna walk through a v2 upload + a calendar review. Confirm the alternatives picker copy reads correctly, the drawer N-stacked disclosures don't overwhelm, and the submission timeline shows the picked alternative.

---

## 4. Production flip sequence

Once steps 1-7 pass on staging:

1. **Render env (backend):** set `RECURRING_CATALOG_V2=true`. Trigger a redeploy if env reload doesn't pick up automatically. The Render dashboard env-var change typically causes a rolling restart.

2. **Smoke (≤ 2 minutes):**
   - Hit `GET /api/v1/compliance/calendar?year=2026` (no auth required). Expect 34 items.
   - Hit one provider workspace's `/calendar` endpoint with a known session. Expect 34 items, all with `accepts_documents` populated.

3. **Watch the audit log** for the first hour:
   - Look for `action="submission.created"` rows where `entity_id` has a `REC-IMSS-2026-XX` code (no per-doc suffix) — those are the first v2 submissions in prod.
   - Confirm none are returning 500 from the submission write path.

4. **Provider portal smoke** with jluna's prod session:
   - Open the calendar — see 34 obligations instead of 139.
   - Open the wizard from an IMSS January row — see the radio picker.
   - Submit a doc, confirm the calendar marks the slot satisfied on reload.

5. **No frontend env change required.** The frontend reads the v2 signal from the backend's URL output.

---

## 5. Rollback triggers + procedure

**Flip back to `RECURRING_CATALOG_V2=false`** if any of the following happen:

- 500s on the calendar endpoint sustained for > 60 seconds.
- Compliance % math regresses (a provider who was at 100% drops below 100% on the v2 view — would indicate the compatibility join is missing a slot).
- Reviewer/admin tooling can't find submissions by `requirement_code` (would indicate `lookup_recurring_by_code` is broken for one of the namespaces).
- jluna or another provider reports the radio picker is confusing or the alternative they need isn't listed.

**Rollback procedure:**

1. Render env: set `RECURRING_CATALOG_V2=false`. Render redeploys (~30s).
2. The frontend immediately stops receiving `v2=1` markers in calendar hrefs → wizard reverts to single-doc mode on next navigation.
3. The calendar reverts to 139 items per year.
4. **No DB action.** v2-coded submissions written during the flag-on window remain in the DB; they're queryable via `lookup_recurring_by_code` but won't appear on the v1 calendar (they reference a `requirement_code` that's not in the v1 catalog). After rollback, those submissions can be manually re-coded to a matching v1 code if desired — but they don't need to be for read paths to keep working.

The "no DB action" property is the key reason we chose the always-seed-both + compatibility-join strategy. A rollback is a 30-second env flip, not a database recovery.

---

## 6. Known gaps + follow-ups

| # | What | When to address |
|---|---|---|
| 1 | `minimum_documents="all"` matching is stubbed (no production v2 row uses `"all"` today). | Land alongside the first row that needs it so the per-doc coverage matcher is informed by a concrete example. |
| 2 | Sparse per-doc `_RECURRING_DOC_OVERRIDES` for SAT monthly's 5 alternatives — only 2 have rich overrides today; the other 3 fall back to institution defaults. | Content authoring follow-up. Not blocking. |
| 3 | Wizard alternatives picker shows the per-doc anatomy inline below each radio. For very long anatomy text this can crowd the step. | Iterate on visual density if user-testing flags it. |
| 4 | Calendar drawer with 5+ stacked disclosures (SAT monthly v2 row) is tall when all are expanded. | Consider switching to a tab pattern if testers complain. Defer until signal. |
| 5 | Frontend assumes the backend always sets `accepts_documents` on calendar items (`?? []` defensive default). True today but worth documenting in the API contract. | Add to the OpenAPI spec when one exists. |
| 6 | No analytics on flag-flip events. Operator has to read the Render env-var history manually. | Optional: emit an audit_log row when settings change at boot. |

---

## 7. Open questions

None at time of writing. If new ones surface during staging validation, add them here.

---

*End of catalog v2 rollout plan.*
