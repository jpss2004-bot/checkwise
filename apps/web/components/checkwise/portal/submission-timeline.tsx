import * as React from "react";
import {
  ClockCounterClockwise,
  Robot,
  Gavel,
  ShieldCheck,
  Warning,
  WarningCircle,
  CheckCircle,
  Question,
  ArrowsClockwise,
} from "@phosphor-icons/react";

import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { statusToDocumentStateCode } from "@/lib/api/portal";
import type {
  RequirementStatus,
  SubmissionDetail,
  SubmissionEvent,
  SubmissionHistoryEntry,
} from "@/lib/api/portal";
import type { DocumentStateCode } from "@/lib/types";
import { STATUS_LABELS_ES } from "@/lib/constants/statuses";

/**
 * SubmissionTimeline — the trust layer.
 *
 * Backed by the canonical triple-trail:
 *   - DocumentStatusHistory  (status transitions)
 *   - ValidationEvent         (automation + reviewer-decision audit)
 *   - replacement lineage     (supersedes / superseded_by)
 *
 * Renders one chronological trail so providers and reviewers see
 * exactly what happened and *who* (provider / system / reviewer)
 * caused each change. State transitions get the bigger doc-state
 * colored dot; validation events get a smaller secondary dot.
 *
 * Spec: docs/design-system/VISUAL_REDESIGN_DOCTRINE.md
 *       §"Submission Timeline" + docs/EVIDENCE_SLOTS.md.
 */

type Item =
  | {
      kind: "status";
      occurredAt: string;
      from: string | null;
      to: RequirementStatus;
      docState: DocumentStateCode;
      reason: string | null;
      actor: string;
    }
  | {
      kind: "event";
      occurredAt: string;
      eventType: string;
      result: string;
      severity: string;
      message: string | null;
      actorType: string;
    };

interface SubmissionTimelineProps {
  detail: Pick<
    SubmissionDetail,
    "history" | "events" | "supersedes_submission_id" | "superseded_by_submission_id"
  >;
  /** Show the heading + description; turn off for embedded use. */
  showHeader?: boolean;
  className?: string;
  /**
   * Which audience is viewing the timeline. Provider (default) hides
   * admin-only diagnostic events like `shadow_analysis_completed` and
   * `ocr_performed`; admin shows them so reviewers can see when the
   * automatic lectura ran. Does not change any other behaviour.
   */
  audience?: "provider" | "admin";
}

// Status labels delegate to the central dictionary so a vocabulary
// rename in one place propagates here. See lib/constants/statuses.ts.
const STATUS_LABEL: Record<string, string> = STATUS_LABELS_ES;

// Provider-friendly event labels. The backend emits engineer-shaped
// event_type strings (snake_case, technical); this map translates
// them into plain Spanish a non-technical provider can scan. Events
// without an entry fall back to the raw event_type so any new event
// added on the backend stands out as untranslated until a label is
// added here.
const EVENT_LABEL: Record<string, string> = {
  reviewer_decision: "Decisión del equipo legal",
  submission_replacement_linked: "Reemplaza un envío anterior",
  submission_replaced: "Reemplazado por un envío más reciente",
  pdf_validation: "Verificación del archivo",
  document_intelligence: "Revisión automática",
  duplicate_check: "Comparación con cargas anteriores",
  intake_received: "Documento recibido",
  // Phase 2 shadow analysis events are internal (admin reviewer
  // surface only). Providers should not see them on their timeline;
  // we keep the label here so if they leak the wording is friendly.
  shadow_analysis_completed: "Lectura automática terminada",
  ocr_performed: "Lectura automática del archivo",
};

// Event types that are reviewer/admin-only diagnostics — never shown
// on the provider-facing timeline. The component filters these out
// before rendering when `audience` is "provider" (the default).
const ADMIN_ONLY_EVENT_TYPES = new Set<string>([
  "shadow_analysis_completed",
  "ocr_performed",
]);

