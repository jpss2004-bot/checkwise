# CheckWise 1.5 — Implementation note

Companion to [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) and [ONBOARDING_V1.md](ONBOARDING_V1.md). Documents what landed on `feat/onboarding-v1` for the 1.5 product correction.

## Goals

Split the V1 invitation entry into a public **product** experience and a private **portal** experience, scaffold welcome-email activation, and start the **reports** surface that's the biggest CheckWise differentiator. Preserve everything from ONBOARDING_V1 — no working flow was broken.

## Route map

| Route | Visibility | Purpose | Status |
|---|---|---|---|
| `/` | Public | Marketing landing — hero, value prop, dual CTA, product preview, features, how-it-works, Legal Shelf block, contact form | ✅ Implemented (mock contact form) |
| `/login` | Public | Role selector (Provider / Cliente / Admin), access form, activation link | ✅ Implemented (admin = placeholder) |
| `/activate?token=…` | Public | Welcome-email-token activation — auto-skip credentials, role confirmation | ✅ Implemented (mock invitations) |
| `/activate` | Public | Manual temp-credential activation (legacy path preserved) | ✅ Implemented (mock activation) |
| `/portal/onboarding` | Authed | Expediente gate with mandatory/optional pills + 3-state hero (locked / provisional / approved) | ✅ Implemented (mock expediente) |
| `/portal/dashboard` | Authed | Semaphore + expediente summary + suggested actions + attention rows + state overview + calendar teaser | ✅ Implemented (mock dashboard) |
| `/portal/calendar` | Authed | Yearly REPSE grid + detail drawer | ✅ Implemented (unchanged from V1) |
| `/portal/reports` | Authed | 4 report types with metadata, status, ready/disabled CTAs + future roadmap | ✅ Scaffolded (mock reports) |
| `/portal/upload` | Authed | Wizard upload (unchanged from V1) | ✅ Implemented |
| `/portal/submissions/[id]` | Authed | Submission detail (unchanged from V1) | ✅ Implemented |
| `/admin/login` | Authed | Reviewer JWT login (existing) | ✅ Implemented |
| `/admin/reviewer` | Authed | Reviewer queue (existing) | ✅ Implemented |
| `/admin/reviewer/[id]` | Authed | Reviewer decision detail (existing) | ✅ Implemented |

## User journey map

```
                  ┌────────────────────────────┐
                  │ Public visitor              │
                  └──────────────┬─────────────┘
                                 ▼
                          ┌────────────┐
                          │  /         │  Public marketing
                          └─┬──────┬───┘
                            │      │
              Solicita info │      │ Iniciar sesión
                            ▼      ▼
                  ┌─────────────┐  ┌────────────────────┐
                  │ ContactForm │  │  /login            │
                  │ (mock)      │  │  (role selector)   │
                  └─────────────┘  └─────────┬──────────┘
                                             │
                              ┌──────────────┼───────────────────┐
                              ▼              ▼                   ▼
                       Proveedor /     Administrador        ¿Tienes credenciales
                       Cliente form    placeholder           temporales? link
                              │              │                   ▼
                              ▼              ▼              ┌──────────────┐
                       ProviderAccess   /admin/login        │ /activate    │
                              │         (reviewers)         └──┬───────────┘
                              ▼                                │
                                                               │
                                                               ▼
                                              token? → InvitationBanner +
                                                       skip credentials step
                                                               │
                                                               ▼
                                                       Password → Identity
                                                               │
                                              decidePostLoginRoute(expediente)
                                                               │
                              ┌────────────────────────────────┼──────────────────┐
                              ▼                                ▼                  ▼
              expediente_blocked                  provisional_access            none
                              │                                │                  │
                              ▼                                ▼                  ▼
                  /portal/onboarding              /portal/dashboard       /portal/dashboard
                  (LockedDashboardHero            (ProvisionalAccessBanner) (no banner)
                   on dashboard too)
```

