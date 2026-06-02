"use client";

import * as React from "react";
import {
  CheckCircle,
  CircleDashed,
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
 * The underlying per-rule signal list is available via the QA tooltip
 * on each row (title attribute) for support / debugging, but is never
 * the primary label.
 */

type IconComponent = React.ComponentType<{
  className?: string;
  weight?: "fill" | "regular" | "duotone";
  "aria-hidden"?: boolean | "true" | "false";
}>;

const ICON_FOR_STATE: Record<GroupedValidationState, IconComponent> = {
  ok: CheckCircle,
  warning: CircleDashed,
  failure: XCircle,
  pending: CircleNotch,
};

const ICON_TONE_FOR_STATE: Record<GroupedValidationState, string> = {
  ok: "text-[color:var(--status-success-text,#16a34a)]",
  warning: "text-[color:var(--status-warning-text,#d97706)]",
  failure: "text-[color:var(--status-error-text,#dc2626)]",
  pending: "text-[color:var(--text-tertiary)] animate-spin",
};

const BORDER_FOR_STATE: Record<GroupedValidationState, string> = {
  ok: "border-l-[color:var(--status-success-text,#16a34a)]",
  warning: "border-l-[color:var(--status-warning-text,#d97706)]",
  failure: "border-l-[color:var(--status-error-text,#dc2626)]",
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
    if (!groups.length) return;
    track("prevalidation.summary.shown", {
      surface,
      file_state: groups[0].state,
      match_state: groups[1].state,
    });
    // Intentionally fires once per mount with the snapshot of states.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (groups.length === 0) return null;

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
        "flex items-start gap-3 rounded-md border bg-[color:var(--surface-primary,#fff)] p-3 sm:p-4",
        "border-[color:var(--border-subtle)] border-l-2",
        borderClass,
      )}
      // QA tooltip: hover shows the underlying rule_codes that folded
      // into this group. Never visible by default — it's an off-screen
      // affordance for support, not a label.
      title={group.ruleCodes.length ? `Reglas: ${group.ruleCodes.join(", ")}` : undefined}
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
