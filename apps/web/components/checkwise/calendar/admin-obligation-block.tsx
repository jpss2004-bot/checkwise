"use client";

import Link from "next/link";
import { ArrowRight } from "@phosphor-icons/react";

import { Badge } from "@/components/ui/badge";
import { INSTITUTION_LABELS } from "@/lib/api/portal";
import { statusLabel, statusVariant } from "@/lib/constants/statuses";
import type { AdminCalendarObligation } from "@/lib/api/admin";

import {
  INSTITUTION_ICON,
  RISK_LABEL,
  relativeDeadline,
  type CalendarRisk,
} from "./calendar-shared";

/**
 * One obligation in the admin calendar's detail panel. Admin-framed: it shows
 * the institution + period eyebrow, the requirement, an urgency/relative-due
 * label, the current status, and a single action that deep-links to the exact
 * remediation surface — the Bandeja (filtered by client/vendor/institution)
 * when there is review work, otherwise the vendor expediente. No upload/chase
 * framing — that's the client's job, not the operator's.
 */

const URGENCY_TONE: Record<string, string> = {
  overdue: "text-[color:var(--status-error-text)]",
  action_required: "text-[color:var(--status-error-text)]",
  due_soon: "text-[color:var(--status-warning-text)]",
  in_review: "text-[color:var(--status-info-text)]",
  upcoming: "text-[color:var(--text-secondary)]",
  on_track: "text-[color:var(--status-success-text)]",
};

function urgencyLabel(ob: AdminCalendarObligation, today: Date): string {
  if (
    ob.risk_level === "in_review" ||
    ob.risk_level === "on_track" ||
    ob.risk_level === "action_required"
  ) {
    return RISK_LABEL[ob.risk_level as CalendarRisk];
  }
  return relativeDeadline(ob.deadline_iso, today).split(" · ")[0];
}

function actionFor(ob: AdminCalendarObligation): { href: string; label: string } {
  if (ob.risk_level === "action_required" || ob.risk_level === "in_review") {
    const params = new URLSearchParams();
    if (ob.institution) params.set("institution", ob.institution);
    params.set("client_id", ob.client_id);
    params.set("vendor_id", ob.vendor_id);
    return { href: `/admin/reviewer?${params.toString()}`, label: "Ver en Bandeja" };
  }
  return { href: `/admin/vendors/${ob.vendor_id}`, label: "Ver proveedor" };
}

export function AdminObligationBlock({
  obligation,
  today,
}: {
  obligation: AdminCalendarObligation;
  today: Date;
}) {
  const InstitutionIcon = INSTITUTION_ICON[obligation.institution];
  const institutionLabel =
    INSTITUTION_LABELS[obligation.institution] ?? obligation.institution;
  const action = actionFor(obligation);

  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-3.5 py-2.5">
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
          {InstitutionIcon ? (
            <InstitutionIcon
              className="h-3 w-3 shrink-0 text-[color:var(--text-brand)]"
              weight="bold"
              aria-hidden="true"
            />
          ) : null}
          <span className="truncate">
            {institutionLabel} · {obligation.period_label}
          </span>
        </p>
        <p className="truncate text-[13px] font-medium text-[color:var(--text-primary)]">
          {obligation.requirement_name}
        </p>
      </div>

      <span
        className={
          "whitespace-nowrap text-[12px] font-medium " +
          (URGENCY_TONE[obligation.risk_level] ?? "text-[color:var(--text-secondary)]")
        }
      >
        {urgencyLabel(obligation, today)}
      </span>

      <Badge variant={statusVariant(obligation.status)}>
        {statusLabel(obligation.status)}
      </Badge>

      <Link
        href={action.href}
        className="inline-flex items-center gap-1 whitespace-nowrap text-[12px] font-medium text-[color:var(--text-link)] hover:underline"
      >
        {action.label}
        <ArrowRight className="h-3 w-3" weight="bold" aria-hidden="true" />
      </Link>
    </li>
  );
}
