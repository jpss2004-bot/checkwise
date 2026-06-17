import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import type {
  ExpedienteAssessmentPayload,
  SubmissionDetail,
} from "@/lib/api/portal";
import { ExpedienteAssessmentCard } from "./expediente-assessment-card";

function detailWith(
  assessment: ExpedienteAssessmentPayload | null | undefined,
): SubmissionDetail {
  return { expediente_assessment: assessment } as SubmissionDetail;
}

function makeAssessment(
  overrides: Partial<ExpedienteAssessmentPayload> = {},
): ExpedienteAssessmentPayload {
  return {
    coherence: "minor_issues",
    summary_for_reviewer: "El expediente es mayormente coherente.",
    findings: [
      {
        code: "headcount_inconsistency",
        severity: "medium",
        detail_es: "El IMSS reporta 3 trabajadores; el contrato estima 12.",
        evidence: "IMSS: 3; contrato: 12.",
      },
    ],
    coverage_gaps: [
      {
        requirement_code: "REC-IMSS-PAGO",
        detail_es: "Falta el pago del IMSS del periodo.",
      },
    ],
    document_count: 4,
    provider_id: "anthropic:claude-sonnet-4-6",
    completed_at: "2026-06-16T12:00:00.000Z",
    ...overrides,
  };
}

describe("ExpedienteAssessmentCard", () => {
  it("renders nothing when there is no assessment", () => {
    const { container } = render(
      <ExpedienteAssessmentCard detail={detailWith(null)} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the coherence verdict, summary, findings and coverage gaps", () => {
    render(<ExpedienteAssessmentCard detail={detailWith(makeAssessment())} />);
    expect(screen.getByText("Inconsistencias menores")).toBeInTheDocument();
    expect(
      screen.getByText("El expediente es mayormente coherente."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("El IMSS reporta 3 trabajadores; el contrato estima 12."),
    ).toBeInTheDocument();
    expect(screen.getByText("Hallazgos")).toBeInTheDocument();
    expect(
      screen.getByText("Falta el pago del IMSS del periodo."),
    ).toBeInTheDocument();
    expect(screen.getByText("Obligaciones faltantes")).toBeInTheDocument();
  });

  it("shows the coherent state and omits empty sections", () => {
    render(
      <ExpedienteAssessmentCard
        detail={detailWith(
          makeAssessment({
            coherence: "coherent",
            findings: [],
            coverage_gaps: [],
          }),
        )}
      />,
    );
    expect(screen.getByText("Expediente coherente")).toBeInTheDocument();
    expect(screen.queryByText("Hallazgos")).not.toBeInTheDocument();
    expect(screen.queryByText("Obligaciones faltantes")).not.toBeInTheDocument();
  });
});
