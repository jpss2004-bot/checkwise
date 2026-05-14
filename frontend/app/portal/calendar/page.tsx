"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  Buildings,
  CalendarBlank,
  CloudArrowUp,
  Files,
  Scales,
  ShieldCheck,
  Stamp,
  X,
  type Icon,
} from "@phosphor-icons/react";

import { DocStateBadge, DOC_STATE_LABELS } from "@/components/checkwise/doc-state-badge";
import { ProviderContextBar } from "@/components/checkwise/portal/provider-context-bar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getCalendar } from "@/lib/api/portal";
import { adaptCalendarToEvents } from "@/lib/api/portal-adapters";
import {
  INSTITUTION_LABELS,
  MOCK_CALENDAR_2026,
  MONTH_LABELS,
  MONTH_LABELS_SHORT,
  type CalendarEvent,
  type CalendarInstitution,
} from "@/lib/mock/calendar";
import { withPortalSession } from "@/lib/session/with-portal-session";
import type { PortalSession } from "@/lib/session/portal";

const INSTITUTIONS: CalendarInstitution[] = ["sat", "imss", "infonavit", "stps_repse"];

const INSTITUTION_ICON: Record<CalendarInstitution, Icon> = {
  sat: Scales,
  imss: Buildings,
  infonavit: Buildings,
  stps_repse: ShieldCheck,
};

/**
 * Yearly REPSE calendar — institution × month grid.
 *
 * Click any cell to open a detail drawer with obligation name,
 * institution, required document, deadline, state, and CTA.
 *
 * Mock-data only for the moment. The existing
 * /api/v1/portal/calendar response already covers most of this; we'll
 * swap when the suggested_action + required_document fields land.
 *
 * TODO[backend-integration]: replace MOCK_CALENDAR_2026 with a fetch
 * from /api/v1/portal/calendar?year=2026 + augment the response shape.
 */
