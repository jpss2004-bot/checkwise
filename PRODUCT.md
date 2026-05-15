---
name: CheckWise
register: product
---

# CheckWise Product Context

CheckWise is a REPSE/document compliance SaaS for Mexican enterprise legal-tech operations. It replaces spreadsheet, form, and manual review workflows with a controlled platform where provider evidence is uploaded, prevalidated, reviewed, audited, and reported.

## Users

- Providers: companies that must submit REPSE and related compliance evidence on time.
- Reviewers: Legal Shelf / CheckWise operators who validate documents and decide approval, rejection, clarification, or legal exception.
- Future clients/admins: teams that need portfolio-level compliance visibility across providers.

## Product Purpose

The product is not a generic upload database. It should feel like a guided compliance assistant and operational command system. The UI must make real compliance truth visible:

- authenticated workspace identity
- reviewer workflow state machine
- evidence slots
- replacement lineage
- current obligation state
- audit and validation timelines

## Strategic Principles

1. Architecture first, visual redesign second.
2. Backend truth beats visual invention.
3. Every surface should answer what is missing, risky, due, changed, owned, or next.
4. Providers need guidance, not technical noise.
5. Reviewers need traceability, speed, and decision quality.
6. Future dashboards, reports, and notifications must be powered by evidence slots, not mock cards.

## Voice

- Calm
- Precise
- Professional
- Spanish-first for user-facing compliance copy
- No hype, no vague SaaS promises
- Direct next-action language

## Anti-References

- Generic equal-card SaaS dashboards
- Static HTML pasted from design previews
- Decorative metrics without operational meaning
- Fake AI surfaces not backed by workflow state
- Upload forms that hide requirement/period context
- Visual redesign that bypasses tokens or backend contracts

## North Star

CheckWise should feel like a compliance cockpit built around this product object:

```text
workspace + requirement + period -> current obligation state
```

The eventual frontend redesign may change layouts, add routes, add visual components, add motion, and rethink navigation, but it must preserve auth boundaries, data contracts, auditability, and token discipline.