## Routing logic — `lib/routing/post-login.ts`

`decidePostLoginRoute(requirements)` returns:

| Banner | Condition | Destination | UX |
|---|---|---|---|
| `expediente_blocked` | Any mandatory item in `pending / empty / rejected / expired / needs_review` | `/portal/onboarding` | LockedDashboardHero + ExpedienteCard sections |
| `provisional_access` | All mandatory items in `uploaded / in_review / approved` AND some still in_review | `/portal/dashboard` | ProvisionalAccessBanner + full dashboard |
| `none` | All mandatory items `approved` | `/portal/dashboard` | No banner, full dashboard |

Same helper drives:
- The onboarding gate hero variant
- The dashboard top banner

Optional items never block. The pill on each ExpedienteCard makes mandatory vs optional explicit.

## Welcome email activation flow

Today it's scaffolded only — no real provider wired.

```
Admin (future)  →  POST /api/v1/invitations          ← TODO[backend-integration]
                       (email, role, company_hint)
                          │
                          ▼
                   issueInvitation(payload)            ← lib/mock/invitations.ts
                          │
                          ▼
                   Invitation { token, expires_at, … }
                          │
                          ▼
                   renderWelcomeEmailHtml(ctx)         ← lib/email/welcome.ts
                   renderWelcomeEmailText(ctx)
                          │
                          ▼
                   Send via provider                   ← TODO (Resend / Postmark / SES)
                          │
                          ▼
            Recipient clicks https://app.checkwise.mx/activate?token=…
                          │
                          ▼
                   verifyToken(token)                   ← lib/mock/invitations.ts
                          │
                          ▼
                   InvitationBanner + auto-skip step 0
                          │
                          ▼
                   Password → Identity → consumeInvitation(token)
                          │
                          ▼
                          decidePostLoginRoute()
```

Demo: `/activate?token=demo` always resolves to the seeded `juan.perez@constructoraabc.com` provider invitation.

## Files changed / added in 1.5

### New files
- `app/login/page.tsx` — role selector + form + admin placeholder
- `app/portal/reports/page.tsx` — reports scaffold
- `components/marketing/contact-form.tsx` — landing contact form
- `lib/email/welcome.ts` — HTML + text email templates + subject helper
- `lib/mock/contact-requests.ts` — mock CRM submission
- `lib/mock/invitations.ts` — mock token issue/verify/consume
- `lib/mock/reports.ts` — 4 seed reports + type tables
- `lib/routing/post-login.ts` — central routing helper

### Rewritten / refactored
- `app/page.tsx` — now public marketing (was invitation entry)
- `app/activate/page.tsx` — adds token reader, InvitationBanner, role confirmation, no-back-from-token path
- `app/portal/onboarding/page.tsx` — wires routing helper, adds provisional-access hero variant
- `app/portal/dashboard/page.tsx` — wires routing helper, adds ProvisionalAccessBanner + ExpedienteSummaryCard
- `components/checkwise/portal/expediente-card.tsx` — Obligatorio/Opcional pill below the title
- `components/checkwise/portal/provider-access-form.tsx` — drops the duplicated inner header
- `components/checkwise/portal/provider-context-bar.tsx` — adds the 5-tab portal nav row

## Mock data modules

| Module | What it mocks | Replace with |
|---|---|---|
| `lib/mock/activation.ts` | Verify-creds + setPassword + submitIdentity | `POST /api/v1/activation/{verify,password,identity}` |
| `lib/mock/contact-requests.ts` | Landing "Solicitar información" submissions | `POST /api/v1/leads` or CRM/Slack webhook |
| `lib/mock/invitations.ts` | Token issue / verify / consume | Server-side equivalent + signed tokens |
| `lib/mock/expediente.ts` | 8 expediente requirements with REPSE states | `GET /api/v1/portal/onboarding` (enriched) |
| `lib/mock/dashboard.ts` | Semaphore + suggested actions + attention rows | `GET /api/v1/portal/dashboard` (new) |
| `lib/mock/calendar.ts` | Yearly calendar events | `GET /api/v1/portal/calendar` (enriched) |
| `lib/mock/reports.ts` | 4 seed report metadata records | 5 endpoints documented at the top of the file |

