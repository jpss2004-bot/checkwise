import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import type {
  ShadowAnalysisPayload,
  ShadowAnalysisSignals,
  SubmissionDetail,
} from "@/lib/api/portal";
import { LecturaDelDocumento } from "./lectura-del-documento";

// ─────────────────────────────────────────────────────────────────────
// Detail-shape helpers
// ─────────────────────────────────────────────────────────────────────

function makeSignals(
  overrides: Partial<ShadowAnalysisSignals> = {},
): ShadowAnalysisSignals {
  return {
    detected_institution: "sat",
    detected_document_type: "csf",
    detected_rfcs: ["ABCD010203XYZ"],
    detected_dates: ["2026-05-01"],
    period_mentions: [],
    requirement_match_confidence: 0.92,
    mismatch_reason: null,
    ...overrides,
  };
}

function makeShadow(
  overrides: Partial<ShadowAnalysisPayload["shadow"]> = {},
): ShadowAnalysisPayload["shadow"] {
  return {
    provider_id: "anthropic:claude-sonnet-4-6",
    prompt_version: "csf_sat.v1",
    completed_at: "2026-06-02T18:15:00.000Z",
    latency_ms: 2500,
    error: null,
    confidence: 0.92,
    signals: makeSignals(),
    ...overrides,
  };
}

function makeDetail(
  overrides: Partial<SubmissionDetail> & {
    shadowSignalsOverride?: Partial<ShadowAnalysisSignals>;
    heuristicSignalsOverride?: Partial<ShadowAnalysisSignals>;
    shadowOverride?: Partial<ShadowAnalysisPayload["shadow"]>;
    documentOverride?: Partial<NonNullable<SubmissionDetail["document"]>>;
  } = {},
): SubmissionDetail {
  const {
    shadowSignalsOverride,
    heuristicSignalsOverride,
    shadowOverride,
    documentOverride,
    ...rest
  } = overrides;
  const heuristicSignals = makeSignals(heuristicSignalsOverride);
  const shadow = makeShadow({
    signals: shadowSignalsOverride
      ? makeSignals(shadowSignalsOverride)
      : heuristicSignals,
    ...shadowOverride,
  });
  return {
    submission_id: "sub-1",
    workspace_id: "ws-1",
    status: "pendiente_revision" as SubmissionDetail["status"],
    load_type: "mensual",
    submitted_at: "2026-06-02T18:00:00.000Z",
    comments: null,
    requirement: {
      code: null,
      name: "Constancia de Situación Fiscal",
      institution: "sat",
      load_type: "mensual",
      requirement_code: "REC-SAT-CSF-2026",
      requirement_version: 1,
    },
    period: { code: "2026-01", period_key: "2026-M01", period_type: "monthly" },
    document: {
      document_id: "doc-1",
      filename: "csf.pdf",
      sha256: "abc",
      size_bytes: 1024,
      page_count: 1,
      has_text: true,
      is_probably_scanned: false,
      detected_institution: "sat",
      detected_document_type: "csf",
      mismatch_reason: null,
      ...documentOverride,
    },
    reasons: [],
    events: [],
    history: [],
    previous_attempts: [],
    suggested_action: "wait_for_review",
    supersedes_submission_id: null,
    superseded_by_submission_id: null,
    reviewer_note: null,
    shadow_analysis: {
      heuristic: {
        provider_id: "heuristic:v1",
        completed_at: "2026-06-02T18:00:01.000Z",
        signals: heuristicSignals,
      },
      shadow,
    },
    ...rest,
  } as SubmissionDetail;
}

// ─────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────

