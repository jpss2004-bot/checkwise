"use client";

import Link from "next/link";
import {
  ArrowRight,
  Package,
  Paperclip,
  WarningCircle,
  type Icon,
} from "@phosphor-icons/react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DocumentGuidanceDisclosure } from "@/components/checkwise/portal/expediente-card";
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

  // Server-owned next step (oversight voice) with a FE fallback for a stale
  // backend that hasn't shipped the field yet.
  const nextStep = item.suggested_action ?? nextActionFor(item);
  // Oversight evidence — what the provider delivered, and (on rejected items)
  // the reviewer's reason so the client can relay it verbatim.
  const deliveredFile =
    item.submission_id && item.filename ? item.filename : null;
  const deliveredOn = item.submitted_at ? formatLongDate(item.submitted_at) : null;
  // The backend only sets reviewer_note on rejected / needs-clarification /
  // mismatch items, so its mere presence is the signal to show it (an
  // overdue-but-rejected doc still needs to surface why it bounced).
  const reviewerNote = item.reviewer_note ?? null;
  // Document literacy. v2 obligations satisfiable by any of several documents
  // carry an `accepts_documents` list; v1 obligations carry the single-doc
  // anatomy/where/common_errors instead.
  const acceptsDocuments = item.accepts_documents ?? [];
  const hasGuidance =
    acceptsDocuments.length > 0 ||
    (item.anatomy ?? "").trim().length > 0 ||
    (item.where_to_obtain ?? "").trim().length > 0;

  // B2 — prefer the server-owned oversight deep-link (single source of truth).
  // The backend now fills ``item.href`` with the client expediente URL
  // (pre-focused on this obligation's bucket); fall back to recomputing it
  // locally only if a stale backend (rolling deploy) still sends the legacy
  // provider-upload URL. ``withReturnTo`` preserves list context either way.
  const oversightHref = item.href?.startsWith("/client/")
    ? item.href
    : `/client/vendors/${item.vendor_id}?focus=${focusForItem(item)}#documentos`;
  const vendorHref = withReturnTo(oversightHref, returnToHref);
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
        {deliveredFile ? (
          <DetailLine
            icon={Paperclip}
            label="Entregado"
            value={deliveredOn ? `${deliveredFile} · ${deliveredOn}` : deliveredFile}
          />
        ) : null}
        <DetailLine label="Siguiente paso" value={nextStep} emphasis />
      </dl>

      {/* Reviewer's reason on bounced obligations — lets the client forward
          the exact motive to the provider instead of a vague "please fix". */}
      {reviewerNote ? (
        <div className="mt-2.5 rounded-md border border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] px-3 py-2">
          <p className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-[color:var(--status-error-text)]">
            <WarningCircle className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            Observación del revisor
          </p>
          <p className="mt-1 text-xs leading-5 text-[color:var(--text-secondary)]">
            {reviewerNote}
          </p>
        </div>
      ) : null}

      {/* Document literacy — what a valid document must contain, where the
          provider gets it, and the pitfalls the client should verify. Framed
          for review (the client validates, it does not upload). Reuses the
          provider calendar's disclosure. */}
      {hasGuidance ? (
        <div className="mt-2.5 space-y-2">
          {acceptsDocuments.length > 0 ? (
            <>
              <p className="text-[11px] leading-4 text-[color:var(--text-secondary)]">
                Cualquiera de estos documentos satisface la obligación — el
                proveedor solo necesita entregar uno.
              </p>
              {acceptsDocuments.map((doc) => (
                <DocumentGuidanceDisclosure
                  key={doc.name}
                  anatomy={doc.anatomy}
                  where_to_obtain={doc.where_to_obtain}
                  common_errors={doc.common_errors}
                  summary_label={`Acerca de ${doc.name}`}
                  errors_label="Errores comunes a verificar"
                />
              ))}
            </>
          ) : (
            <DocumentGuidanceDisclosure
              anatomy={item.anatomy ?? ""}
              where_to_obtain={item.where_to_obtain ?? ""}
              common_errors={item.common_errors ?? []}
              summary_label="Qué debe contener este documento"
              errors_label="Errores comunes a verificar"
            />
          )}
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button asChild size="sm" variant="outline">
          <Link href={vendorHref} title="Abrir el expediente del proveedor">
            {item.submission_id ? "Ver documento" : "Abrir expediente"}
            <ArrowRight className="h-3 w-3" weight="bold" aria-hidden="true" />
          </Link>
        </Button>
        <Button asChild size="sm" variant="ghost">
          <Link
            href={auditHref}
            title="Abre el paquete de auditoría con este periodo ya seleccionado para descargar los documentos."
          >
            <Package className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            Armar paquete de auditoría
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
