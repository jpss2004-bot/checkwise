# Provider calendar — completed requirements not visible (bugfix)

**Status:** authored 2026-05-21.
**Source:** Jay Luna feedback screenshot — `/portal/calendar?year=2026` on a Persona Física workspace showing every filter chip at `0`, the table replaced by a "SIN OBLIGACIONES — No hay obligaciones para este año" empty state, despite the provider having uploaded documents.
**Affected route:** `/portal/calendar` (provider portal). Same root cause also affects `/portal/onboarding` (expediente) and the client/admin calendar surfaces for any workspace with the same legacy data.

---

## 1. Bug summary

A provider with a non-canonical `workspace.persona_type` value sees a completely empty `/portal/calendar`. The calendar's filter chips show `0` for every institution and the "Sin obligaciones" empty state renders, regardless of how many obligations exist in the catalog and how many submissions the provider has uploaded.

The provider's uploaded history is technically still in the database — it's the **catalog of obligations** (~139 rows / year per persona) that comes back empty, so there's no `(requirement, period)` grid for the slot resolver to project onto.

## 2. Current behavior (before fix)

Jay Luna's screenshot: blank grid, all chips at 0, "No hay obligaciones para este año." The provider cannot see:

- which requirements are completed
- which documents were uploaded
- which month each requirement belongs to
- which institution each requirement belongs to
- whether each item is approved, pending, rejected, or missing
- what still needs action

## 3. Expected behavior

The calendar must render a full 12-month × 4-institution grid populated with the provider's obligations regardless of any data-storage detail of `persona_type`. When obligations DO render, cells with uploads show full-opacity status badges so the provider's history is plain to see (already fixed in `8ab9514`).

When the grid genuinely cannot populate (data integrity issue, API failure, unknown persona_type), the surface must say so honestly — not pretend the user has no obligations.

## 4. Root cause

The recurring catalog generator filters rows strictly:

```python
def recurring_for_year(year: int, persona_type: PersonaType = "moral"):
    # ... build all rows ...
    return [r for r in result if persona_type in r.persona_types]
```

Every row's `persona_types` tuple is exactly `("moral", "fisica")` — the canonical tokens. So any other value passed in returns `[]`.

`workspace.persona_type` is `Mapped[str]` (no enum constraint at the DB layer). Legacy provisioning paths — CLI scripts, manual SQL, older admin endpoints — wrote full-label variants like `"persona_moral"` and `"persona_fisica"`. The frontend sidebar's display logic is `session.persona_type === "moral" ? "Persona Moral" : "Persona Física"` — *anything* that isn't strictly `"moral"` renders as "Persona Física," so the sidebar looked correct even though the underlying value was bad.

Result: the catalog returned `[]` silently, every endpoint that depends on it (`/portal/calendar`, `/portal/onboarding`, `/client/{id}/calendar`) emitted an empty payload, and the calendar's empty-state branch fired with "Sin obligaciones."

Variant sweep that confirmed the bug:

```
persona_type='moral'                   → 139 items
persona_type='fisica'                  → 139 items
persona_type='persona_moral'           → 0 items   ← Jay Luna's workspace
persona_type='persona_fisica'          → 0 items
persona_type='MORAL' / 'FISICA'        → 0 items
persona_type='' / None                 → 0 items
```

## 5. Fix implemented

**A) Defensive normalization at every catalog boundary.** New `normalize_persona_type(value)` helper in `backend/app/core/compliance_catalog.py` maps any reasonable variant (full-label, accented, case-different, short codes `"PM"`/`"PF"`) to the canonical token. Unknown values fall back to `"moral"` with a WARNING log — preferring a wrong-but-visible calendar to a silent empty one. Operators can grep the log for `compliance_catalog: unrecognized persona_type` to find bad rows.

Wired the normalizer into every catalog call site that reads from DB:

- `backend/app/services/evidence_slots.py` — both `build_workspace_onboarding_slots` and the v1 + v2 branches of `build_workspace_calendar_slots`.
- `backend/app/api/v1/portal.py` — `/portal/workspaces/{id}/onboarding` and `/portal/workspaces/{id}/calendar` endpoints.
- `backend/app/api/v1/client.py` — `list_client_calendar`.

The compliance.py / admin.py catalog endpoints take `persona_type` as a URL query parameter typed `Literal["moral", "fisica"]` — FastAPI enforces the contract at the boundary, so they don't need the normalizer.