All mocks have a `TODO[backend-integration]` block at the top pointing at the target endpoint(s).

## Backend integration TODOs

Discoverable with:

```bash
rg 'TODO\[backend-integration\]' frontend/lib
```

Priorities:

1. **Activation API** — `lib/mock/activation.ts` + `lib/mock/invitations.ts`. The portal session today is opaque-token only; activation success drops a fake session into localStorage.
2. **Email provider** — wire `lib/email/welcome.ts` to a real transport (Resend / Postmark / SES) once invitations have a server-side issuer.
3. **Onboarding API enrichment** — backend already returns the bare list at `/api/v1/portal/onboarding`. Mock adds `why / format / next_action / reviewer_note / required`. Have the API return those.
4. **Dashboard aggregate** — new endpoint `/api/v1/portal/dashboard` returning the four mock subsets.
5. **Reports pipeline** — 5 endpoints listed at the top of `lib/mock/reports.ts`. Big lift, but unlocks the marketing-page differentiator.
6. **Contact form CRM** — `lib/mock/contact-requests.ts`.

## What still depends on real auth / session / backend

- Provider sessions are still opaque workspace tokens in `localStorage` (`lib/session/portal.ts`). Real password auth is V1.6+.
- `/activate` success fakes a portal session client-side. When auth lands, swap the writePortalSession + setTimeout for a real backend session bootstrap.
- The "Soy revisor interno" path on the Admin tab of `/login` routes to the existing `/admin/login` JWT flow. That path is untouched.
- The reports page has no real download or send-to-client — buttons disabled with helper copy pointing at V1.6.

## Reports — future plan

The mock seeds four representative reports. The brief is explicit that reports are a core differentiator. Plan:

1. **Generation pipeline** — `POST /api/v1/reports` triggers an async job. Status polls move `generating → ready` or `needs_review`.
2. **Template engine** — start with HTML→PDF (Playwright headless render). Templates live as React components.
3. **Aggregations** — pulls from `submissions`, `requirements`, `audit_log`, `validation_events`. Backend service that maps to the same ReportMeta shape.
4. **Distribution** — per-report "send to client" wired to the email provider (same one used for invitations).
5. **Scheduling** — monthly auto-generation closed at month-end + cuatrimestral closings for STPS.
6. **Comparativos** — month-vs-month and proveedor-vs-cartera.
7. **Embedded actions** — each report row links to the corresponding portal action.

## Quality gate

- `tsc --noEmit` clean
- `next lint --quiet` clean
- `next build` clean (14 routes generated)
- Browser smoke test against the 5 new/updated screens — public `/`, `/login`, `/activate?token=demo`, `/portal/onboarding` (gate locked + provisional), `/portal/dashboard` (with summary card), `/portal/reports` — all render with zero console errors

## Suggested follow-ups

1. **Wizard split** — `intake-wizard.tsx` is still 1,268 LOC. Use the Stepper primitive from V1.
2. **Frontend tests** — Vitest + RTL coverage for the routing helper, the activation token path, and the reports card rendering matrix.
3. **Real client view** — the role-selector currently shows Provider + Client share the same form. When the backend exposes `client_admin`, build the multi-vendor portfolio view at `/portal/clients`.
4. **Migrate ProviderContextBar to a layout** — the nav row should live in a `app/portal/layout.tsx` so it auto-applies to every authed route without each page passing `session`.
5. **Empty states for every list** — `/portal/reports` has 4 mock cards; needs an empty state if a real backend returns 0.
6. **Storybook / component sandbox** — the design system + brand badges now have enough primitives that a separate sandbox would speed up iteration.
