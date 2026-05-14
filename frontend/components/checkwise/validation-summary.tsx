import { Warning, CheckCircle, CircleDashed } from "@phosphor-icons/react";

import { Badge } from "@/components/ui/badge";

export type ValidationSignal = {
  rule_code: string;
  rule_type: string;
  result: string;
  severity: string;
  message: string;
  requires_human_review: boolean;
  confidence?: number | null;
};

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
        return (
          <div key={validation.rule_code} className="rounded-md border border-border bg-white p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Icon className="h-4 w-4 text-primary" aria-hidden="true" />
              <span className="text-sm font-medium">{validation.rule_code}</span>
              <Badge variant={validation.severity === "warning" ? "warning" : "secondary"}>
                {validation.result}
              </Badge>
              {validation.requires_human_review ? <Badge variant="outline">revisión humana</Badge> : null}
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{validation.message}</p>
          </div>
        );
      })}
    </div>
  );
}
