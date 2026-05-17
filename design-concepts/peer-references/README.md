# `peer-references/` — Curated peer set for the 2.x visual rework

The 16 Pinterest inspos in `../inspo-screenshots/` skew consumer-SaaS, fintech, and marketing landings. They miss the registers most relevant to CheckWise. This folder fixes that gap with a curated peer set spanning **compliance** (Vanta, Drata, Secureframe), **premium-dense fintech operations** (Mercury, Ramp), and **terminal-grade productivity** (Linear, Stripe).

Each entry below names the product, the URL to verify the aesthetic, and the **specific signals** to translate into CheckWise's voice. Visit the URLs in a browser — the marketing pages carry product screenshots that are the actual references; this README is the curated lens to view them through.

## Compliance peers (closest to CheckWise)

### Vanta — https://www.vanta.com/product

The reference for "continuous compliance" surfaces. CheckWise is REPSE-specific where Vanta is SOC2/ISO/HIPAA, but the operational shape is identical: vendor + requirement + period → current obligation state.

**Signals to translate:**
- **Status density.** Vanta's compliance dashboard renders 40+ control rows per viewport with strong inline status pills, mono metadata, and a left-rail framework switcher. CheckWise's equivalent is 40+ vendor-requirement-period combinations.
- **Section dividers, not cards.** Vanta groups controls by framework using `border-t` dividers and a sticky section header, not card containers. This is `impeccable`'s anti-card-overuse rule executed correctly.
- **Inline pass/fail with monospace timestamps.** Every control row has its last-checked time in mono, right-aligned. CheckWise should do the same with `last_reviewed_at`.
- **Empty-state copy.** Vanta's empty states tell you exactly *what* will run *when* (e.g., "Drift check runs every 4 hours"). CheckWise's plain-Spanish equivalent: "Próxima revisión humana: jueves 22 de mayo, 10:00."

**Reject:** Vanta's marketing-page color treatment (purple/blue gradient hero, glass cards). Inside the product app is restrained — that's the reference, not the landing.

### Drata — https://drata.com/product

Mid-density compliance peer. Similar shape to Vanta. The difference worth noting:

**Signals to translate:**
- **"Trust Center" public-facing report layout.** Drata's external-facing report (https://drata.com/trust-center) is a long-form scrollable document with sections for security posture, certifications, controls. Closest visual analogue to what `/portal/reports` archetypes should look like in Phase 3: not a card grid, but a *document*.
- **Risk register row pattern.** Severity color + mono ID + short description + assignee + due date. CheckWise's reviewer queue should adopt this exact row composition.

### Secureframe — https://secureframe.com/platform

**Signals to translate:**
- **Framework-by-framework drill-down.** Click into a framework → see all its controls, status, evidence count, last update. CheckWise's `/admin/requirements` should drill the same way: institution → requirement → submissions.

## Premium-dense fintech operations

### Mercury — https://mercury.com/

The reference for the density target. Mercury's app UI sits at the exact density level we want for `/admin/*` and `/portal/reports`: every row carries 5-7 signals, mono is used for every number/timestamp/ID, surface chrome is minimal, and the only ornament is the brand mark.

**Signals to translate:**
- **Transaction row composition.** Date (mono) · counterparty · category · status pill · amount (mono, right-aligned, larger). CheckWise's equivalent for submission rows: period (mono) · institution · requirement · status pill · last-event timestamp.
- **Filter strip without chrome.** Mercury's filters live in a top strip with no card container — just text labels with dropdown indicators. CheckWise's `/admin/reviewer` filter row should drop its current pill chrome.
- **The right-rail detail panel.** When you click a transaction, a right-rail slides in showing full detail without leaving the list. CheckWise's submission/correction details should follow this pattern instead of dedicated detail routes.

**Reject:** Mercury's marketing site palette (cream + light navy + occasional yellow) is too consumer-warm. We want the *density and composition*, not the palette.

### Ramp — https://ramp.com/

Spend-management peer. Same density target.

**Signals to translate:**
- **Card spending dashboard composition.** A primary big-number widget (total spend) anchored top-left, then a right-side breakdown table, then a full-width category trend below. Asymmetric, varied widget weights — the opposite of an equal 4-up KPI grid. CheckWise's `/admin/dashboard` should adopt this composition.
- **Inline approvals UX.** Ramp shows each expense waiting for approval as a row with an inline "Approve / Reject / Request info" trio. CheckWise's reviewer queue today renders a button column with a single "Decidir" CTA — promote to inline trio.

## Terminal-grade productivity

### Linear — https://linear.app/method

The reference for keyboard-first, density-first product UI. Linear's table primitive is the gold standard.

**Signals to translate:**
- **Issue list composition.** Status icon · ID (mono) · title · assignee avatar · labels · priority · created (mono). CheckWise's `<DataTable>` should have the same column rhythm and the same `tabular-nums` mono treatment for IDs and timestamps.
- **Filter chips that don't shout.** Linear filters render as text + small icon, no border, no fill. Active filters get a subtle navy underline. CheckWise should drop its current pill-with-border filters in favor of this treatment.
- **Status pills as solid tints, not bordered chips.** Linear status is `bg-tint + text-color`, no border. We have `--doc-*-bg` / `--doc-*-text` / `--doc-*-border` triplets — flip the border to optional, default to no border, use the border tokens only when a status pill needs to live on a tinted background.

### Stripe Dashboard — https://stripe.com/

The reference for the reports / payment-flow surfaces.

**Signals to translate:**
- **Report cover layout.** Stripe's exported reports (statements, balance summaries) have a real document layout: header band with metadata, then a section spine of "Summary → Detail → Footnotes." Print-friendly. Phase 3 reports should follow this skeleton.
- **Inline mini-charts in tables.** Stripe shows 30-day sparklines inline in customer rows. CheckWise should do the same in vendor/client rows: 6-month compliance trend as a small inline sparkline.

## How to use this folder

1. **Phase 2 (Visual Direction Lock):** cite specific peer patterns by name in `VISUAL_DIRECTION_2_X.md`. Don't copy any one peer; pull the right signal from the right peer.
2. **Phase 3 (Reports):** Vanta + Drata Trust Center + Stripe Dashboard are the three references for report archetypes.
3. **Phase 4 (Hero + Marketing):** none of these — the inspo set is the right input for marketing.
4. **Phase 5 (Internal Polish):** Mercury + Ramp + Linear are the references for the dashboard polish pass.

Add screenshots here over time as we verify specific patterns. Keep the file size budget tight — these are reference points, not the asset library.
