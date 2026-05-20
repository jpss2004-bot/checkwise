import { Warning, CheckCircle, CircleDashed } from "@phosphor-icons/react";

import { Badge } from "@/components/ui/badge";
import { validationLabel } from "@/lib/constants/validation";

export type ValidationSignal = {
  rule_code: string;
  rule_type: string;
  result: string;
  severity: string;
  message: string;
  requires_human_review: boolean;
  confidence?: number | null;
};

/**
 * Map backend ``result`` enum to plain Spanish. The rule emits values
 * like "pass" / "fail" / "warning" / "pending" / "required" /
 * "not_required" — useful to engineers but opaque to providers.
 */
const RESULT_LABELS_ES: Record<string, string> = {
  pass: "OK",
  fail: "Falla",
  warning: "Revisar",
  pending: "Pendiente",
  required: "Requerido",
  not_required: "No requerido",
  info: "Información",
};

function resultLabel(result: string): string {
  return RESULT_LABELS_ES[result] ?? result;
}

/**
 * Stage 2.6 (BL-T8b, 2026-05-20) — UI honesty around possible
 * mismatches. The classifier writes a plain-Spanish
 * ``mismatch_reason`` to the ``requirement_match`` signal
 * ("El documento parece 'manual', pero el requisito sugiere 'cfdi'.").
 * Without a heading the message read like a status update; with
 * "Posible discrepancia detectada · No podemos confirmar que sea el
 * documento solicitado" the provider knows immediately that the
 * automatic check is asking for a second look. We do not overclaim
 * AI — the framing is intentionally humble ("posible", "parece") so
 * the rule-based classifier never reads as a definitive verdict.
 */
function isPossibleMismatch(signal: ValidationSignal): boolean {
  return (
    signal.rule_code === "requirement_match" &&
    signal.severity === "warning" &&
    signal.requires_human_review
  );
}

export function ValidationSummary({ validations }: { validations: ValidationSignal[] }) {
  return (
    <div className="space-y-3">
      {validations.map((validation) => {
        const Icon =
          validation.severity === "error"
            ? Warning
            : validation.severity === "warning"
              ? CircleDashed
              : CheckCircle;
        const mismatchHighlight = isPossibleMismatch(validation);
        // BL-003 (2026-05-20): the primary label is now the plain-
        // Spanish title from VALIDATION_RULE_LABELS_ES. The raw
        // ``rule_code`` lives in the title= attribute so QA / reviewers
        // can still match a UI row to a backend assertion without it
        // becoming the headline a non-technical provider has to parse.
        return (
          <div
            key={validation.rule_code}
            className={`rounded-md border bg-white p-3 ${
              mismatchHighlight
                ? "border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)]/30"
                : "border-border"
            }`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <Icon className="h-4 w-4 text-primary" aria-hidden="true" />
              <span
                className="text-sm font-medium"
                title={validation.rule_code}
              >
                {mismatchHighlight
                  ? "Posible discrepancia detectada"
                  : validationLabel(validation.rule_code)}
              </span>
              <Badge variant={validation.severity === "warning" ? "warning" : "secondary"}>
                {resultLabel(validation.result)}
              </Badge>
              {validation.requires_human_review ? <Badge variant="outline">Revisión humana</Badge> : null}
            </div>
            {mismatchHighlight ? (
              <p className="mt-2 text-sm font-medium text-[color:var(--status-warning-text)]">
                No podemos confirmar que sea el documento solicitado.
              </p>
            ) : null}
            <p className="mt-2 text-sm text-muted-foreground">{validation.message}</p>
          </div>
        );
      })}
    </div>
  );
}
