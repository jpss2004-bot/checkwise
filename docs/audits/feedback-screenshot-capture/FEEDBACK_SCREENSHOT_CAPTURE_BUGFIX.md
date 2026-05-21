# Feedback screenshot capture — bugfix

**Status:** authored 2026-05-21.
**Tracked task:** task #12 in the current session log.
**Touched files:**
- `frontend/components/feedback/feedback-launcher.tsx`
- `frontend/components/ui/dialog.tsx`

---

## 1. Bug summary

When a user clicks the floating "Reportar" button (the global feedback launcher mounted in every authenticated shell plus the public landing page), the screenshot that ends up attached to the Slack message captures the feedback dialog overlay / content, not the page the user was looking at when they triggered the report.

For example: a provider on `/portal/calendar` who notices something off, clicks "Reportar", types up the bug and submits — and the screenshot in `#checkwise-feedback` shows the dialog itself, sometimes with the partially-faded backdrop bleeding over the original page. The route label in the Slack message (`Page: /portal/calendar`) and the screenshot disagree.

## 2. Affected routes / components

Every surface that mounts `<FeedbackLauncher />`:

- `/` (public landing — via `app/page.tsx`).
- `/portal/*` (all provider portal routes — via `PortalAppShell`).
- `/admin/*` (admin shell — via `AdminShell`).
- `/client/*` (client shell — via `ClientShell`).
- `/portal/reports/[id]/print` and the report editor (via `ReportEditor`).
- `/admin/reviewer/[submission_id]` (admin shell).

All routes inherit the same bug because the launcher component is shared.

## 3. Root cause

Three failures stacked.

**(a) Wrong capture timing.** The floating button only called `setOpen(true)` — it didn't capture anything. The screenshot was only triggered when the user later clicked "Capturar página" *inside* the open dialog. By then the dialog had already changed what the user was looking at.

**(b) `ignoreElements` couldn't reach the dialog portal.** The existing filter excluded only elements whose `dataset.feedbackLauncher === "true"`. The Dialog uses `@radix-ui/react-dialog`'s `Portal`, which renders its overlay and content into `document.body` as siblings of the launcher's wrapper `<div data-feedback-launcher="true">`. Those portal nodes did not carry the attribute, so `html2canvas` walked into them.

**(c) The 80ms close-then-snap delay raced the Radix exit animation.** `setOpen(false)` triggered `data-[state=closed]:animate-out fade-out-0 zoom-out-95 slide-out-*` on the overlay + content. Those animations take ~150–200ms to finish. After 80ms, html2canvas painted while the dialog was still visibly mid-fade in the DOM.

**(d) Stale route metadata.** `url` / `path` / `viewport` were read at submit time from live `window.location.*`. A navigation or viewport change between click and submit would silently desync the metadata from the screenshot the backend received.

## 4. Expected behavior

1. Click "Reportar" on `/portal/calendar`.
2. Screenshot of `/portal/calendar` (no dialog, no overlay) is captured immediately.
3. Original route metadata (`/portal/calendar`, full URL, viewport at click time) is locked.
4. Dialog opens with the screenshot pre-attached and the original-route metadata pinned for the eventual submit.
5. Slack message arrives carrying both the correct route label and a screenshot that shows that route.

## 5. Actual behavior before fix

1. Click "Reportar" on `/portal/calendar`.
2. Dialog opens immediately on top of `/portal/calendar`.
3. User clicks "Capturar página" inside the dialog.
4. Dialog closes (begins exit animation). After 80ms, html2canvas paints. The exit animation has not finished; the half-faded overlay + content sit in the screenshot.
5. Dialog re-opens. User submits. Slack receives a screenshot that shows the dialog UI, sometimes overlaid on a darkened version of the original page.

If the user never clicked "Capturar página" no screenshot was attached at all, and the only route metadata sent was whatever `window.location.*` happened to read at submit time.

## 6. Fix implemented

Two-file patch. No backend changes, no Slack config touched.

**`frontend/components/feedback/feedback-launcher.tsx`** — new primary capture path:

- New `originalContextRef = useRef<{ url, path, viewport, capturedAt } | null>(null)`.
- New `openWithCapture` callback wired to the floating button:
  1. Locks `window.location.href`, `pathname`, `${innerWidth}x${innerHeight}`, and `new Date().toISOString()` into `originalContextRef` **first** so a downstream crash can't lose them.
  2. Calls `html2canvas(document.documentElement, { ignoreElements: shouldIgnoreForScreenshot })` while the dialog is still unmounted.
  3. Converts to PNG blob, runs the same `attachBlob` PNG validation as the file/paste paths.
  4. Opens the dialog.