**B) Truthful frontend empty state.** `frontend/app/portal/calendar/page.tsx` now has three distinct empty branches:

| Case | Trigger | UI |
|---|---|---|
| Unexpected | `totalCount === 0 && !loadError` | New `UnexpectedEmpty` — "No pudimos cargar tu calendario. Tu calendario debería mostrar tus obligaciones REPSE; algo no cuadra del lado nuestro. Recarga la página. Si sigues sin ver obligaciones, escríbenos a soporte@checkwise.mx para revisarlo." Warning-toned border. |
| Filtered | `filteredCount === 0 && filterInstitution !== "all"` | Existing `FilteredEmpty` — "No hay obligaciones para {institution}." with a "Quitar filtro" reset. |
| Normal | otherwise | The grid renders. |

The legacy "este año" copy collapsed (1) and (2) into the same message, which was the silent lie. Now the unexpected-empty case asks the user to flag it — which is what should have happened from day one.

## 6. Data-flow explanation

```
Browser /portal/calendar?year=2026
    │
    ├── GET /api/v1/portal/workspaces/{id}/calendar?year=2026
    │       │
    │       ├── current_portal_workspace dependency → ProviderWorkspace row
    │       │       (persona_type column, plain string, no DB constraint)
    │       │
    │       ├── build_workspace_calendar_slots(db, workspace, year)
    │       │       │
    │       │       ├── normalize_persona_type(workspace.persona_type)  ← NEW
    │       │       │       returns canonical "moral" / "fisica"
    │       │       │
    │       │       └── recurring_for_year(year, persona) → 139 rows
    │       │       └── slot lookup per submission row
    │       │       → list[SlotView]
    │       │
    │       └── recurring_for_year(year, normalize(persona)) → 139 rows  ← NEW
    │           emit list[items] per (month, institution)
    │       → CalendarPayload { months: [...] }
    │
    └── flattenCalendarPayload(payload)
            → CalendarEntry[] (139 entries pre-filter, 0 post-filter only for v2
              annual which sits in stps_repse and is filtered to that surface
              already)
            → Calendar grid renders
            → If 0 entries: UnexpectedEmpty (was Sin obligaciones)
```

## 7. Files changed

| Layer | File | Change |
|---|---|---|
| Backend (catalog) | `backend/app/core/compliance_catalog.py` | New `normalize_persona_type` helper + alias table; exported in `__all__`. |
| Backend (services) | `backend/app/services/evidence_slots.py` | Onboarding + v1 + v2 slot resolvers normalize before calling the catalog. |
| Backend (portal) | `backend/app/api/v1/portal.py` | `/onboarding` + `/calendar` endpoints normalize before calling the catalog. |
| Backend (client) | `backend/app/api/v1/client.py` | `list_client_calendar` normalizes. |
| Backend (tests) | `backend/tests/test_compliance.py` | 4 new tests pinning canonical/variant/unknown/end-to-end behavior. |
| Frontend (calendar) | `frontend/app/portal/calendar/page.tsx` | Three-branch empty state; new `UnexpectedEmpty` component. |
| Docs | `docs/audits/provider-calendar-completed-requirements/PROVIDER_CALENDAR_COMPLETED_REQUIREMENTS_BUGFIX.md` | This document. |

## 8. Test scenarios verified

### Backend pytest

- `tests/test_compliance.py::test_normalize_persona_type_handles_canonical_tokens` — `"moral"` / `"fisica"` pass through.
- `...handles_full_label_variants` — every variant in `_PERSONA_TYPE_ALIASES` maps correctly.
- `...falls_back_to_moral_for_unknown` — `None` / empty / garbage all return `"moral"` (and the WARNING fires).
- `...recurring_for_year_with_normalize_bridges_legacy_workspaces` — end-to-end: `recurring_for_year(2026, normalize_persona_type("persona_fisica"))` returns 139 items, identical to the canonical-input path; pins that the raw legacy value still returns 0 so the bug doesn't silently disappear if the catalog filter changes.

All 594 backend tests pass (was 590 — +4 new).

### Frontend
- `npx tsc --noEmit` — clean.
- `npx next lint --file app/portal/calendar/page.tsx` — clean.
- `npm run build` — clean cold build. `/portal/calendar` at 8.16 kB.

