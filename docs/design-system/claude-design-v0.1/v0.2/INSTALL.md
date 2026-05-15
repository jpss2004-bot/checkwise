# Phase 1 install

## 1. Install dependencies

```bash
cd frontend
npm install geist@^1.3.0 @phosphor-icons/react@^2.1.7
```

If `geist` is already in `package.json`, skip — but confirm it's `^1.3` (the namespaced font import shape changed between major versions).

## 2. Wire Geist in `app/layout.tsx`

See `app-layout.snippet.tsx` in this folder. The required edit is:

- Add `import { GeistSans } from 'geist/font/sans'`
- Add `import { GeistMono } from 'geist/font/mono'`
- Apply both variables to the `<html>` element: `className={\`${GeistSans.variable} ${GeistMono.variable}\`}`

## 3. Replace `app/globals.css`

Copy this folder's `globals.css` over the existing file. Do NOT merge — the existing file uses the wrong `--primary` and partial token coverage; full replacement is safer.

## 4. Update `tailwind.config.ts`

Open the existing `tailwind.config.ts`, locate `theme: { extend: { ... } }`, and replace the `extend` object with the one from this folder's `tailwind.config.ts`. Keep your existing `content` array and any plugins you've added.

## 5. Add the shared types

`lib/types.ts` is net-new. Create the file with the content from this folder.

## 6. Add the session HOC

`lib/with-portal-session.tsx` is net-new. Create the file. Phase 4 will migrate the four portal pages to use it, but it's safe to ship now.

## 7. Verify

```bash
npm run typecheck     # expect: clean
npm run lint          # expect: clean (warnings about hardcoded amber/red OK — Phase 2 fixes)
npm run build         # expect: clean
npm run dev
```

Open in browser:
- `/` — Geist font visible; primary CTA = navy
- `/login` — same
- `/activate?token=demo` — same
- `/portal/dashboard` — primary buttons navy, calendar still renders

## 8. Commit

```bash
git add -A
git commit -m "feat(ds): v0.2 phase 1 — token + typography hardening

- Switch --primary from #1B6B59 forest teal → #013557 brand navy
- Add three-tier token architecture (primitive → semantic → component)
- Add density tokens (--density-compact-*, --density-comfortable-*)
- Document teal-use rule at top of globals.css
- Install + wire Geist Sans + Geist Mono
- Add lib/types.ts (shared types)
- Add lib/with-portal-session.tsx (session-check HOC)

No component changes. No page changes. Phase 2 (primitive upgrade) next."
```

## 9. Stop here

Do not start Phase 2 in the same PR. Phase 1 is intentionally scoped to be revertable with a single revert commit if anything goes wrong.