- Floating button now disables itself and shows `Capturando…` while the capture is in flight (`aria-busy`, `cursor-progress`, pulsing icon).
- `onSubmit` reads `url` / `path` / `viewport` from `originalContextRef.current` first, falling back to live `window.location.*` only if the ref is unexpectedly null (defensive — the primary path always populates it).
- `ContextStrip` (the "Se enviará: ruta X · viewport Y …" disclosure inside the dialog) now displays the locked path/viewport so the user sees what will actually be sent.
- `originalContextRef.current = null` on dialog close (either via submit success or `onOpenChange`) so the next click starts a fresh snapshot.
- Existing in-dialog "Capturar página" button kept as a re-capture path for users who want to scroll first or grab a different state. Its close-then-snap wait is bumped from 80ms → 280ms to outwait the Radix exit animation.
- `ignoreElements` factored into a reusable `shouldIgnoreForScreenshot` callback that excludes both `data-feedback-launcher="true"` (the launcher chip) AND `data-screenshot-exclude="true"` (the Dialog primitive — see below).

**`frontend/components/ui/dialog.tsx`** — generic opt-out attribute:

- `DialogOverlay` and `DialogPrimitive.Content` now render `data-screenshot-exclude="true"`. Radix renders both inside a portal attached to `document.body`, so consumers that filter by a wrapper class can't reach them; the attribute gives screenshot tools a single semantic selector to honor. Harmless on every other Dialog in the app.

## 7. Files changed

| File | Change |
|---|---|
| `frontend/components/feedback/feedback-launcher.tsx` | Primary capture-on-click path, locked route metadata, longer Radix-animation buffer for the recapture path, factored `shouldIgnoreForScreenshot` filter, capturing-state UI. |
| `frontend/components/ui/dialog.tsx` | Added `data-screenshot-exclude="true"` to `DialogOverlay` and `DialogContent`. |
| `docs/audits/feedback-screenshot-capture/FEEDBACK_SCREENSHOT_CAPTURE_BUGFIX.md` | This document. |

No other files touched. Backend unchanged. Slack config unchanged. No new dependencies.

## 8. Testing performed

### Automated

- `npx tsc --noEmit` (frontend) — clean (filtering pre-existing `.cw-next-*` stale-generated-type duplicate-identifier noise per handoff §7).
- `npx next lint --file components/feedback/feedback-launcher.tsx --file components/ui/dialog.tsx` — clean.
- `npm run build` — clean cold production build. No new warnings. No new errors.

### Backend (sanity, not touched)

Did not run the backend pytest suite because no backend file changed. The `/api/v1/feedback{,/public}` contract is unchanged — the launcher still posts the same multipart fields (`type`, `description`, `url`, `path`, `viewport`, `user_agent`, `console_logs`, optional `screenshot`).

### Manual QA — required

