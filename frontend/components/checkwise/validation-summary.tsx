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
        // BL-003 (2026-05-20): the primary label is now the plain-
        // Spanish title from VALIDATION_RULE_LABELS_ES. The raw
        // ``rule_code`` lives in the title= attribute so QA / reviewers
        // can still match a UI row to a backend assertion without it
        // becoming the headline a non-technical provider has to parse.
        return (
          <div
            key={validation.rule_code}
            className="rounded-md border border-border bg-white p-3"
          >
            <div className="flex flex-wrap items-center gap-2">
              <Icon className="h-4 w-4 text-primary" aria-hidden="true" />
              <span
                className="text-sm font-medium"
                title={validation.rule_code}
              >
                {validationLabel(validation.rule_code)}
              </span>
              <Badge variant={validation.severity === "warning" ? "warning" : "secondary"}>
                {resultLabel(validation.result)}
              </Badge>
              {validation.requires_human_review ? <Badge variant="outline">Revisión humana</Badge> : null}
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{validation.message}</p>
          </div>
        );
      })}
    </div>
  );
}
