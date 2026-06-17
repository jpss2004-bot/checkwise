"use client";

import Link from "next/link";
import { ArrowRight, MapPin, Package, type Icon } from "@phosphor-icons/react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { INSTITUTION_LABELS } from "@/lib/api/portal";
import type { ClientCalendarItem } from "@/lib/api/client";
import { withReturnTo } from "@/lib/navigation/return-to";

import {
  INSTITUTION_ICON,
  focusForItem,
  formatLongDate,
  itemStatusDisplay,
  nextActionFor,
  relativeDeadline,
} from "./client-calendar-shared";

/**
 * One obligation, rendered roomy and self-explanatory: what document,
 * where to get it, how urgent, and the concrete next step, with inline
 * actions. Shared by the provider review cards and the calendar's
 * selected-day detail so the two surfaces stay identical.
 */
export function ObligationBlock({
  item,
  today,
  returnToHref,
}: {
  item: ClientCalendarItem;
  today: Date;
  returnToHref: string;
}) {
  const InstitutionIcon = INSTITUTION_ICON[item.institution];
  const institutionLabel =
    INSTITUTION_LABELS[item.institution] ?? item.institution;
  const statusDisplay = itemStatusDisplay(item);
  const overdue = item.risk_level === "overdue";

  const vendorHref = withReturnTo(
    `/client/vendors/${item.vendor_id}?focus=${focusForItem(item)}#documentos`,
    returnToHref,
  );
  const monthKey = `${item.deadline_iso.slice(0, 4)}-M${item.deadline_iso.slice(5, 7)}`;
  const auditHref = `/client/auditoria?period_from=${monthKey}&period_to=${monthKey}`;

  return (
    <li className="rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-3.5">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            {InstitutionIcon ? (
              <InstitutionIcon
                className="h-3.5 w-3.5 shrink-0 text-[color:var(--text-brand)]"
                weight="bold"
                aria-hidden="true"
              />
            ) : null}
            <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-secondary)]">
              {institutionLabel} · {item.period_label}
            </span>
          </div>
          <p className="mt-1 text-sm font-medium text-[color:var(--text-primary)]">
            {item.requirement_name}
          </p>
        </div>
        <Badge variant={statusDisplay.variant}>{statusDisplay.label}</Badge>
      </div>

      <dl className="mt-2.5 space-y-1.5 text-xs">
        <DetailLine
          label="Vence"
          value={`${relativeDeadline(item.deadline_iso, today)} (${formatLongDate(item.deadline_iso)})`}
          danger={overdue}
        />
        {item.where_to_obtain ? (
          <DetailLine
            icon={MapPin}
            label="Dónde se obtiene"
            value={item.where_to_obtain}
          />
        ) : null}
        <DetailLine label="Siguiente paso" value={nextActionFor(item)} emphasis />
      </dl>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button asChild size="sm" variant="outline">
          <Link href={vendorHref} title="Abrir el expediente del proveedor">
            {item.submission_id ? "Ver documento" : "Abrir expediente"}
            <ArrowRight className="h-3 w-3" weight="bold" aria-hidden="true" />
          </Link>
        </Button>
        <Button asChild size="sm" variant="ghost">
          <Link href={auditHref} title="Empaquetar este periodo para auditoría">
            <Package className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            Empaquetar
          </Link>
        </Button>
      </div>
    </li>
  );
}

function DetailLine({
  icon: IconComponent,
  label,
  value,
  danger,
  emphasis,
}: {
  icon?: Icon;
  label: string;
  value: string;
  danger?: boolean;
  emphasis?: boolean;
}) {
  return (
    <div className="flex gap-2">
      <dt className="flex w-32 shrink-0 items-center gap-1 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        {IconComponent ? (
          <IconComponent className="h-3 w-3" weight="bold" aria-hidden="true" />
        ) : null}
        {label}
      </dt>
      <dd
        className={
          "min-w-0 flex-1 " +
          (danger
            ? "font-medium text-[color:var(--status-error-text)]"
            : emphasis
              ? "font-medium text-[color:var(--text-primary)]"
              : "text-[color:var(--text-secondary)]")
        }
      >
        {value}
      </dd>
    </div>
  );
}