### Visual scenarios (require an authenticated session — manual QA)

For each, confirm the grid populates with all 12 months and 4 institutions:

1. Provider with `persona_type="moral"` — must still work (no regression).
2. Provider with `persona_type="fisica"` — must still work (no regression).
3. Provider with `persona_type="persona_moral"` — must now show full grid (was empty).
4. Provider with `persona_type="persona_fisica"` — must now show full grid (was empty).
5. Provider with `persona_type=""` or `None` — must now show full grid (defaults to moral).
6. Provider with all approved status — past months render full-opacity (already fixed in `8ab9514`).
7. Provider with mixed approved / pending / rejected — each cell shows correct status icon.
8. Provider with no uploads — all cells show pending state.
9. API failure (network drop) — `loadError` branch renders, no `UnexpectedEmpty`.
10. `filterInstitution !== "all"` with 0 items in that institution — `FilteredEmpty` with "Quitar filtro" reset (legitimate filtered zero).

## 9. Screenshots / auth blocker

Visual confirmation of the v2 / v1 calendar render requires an authenticated provider portal session. The fix is testable structurally via the backend pytest suite (covers scenarios 1-5 above against synthetic workspaces). Scenarios 6-10 need a real session; the existing handoff §7 captures the auth blocker.

When tested with `provision_test_provider.py` for both canonical persona_types + a manually-edited workspace row with `persona_type="persona_fisica"`, all three load the full grid.

## 10. Remaining limitations + risks

1. **Bad data still lives in the DB.** The normalizer maps `"persona_moral"` → `"moral"` at read time. The DB still carries the bad value, so other consumers of `workspace.persona_type` (analytics, audit, future endpoints that don't go through normalize) could still trip over it. Follow-up: schedule a one-off SQL migration to canonicalize the values (`UPDATE provider_workspaces SET persona_type = CASE persona_type WHEN 'persona_moral' THEN 'moral' WHEN 'persona_fisica' THEN 'fisica' ELSE persona_type END;`).
2. **Provisioning paths.** `backend/scripts/add_test_provider.py` and `backend/scripts/dev_seed.py` both accept arbitrary strings for `persona_type`. Adding a `Literal["moral", "fisica"]` validator at the CLI argparse level would prevent new bad rows. Out of scope for this bugfix but a sensible follow-up.
3. **The fallback is `"moral"`.** A workspace with a truly unrecognized value will see persona-moral obligations (~139 rows) instead of persona-fisica (which happens to also be 139 rows in the current catalog — they share the same set). If the catalog ever diverges by persona, the fallback will produce subtly wrong content. The WARNING log is the operational mitigation; routine grepping should catch it.
4. **Calendar empty state.** The new `UnexpectedEmpty` triggers on `totalCount === 0`. The normalizer fix means this should now be impossible in practice — but the branch is a defense-in-depth net so it never silently lies again.

## 11. Recommended follow-up work

- **One-shot SQL migration** to canonicalize `persona_type` values in the DB. Run during a low-traffic window; the migration is idempotent and the normalizer keeps working alongside it.
- **Add a CHECK constraint** to `provider_workspaces.persona_type` (and `vendors.persona_type`) once the migration completes: `CHECK (persona_type IN ('moral', 'fisica'))`. Prevents future bad rows at the DB layer.
- **CLI script validation:** add `choices=["moral", "fisica"]` to argparse on `add_test_provider.py` and any other script that accepts `--persona-type`.
- **Frontend: enrich the calendar with submission detail.** The current calendar shows status counts per cell. Drilling deeper into per-cell uploads (filename, upload date, reviewer comment) lives in the drawer today; consider surfacing more of it inline for compliant users so their history is even more obvious without clicking each cell.

---

## 12. `git status`

```
 M backend/app/api/v1/client.py
 M backend/app/api/v1/portal.py
 M backend/app/core/compliance_catalog.py
 M backend/app/services/evidence_slots.py
 M backend/tests/test_compliance.py
 M frontend/app/portal/calendar/page.tsx
?? docs/audits/provider-calendar-completed-requirements/
```

(plus the pre-existing unrelated working-tree changes the handoff §10 says are not mine to touch).

No commits. No pushes. Awaiting review.

---

*End of provider calendar completed-requirements bugfix report.*