Visual verification of a screenshot capture requires an authenticated portal session and a Slack webhook (or at least the backend running with `SLACK_BOT_TOKEN` + `SLACK_FEEDBACK_CHANNEL_ID` unset so the launcher's `delivered=false` toast surfaces). The portal routes redirect anonymous visitors to `/login`, so a logged-in tester (jluna or admin) is needed to walk the flow. The manual checklist below captures what to verify.

#### Manual QA checklist

For each of `/portal/dashboard`, `/portal/upload`, `/portal/reports`, `/portal/calendar`, and one admin route (e.g. `/admin/reviewer/<id>`):

1. Navigate to the route while signed in.
2. Click the floating "Reportar" button.
3. Confirm: the button briefly shows the `Capturando…` label and the chat-bubble icon pulses.
4. Confirm: the dialog opens with a screenshot already attached in the "Captura adjunta" preview, sized ~ a few hundred KB.
5. Confirm: the "Se enviará: ruta X · viewport Y …" strip inside the dialog shows the correct route — the one you were on when you clicked, NOT the dialog's route.
6. Click the thumbnail to enlarge if needed. Confirm: the screenshot shows the route, NOT the dialog overlay or content.
7. Type a description (>= 10 chars). Submit.
8. Confirm in `#checkwise-feedback`: the Block Kit message lists the route you were on, the screenshot reply shows the same route (no dialog visible), and the timestamp matches the click time.

For the public landing path:

9. Open `/` in an incognito window (no admin JWT).
10. Repeat steps 2-8 above. The launcher's anonymous endpoint (`POST /api/v1/feedback/public`) should accept the submission and the screenshot should show `/`, not the dialog.

For the in-dialog recapture path:

11. After the dialog opens with the auto-captured screenshot, click "Capturar página" again. The dialog should close, the screenshot should re-snap (now after a scroll, or after dismissing an open menu, etc.), and the dialog should reopen with the new screenshot. The new screenshot should NOT contain the dialog.

If any of the above shows the dialog overlay or content, the bug has regressed.

## 9. Routes tested (static)

The diagnostic walk + static verification covered every route that mounts `<FeedbackLauncher />`:

- `/` (public landing) — capture-on-click path with anonymous endpoint.
- `/portal/dashboard`, `/portal/upload`, `/portal/reports`, `/portal/calendar`, `/portal/onboarding`, `/portal/entra-a-tu-espacio`, `/portal/submissions/[id]` — capture-on-click path with authenticated endpoint.
- `/admin/*` (via `_shell.tsx`).
- `/client/*` (via `_shell.tsx`).

All routes share the launcher, so the fix lands in one place and applies everywhere.

## 10. Screenshots / verification notes

Visual screenshots not captured in this session — the portal routes require a real session (handoff §7) and the verification is fundamentally about what a screenshot would contain, which needs the manual QA above. Static guarantees that hold without running the dev server:

- **Capture timing is now click-time, not dialog-internal.** The `openWithCapture` callback is the only thing the floating button's `onClick` invokes; the dialog is unmounted at that moment.
- **`html2canvas` excludes portal'd dialog nodes.** The Dialog primitive ships `data-screenshot-exclude="true"` on overlay + content; `shouldIgnoreForScreenshot` honors it.
- **Original route metadata is locked.** `originalContextRef.current` is set synchronously inside the click handler before any async work begins.
- **Submit reads from the ref.** `commonPayload.url` / `path` / `viewport` are derived from `originalContextRef.current` first.

## 11. Remaining risks

1. **The dev server is gated by login.** Visual confirmation of the fix needs a real session. Encourage jluna or admin to run the manual QA checklist before declaring the fix landed.
2. **`html2canvas` quirks on Safari / iOS.** The library has known limitations with CSS filters, `backdrop-filter`, and some `mask-image` properties. If a tested route uses any of those, the auto-captured screenshot may render imperfectly. The fix doesn't change what html2canvas can or can't render; it only changes when and what is excluded.
3. **`html2canvas` is ~50KB gzipped.** It was already a runtime dependency (lazy-loaded via dynamic `import()`); this fix doesn't add bundle weight. The dynamic import now fires on the very first feedback button click instead of on the in-dialog "Capturar página" click, which may add ~100-200ms to that first click. Subsequent clicks reuse the cached module.
4. **Capture errors degrade gracefully.** If html2canvas crashes (e.g. tainted canvas from a cross-origin image without CORS), the dialog still opens; the original route metadata is still locked; the user can paste or upload a PNG manually. They lose the auto-attach, not the ability to report.
5. **Recapture timing buffer (280ms) is empirically chosen.** If a future Dialog redesign lengthens the exit animation past 280ms, the recapture path could race again. Mitigation: the `data-screenshot-exclude` filter on the overlay + content is a hard floor even if the animation hasn't finished.

## 12. Follow-up recommendations

1. **Add a real frontend test runner** so the regression protection in §13 below can become automated rather than manual. The CheckWise frontend currently has no `*.test.*` framework. Bootstrapping one is out of scope for this bugfix.
2. **Telemetry on auto-capture failures.** Currently a failed capture only surfaces a toast. Logging a synthetic console error tagged `feedback:auto-capture-failed` would let us count incidents post-rollout.
3. **Reuse `shouldIgnoreForScreenshot` if more screenshot consumers appear.** If any future feature needs to grab a page screenshot, factor the predicate into `lib/feedback/screenshot.ts` (or similar) so the Dialog opt-out remains a single signal.
4. **Consider `OffscreenCanvas` / browser-native screenshot APIs** when broader support exists. `html2canvas` is a re-rasterization library; browser-native `Element.captureViewport()` (proposed) or a future `chrome://flags` API would be faster and more accurate. Not a today problem.

## 13. Manual regression protection checklist

Re-run the manual QA in §8 after any of the following:

- Any change to `frontend/components/feedback/feedback-launcher.tsx`.
- Any change to `frontend/components/ui/dialog.tsx` that touches the overlay / content rendering.
- Any upgrade of `html2canvas` or `@radix-ui/react-dialog`.
- Any redesign of the global app shells (`AdminShell`, `ClientShell`, `PortalAppShell`) that changes where the launcher mounts.

---

*End of feedback screenshot capture bugfix report.*