function CalendarInner({ session }: { session: PortalSession }) {
  const [year] = useState(2026);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filterInstitution, setFilterInstitution] =
    useState<CalendarInstitution | "all">("all");

  // CheckWise 1.7: real /portal/workspaces/{id}/calendar payload,
  // flattened by adaptCalendarToEvents into the existing CalendarEvent
  // shape so the UI below stays as-is.
  const [events, setEvents] = useState<CalendarEvent[] | null>(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getCalendar(session, year)
      .then((payload) => {
        if (cancelled) return;
        const adapted = adaptCalendarToEvents(payload);
        setEvents(adapted.length > 0 ? adapted : MOCK_CALENDAR_2026);
      })
      .catch(() => {
        if (cancelled) return;
        setLoadError(true);
        setEvents(MOCK_CALENDAR_2026);
      });
    return () => {
      cancelled = true;
    };
  }, [session, year]);

  const filteredEvents = useMemo(() => {
    if (!events) return [];
    if (filterInstitution === "all") return events;
    return events.filter((e) => e.institution === filterInstitution);
  }, [filterInstitution, events]);

  // Index events by (institution, month) for fast lookup.
  const eventsByCell = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();
    for (const e of filteredEvents) {
      const key = `${e.institution}-${e.month}`;
      const list = map.get(key) ?? [];
      list.push(e);
      map.set(key, list);
    }
    return map;
  }, [filteredEvents]);

  const selected = useMemo(
    () => (events ?? []).find((e) => e.id === selectedId) ?? null,
    [selectedId, events],
  );

  if (!events) {
    return (
      <>
        <ProviderContextBar session={session} />
        <main className="mx-auto max-w-7xl space-y-6 px-5 py-8">
          <Skeleton className="h-24 w-1/2 rounded-xl" />
          <Skeleton className="h-[420px] w-full rounded-xl" />
        </main>
      </>
    );
  }

  return (
    <>
      <ProviderContextBar session={session} />
      <main className="mx-auto max-w-7xl space-y-6 px-5 py-8">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div className="space-y-1">
            <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-teal)]">
              Calendario REPSE · {year}
            </p>
            <h1 className="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)]">
              Tu año de cumplimiento de un vistazo
            </h1>
            <p className="max-w-prose text-[13px] text-[color:var(--text-secondary)]">
              Cada celda representa una obligación. Toca cualquier mes para ver
              detalle, requisito y siguiente acción.
            </p>
          </div>
          <Button asChild variant="outline" size="sm">
            <Link href="/portal/dashboard">
              <ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
              Dashboard
            </Link>
          </Button>
        </header>

        <FilterChips
          value={filterInstitution}
          onChange={setFilterInstitution}
          counts={{
            all: events.length,
            sat: events.filter((e) => e.institution === "sat").length,
            imss: events.filter((e) => e.institution === "imss").length,
            infonavit: events.filter((e) => e.institution === "infonavit").length,
            stps_repse: events.filter((e) => e.institution === "stps_repse").length,
          }}
        />

        {loadError && (
          <p className="text-xs text-[color:var(--text-secondary)]">
            No pudimos cargar tu calendario en este momento. Mostramos datos de
            respaldo mientras se restablece la conexión.
          </p>
        )}

        <section
          className="cw-fade-up overflow-x-auto rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs"
          aria-label="Cuadrícula del calendario"
        >
          <table className="w-full min-w-[760px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] text-left">
                <th
                  scope="col"
                  className="px-4 py-3 text-[10px] font-mono uppercase tracking-wide text-[color:var(--text-tertiary)]"
                >
                  Institución
                </th>
                {MONTH_LABELS_SHORT.map((m, idx) => (
                  <th
                    key={m}
                    scope="col"
                    className={
                      "px-2 py-3 text-center text-[10px] font-mono uppercase tracking-wide " +
                      (idx === 4
                        ? "text-[color:var(--text-brand)]"
                        : "text-[color:var(--text-tertiary)]")
                    }
                  >
                    {m}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {INSTITUTIONS.map((inst) => {
                if (
                  filterInstitution !== "all" &&
                  filterInstitution !== inst
                ) {
                  return null;
                }
                const IconComponent = INSTITUTION_ICON[inst];
                return (
                  <tr
                    key={inst}
                    className="border-b border-[color:var(--border-subtle)] last:border-0"
                  >
                    <th
                      scope="row"
                      className="border-r border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-4 py-3 text-left align-middle"
                    >
                      <span className="flex items-center gap-2 text-[13px] font-semibold text-[color:var(--text-primary)]">
                        <IconComponent
                          className="h-4 w-4 text-[color:var(--text-brand)]"
                          weight="duotone"
                          aria-hidden="true"
                        />
                        {INSTITUTION_LABELS[inst]}
                      </span>
                    </th>
                    {Array.from({ length: 12 }, (_, monthIdx) => {
                      const month = monthIdx + 1;
                      const cellEvents = eventsByCell.get(`${inst}-${month}`) ?? [];
                      return (
                        <td key={month} className="p-1 text-center align-middle">
                          <MonthCell
                            events={cellEvents}
                            isCurrent={month === 5}
                            onSelect={setSelectedId}
                          />
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>

        <Legend />
      </main>

      {selected && (
        <EventDrawer event={selected} onClose={() => setSelectedId(null)} />
      )}
    </>
  );
}

export default withPortalSession(CalendarInner);

// ─── Filter chips ───────────────────────────────────────────────

function FilterChips({
  value,
  onChange,
  counts,
}: {
  value: CalendarInstitution | "all";
  onChange: (v: CalendarInstitution | "all") => void;
  counts: Record<CalendarInstitution | "all", number>;
}) {
  const options: { value: CalendarInstitution | "all"; label: string }[] = [
    { value: "all", label: "Todas" },
    { value: "sat", label: "SAT" },
    { value: "imss", label: "IMSS" },
    { value: "infonavit", label: "INFONAVIT" },
    { value: "stps_repse", label: "STPS / REPSE" },
  ];
  return (
    <div role="tablist" className="flex flex-wrap gap-2">
      {options.map((opt) => {
        const active = value === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(opt.value)}
            className={
              "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors " +
              (active
                ? "border-[color:var(--border-brand)] bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]"
                : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)]")
            }
          >
            <span>{opt.label}</span>
            <span
              className={
                "font-mono text-[10px] tabular-nums " +
                (active ? "opacity-80" : "text-[color:var(--text-tertiary)]")
              }
            >
              {counts[opt.value]}
            </span>
          </button>
        );
      })}
    </div>
  );
}

// ─── Cell ───────────────────────────────────────────────────────

const CELL_BG = {
  approved: "bg-[color:var(--doc-approved-bg)] text-[color:var(--doc-approved-text)] border-[color:var(--doc-approved-border)]",
  in_review: "bg-[color:var(--doc-in-review-bg)] text-[color:var(--doc-in-review-text)] border-[color:var(--doc-in-review-border)]",
  uploaded: "bg-[color:var(--doc-uploaded-bg)] text-[color:var(--doc-uploaded-text)] border-[color:var(--doc-uploaded-border)]",
  rejected: "bg-[color:var(--doc-rejected-bg)] text-[color:var(--doc-rejected-text)] border-[color:var(--doc-rejected-border)]",
  expired: "bg-[color:var(--doc-expired-bg)] text-[color:var(--doc-expired-text)] border-[color:var(--doc-expired-border)]",
  needs_review: "bg-[color:var(--doc-needs-review-bg)] text-[color:var(--doc-needs-review-text)] border-[color:var(--doc-needs-review-border)]",
  pending: "bg-[color:var(--doc-pending-bg)] text-[color:var(--doc-pending-text)] border-[color:var(--doc-pending-border)]",
  empty: "bg-[color:var(--doc-empty-bg)] text-[color:var(--doc-empty-text)] border-[color:var(--doc-empty-border)]",
} as const;

function MonthCell({
  events,
  isCurrent,
  onSelect,
}: {
  events: CalendarEvent[];
  isCurrent: boolean;
  onSelect: (id: string) => void;
}) {
  if (events.length === 0) {
    return (
      <div
        className={
          "h-10 w-full rounded-sm border " +
          (isCurrent
            ? "border-[color:var(--border-focus)]/40 bg-[color:var(--surface-brand-muted)]/40"
            : "border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]")
        }
        aria-hidden="true"
      />
    );
  }
  const event = events[0];
  const tone = CELL_BG[event.state];
  return (
    <button
      type="button"
      onClick={() => onSelect(event.id)}
      className={
        "group relative flex h-10 w-full items-center justify-center gap-1 rounded-sm border font-mono text-[10px] font-semibold uppercase transition-all hover:scale-[1.04] focus:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40 " +
        tone +
        (isCurrent ? " ring-2 ring-[color:var(--border-focus)]/40" : "")
      }
      aria-label={`${event.obligation} en ${MONTH_LABELS[event.month - 1]}: ${DOC_STATE_LABELS[event.state]}`}
    >
      <StateDot state={event.state} />
      {events.length > 1 && (
        <span className="rounded-full bg-current/10 px-1 text-[8px]">
          +{events.length - 1}
        </span>
      )}
    </button>
  );
}

function StateDot({ state }: { state: CalendarEvent["state"] }) {
  const symbol =
    state === "approved"
      ? "✓"
      : state === "in_review" || state === "uploaded"
        ? "·"
        : state === "rejected"
          ? "✕"
          : state === "expired"
            ? "!"
            : state === "needs_review"
              ? "?"
              : state === "pending"
                ? "○"
                : "";
  return <span aria-hidden="true">{symbol}</span>;
}

// ─── Detail drawer ──────────────────────────────────────────────

function EventDrawer({
  event,
  onClose,
}: {
  event: CalendarEvent;
  onClose: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="drawer-title"
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
            <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              {INSTITUTION_LABELS[event.institution]} ·{" "}
              {MONTH_LABELS[event.month - 1]} {event.year}
            </p>
            <h2
              id="drawer-title"
              className="mt-1 text-lg font-semibold text-[color:var(--text-primary)]"
            >
              {event.obligation}
            </h2>
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
          <div className="flex items-center gap-2">
            <DocStateBadge state={event.state} />
            <Badge variant="outline">{frequencyLabel(event.frequency)}</Badge>
          </div>

          <DetailRow
            icon={Files}
            label="Documento requerido"
            value={event.required_document}
          />
          <DetailRow
            icon={CalendarBlank}
            label="Vence"
            value={formatLongDate(event.deadline_iso)}
          />
          <DetailRow
            icon={Stamp}
            label="Institución"
            value={INSTITUTION_LABELS[event.institution]}
          />

          <div className="rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)] p-4">
            <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              Siguiente paso
            </p>
            <p className="mt-1 text-[13px] leading-5 text-[color:var(--text-primary)]">
              {event.suggested_action}
            </p>
          </div>

          {event.state !== "approved" && (
            <Button asChild className="w-full" size="lg">
              <Link
                href={`/portal/upload?period_key=${event.year}-M${String(event.month).padStart(2, "0")}`}
              >
                <CloudArrowUp className="h-4 w-4" weight="bold" aria-hidden="true" />
                <span>Subir documento</span>
                <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
              </Link>
            </Button>
          )}
        </div>
      </aside>
    </div>
  );
}

function DetailRow({
  icon: IconComponent,
  label,
  value,
}: {
  icon: Icon;
  label: string;
  value: string;
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
        <p className="mt-0.5 text-[13px] text-[color:var(--text-primary)]">{value}</p>
      </div>
    </div>
  );
}

function frequencyLabel(freq: CalendarEvent["frequency"]): string {
  switch (freq) {
    case "monthly":
      return "Mensual";
    case "bimonthly":
      return "Bimestral";
    case "four_monthly":
      return "Cuatrimestral";
    case "annual":
      return "Anual";
  }
}

function formatLongDate(iso: string): string {
  try {
    const date = new Date(iso);
    return date.toLocaleDateString("es-MX", {
      day: "2-digit",
      month: "long",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

// ─── Legend ─────────────────────────────────────────────────────

const LEGEND_STATES: CalendarEvent["state"][] = [
  "approved",
  "in_review",
  "uploaded",
  "pending",
  "needs_review",
  "rejected",
  "expired",
  "empty",
];

function Legend() {
  return (
    <section className="rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] p-4">
      <p className="mb-3 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        Leyenda
      </p>
      <ul className="flex flex-wrap gap-2">
        {LEGEND_STATES.map((state) => (
          <li key={state}>
            <DocStateBadge state={state} />
          </li>
        ))}
      </ul>
    </section>
  );
}
