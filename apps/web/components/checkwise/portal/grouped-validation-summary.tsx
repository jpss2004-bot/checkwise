"use client";

import * as React from "react";
import {
  CheckCircle,
  CircleNotch,
  Warning,
  XCircle,
} from "@phosphor-icons/react";

import { track } from "@/lib/analytics";
import {
  type GroupedValidationOutcome,
  type GroupedValidationState,
  groupValidations,
} from "@/lib/constants/validation";
import type { ValidationSignal } from "@/components/checkwise/validation-summary";
import { cn } from "@/lib/utils";

/**
 * GroupedValidationSummary — provider-facing "did my upload work" view.
 *
 * Replaces the per-rule ``ValidationSummary`` on the upload wizard
 * confirmation step and on the portal submission detail page. Renders
 * exactly three rows so a non-technical provider can scan the outcome
 * in one glance:
 *
 *   ✓  Recibimos el archivo correctamente
 *   ⚠  Podría no coincidir con el requisito
 *      └─ Posible inconsistencia: el documento parece ser …
 *   ✓  Un humano lo revisará y te avisamos
 *
 * Detail / failure messages come from the backend ``message`` field on
 * the failing signal, so the text the provider sees is whatever the
 * classifier wrote in plain Spanish — never a rule_code or technical
 * identifier.
 *
 * The underlying per-rule signal list is exposed via a `data-rule-codes`
 * attribute on each row for support / debugging (inspector only), but is
 * never rendered as a visible label or tooltip.
 */

type IconComponent = React.ComponentType<{
  className?: string;
  weight?: "fill" | "regular" | "duotone";
  "aria-hidden"?: boolean | "true" | "false";
}>;

const ICON_FOR_STATE: Record<GroupedValidationState, IconComponent> = {
  ok: CheckCircle,
  warning: Warning,
  failure: XCircle,
  pending: CircleNotch,
};

const ICON_TONE_FOR_STATE: Record<GroupedValidationState, string> = {
  ok: "text-[color:var(--status-success-text)]",
  warning: "text-[color:var(--status-warning-text)]",
  failure: "text-[color:var(--status-error-text)]",
  pending: "text-[color:var(--text-tertiary)] animate-spin",
};

const BORDER_FOR_STATE: Record<GroupedValidationState, string> = {
  ok: "border-l-[color:var(--status-success-text)]",
  warning: "border-l-[color:var(--status-warning-text)]",
  failure: "border-l-[color:var(--status-error-text)]",
  pending: "border-l-[color:var(--border-subtle)]",
};

export function GroupedValidationSummary({
  validations,
  surface = "wizard",
}: {
  validations: ValidationSignal[];
  /** Identifies the calling page for analytics. */
  surface?: "wizard" | "detail";
}) {
  const groups = React.useMemo(() => groupValidations(validations), [validations]);

  React.useEffect(() => {
    track("prevalidation.summary.shown", {
      surface,
      file_state: groups[0].state,
      match_state: groups[1].state,
    });
    // Intentionally fires once per mount with the snapshot of states.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <ul
      className="space-y-2"
      aria-label="Estado de la revisión automática"
      role="list"
    >
      {groups.map((group) => (
        <GroupedRow key={group.id} group={group} />
      ))}
    </ul>
  );
}

function GroupedRow({ group }: { group: GroupedValidationOutcome }) {
  const Icon = ICON_FOR_STATE[group.state];
  const iconClass = ICON_TONE_FOR_STATE[group.state];
  const borderClass = BORDER_FOR_STATE[group.state];

  return (
    <li
      className={cn(
        "flex items-start gap-3 rounded-md border bg-[color:var(--surface-raised)] p-3 sm:p-4",
        "border-[color:var(--border-subtle)] border-l-2",
        borderClass,
      )}
      // QA affordance: the underlying rule_codes that folded into this
      // group are exposed only via a data attribute (inspector / support),
      // never as a visible tooltip — providers never see raw identifiers.
      data-rule-codes={group.ruleCodes.length ? group.ruleCodes.join(",") : undefined}
      data-group-id={group.id}
      data-state={group.state}
    >
      <Icon
        className={cn("mt-0.5 h-5 w-5 shrink-0", iconClass)}
        weight={group.state === "ok" ? "fill" : "regular"}
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-[color:var(--text-primary)] sm:text-base">
          {group.title}
        </p>
        {group.detail ? (
          <p className="mt-1 text-sm text-[color:var(--text-secondary)]">
            {group.detail}
          </p>
        ) : null}
      </div>
    </li>
  );
}

/**
 * Re-export so callers can use the same component for the
 * mismatch-only "what does the mismatch say" inline display, e.g. on
 * the reviewer-note card.
 */
export { GroupedRow as GroupedValidationRow };
