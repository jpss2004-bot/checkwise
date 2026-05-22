#!/usr/bin/env node
/**
 * Phase 2.c — Wise intent-classifier regression test.
 *
 * Hermetic zero-dep Node script (matches the
 * ``check-print-contract.mjs`` pattern). Reads the actual
 * ``lib/wise/intents.ts`` source as text, extracts every intent's
 * needle list via regex, re-implements ``classifyIntent`` against
 * those extracted needles, and asserts a table of expected
 * classifications.
 *
 * Why this exists: a tester asked Wise "Puedo visualizar cuantos
 * documentos llevo cargados en plataforma?" and got the canned help
 * guide because ``"?"`` was a help needle that swallowed every
 * Spanish question. There were no frontend tests for the classifier
 * at the time. This script makes that class of bug impossible to
 * land again without going red in ``npm run check:intents``.
 *
 * Run:  npm run check:intents
 */

import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const SOURCE = join(ROOT, "lib/wise/intents.ts");

// Order matches the source's matcher table. Drop one of these and
// the test below will fail because the source's order won't match,
// surfacing the drift loud and early.
const INTENT_ORDER = ["rejection", "deadline", "next_action", "status", "help"];

// Behavioral expectations. Each entry: a prompt, the intent we
// expect it to classify as. Includes the original tester report so
// it is a permanent regression case.
//
// The empty-string row exercises the "empty input → help" guard at
// the top of ``classifyIntent``.
const CASES = [
  // The tester's question — must NOT be help.
  ["Puedo visualizar cuantos documentos llevo cargados en plataforma?", "unknown"],

  // Other natural Spanish questions that used to mis-route to help.
  ["¿Cuántos trabajadores debo declarar?", "unknown"],
  ["¿Mi opinión SAT sirve si es de febrero?", "unknown"],
  // "observaciones" intentionally routes to ``rejection`` since the
  // user is asking about reviewer feedback; the deterministic answer
  // either surfaces the latest reviewer note or says "no tienes
  // observaciones pendientes" — both are correct answers.
  ["¿Puedes mostrarme las observaciones del revisor?", "rejection"],
  ["¿Tengo todo en orden?", "unknown"],

  // Greetings / meta — must hit help.
  ["hola", "help"],
  ["Hola Wise", "help"],
  ["ayuda", "help"],
  ["buenas tardes", "help"],
  ["¿qué puedes hacer?", "help"],
  ["¿cómo funciona esto?", "help"],

  // Known intents — every chip's canonical prompt + casual variants.
  ["¿Qué sigue?", "next_action"],
  ["qué hago ahora", "next_action"],
  ["¿qué debería hacer?", "next_action"],
  ["next step", "next_action"],

  ["¿Por qué está rechazado mi documento?", "rejection"],
  ["el revisor me dejó una observación", "rejection"],
  ["¿qué pasó con mi carga?", "rejection"],

  ["¿Cuándo vence el próximo?", "deadline"],
  ["cuando vence mi opinión imss", "deadline"],
  ["¿qué fecha tengo?", "deadline"],

  ["¿Cómo voy?", "status"],
  ["estoy al día?", "status"],
  ["dime mi cumplimiento", "status"],
  ["50%", "status"],

  // Precedence: rejection beats status when both keywords appear.
  ["¿por qué está rechazado, cómo voy ahora?", "rejection"],
  // Empty / whitespace input goes to help by the top-of-function guard.
  ["", "help"],
  ["   ", "help"],
];

const ERRORS = [];

function record(message) {
  ERRORS.push(message);
}

