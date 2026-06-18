import { describe, expect, it } from "vitest";

import { matchesAnyField, normalizeForSearch } from "./normalize";

describe("normalizeForSearch", () => {
  it("folds case and strips Spanish diacritics", () => {
    expect(normalizeForSearch("González")).toBe("gonzalez");
    expect(normalizeForSearch("ANÁHUAC")).toBe("anahuac");
    expect(normalizeForSearch("  Peña  ")).toBe("pena");
    expect(normalizeForSearch("Über")).toBe("uber");
  });
});

describe("matchesAnyField", () => {
  it("is accent- and case-insensitive in both directions", () => {
    expect(matchesAnyField(["Corporativo Anáhuac"], "anahuac")).toBe(true);
    expect(matchesAnyField(["Corporativo Anahuac"], "anáhuac")).toBe(true);
    expect(matchesAnyField(["José Peña"], "PENA")).toBe(true);
  });

  it("matches each field independently — no cross-field false positives", () => {
    // "documento" must NOT match by spanning two separate fields.
    expect(matchesAnyField(["Proveedor SA", "Acta constitutiva"], "sa acta")).toBe(
      false,
    );
    expect(matchesAnyField(["Proveedor SA", "Acta constitutiva"], "acta")).toBe(
      true,
    );
  });

  it("empty query matches everything; null fields are skipped", () => {
    expect(matchesAnyField(["x"], "")).toBe(true);
    expect(matchesAnyField([null, undefined], "x")).toBe(false);
  });
});
