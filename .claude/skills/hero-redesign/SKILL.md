---
description: Redesign the public marketing hero on CheckWise's landing page (frontend/app/page.tsx). Activate when reworking the first viewport at /, the headline + subhead, the primary/secondary CTAs, the preview card or compliance illustration, the trust strip, and the section that has to convert a non-technical compliance buyer in 8 seconds. Not for inner product surfaces — those go to the real downloaded Taste skills and impeccable.
---

# CheckWise Hero Redesign

The landing page hero (`frontend/app/page.tsx`, the `<Hero />` and
`<HeroPreviewCard />` blocks plus the `<Header />` it sits beneath)
is the only marketing surface the product owns. This skill bounds
how it can change.

## What the hero is for

CheckWise is sold to a compliance buyer who already knows REPSE is a
cost centre and is shopping for relief. The hero must accomplish, in
order:

1. Confirm in one line that this is the REPSE product they want.
2. Show one believable proof element — a credible workspace state
   preview, not a photo.
3. Offer two paths: contact sales (`#contacto`) and log in (`/login`).
4. Earn a downward scroll into the feature grid.

It is **not**:

- A product tour.
- A general "what is compliance" explainer.
- A place to demo every feature.

If you find yourself adding a fourth CTA, you have lost the hero.

## Hard constraints

| | Rule |
|---|---|
| Headline | One sentence, ≤ 12 words. Spanish. Concrete benefit, not abstract value. |
| Subhead | One sentence, ≤ 24 words. Names the audience and the relief. |
| Primary CTA | Always `Solicitar información` → `#contacto`. Never two primaries. |
| Secondary CTA | Always `Iniciar sesión` → `/login`. Outline variant. |
| Preview | One card. Real workspace shape (header, status badge, progress, 3–4 row list). Use existing tokens — `--surface-raised`, `--border-default`, `--shadow-lg`. |
| Background | Two soft radial blobs in `--brand-navy` and `--brand-teal`, opacity ≤ 0.18. No third color. |
| Trust marker | A small "Plataforma de cumplimiento REPSE" badge with the Sparkle icon. Same pattern across the site. |
| Photography | None. Phosphor icons only. |
| Animation | One `cw-fade-up` on mount per major block. No loops. No parallax. |

## Required structure

The hero must keep this layout — only contents change:

```
<Header>           ← logo + nav anchors + Iniciar sesión + Solicitar
<Hero>
  <Badge>          ← brand promise tag
  <h1>             ← headline (the ≤12-word rule)
  <p>              ← subhead (the ≤24-word rule)
  <CTAs>           ← primary + secondary, in that order
  <FinePrint>      ← compliance disclosure, gray, 12px
  <HeroPreviewCard ← right side on lg, below on mobile />
```

If the redesign proposes removing the preview card, push back. The
card is the proof element that makes the headline credible.

## Authoring checklist

Before declaring a hero pass done:

- [ ] Headline ≤ 12 words, ends in a benefit verb or noun.
- [ ] Subhead ≤ 24 words, contains the words "REPSE" and either
      "proveedor" or "cliente".
- [ ] Both CTAs render side-by-side ≥ 768 px and stack ≤ 480 px.
- [ ] Preview card uses real component tokens (not custom hex).
- [ ] Badge uses the existing `Badge` component, `variant="teal"`.
- [ ] No "Coming soon" stickers anywhere in the hero.
- [ ] No more than one `cw-fade-up` per immediate child of `<Hero>`.
- [ ] Mobile: H1 stays under 36 lines on a 360-px-wide viewport.
- [ ] If the user is already logged in, the page redirects to
      `/portal/entra-a-tu-espacio` before the hero renders. This is
      handled in `useEffect` of `Home`; do not break it.

## Copy starter pool

Approved phrasings to draw from. Pick exactly one of each, never
combine.

**Headlines**
- "Cumplimiento documental REPSE guiado, trazable y accionable."
- "Tu expediente REPSE, ordenado y siempre al día."
- "Compliance REPSE sin spreadsheets ni correos perdidos."

**Subheads**
- "CheckWise ayuda a empresas y proveedores a gestionar documentos
  recurrentes, vencimientos, evidencia y reportes ejecutivos."
- "Ordenamos el alta REPSE, los acuses mensuales y la evidencia
  documental en un solo lugar — sin spreadsheets."

**Fine print**
- "CheckWise no firma documentos. La revisión humana sigue siendo
  obligatoria para el cumplimiento REPSE."

## How to deliver

1. Inspect `frontend/app/page.tsx` lines around `function Hero` and
   `function HeroPreviewCard`. Read both before suggesting anything.
2. Draft the change as a precise diff against the current file. Do
   not regenerate the whole page.
3. Reuse `BackgroundOrnaments`, `Badge`, `Button`, `Progress`,
   `DocStateBadge`, and the existing `cw-fade-up` class. New
   components only if the existing primitives genuinely cannot
   express the change — argue why before authoring.
4. Run `npm run typecheck && npm run build`.
5. Acknowledge that visual verification of the deployed hero
   requires Vercel + the real `NEXT_PUBLIC_API_BASE_URL`. Local
   preview can render the page, but the "already logged in" branch
   needs the live backend.

## Out of scope

- The header navigation order beyond rearranging existing anchors.
- Footer changes.
- Anything below the second viewport (those are separate
  `<HowItWorks>`, `<Features>`, `<ContactForm>` blocks).
- Adding a video, lottie, GIF, or background image.
- Adding analytics or marketing tags.
