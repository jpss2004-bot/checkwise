# CheckWise v0.2 · Phase 1 — Patch-ready files

These files implement **Phase 1 (Token + typography hardening)** from the v0.2 plan. They are written to live in the CheckWise Next.js repo at the paths shown below — copy them across in Claude Code.

## Map

| File in this folder | Destination in the Next.js repo | Action |
|---|---|---|
| `globals.css` | `frontend/app/globals.css` | **Replace** the existing file |
| `tailwind.config.ts` | `frontend/tailwind.config.ts` | **Merge** — keep your existing `content` array; replace `theme.extend` |
| `lib/types.ts` | `frontend/lib/types.ts` | **Create** (new file) |
| `lib/with-portal-session.tsx` | `frontend/lib/with-portal-session.tsx` | **Create** (new file) |
| `app-layout.snippet.tsx` | `frontend/app/layout.tsx` | **Merge** — apply the diff shown in that file |
| `INSTALL.md` | — | Read first; runs the deps install + wiring |

## Pre-flight checklist (run in Claude Code)

```bash
cd frontend
cat package.json | grep -E 'geist|phosphor-icons|tailwindcss'   # confirm state
git status                                                       # clean tree before edits
git checkout -b feat/design-system-v0.2-phase-1
```

## What this phase does

1. Switches the brand primary from forest teal `#1B6B59` → navy `#013557` at the **token layer**, so every component that uses `--primary` inherits the fix.
2. Adds the three-tier token architecture: primitive → semantic → component.
3. Adds **density tokens** (`--density-compact-*`, `--density-comfortable-*`) — net-new vs your v1.0 spec.
4. Adds the **teal-use rule** as a comment block at the top of `globals.css` so reviewers see it before they reach for teal.
5. Adds the **`Density`**, **`ConfidenceLevel`**, **`RequirementStatus`** types to `lib/types.ts` so primitives in Phase 2 have a shared vocabulary.
6. Replaces 4× session-check duplication with `withPortalSession` HOC.
7. Installs and wires Geist Sans + Geist Mono.

## What this phase deliberately does NOT do

- Touch any component (`components/**`). Components still consume `--primary` and inherit the navy automatically; visual regressions should be limited to color shifts.
- Replace `Badge`, `Input`, `Alert`. Those land in Phase 2.
- Touch any page. Pages still render — they'll just inherit the corrected tokens.
- Change Spanish copy or REPSE terminology — pure infra pass.

## Quality gate after applying

```bash
npm run typecheck
npm run lint
npm run build
npm run dev   # smoke 8 routes
```

Expected visible changes:
- Primary buttons / nav active states shift from forest teal → navy `#013557`.
- Body font becomes Geist (was Arial fallback).
- Cards / surfaces look slightly cooler (shadow tinted toward navy now).
- Anything that hardcoded `bg-amber-50 text-amber-700` etc still works — Phase 2 migrates those.

If anything breaks, the diff is small enough to bisect: revert `globals.css` first, then `tailwind.config.ts`, then `layout.tsx`.
