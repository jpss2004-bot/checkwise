import { describe, expect, it } from "vitest";

import {
  BUCKET_LABELS_ES,
  DocumentStatus,
  SEMAPHORE_LABELS_ES,
  SlotState,
  SLOT_STATE_LABELS_ES,
  SLOT_STATE_VARIANT,
  semaphoreLabel,
  slotStateLabel,
  statusExplainer,
  statusLabel,
  statusVariant,
  STATUS_EXPLAINER_ES,
  STATUS_LABELS_ES,
  STATUS_VARIANT,
} from "./statuses";

const VALID_VARIANTS = [
  "success",
  "warning",
  "info",
  "destructive",
  "secondary",
] as const;

describe("statusLabel", () => {
  it("returns the Spanish label for every known status", () => {
    for (const code of Object.values(DocumentStatus)) {
      const label = statusLabel(code);
      expect(label).toBe(STATUS_LABELS_ES[code]);
      expect(label).not.toBe(code); // Spanish label is never the raw code
    }
  });

  it("reads both pre-human-review states as 'En revisión' (unification 2026-06-10)", () => {
    expect(statusLabel(DocumentStatus.PENDIENTE_REVISION)).toBe("En revisión");
    expect(statusLabel(DocumentStatus.PREVALIDADO)).toBe("En revisión");
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

describe("statusVariant", () => {
  it("maps every known status to a valid Badge variant (Audit F2)", () => {
    for (const code of Object.values(DocumentStatus)) {
      const variant = STATUS_VARIANT[code];
      expect(variant).toBeDefined();
      expect(VALID_VARIANTS).toContain(variant);
      expect(statusVariant(code)).toBe(variant);
    }
  });

  it("has no extra entries beyond the canonical status set", () => {
    expect(Object.keys(STATUS_VARIANT).sort()).toEqual(
      Object.values(DocumentStatus).sort(),
    );
  });

  it("treats resolved positives as success and no_aplica as neutral", () => {
    // Reconciled toward the dashboard's mapping (the call sites converged
    // here): excepcion_legal is a positive outcome, no_aplica is neutral.
    expect(statusVariant(DocumentStatus.APROBADO)).toBe("success");
    expect(statusVariant(DocumentStatus.EXCEPCION_LEGAL)).toBe("success");
    expect(statusVariant(DocumentStatus.NO_APLICA)).toBe("secondary");
  });

  it("falls back to secondary for an unknown status (matches the old per-page default)", () => {
    expect(statusVariant("future_status_not_yet_mirrored")).toBe("secondary");
  });
});

// ---------------------------------------------------------------------------
// Canonical-vocabulary unification (2026-06-10). These guard against the
// pre-unification drift where the same compliance concept was worded
// differently per screen. The invariant: a shared concept reads the SAME
// Spanish word across every axis (DocumentStatus / SlotState / bucket /
// semáforo). If a future edit re-introduces "Con observaciones",
// "Prevalidado", "Esperando revisión", "Verde", etc. for these concepts,
// one of these assertions fails.
// ---------------------------------------------------------------------------

describe("semáforo labels", () => {
  it("uses the ratified Al día / En proceso / En riesgo set", () => {
    expect(SEMAPHORE_LABELS_ES.green).toBe("Al día");
    expect(SEMAPHORE_LABELS_ES.yellow).toBe("En proceso");
    expect(SEMAPHORE_LABELS_ES.red).toBe("En riesgo");
    expect(semaphoreLabel("green")).toBe("Al día");
  });

  it("never falls back to raw color names", () => {
    for (const label of Object.values(SEMAPHORE_LABELS_ES)) {
      expect(["Verde", "Amarillo", "Rojo"]).not.toContain(label);
    }
  });
});

describe("slot-state labels", () => {
  it("maps every SlotState code to a non-raw Spanish label + valid variant", () => {
    for (const code of Object.values(SlotState)) {
      expect(slotStateLabel(code)).toBe(SLOT_STATE_LABELS_ES[code]);
      expect(slotStateLabel(code)).not.toBe(code);
      expect(VALID_VARIANTS).toContain(SLOT_STATE_VARIANT[code]);
    }
  });

  it("never re-introduces the pre-unification report wording", () => {
    const banned = ["Con observaciones", "Pendiente aclaración", "Revisar archivo"];
    for (const label of Object.values(SLOT_STATE_LABELS_ES)) {
      expect(banned).not.toContain(label);
    }
  });
});

describe("cross-axis wording consistency", () => {
  it("a rejected document reads 'Requiere corrección' on every axis", () => {
    expect(STATUS_LABELS_ES[DocumentStatus.RECHAZADO]).toBe("Requiere corrección");
    expect(SLOT_STATE_LABELS_ES[SlotState.REJECTED]).toBe("Requiere corrección");
  });

  it("an in-review document reads 'En revisión' on every axis", () => {
    expect(STATUS_LABELS_ES[DocumentStatus.PENDIENTE_REVISION]).toBe("En revisión");
    expect(SLOT_STATE_LABELS_ES[SlotState.IN_REVIEW]).toBe("En revisión");
    expect(BUCKET_LABELS_ES.pending_reviews).toBe("En revisión");
  });

  it("shared terminal states match across DocumentStatus and SlotState", () => {
    expect(SLOT_STATE_LABELS_ES[SlotState.APPROVED]).toBe(
      STATUS_LABELS_ES[DocumentStatus.APROBADO],
    );
    expect(SLOT_STATE_LABELS_ES[SlotState.EXPIRED]).toBe(
      STATUS_LABELS_ES[DocumentStatus.VENCIDO],
    );
    expect(SLOT_STATE_LABELS_ES[SlotState.NOT_APPLICABLE]).toBe(
      STATUS_LABELS_ES[DocumentStatus.NO_APLICA],
    );
    expect(SLOT_STATE_LABELS_ES[SlotState.EXCEPTION]).toBe(
      STATUS_LABELS_ES[DocumentStatus.EXCEPCION_LEGAL],
    );
  });
});
