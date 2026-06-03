#!/usr/bin/env node
/**
 * P1.9 — Print-contract assertions.
 *
 * Zero-dep static check that guards the P1.8 print/PDF surface
 * against silent regression. Asserts directly on the source files;
 * does not need the dev server or a browser.
 *
 * If a contributor renames a CSS class, removes the `?autoprint=1`
 * handler, deletes a `data-block-type`, or drops the freshness seal,
 * this script fails before the change reaches CI.
 *
 * Run:  npm run check:print
 */

import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");

const PRINT_PAGE = "app/portal/reports/[id]/print/page.tsx";
const EDITOR = "components/checkwise/reports/editor/report-editor.tsx";
const FRESHNESS = "components/checkwise/reports/freshness-label.tsx";
const BLOCK_HEADER = "components/checkwise/reports/block-header.tsx";

// Each block file → the data-block-type its <section> wrapper MUST expose.
const BLOCK_CONTRACTS = [
  { file: "components/checkwise/reports/blocks/compliance-state.tsx", type: "compliance_state" },
  { file: "components/checkwise/reports/blocks/attention-list.tsx", type: "attention_list" },
  { file: "components/checkwise/reports/blocks/upcoming-deadlines.tsx", type: "upcoming_deadlines" },
  { file: "components/checkwise/reports/blocks/prioritized-actions.tsx", type: "prioritized_actions" },
  { file: "components/checkwise/reports/blocks/executive-summary.tsx", type: "executive_summary" },
  { file: "components/checkwise/reports/blocks/kpi-strip.tsx", type: "kpi_strip" },
  { file: "components/checkwise/reports/blocks/vendor-risk-matrix.tsx", type: "vendor_risk_matrix" },
  { file: "components/checkwise/reports/blocks/ai-recommendation.tsx", type: "ai_recommendation" },
];

let failures = 0;

function fail(file, msg) {
  failures += 1;
  console.error(`  ✗ ${file}: ${msg}`);
}

function pass(label) {
  console.log(`  ✓ ${label}`);
}

async function check(file, asserts) {
  const src = await readFile(join(ROOT, file), "utf8");
  for (const [label, needle] of asserts) {
    const ok = typeof needle === "string" ? src.includes(needle) : needle.test(src);
    if (ok) {
      pass(`${file} — ${label}`);
    } else {
      fail(file, `missing: ${label}`);
    }
  }
}

console.log("→ Print page contract");
await check(PRINT_PAGE, [
  ["screen toolbar wrapper", "cw-print-toolbar"],
  ["printed cover wrapper", "cw-print-cover"],
  ["printed footer wrapper", "cw-print-footer"],
  ["freshness seal element", "cw-print-seal"],
  ["?autoprint=1 query handler", /autoprint.*===.*['"]1['"]/],
  ["window.print invocation", /window\.print\(\)/],
  ["@page running header", "@top-left"],
  ["@page running footer w/ page counter", "counter(page)"],
  ["@page :first cover override", /@page\s*:first/],
  ["per-block-type page-break: executive_summary first", /data-block-type="executive_summary"\s*]\s*:first-of-type/],
  ["per-block-type page-break: prioritized_actions break-before", /data-block-type="prioritized_actions"\s*]\s*\{[^}]*page-break-before:\s*always/],
  ["per-block-type table row keep-together: vendor_risk_matrix", /data-block-type="vendor_risk_matrix"\s*]\s*tr/],
  ["per-block-type table row keep-together: upcoming_deadlines", /data-block-type="upcoming_deadlines"\s*]\s*tr/],
  ["freshness extractor helper", "firstFreshness"],
  ["'Datos al' seal fallback wording", "Datos al"],
  ["'Generado el' seal fallback wording", "Generado el"],
]);

console.log("\n→ Editor toolbar contract");
await check(EDITOR, [
  ["'Vista previa PDF' button label", "Vista previa PDF"],
  ["'Descargar PDF' button label", "Descargar PDF"],
  ["autoprint query on Descargar PDF link", "autoprint=1"],
  ["link opens in new tab", /target="_blank"/],
]);

console.log("\n→ FreshnessLabel contract");
await check(FRESHNESS, [
  ["refresh chip print:hidden", /print:hidden[\s\S]{0,400}aria-label="Actualizar con datos de hoy"|aria-label="Actualizar con datos de hoy"[\s\S]{0,400}print:hidden/],
  ["'Datos al' literal still rendered", "Datos al"],
]);

console.log("\n→ BlockHeader contract");
// Updated 2026-05-19 (visual audit F1+F6): the whole BlockHeader is now
// hidden in read-only/print mode via an early `if (!editable) return null;`.
// The old per-element `print:hidden` rules became unnecessary because the
// component never renders for print. The contract is therefore stronger:
// the source must contain the early-return guard, and the label span must
// still carry `print:hidden` as belt-and-braces for any future surface
// that mounts the editor in print context.
//
// Updated 2026-06-02 (reports redesign R3): the "softer labels" pass
// dropped the uppercase mono `cw-eyebrow` eyebrow in favour of a
// sentence-case sans label. The belt-and-braces `print:hidden` moved onto
// that new label span, so the assertion now ties `print:hidden` directly to
// the `{label}` render rather than to the retired `cw-eyebrow` class name.
await check(BLOCK_HEADER, [
  ["early-return when !editable", /if\s*\(\s*!editable\s*\)\s*return\s+null/],
  ["label belt-and-braces print:hidden", /print:hidden[^>]*>\s*\{label\}/],
]);

console.log("\n→ Block data-block-type contract");
for (const { file, type } of BLOCK_CONTRACTS) {
  const src = await readFile(join(ROOT, file), "utf8");
  if (src.includes(`data-block-type="${type}"`)) {
    pass(`${file} exposes data-block-type="${type}"`);
  } else {
    fail(file, `missing data-block-type="${type}" on block wrapper`);
  }
}

console.log();
if (failures > 0) {
  console.error(`✗ Print contract: ${failures} assertion(s) failed.`);
  process.exit(1);
} else {
  console.log("✓ Print contract: all assertions passed.");
}
