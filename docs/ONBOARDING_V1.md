# Onboarding v1 — Implementation note

Companion to `docs/DESIGN_SYSTEM.md`. Documents what landed on the
`feat/onboarding-v1` branch.

## Goals

Build the **first version** of the provider/client onboarding journey:
landing → activation → identity → expediente gate → guided dashboard →
calendar. Use the design system's tokens, primitives, REPSE doc
states, AI/OCR confidence states, shimmer skeleton pattern, and the
`withPortalSession` HOC.

## Routes shipped

| Route | Purpose | Status |
| --- | --- | --- |
| `/` | Invitation-style entry — 2-col landing + access form card | ✅ Implemented |
| `/activate` | 3-step temp-credentials wizard (creds → password → identity) | ✅ Implemented (mock backend) |
| `/portal/onboarding` | Expediente inicial gate (8 requirements, REPSE states) | ✅ Implemented (mock backend) |
| `/portal/dashboard` | Locked-state alert + semaphore + suggested actions + calendar teaser | ✅ Implemented (mock backend) |
| `/portal/calendar` | Yearly institution × month grid + detail drawer | ✅ Implemented (mock backend) |

## Components added

### Primitive layer (`components/ui/`)

| Component | Replaces / Adds |
| --- | --- |
| `Field` | Composed Label + control + helper/error with auto-wired aria-* |
| `Skeleton` | Shimmer-pass loader (replaces Loader2 spinners) |
| `Spinner` | Inline spinner for button-loading + small in-flow loaders |
| `Alert` | Page-level banner: info / success / warning / error |
| `Progress` | Determinate bar with optional label + percentage |
| `Stepper` | Horizontal step indicator for multi-step wizards |
| `Button` | Rewrite — semantic tokens + `loading` prop + `link` variant + size scale |
| `Input` | Rewrite — semantic tokens + auto error styling via aria-invalid |
| `Badge` | Rewrite — 17 variants spanning brand/status/REPSE-states/AI-confidence |

### Brand layer (`components/checkwise/`)

| Component | Purpose |
| --- | --- |
| `DocStateBadge` | Single source of truth for 8 REPSE doc states + Spanish labels (`DOC_STATE_LABELS`) |
| `ConfidenceBadge` | AI/OCR confidence pill (high/medium/low/none) + `confidenceLevelFromPercent` helper |

### Portal layer (`components/checkwise/portal/`)

| Component | Purpose |
| --- | --- |
| `ExpedienteCard` | Single requirement card with institution chip, why/format/reviewer-note, adaptive CTA |
| `SemaphoreCard` | Compliance health hero (green/yellow/red tone) with progress + description |
| `SuggestedActions` | Priority-railed list of next-best actions with deadlines + state badges |

## Library modules added

| File | Purpose |
| --- | --- |
| `lib/types.ts` | `DocumentStateCode`, `ConfidenceLevel`, `ValidationResult`, `DocumentGroup`, `ActionPriority`, `SuggestedAction` |
| `lib/session/with-portal-session.tsx` | HOC that injects `session: PortalSession` after redirecting to `/` if absent |
| `lib/email-inference.ts` | `inferFromEmail()` + `evaluatePassword()` for the activation flow |
| `lib/mock/activation.ts` | **MOCK** verifyTempCredentials / setPassword / submitIdentity |
| `lib/mock/expediente.ts` | **MOCK** 8 expediente requirements + `countExpediente()` |
| `lib/mock/dashboard.ts` | **MOCK** DashboardSemaphore / SuggestedAction list / AttentionRow / DocStateCounts |
| `lib/mock/calendar.ts` | **MOCK** CalendarEvent array for 2026 (monthly SAT/IMSS + bimonthly INFONAVIT + four-monthly STPS + annual ISR) |

## Backend integration TODOs

Every mock module includes a `TODO[backend-integration]` block at the
top pointing at the endpoint that should replace it once the API
catches up. Search for that string to find them all.

