import { describe, expect, it } from "vitest";

import {
  DocumentStatus,
  statusExplainer,
  statusLabel,
  STATUS_EXPLAINER_ES,
  STATUS_LABELS_ES,
} from "./statuses";

describe("statusLabel", () => {
  it("returns the Spanish label for every known status", () => {
    for (const code of Object.values(DocumentStatus)) {
      const label = statusLabel(code);
      expect(label).toBe(STATUS_LABELS_ES[code]);
      expect(label).not.toBe(code); // Spanish label is never the raw code
    }
  });

  it("renames Prevalidado to the recibido-style label (vocabulary pass 2026-06-02)", () => {
    expect(statusLabel(DocumentStatus.PREVALIDADO)).toBe(
      "Recibido — esperando revisión",
    );
  });

  it("softens rechazado to 'Requiere corrección' (Audit P1-02)", () => {
    expect(statusLabel(DocumentStatus.RECHAZADO)).toBe("Requiere corrección");
  });

  it("renames excepcion_legal to 'Aprobado con nota legal'", () => {
    expect(statusLabel(DocumentStatus.EXCEPCION_LEGAL)).toBe(
      "Aprobado con nota legal",
    );
  });

  it("falls back to the raw code for unknown statuses so QA can spot drift", () => {
    expect(statusLabel("future_status_not_yet_mirrored")).toBe(
      "future_status_not_yet_mirrored",
    );
  });
});

describe("statusExplainer", () => {
  it("returns a one-line plain-Spanish explainer for every known status", () => {
    for (const code of Object.values(DocumentStatus)) {
      const explainer = statusExplainer(code);
      expect(explainer).toBe(STATUS_EXPLAINER_ES[code]);
      expect(explainer).not.toBeNull();
      expect(explainer!.length).toBeGreaterThan(0);
      // Explainers fit on a single line at mobile widths; cap is soft
      // but a runaway entry indicates a wording slip-up.
      expect(explainer!.length).toBeLessThanOrEqual(120);
    }
  });

  it("returns null for unknown statuses (lets the caller hide the line)", () => {
    expect(statusExplainer("future_status_not_yet_mirrored")).toBeNull();
  });

  it("frames rechazado as actionable (must mention what to do next)", () => {
    const text = statusExplainer(DocumentStatus.RECHAZADO);
    expect(text).toMatch(/sub(e|ir)|nuev[ao]|corre(gir|cci)/i);
  });
});