const ACTOR_TYPE_LABEL: Record<string, string> = {
  supplier: "Proveedor",
  reviewer: "Revisor humano",
  system: "Sistema CheckWise",
  internal_admin: "Administrador interno",
};

const STATE_DOT_CLASS: Record<DocumentStateCode, string> = {
  empty: "bg-[color:var(--doc-empty-text)]",
  pending: "bg-[color:var(--doc-pending-text)]",
  uploaded: "bg-[color:var(--doc-uploaded-text)]",
  in_review: "bg-[color:var(--doc-in-review-text)]",
  approved: "bg-[color:var(--doc-approved-text)]",
  rejected: "bg-[color:var(--doc-rejected-text)]",
  expired: "bg-[color:var(--doc-expired-text)]",
  needs_review: "bg-[color:var(--doc-needs-review-text)]",
};

const SEVERITY_TONE: Record<string, string> = {
  error: "text-[color:var(--status-error-text)]",
  warning: "text-[color:var(--status-warning-text)]",
  info: "text-[color:var(--status-info-text)]",
  success: "text-[color:var(--status-success-text)]",
};

function actorIcon(actorType: string) {
  switch (actorType) {
    case "reviewer":
    case "internal_admin":
      return Gavel;
    case "system":
      return Robot;
    case "supplier":
      return ArrowsClockwise;
    default:
      return ShieldCheck;
  }
}

function eventIcon(eventType: string, severity: string) {
  if (eventType === "reviewer_decision") return Gavel;
  if (eventType.startsWith("submission_replac")) return ArrowsClockwise;
  if (severity === "error") return WarningCircle;
  if (severity === "warning") return Warning;
  if (severity === "info") return Question;
  return CheckCircle;
}

export function SubmissionTimeline({
  detail,
  showHeader = true,
  className,
  audience = "provider",
}: SubmissionTimelineProps) {
  const visibleEvents =
    audience === "admin"
      ? detail.events
      : detail.events.filter((e) => !ADMIN_ONLY_EVENT_TYPES.has(e.event_type));
  const items = mergeAndSort(detail.history, visibleEvents);

  return (
    <section
      aria-label="Línea de tiempo del documento"
      className={cn(
        "rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs",
        className,
      )}
    >
      {showHeader ? (
        <header className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] px-5 py-3">
          <ClockCounterClockwise
            className="h-4 w-4 text-[color:var(--text-brand)]"
            weight="duotone"
            aria-hidden="true"
          />
          <h2 className="text-[13px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
            Línea de tiempo
          </h2>
          <span className="ml-auto font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
            {items.length} {items.length === 1 ? "evento" : "eventos"}
          </span>
        </header>
      ) : null}

      {items.length === 0 ? (
        <div className="px-5 py-6 text-sm text-[color:var(--text-secondary)]">
          Aún no hay eventos registrados para este documento.
        </div>
      ) : (
        <ol
          className="cw-stagger relative space-y-0 px-5 py-4"
          aria-label="Cronología de cambios"
        >
          {items.map((item, idx) => (
            <TimelineRow
              key={`${item.kind}-${item.occurredAt}-${idx}`}
              item={item}
              isLast={idx === items.length - 1}
              index={idx}
            />
          ))}
        </ol>
      )}
    </section>
  );
}