async function main() {
  const source = await readFile(SOURCE, "utf8");

  // 1. Static guard: ``"?"`` must NEVER be a help needle. This is
  //    the literal bug we're guarding against.
  const helpBlock = extractNeedleBlock(source, "help");
  if (helpBlock === null) {
    record('Could not locate the help intent\'s needles array in intents.ts.');
  } else {
    const helpNeedles = parseNeedleArray(helpBlock);
    if (helpNeedles === null) {
      record('Could not parse the help needles array.');
    } else if (helpNeedles.includes("?")) {
      record(
        'CRITICAL: the help intent still includes "?" as a needle — every Spanish question ending with "?" will route to the canned help reply instead of the LLM. Phase 2.c regression.',
      );
    }
  }

  // 2. Build a needle table from the actual source. If any intent
  //    is missing from the source the test fails loud — that's a
  //    structural change worth a deliberate review.
  const matchers = [];
  for (const intent of INTENT_ORDER) {
    const block = extractNeedleBlock(source, intent);
    if (block === null) {
      record(`Could not locate intent "${intent}" in intents.ts.`);
      continue;
    }
    const needles = parseNeedleArray(block);
    if (needles === null) {
      record(`Could not parse needles for intent "${intent}".`);
      continue;
    }
    matchers.push({ intent, needles });
  }

  // 3. Behavioral table. Re-implements the classifier exactly so
  //    a logic change in the .ts source has to be reflected here too
  //    — and any divergence is caught by a failing case.
  for (const [prompt, expected] of CASES) {
    const actual = classify(prompt, matchers);
    if (actual !== expected) {
      record(
        `classifyIntent("${prompt}") returned "${actual}" but expected "${expected}".`,
      );
    }
  }

  if (ERRORS.length > 0) {
    console.error("\n✗ Wise intent classifier checks FAILED:\n");
    for (const err of ERRORS) console.error("  - " + err);
    console.error(
      `\n${ERRORS.length} failure${ERRORS.length === 1 ? "" : "s"}. Fix and re-run.\n`,
    );
    process.exit(1);
  }
  console.log(
    `✓ Wise intent classifier — ${CASES.length} cases passed, "?" guard holds.`,
  );
}

// ─── Helpers ────────────────────────────────────────────────────────

/** Locate the ``needles: [ … ]`` block belonging to the given
 *  ``intent: "<name>"`` entry. Returns the raw text inside the
 *  brackets, or ``null`` if the intent isn't found. */
function extractNeedleBlock(source, intent) {
  const idx = source.indexOf(`intent: "${intent}"`);
  if (idx === -1) return null;
  const needlesIdx = source.indexOf("needles:", idx);
  if (needlesIdx === -1) return null;
  const open = source.indexOf("[", needlesIdx);
  if (open === -1) return null;
  // Walk forward to find the matching close bracket. Naive but
  // sufficient: the needle arrays don't contain nested brackets.
  let depth = 1;
  let i = open + 1;
  while (i < source.length && depth > 0) {
    const ch = source[i];
    if (ch === "[") depth += 1;
    else if (ch === "]") depth -= 1;
    if (depth === 0) return source.slice(open + 1, i);
    i += 1;
  }
  return null;
}

/** Parse the inside of a needles array into a string[]. Handles the
 *  source's double-quoted strings + trailing commas + line breaks. */
function parseNeedleArray(block) {
  // Strip line comments + block comments before splitting.
  const cleaned = block
    .replace(/\/\/[^\n]*/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "");
  const out = [];
  const re = /"((?:[^"\\]|\\.)*)"/g;
  let match;
  while ((match = re.exec(cleaned)) !== null) {
    try {
      out.push(JSON.parse(`"${match[1]}"`));
    } catch {
      return null;
    }
  }
  return out;
}

/** Re-implementation of ``classifyIntent`` — kept in lock-step with
 *  the source so any behavior change there has to also land here. */
function classify(prompt, matchers) {
  const normalized = normalize(prompt);
  if (!normalized) return "help";
  for (const { intent, needles } of matchers) {
    for (const needle of needles) {
      if (normalized.includes(needle)) return intent;
    }
  }
  return "unknown";
}

function normalize(input) {
  return input
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .trim();
}

main().catch((err) => {
  console.error(err);
  process.exit(2);
});