| Mock module | Replaces | Future endpoint |
| --- | --- | --- |
| `lib/mock/activation.ts` | Full activation handshake | `POST /api/v1/activation/verify`, `POST /api/v1/activation/password`, `POST /api/v1/activation/identity` |
| `lib/mock/expediente.ts` | Onboarding requirement list with rich copy | `GET /api/v1/portal/onboarding` (currently returns only bare requirement names; needs `why` / `format` / `next_action` / `reviewer_note` / `required` fields) |
| `lib/mock/dashboard.ts` | Dashboard aggregates | `GET /api/v1/portal/dashboard` (new — needs `semaphore`, `suggested_actions`, `attention_today`, `doc_state_counts`) |
| `lib/mock/calendar.ts` | Calendar event list | `GET /api/v1/portal/calendar?year=2026` (already exists but needs `suggested_action` + `required_document` added per event) |

## What still depends on real auth / session / backend

- **Provider portal session** still uses opaque `X-Workspace-Token` from `lib/session/portal.ts` (localStorage). Real email/password auth is a backend roadmap item.
- **`/activate`** is fully mocked. The success flow writes a fake portal session into localStorage so the user can land on `/portal/onboarding`. The real wiring depends on the backend issuing a workspace alongside identity submission.
- **All status writes** in the new screens (upload, decision) currently no-op or simulate locally. The existing `/api/v1/submissions` POST still works for uploads via the wizard at `/portal/upload`.

## Design-system fidelity checklist

- [x] Primary color = navy `#013557`, accent = teal `#09c1b0` everywhere
- [x] Old `#1B6B59` not present anywhere
- [x] 3-layer token architecture in `globals.css` (primitive → semantic → component)
- [x] Geist + Geist Mono wired via `next/font`; body uses var(--font-geist-sans)
- [x] Phosphor icons exclusively (lucide-react uninstalled)
- [x] REPSE doc states (`pending` / `uploaded` / `in_review` / `approved` / `rejected` / `expired` / `needs_review` / `empty`) tokenized and used via `DocStateBadge`
- [x] AI/OCR confidence states (`high` / `medium` / `low` / `none`) tokenized; `ConfidenceBadge` primitive available
- [x] Shimmer skeleton pattern (`Skeleton` component) replaces `Loader2` on initial loads
- [x] `withPortalSession` HOC adopted on the 3 portal routes touched in this branch (`/portal/onboarding`, `/portal/dashboard`, `/portal/calendar`)
- [x] Navy-tinted shadow scale (xs / sm / md / lg / xl) in `tailwind.config.ts`
- [x] Border radius scale (sharp 4 / sm 6 / DEFAULT 8 / md 10 / lg 12 / xl 16 / 2xl 20 / full)
- [x] No hardcoded amber-*/red-*/emerald-* classes — all colors flow through semantic CSS variables

## Quality gate

- `tsc --noEmit` clean
- `next lint --quiet` clean
- `next build` clean (12 routes generated)
- Browser smoke test against the 5 new screens — landing, activation, onboarding gate, dashboard locked, calendar drawer — all render with zero console errors.

## Branch / next steps

Branch: `feat/onboarding-v1` off `cleanup/structural-pass`.
Stack: depends on the cleanup PR #2 (which depends on the V1.2–V1.4 merge in PR #1).

Suggested follow-ups (not in this branch):
1. **Real backend for activation.** Wire `/api/v1/activation/*` and delete `lib/mock/activation.ts`.
2. **Wizard split.** The 1,268-line `intake-wizard.tsx` is still a monolith. Split into step-per-file using the new Stepper primitive.
3. **AI metadata review panel.** `ConfidenceBadge` is wired but no consumer yet — first user is the upload result screen once OCR ships.
4. **Empty states for every list.** The dashboard's lists have data today but need explicit empty-state copy when the backend returns zero rows.
5. **Frontend tests.** Vitest + React Testing Library for the activation flow + ExpedienteCard rendering matrix (one test per DocumentStateCode).
