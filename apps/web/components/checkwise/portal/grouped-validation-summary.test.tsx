import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";

import type { ValidationSignal } from "@/components/checkwise/validation-summary";
import { GroupedValidationSummary } from "./grouped-validation-summary";

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

describe("GroupedValidationSummary", () => {
  it("renders three rows even when there are no signals", () => {
    render(<GroupedValidationSummary validations={[]} />);
    const list = screen.getByRole("list", {
      name: /estado de la revisión automática/i,
    });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(3);
  });

  it("shows the file-received headline when no file-rule signals escalate", () => {
    render(<GroupedValidationSummary validations={[]} />);
    expect(
      screen.getByText("Recibimos el archivo correctamente"),
    ).toBeInTheDocument();
  });

  it("escalates the file row to failure with the backend's message", () => {
    render(
      <GroupedValidationSummary
        validations={[
          signal("pdf_encrypted", {
            result: "fail",
            severity: "error",
            message: "El PDF está protegido con contraseña.",
          }),
        ]}
      />,
    );
    expect(
      screen.getByText("No pudimos procesar el archivo"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("El PDF está protegido con contraseña."),
    ).toBeInTheDocument();
  });

  it("flags the match row when the classifier reports a mismatch_reason", () => {
    render(
      <GroupedValidationSummary
        validations={[
          signal("requirement_match", {
            result: "warning",
            severity: "warning",
            message: "El documento parece ser una factura CFDI.",
            requires_human_review: true,
          }),
        ]}
      />,
    );
    expect(
      screen.getByText("Podría no coincidir con el requisito"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("El documento parece ser una factura CFDI."),
    ).toBeInTheDocument();
  });

  it("switches the next-step headline when human review is required", () => {
    render(
      <GroupedValidationSummary
        validations={[
          signal("human_review_required", {
            result: "required",
            requires_human_review: true,
          }),
        ]}
      />,
    );
    expect(
      screen.getByText("Un humano lo revisará y te avisamos"),
    ).toBeInTheDocument();
  });

  it("never leaks raw rule_codes as visible text", () => {
    render(
      <GroupedValidationSummary
        validations={[
          signal("pdf_magic_header", { result: "fail", severity: "error" }),
          signal("sha256_hash", { result: "warning", severity: "warning" }),
          signal("document_intelligence", {
            result: "warning",
            severity: "warning",
            message: "Lectura ambigua.",
          }),
        ]}
      />,
    );
    const list = screen.getByRole("list");
    const text = list.textContent ?? "";
    expect(text).not.toMatch(/pdf_magic_header|sha256_hash|document_intelligence/);
  });

  it("exposes data-state attributes for QA / styling hooks", () => {
    const { container } = render(
      <GroupedValidationSummary
        validations={[
          signal("pdf_encrypted", { result: "fail", severity: "error" }),
        ]}
      />,
    );
    const fileRow = container.querySelector('[data-group-id="file_received"]');
    expect(fileRow).not.toBeNull();
    expect(fileRow!.getAttribute("data-state")).toBe("failure");
  });
});
