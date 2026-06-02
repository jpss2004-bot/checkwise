import { describe, expect, it } from "vitest";

import type { ValidationSignal } from "@/components/checkwise/validation-summary";
import {
  groupValidations,
  validationLabel,
} from "./validation";

function signal(
  rule_code: string,
  overrides: Partial<ValidationSignal> = {},
): ValidationSignal {
  return {
    rule_code,
    rule_type: "",
    result: "pass",
    severity: "info",
    message: "",
    requires_human_review: false,
    ...overrides,
  };
}

describe("groupValidations", () => {
  it("always returns three groups in a stable order", () => {
    const result = groupValidations([]);
    expect(result).toHaveLength(3);
    expect(result.map((g) => g.id)).toEqual([
      "file_received",
      "matches_requirement",
      "next_step",
    ]);
  });

  it("returns all-ok groups when no signals were emitted", () => {
    const [fileGroup, matchGroup, nextGroup] = groupValidations([]);
    expect(fileGroup.state).toBe("ok");
    expect(fileGroup.title).toBe("Recibimos el archivo correctamente");
    expect(matchGroup.state).toBe("ok");
    expect(matchGroup.title).toBe("Parece coincidir con lo que pediste");
    expect(nextGroup.state).toBe("ok");
    expect(nextGroup.detail).toBeNull();
  });

  it("rolls a file-failure into the first group with the signal's message as detail", () => {
    const [fileGroup] = groupValidations([
      signal("pdf_encrypted", {
        result: "fail",
        severity: "error",
        message: "El PDF está protegido con contraseña.",
      }),
    ]);
    expect(fileGroup.state).toBe("failure");
    expect(fileGroup.title).toBe("No pudimos procesar el archivo");
    expect(fileGroup.detail).toBe("El PDF está protegido con contraseña.");
  });

  it("escalates from ok to warning when a file-rule warns", () => {
    const [fileGroup] = groupValidations([
      signal("duplicate_hash", {
        result: "warning",
        severity: "warning",
        message: "Ya subiste este archivo antes.",
      }),
    ]);
    expect(fileGroup.state).toBe("warning");
    expect(fileGroup.title).toBe(
      "Recibimos el archivo, pero detectamos algo",
    );
  });

  it("flags the match group with mismatch reason text on a requirement_match warning", () => {
    const [, matchGroup] = groupValidations([
      signal("requirement_match", {
        result: "warning",
        severity: "warning",
        message: "El documento parece ser una factura CFDI.",
        requires_human_review: true,
      }),
    ]);
    expect(matchGroup.state).toBe("warning");
    expect(matchGroup.title).toBe("Podría no coincidir con el requisito");
    expect(matchGroup.detail).toBe(
      "El documento parece ser una factura CFDI.",
    );
  });

  it("uses the worst signal state when multiple file rules report", () => {
    const [fileGroup] = groupValidations([
      signal("file_exists", { result: "pass", severity: "info" }),
      signal("duplicate_hash", { result: "warning", severity: "warning" }),
      signal("pdf_encrypted", { result: "fail", severity: "error" }),
    ]);
    expect(fileGroup.state).toBe("failure");
  });

  it("switches the next-step headline when human review is required", () => {
    const [, , nextGroup] = groupValidations([
      signal("human_review_required", {
        result: "required",
        requires_human_review: true,
      }),
    ]);
    expect(nextGroup.title).toBe("Un humano lo revisará y te avisamos");
    expect(nextGroup.state).toBe("ok"); // informational, not a failure
  });

  it("does not bleed a file-rule signal into the match group (or vice versa)", () => {
    const [fileGroup, matchGroup] = groupValidations([
      signal("pdf_encrypted", { result: "fail", severity: "error" }),
    ]);
    expect(fileGroup.state).toBe("failure");
    expect(matchGroup.state).toBe("ok");
  });

  it("does not leak rule codes into the title", () => {
    const [fileGroup] = groupValidations([
      signal("pdf_magic_header", { result: "fail", severity: "error" }),
    ]);
    expect(fileGroup.title).not.toMatch(/pdf_|magic_/);
  });

  it("captures the underlying rule codes on the group for QA tooltips", () => {
    const [fileGroup] = groupValidations([
      signal("file_exists"),
      signal("pdf_magic_header"),
    ]);
    expect(fileGroup.ruleCodes).toContain("file_exists");
    expect(fileGroup.ruleCodes).toContain("pdf_magic_header");
  });
});

describe("validationLabel", () => {
  it("returns the Spanish label for known rule codes", () => {
    expect(validationLabel("file_exists")).toBe("Archivo recibido");
    expect(validationLabel("requirement_match")).toBe(
      "Coincide con el requisito",
    );
  });

  it("falls back to the raw code for unknown rules so QA spots drift", () => {
    expect(validationLabel("future_rule_added_to_backend")).toBe(
      "future_rule_added_to_backend",
    );
  });

  it("no longer renders 'Huella de integridad' (audit cleanup 2026-06-02)", () => {
    expect(validationLabel("sha256_hash")).not.toBe("Huella de integridad");
  });
});
