import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * Source sweep guardrail (state-vocabulary unification, 2026-06-19).
 *
 * The canonical document/obligation state labels must come from the helpers
 * in lib/constants/statuses.ts (statusLabel / slotStateLabel / semaphoreLabel
 * / bucketLabel) or calendar-shared.ts (RISK_LABEL) — NEVER hardcoded on a
 * portal surface. If a new screen re-inlines one of these strings, this test
 * fails CI, so the "same concept, different word" drift this consolidation
 * removed cannot creep back. (ESLint would be the usual home for this, but the
 * local eslint-config-next toolchain can't run here; a test is the reliable,
 * CI-enforced equivalent.)
 */

const WEB_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

// Portal surfaces only — landing/marketing pages carry these words as prose.
const ROOTS = [
  "app/client",
  "app/portal",
  "app/admin",
  "app/platform",
  "app/reports",
  "components/checkwise",
];

// Canonical state labels that must be sourced from a helper.
const BANNED = [
  "En revisión",
  "Por entregar",
  "Requiere corrección",
  "Necesita aclaración",
  "Posible inconsistencia",
  "Aprobado con nota legal",
  "Por corregir",
  "En riesgo",
  "En proceso",
  "Al día",
  "Por vencer",
  "Faltantes",
  "Rechazado",
  "Excepción legal",
  "Excepción autorizada",
  "Por aclarar",
];

// Files allowed to contain the literal strings: the canonical dicts themselves,
// and the reviewer-ACTION vocabulary (a distinct axis: the verb a reviewer
// picks — "Excepción legal" — not the resulting document state).
const ALLOW = [
  "lib/constants/statuses.ts",
  "components/checkwise/calendar/calendar-shared.ts",
  "components/checkwise/calendar/client-calendar-shared.ts",
  "components/checkwise/doc-state-badge.tsx",
  "components/checkwise/portal/requirement-status-badge.tsx",
  "components/checkwise/admin/review-decision-panel.tsx",
];

function walk(dir: string, out: string[] = []): string[] {
  let entries: string[] = [];
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const entry of entries) {
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) {
      if (entry === "node_modules" || entry.startsWith(".")) continue;
      walk(p, out);
    } else if (/\.(ts|tsx)$/.test(entry) && !/\.test\.(ts|tsx)$/.test(entry)) {
      out.push(p);
    }
  }
  return out;
}

function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");
}

describe("no hardcoded state labels on portal surfaces", () => {
  const files = ROOTS.flatMap((r) => walk(join(WEB_ROOT, r))).filter(
    (f) => !ALLOW.some((a) => f.endsWith(a)),
  );

  it("scans a non-trivial number of portal files", () => {
    expect(files.length).toBeGreaterThan(50);
  });

  it("sources every canonical state label from a helper, never inline", () => {
    const offenders: string[] = [];
    for (const f of files) {
      const code = stripComments(readFileSync(f, "utf8"));
      for (const label of BANNED) {
        if (code.includes(`"${label}"`) || code.includes(`'${label}'`)) {
          offenders.push(`${f.replace(WEB_ROOT + "/", "")}: "${label}"`);
        }
      }
    }
    expect(
      offenders,
      `Hardcoded state labels found — import the canonical helper ` +
        `(statusLabel/slotStateLabel/semaphoreLabel/bucketLabel/RISK_LABEL) ` +
        `instead of the literal:\n${offenders.join("\n")}`,
    ).toEqual([]);
  });
});