function TimelineRow({
  item,
  isLast,
  index,
}: {
  item: Item;
  isLast: boolean;
  index: number;
}) {
  // Clamp the stagger delay to the same 8-step (480ms) cap the
  // nth-child fallback uses in globals.css, so late timeline rows
  // don't stay invisible for a second-plus on long histories.
  const staggerStyle = { "--cw-index": Math.min(index, 8) } as React.CSSProperties;
  if (item.kind === "status") {
    const ActorIcon = actorIcon(item.actor.split(":")[0] ?? item.actor);
    return (
      <li className="relative flex gap-3 pb-4 last:pb-0" style={staggerStyle}>
        {!isLast ? (
          <span
            aria-hidden="true"
            className="absolute left-[5px] top-3 h-full w-px bg-[color:var(--border-subtle)]"
          />
        ) : null}
        <span
          aria-hidden="true"
          className={cn(
            "relative z-10 mt-1 h-2.5 w-2.5 shrink-0 rounded-full ring-2 ring-[color:var(--surface-raised)]",
            STATE_DOT_CLASS[item.docState],
          )}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-[13px] font-medium text-[color:var(--text-primary)]">
              {item.from
                ? `${STATUS_LABEL[item.from] ?? item.from} → ${STATUS_LABEL[item.to] ?? item.to}`
                : (STATUS_LABEL[item.to] ?? item.to)}
            </p>
            <Tooltip content={prettyActor(item.actor)} side="left">
              <span className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                <ActorIcon className="h-3 w-3" weight="bold" aria-hidden="true" />
                {prettyActor(item.actor)}
              </span>
            </Tooltip>
          </div>
          <p className="font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
            {formatTime(item.occurredAt)}
          </p>
          {item.reason ? (
            <p className="mt-1.5 rounded-sm border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-2.5 py-1.5 text-[12px] leading-[1.5] text-[color:var(--text-secondary)]">
              {item.reason}
            </p>
          ) : null}
        </div>
      </li>
    );
  }

  const EventIcon = eventIcon(item.eventType, item.severity);
  const tone = SEVERITY_TONE[item.severity] ?? "text-[color:var(--text-tertiary)]";
  return (
    <li className="relative flex gap-3 pb-4 last:pb-0" style={staggerStyle}>
      {!isLast ? (
        <span
          aria-hidden="true"
          className="absolute left-[5px] top-3 h-full w-px bg-[color:var(--border-subtle)]"
        />
      ) : null}
      <span
        aria-hidden="true"
        className="relative z-10 mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-[color:var(--surface-raised)] ring-2 ring-[color:var(--border-default)]"
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="flex items-center gap-1.5 text-[12px] font-medium text-[color:var(--text-secondary)]">
            <EventIcon className={cn("h-3.5 w-3.5", tone)} weight="bold" aria-hidden="true" />
            {EVENT_LABEL[item.eventType] ?? item.eventType}
          </p>
          <Tooltip content={ACTOR_TYPE_LABEL[item.actorType] ?? item.actorType} side="left">
            <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              {ACTOR_TYPE_LABEL[item.actorType] ?? item.actorType}
            </span>
          </Tooltip>
        </div>
        <p className="font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
          {formatTime(item.occurredAt)}
        </p>
        {item.message ? (
          <p className="mt-1 text-[12px] leading-[1.5] text-[color:var(--text-secondary)]">
            {item.message}
          </p>
        ) : null}
      </div>
    </li>
  );
}

function mergeAndSort(
  history: SubmissionHistoryEntry[],
  events: SubmissionEvent[],
): Item[] {
  const out: Item[] = [];
  for (const h of history) {
    out.push({
      kind: "status",
      occurredAt: h.occurred_at,
      from: h.from_status,
      to: h.to_status as RequirementStatus,
      docState: statusToDocumentStateCode(h.to_status as RequirementStatus),
      reason: h.reason,
      actor: h.actor,
    });
  }
  for (const e of events) {
    // Skip reviewer_decision validation events — already represented as
    // a status transition row above. Keep replacement-link events because
    // they don't change status (lineage runs on the side).
    if (e.event_type === "reviewer_decision") continue;
    out.push({
      kind: "event",
      occurredAt: e.occurred_at,
      eventType: e.event_type,
      result: e.result,
      severity: e.severity,
      message: e.message,
      actorType: e.actor_type,
    });
  }
  out.sort((a, b) => a.occurredAt.localeCompare(b.occurredAt));
  return out;
}

function prettyActor(actor: string): string {
  // Backend stores actors as `reviewer:<user_id>` / `supplier:<user_id>` /
  // `system`. Surface the role to the user; the id stays for audit logs.
  const [role] = actor.split(":");
  return ACTOR_TYPE_LABEL[role] ?? role;
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("es-MX", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