describe("LecturaDelDocumento", () => {
  it("shows the positive verdict when AI is confident and there is no mismatch", () => {
    render(<LecturaDelDocumento detail={makeDetail()} />);
    expect(
      screen.getByText("Parece coincidir con el requisito esperado."),
    ).toBeInTheDocument();
  });

  it("renders the comprehension obligation verdict, reasoning and key facts", () => {
    const detail = makeDetail({
      shadowOverride: {
        comprehension: {
          purpose: "Opinión 32-D del proveedor.",
          key_facts: [{ label: "Sentido de la opinión", value: "Negativo" }],
          status_assessment: {
            validity: "valid",
            currency_ok: true,
            reasoning: null,
          },
          obligation_satisfaction: {
            verdict: "not_satisfied",
            confidence: 0.9,
            reasoning: "Una opinión negativa indica incumplimiento.",
          },
          discrepancies: [
            {
              issue: "Sentido negativo",
              severity: "high",
              evidence: "El documento indica 'Negativo'.",
            },
          ],
        },
      },
    });
    render(<LecturaDelDocumento detail={detail} />);
    expect(screen.getByText("No cumple la obligación")).toBeInTheDocument();
    expect(
      screen.getByText("Una opinión negativa indica incumplimiento."),
    ).toBeInTheDocument();
    expect(screen.getByText("Sentido de la opinión")).toBeInTheDocument();
    expect(screen.getByText("Negativo")).toBeInTheDocument();
    expect(screen.getByText("Sentido negativo")).toBeInTheDocument();
  });

  it("omits the comprehension section when the deep tier did not run", () => {
    render(<LecturaDelDocumento detail={makeDetail()} />);
    expect(
      screen.queryByLabelText("Comprensión del documento"),
    ).not.toBeInTheDocument();
  });

  it("shows the mismatch verdict with the AI's reason verbatim", () => {
    const detail = makeDetail({
      shadowSignalsOverride: {
        mismatch_reason:
          "El documento parece ser una factura CFDI, no una CSF.",
      },
    });
    render(<LecturaDelDocumento detail={detail} />);
    expect(
      screen.getByText(
        /Posible inconsistencia.+factura CFDI.+no una CSF/i,
      ),
    ).toBeInTheDocument();
  });

  it("warns on low AI confidence even when there is no mismatch reason", () => {
    const detail = makeDetail({
      shadowSignalsOverride: { requirement_match_confidence: 0.3 },
    });
    render(<LecturaDelDocumento detail={detail} />);
    expect(
      screen.getByText(/Confianza baja.+revisa el documento con cuidado/i),
    ).toBeInTheDocument();
  });

  it("shows the pending verdict when the shadow run hasn't finished", () => {
    const detail = makeDetail({
      shadowOverride: { completed_at: null, signals: null, error: null },
    });
    render(<LecturaDelDocumento detail={detail} />);
    expect(
      screen.getByText(/Procesando la lectura automática/i),
    ).toBeInTheDocument();
  });

  it("translates shadow error codes into one friendly Spanish sentence", () => {
    const detail = makeDetail({
      shadowOverride: { error: "timeout", signals: null },
    });
    render(<LecturaDelDocumento detail={detail} />);
    expect(
      screen.getByText("El análisis tardó más de lo esperado."),
    ).toBeInTheDocument();
  });

  it("renders the heuristic value as an inline second opinion on disagreement", () => {
    const detail = makeDetail({
      shadowSignalsOverride: { detected_document_type: "csf" },
      heuristicSignalsOverride: { detected_document_type: "factura_cfdi" },
    });
    render(<LecturaDelDocumento detail={detail} />);
    // The "Heurística:" disagreement chip surfaces the heuristic value.
    expect(screen.getByText(/Heurística:\s*factura_cfdi/i)).toBeInTheDocument();
  });

  it("renders confidence as '<n>% — <qualitative>' in the header chip", () => {
    const detail = makeDetail({
      shadowSignalsOverride: { requirement_match_confidence: 0.73 },
    });
    render(<LecturaDelDocumento detail={detail} />);
    expect(screen.getByText(/Confianza 73% — media/i)).toBeInTheDocument();
  });

  it("hides the card entirely when there is no inspection data at all", () => {
    const detail = makeDetail({
      reasons: [],
      shadow_analysis: undefined,
      documentOverride: { mismatch_reason: null },
    });
    const { container } = render(<LecturaDelDocumento detail={detail} />);
    expect(container.firstChild).toBeNull();
  });

  it("keeps technical details collapsed by default", () => {
    render(<LecturaDelDocumento detail={makeDetail()} />);
    // Provider id is engineer-facing metadata only inside the
    // "Datos técnicos" expandable — should not be visible until
    // the toggle is opened.
    expect(
      screen.queryByText("anthropic:claude-sonnet-4-6"),
    ).not.toBeInTheDocument();
  });
});
