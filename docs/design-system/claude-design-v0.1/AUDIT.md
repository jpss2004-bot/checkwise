# Claude Design Package Audit

Audit date: 2026-05-15

Source downloads:

- `~/Downloads/CheckWise Design System.zip`
- `~/Downloads/CheckWise Design System (1).zip`
- `~/Downloads/CheckWise Design System (2).zip`
- `~/Downloads/CheckWise Design System (1).html`
- `~/Downloads/CheckWise Design System-print.html`

## Status

This folder contains the verified Claude Design artifacts currently available from the browser downloads. It is a useful reference package, but it is not the complete v0.1 editable source package because the HTML references CSS and JSX files that were not included in the downloads.

Do not paste the static HTML into the app. Treat the files here as source evidence for tokens, assets, visual direction, and phased implementation guidance.

## Present

Top level:

- `CheckWise Design System.html`
- `CheckWise Design System-print.html`
- `AUDIT.md`

Assets:

- `assets/checkwise-mark.svg`

Uploads:

- `uploads/CHECKWISE_1_5.md`
- `uploads/CHECKWISE_1_6.md`
- `uploads/CW sin fondo.png`
- `uploads/CheckWise Fon Blanco.jpg`
- `uploads/CheckWise IMPI.jpg`
- `uploads/CheckWise Powered by Legal Shelf.png`
- `uploads/DESIGN_SYSTEM.md`
- `uploads/HTML CheckWise.png`
- `uploads/f0709d587d46c1ae2b92072d4ffeb657.jpg`
- 15 design/inspiration screenshots from `2026-05-14`

v0.2 implementation scaffolding:

- `v0.2/INSTALL.md`
- `v0.2/README.md`
- `v0.2/app-layout.snippet.tsx`
- `v0.2/globals.css`
- `v0.2/tailwind.config.ts`
- `v0.2/lib/types.ts`
- `v0.2/lib/with-portal-session.tsx`

## Missing

The HTML files reference these files, but they were not present in the downloads:

- `tokens.css`
- `base.css`
- `primitives.css`
- `patterns.css`
- `icons.jsx`
- `foundations.jsx`
- `primitives.jsx`
- `pattern-dashboard.jsx`
- `pattern-upload-ocr.jsx`
- `pattern-onboarding-responsive.jsx`
- `app.jsx`

Because these files are missing, the v0.1 preview is not enough for full pattern extraction. Use `v0.2/` for token guidance and use existing CheckWise components as the implementation base.

## Current Repo Comparison

The live app already has a substantial token and component foundation:

- `apps/web/app/globals.css` already defines primitive, semantic, component, status, document-state, confidence, and motion tokens.
- `frontend/tailwind.config.ts` already maps shadcn-compatible aliases, brand aliases, radii, shadows, fonts, and motion easing.
- `apps/web/app/layout.tsx` already wires `GeistSans.variable` and `GeistMono.variable`.
- `apps/web/lib/types.ts` already centralizes several frontend domain types.
- `apps/web/lib/session/with-portal-session.tsx` is newer than the v0.2 snippet and includes cookie/JWT bootstrap behavior.

Important token gap found in the current app:

- `apps/web/app/globals.css` references `--blue-200` via `--doc-uploaded-border`, but `--blue-200` is not defined.

Important compatibility issue:

- v0.2 renames teal semantics from `--surface-teal-muted` / `--text-teal` toward AI-specific names like `--surface-ai-muted` / `--text-ai`.
- Existing app files still use `--surface-teal-muted`, `--text-teal`, `--brand-teal`, and `--interactive-secondary`.
- Do not remove those existing variables until components are migrated or aliases are added.

## Implementation Recommendation

Phase 0: Preserve source artifacts.

- Keep this folder as the immutable Claude Design reference package.
- Do not rely on `CheckWise Design System.html` as a runnable source until the missing CSS/JSX files are recovered.

Phase 1: Token hardening only.

- Fix the missing `--blue-200` token or point `--doc-uploaded-border` to `--blue-100`.
- Selectively merge v0.2 token ideas: density tokens, shadow variables, radius variables, AI-specific teal semantics, font-size scale, and semantic status Tailwind aliases.
- Keep backward-compatible aliases for current usages of `--surface-teal-muted` and `--text-teal`.

Phase 2: Primitive alignment.

- Update existing primitives in `apps/web/components/ui/` instead of creating parallel primitives.
- Review `Button.secondary`, `Badge.teal`, `Progress.teal`, `Alert`, `Field`, `Input`, and `Card` against the v0.2 token rules.
- Preserve current accessibility behavior and loading/error states.

Phase 3: Pattern alignment.

- Map visual patterns into existing CheckWise components:
  - dashboard patterns into `apps/web/app/portal/dashboard/page.tsx` and `apps/web/components/checkwise/portal/*`
  - upload/OCR patterns into `apps/web/components/checkwise/intake-wizard.tsx`
  - onboarding patterns into `apps/web/app/portal/onboarding/page.tsx`
- Do not paste static HTML or Babel JSX examples into the app.

## Next Claude Code Prompt

Audit and implement Phase 1 only from `docs/design-system/claude-design-v0.1/`.

Do not paste static HTML. Do not replace working app files wholesale.

Tasks:

1. Fix the current token gap where `--doc-uploaded-border` references undefined `--blue-200`.
2. Compare `v0.2/globals.css` and `v0.2/tailwind.config.ts` against the live `apps/web/app/globals.css` and `frontend/tailwind.config.ts`.
3. Selectively merge safe token improvements only: density tokens, radius/shadow CSS variables, AI-specific teal aliases, status color aliases, and typography scale.
4. Keep compatibility aliases for existing `--surface-teal-muted`, `--text-teal`, `--brand-teal`, and `--interactive-secondary` usages.
5. Do not replace `apps/web/lib/session/with-portal-session.tsx`; it is newer than the v0.2 snippet.
6. Run `npm run typecheck`, `npm run lint`, and `npm run build` from `frontend`.

Stop after Phase 1 and report the diff.
