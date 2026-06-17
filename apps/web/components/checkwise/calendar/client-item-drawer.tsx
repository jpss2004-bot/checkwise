"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CalendarBlank,
  Eye,
  Files,
  Package,
  Stamp,
  X,
  type Icon,
} from "@phosphor-icons/react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { VendorRef } from "@/components/checkwise/vendor-ref";
import { INSTITUTION_LABELS } from "@/lib/api/portal";
import type { ClientCalendarItem } from "@/lib/api/client";
import { withReturnTo } from "@/lib/navigation/return-to";

import {
  CLIENT_RISK_ORDER,
  INSTITUTION_ICON,
  RISK_ICON,
  RISK_LABEL,
  focusForItem,
  formatLongDate,
  itemStatusDisplay,
  relativeDeadline,
} from "./client-calendar-shared";

/**
 * Detail drawer for one obligation — the single "act on this" surface,
 * opened from an agenda row or a matrix cell. When a matrix cell carries
 * several obligations (e.g. four IMSS docs due the same month) the drawer
 * receives them all, shows the most severe, and lists the siblings so the
 * client can step through them without leaving.
 */
export function ClientItemDrawer({
  items,
  year,
  today,
  returnToHref,
  onClose,
}: {
  items: ClientCalendarItem[];
  year: number;
  today: Date;
  returnToHref: string;
  onClose: () => void;
}) {
  // Worst-first so the default selection is the obligation that matters most.
  const ordered = useMemo(
    () =>
      [...items].sort(
        (a, b) =>
          CLIENT_RISK_ORDER[a.risk_level ?? "on_track"] -
          CLIENT_RISK_ORDER[b.risk_level ?? "on_track"],
      ),
    [items],
  );
  const [selectedIdx, setSelectedIdx] = useState(0);
  const item = ordered[Math.min(selectedIdx, ordered.length - 1)];

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!item) return null;

  const InstitutionIcon = INSTITUTION_ICON[item.institution];
  const institutionLabel =
    INSTITUTION_LABELS[item.institution] ?? item.institution;
  const statusDisplay = itemStatusDisplay(item);
  const risk = item.risk_level ?? "on_track";
  const RiskIcon = RISK_ICON[risk];
  const overdue = risk === "overdue";

  const vendorHref = withReturnTo(
    `/client/vendors/${item.vendor_id}?focus=${focusForItem(item)}#documentos`,
    returnToHref,
  );
  const monthKey = `${year}-M${item.deadline_iso.slice(5, 7)}`;
  const auditHref = `/client/auditoria?period_from=${monthKey}&period_to=${monthKey}`;
  const primaryLabel = item.submission_id
    ? "Ver documento en el expediente"
    : "Abrir expediente del proveedor";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="client-drawer-title"
      className="fixed inset-0 z-40"
    >
      <button
        type="button"
        className="absolute inset-0 bg-[color:var(--gray-950)]/40 backdrop-blur-sm"
        onClick={onClose}
        aria-label="Cerrar"
      />
      <aside
        className="absolute right-0 top-0 h-full w-full max-w-md overflow-y-auto border-l border-[color:var(--border-default)] bg-[color:var(--surface-overlay)] shadow-xl cw-fade-up"
        style={{ animationDuration: "300ms" }}
      >
        <header className="sticky top-0 flex items-start justify-between gap-3 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-overlay)] px-6 py-4">
          <div className="min-w-0">
            <p className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              {InstitutionIcon ? (
                <InstitutionIcon
                  className="h-3 w-3 text-[color:var(--text-brand)]"
                  weight="bold"
                  aria-hidden="true"
                />
              ) : null}
              {institutionLabel} · {item.period_label}
            </p>
            <h2
              id="client-drawer-title"
              className="mt-1 text-lg font-semibold text-[color:var(--text-primary)]"
            >
              {item.requirement_name}
            </h2>
            <div className="mt-1">
              <VendorRef
                vendorId={item.vendor_id}
                vendorName={item.vendor_name}
              />
            </div>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onClose}
            aria-label="Cerrar detalle"
          >
            <X className="h-5 w-5" weight="bold" aria-hidden="true" />
          </Button>
        </header>

        <div className="space-y-5 px-6 py-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={statusDisplay.variant}>{statusDisplay.label}</Badge>
            <span
              className={
                "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium " +
                (overdue
                  ? "border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)]"
                  : "border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] text-[color:var(--text-secondary)]")
              }
            >
              <RiskIcon className="h-3 w-3" weight="bold" aria-hidden="true" />
              {RISK_LABEL[risk]}
            </span>
          </div>

          <DetailRow
            icon={CalendarBlank}
            label="Vence"
            value={`${relativeDeadline(item.deadline_iso, today)} (${formatLongDate(item.deadline_iso)})`}
            danger={overdue}
          />
          <DetailRow icon={Files} label="Requisito" value={item.requirement_name} />
          <DetailRow icon={Stamp} label="Institución" value={institutionLabel} />

          <div className="space-y-2">
            <Button asChild className="w-full" size="lg">
              <Link href={vendorHref}>
                <Eye className="h-4 w-4" weight="bold" aria-hidden="true" />
                <span>{primaryLabel}</span>
                <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
              </Link>
            </Button>
            <Button asChild variant="outline" className="w-full" size="lg">
              <Link href={auditHref}>
                <Package className="h-4 w-4" weight="bold" aria-hidden="true" />
                <span>Empaquetar este periodo para auditoría</span>
              </Link>
            </Button>
          </div>

          {ordered.length > 1 ? (
            <div>
              <p className="mb-2 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                Otras obligaciones de este mes ({ordered.length})
              </p>
              <ul className="divide-y divide-[color:var(--border-subtle)] rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)]">
                {ordered.map((sibling, idx) => {
                  const SibIcon = RISK_ICON[sibling.risk_level ?? "on_track"];
                  const active = idx === selectedIdx;
                  return (
                    <li key={`${sibling.requirement_code ?? sibling.requirement_name}-${sibling.period_key ?? ""}`}>
                      <button
                        type="button"
                        onClick={() => setSelectedIdx(idx)}
                        aria-current={active}
                        className={
                          "flex w-full items-center gap-2 px-3 py-2 text-left text-xs transition-colors " +
                          (active
                            ? "bg-[color:var(--surface-selected)]"
                            : "hover:bg-[color:var(--surface-hover)]")
                        }
                      >
                        <SibIcon
                          className="h-3.5 w-3.5 shrink-0 text-[color:var(--text-secondary)]"
                          weight="bold"
                          aria-hidden="true"
                        />
                        <span className="min-w-0 flex-1 truncate text-[color:var(--text-primary)]">
                          {sibling.requirement_name}
                        </span>
                        <span className="shrink-0 font-mono text-[10px] text-[color:var(--text-tertiary)]">
                          {RISK_LABEL[sibling.risk_level ?? "on_track"]}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

function DetailRow({
  icon: IconComponent,
  label,
  value,
  danger,
}: {
  icon: Icon;
  label: string;
  value: string;
  danger?: boolean;
}) {
  return (
    <div className="flex items-start gap-3">
      <span className="mt-0.5 flex h-7 w-7 items-center justify-center rounded-full bg-[color:var(--surface-sunken)]">
        <IconComponent
          className="h-3.5 w-3.5 text-[color:var(--text-secondary)]"
          weight="bold"
          aria-hidden="true"
        />
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
          {label}
        </p>
        <p
          className={
            "mt-0.5 text-[13px] " +
            (danger
              ? "font-medium text-[color:var(--status-error-text)]"
              : "text-[color:var(--text-primary)]")
          }
        >
          {value}
        </p>
      </div>
    </div>
  );
}
