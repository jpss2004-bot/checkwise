"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  ArrowsClockwise,
  Buildings,
  CalendarBlank,
  CloudArrowUp,
  Eye,
  Files,
  Funnel,
  Scales,
  ShieldCheck,
  Stamp,
  Tray,
  X,
  type Icon,
} from "@phosphor-icons/react";

import { InstitutionRowHeader } from "@/components/checkwise/calendar/institution-row-header";
import { MonthCell } from "@/components/checkwise/calendar/month-cell";
import {
  CALENDAR_INSTITUTIONS,
  type CalendarEntry,
  type CalendarInstitutionCode,
} from "@/components/checkwise/calendar/types";
import { DocStateBadge } from "@/components/checkwise/doc-state-badge";
import { DocumentGuidanceDisclosure } from "@/components/checkwise/portal/expediente-card";
import { PortalAppShell } from "@/components/checkwise/portal/portal-app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import {
  getCalendar,
  INSTITUTION_LABELS,
  MONTH_LABELS_ES,
  MONTH_LABELS_SHORT_ES,
  statusToDocumentStateCode,
  type CalendarPayload,
} from "@/lib/api/portal";
import { withOnboardingGate } from "@/lib/session/with-onboarding-gate";
import type { PortalSession } from "@/lib/session/portal";

const INSTITUTION_ICON: Record<CalendarInstitutionCode, Icon> = {
  sat: Scales,
  imss: Buildings,
  infonavit: Buildings,
  stps_repse: ShieldCheck,
};

function flattenCalendarPayload(payload: CalendarPayload): CalendarEntry[] {
  const entries: CalendarEntry[] = [];
  for (const month of payload.months) {
    for (const inst of month.institutions) {
      if (!CALENDAR_INSTITUTIONS.includes(inst.institution as CalendarInstitutionCode)) {
        continue;
      }
      const institution = inst.institution as CalendarInstitutionCode;
      for (const item of inst.items) {
        entries.push({
          id: `${institution}-${payload.year}-${month.month}-${item.code}`,
          year: payload.year,
          month: month.month,
          institution,
          obligation: item.name,
          required_document: item.required_document,
          deadline_iso: item.deadline_iso,
          state: statusToDocumentStateCode(item.status),
          suggested_action: item.suggested_action,
          frequency: item.frequency,
          href: item.href,
          submission_id: item.submission_id,
          anatomy: item.anatomy ?? "",
          where_to_obtain: item.where_to_obtain ?? "",
          common_errors: item.common_errors ?? [],
          // Session 3 (2026-05-21) — catalog v2 alternatives.
          // ``?? []`` keeps the wizard safe when the backend hasn't
          // rolled out yet (e.g. testing against a stale staging).
          accepts_documents: item.accepts_documents ?? [],
        });
      }
    }
  }
  return entries;
}

const VALID_INSTITUTIONS: ReadonlySet<string> = new Set([
  "sat",
  "imss",
  "infonavit",
  "stps_repse",
]);

function CalendarInner({ session }: { session: PortalSession }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const now = new Date();
  const [year] = useState(now.getFullYear() || 2026);
  const currentMonth = now.getMonth() + 1;
  const viewingCurrentYear = year === now.getFullYear();

  const filterParam = searchParams.get("inst");
  const filterInstitution: CalendarInstitutionCode | "all" =
    filterParam && VALID_INSTITUTIONS.has(filterParam)
      ? (filterParam as CalendarInstitutionCode)
      : "all";

  const setFilterInstitution = (v: CalendarInstitutionCode | "all") => {
    const params = new URLSearchParams(searchParams.toString());
    if (v === "all") {
      params.delete("inst");
    } else {
      params.set("inst", v);
    }
    const qs = params.toString();
    router.replace(qs ? `/portal/calendar?${qs}` : "/portal/calendar", {
      scroll: false,
    });
  };

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [events, setEvents] = useState<CalendarEntry[] | null>(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getCalendar(session, year)
      .then((payload) => {
        if (cancelled) return;
        setEvents(flattenCalendarPayload(payload));
        setLoadError(false);
      })
      .catch(() => {
        if (cancelled) return;
        setLoadError(true);
        setEvents([]);
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

  const eventsByCell = useMemo(() => {
    const map = new Map<string, CalendarEntry[]>();
    for (const e of filteredEvents) {
      const key = `${e.institution}-${e.month}`;
      const list = map.get(key) ?? [];
      list.push(e);
      map.set(key, list);
    }
    return map;
  }, [filteredEvents]);

  const eventsByInstitution = useMemo(() => {
    const map = new Map<CalendarInstitutionCode, CalendarEntry[]>();
    for (const inst of CALENDAR_INSTITUTIONS) {
      map.set(inst, []);
    }
    for (const e of filteredEvents) {
      map.get(e.institution)?.push(e);
    }
    return map;
  }, [filteredEvents]);

  const selected = useMemo(
    () => (events ?? []).find((e) => e.id === selectedId) ?? null,
    [selectedId, events],
  );

  if (!events) {
    return (
      <PortalAppShell session={session}>
        <main className="mx-auto w-full max-w-screen-2xl space-y-6 px-5 py-8 sm:px-6 lg:px-8 2xl:px-10">
          <Skeleton className="h-24 w-1/2 rounded-xl" />
          <Skeleton className="h-[420px] w-full rounded-xl" />
        </main>
      </PortalAppShell>
    );
  }

  const visibleInstitutions =
    filterInstitution === "all"
      ? CALENDAR_INSTITUTIONS
      : CALENDAR_INSTITUTIONS.filter((i) => i === filterInstitution);

  const totalCount = events.length;
  const filteredCount = filteredEvents.length;

  return (
    <PortalAppShell session={session}>
      <main className="mx-auto w-full max-w-screen-2xl space-y-6 px-5 py-8 sm:px-6 lg:px-8 2xl:px-10">
        <PageHeader
          eyebrow={`Calendario REPSE · ${year}`}
          title="Tu año de cumplimiento de un vistazo"
          description="Cada celda muestra las obligaciones de ese mes; pasa el cursor para ver el detalle o toca para abrir la siguiente acción."
          actions={
            <Button asChild variant="outline" size="sm">
              <Link href="/portal/dashboard">
                <ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
                Dashboard
              </Link>
            </Button>
          }
        />

        <FilterChips
          value={filterInstitution}
          onChange={setFilterInstitution}
          counts={{
            all: totalCount,
            sat: events.filter((e) => e.institution === "sat").length,
            imss: events.filter((e) => e.institution === "imss").length,
            infonavit: events.filter((e) => e.institution === "infonavit").length,
            stps_repse: events.filter((e) => e.institution === "stps_repse").length,
          }}
        />

        {loadError && (
          <p className="text-xs text-[color:var(--text-secondary)]">
            No pudimos cargar tu calendario en este momento. Recarga la página
            para intentar de nuevo; tu sesión sigue activa.
          </p>
        )}

        {filteredCount === 0 && !loadError ? (
          <FilteredEmpty
            label={
              filterInstitution === "all"
                ? "este año"
                : INSTITUTION_LABELS[filterInstitution]
            }
            onReset={() => setFilterInstitution("all")}
            canReset={filterInstitution !== "all"}
          />
        ) : (
          <section
            className="cw-fade-up overflow-x-auto rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs"
            aria-label="Cuadrícula del calendario"
          >
            {/* Bugfix (2026-05-21) — spacing drift.
                ``table-fixed`` + the explicit <colgroup> below force
                the 12 month columns to share the remaining width
                equally regardless of cell content. Without this, the
                browser's auto-layout was pushing the institution
                column past 240px and progressively compacting the
                later month columns (the icon-only cells lose to any
                column that ever renders text). */}
            <table className="w-full table-fixed min-w-[860px] border-collapse text-sm">
              <colgroup>
                {/* Institution row header — was effectively ~240px+
                    via min-w on the th. 160px is enough for the icon +
                    label + "X/Y" chip + 40px progress bar. */}
                <col style={{ width: "160px" }} />
                {Array.from({ length: 12 }, (_, i) => (
                  <col key={`month-col-${i}`} />
                ))}
              </colgroup>
              <thead>
                <tr className="border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] text-left">
                  <th
                    scope="col"
                    className="sticky left-0 z-20 border-r border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-4 py-3 text-[10px] font-mono uppercase tracking-wide text-[color:var(--text-tertiary)]"
                  >
                    Institución
                  </th>
                  {MONTH_LABELS_SHORT_ES.map((m, idx) => {
                    const monthNum = idx + 1;
                    const isCurrent = viewingCurrentYear && monthNum === currentMonth;
                    return (
                      <th
                        key={m}
                        scope="col"
                        aria-current={isCurrent ? "true" : undefined}
                        className={
                          "relative px-2 py-3 text-center text-[10px] font-mono uppercase tracking-wide " +
                          (isCurrent
                            ? "text-[color:var(--text-brand)]"
                            : "text-[color:var(--text-tertiary)]")
                        }
                      >
                        {m}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {visibleInstitutions.map((inst) => {
                  const IconComponent = INSTITUTION_ICON[inst];
                  const rowEvents = eventsByInstitution.get(inst) ?? [];
                  return (
                    <tr
                      key={inst}
                      className="border-b border-[color:var(--border-subtle)] last:border-0"
                    >
                      <th
                        scope="row"
                        // Bugfix (2026-05-21) — width comes from the
                        // <colgroup> above (160px). The previous
                        // ``min-w-[240px]`` overrode table-fixed and
                        // pushed the layout. Keep px-4 for padding
                        // so the content has breathing room.
                        className="sticky left-0 z-10 border-r border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-4 py-3 text-left align-middle"
                      >
                        <InstitutionRowHeader
                          icon={IconComponent}
                          label={INSTITUTION_LABELS[inst]}
                          events={rowEvents}
                        />
                      </th>
                      {Array.from({ length: 12 }, (_, monthIdx) => {
                        const month = monthIdx + 1;
                        const cellEvents = eventsByCell.get(`${inst}-${month}`) ?? [];
                        const isCurrent = viewingCurrentYear && month === currentMonth;
                        const isPast = viewingCurrentYear && month < currentMonth;
                        return (
                          <td key={month} className="p-1 align-middle">
                            <MonthCell
                              events={cellEvents}
                              month={month}
                              isCurrent={isCurrent}
                              isPast={isPast}
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
        )}

        <Legend />
      </main>

      {selected && (
        <EventDrawer event={selected} onClose={() => setSelectedId(null)} />
      )}
    </PortalAppShell>
  );
}

export default withOnboardingGate(CalendarInner);

// ─── Filter chips ───────────────────────────────────────────────

function FilterChips({
  value,
  onChange,
  counts,
}: {
  value: CalendarInstitutionCode | "all";
  onChange: (v: CalendarInstitutionCode | "all") => void;
  counts: Record<CalendarInstitutionCode | "all", number>;
}) {
  const options: { value: CalendarInstitutionCode | "all"; label: string }[] = [
    { value: "all", label: "Todas" },
    { value: "sat", label: "SAT" },
    { value: "imss", label: "IMSS" },
    { value: "infonavit", label: "INFONAVIT" },
    { value: "stps_repse", label: "STPS / REPSE" },
  ];
  return (
    <div role="tablist" className="flex flex-wrap items-center gap-2">
      <Funnel
        className="h-3.5 w-3.5 text-[color:var(--text-tertiary)]"
        weight="bold"
        aria-hidden="true"
      />
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

// ─── Filtered empty state ───────────────────────────────────────

function FilteredEmpty({
  label,
  onReset,
  canReset,
}: {
  label: string;
  onReset: () => void;
  canReset: boolean;
}) {
  return (
    <section className="rounded-lg border border-dashed border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-6 py-10 text-center">
      <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        Sin obligaciones
      </p>
      <p className="mt-2 text-sm text-[color:var(--text-primary)]">
        No hay obligaciones para {label}.
      </p>
      {canReset && (
        <Button
          variant="ghost"
          size="sm"
          onClick={onReset}
          className="mt-3"
        >
          Quitar filtro
        </Button>
      )}
    </section>
  );
}

// ─── Detail drawer ──────────────────────────────────────────────

function EventDrawer({
  event,
  onClose,
}: {
  event: CalendarEntry;
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
              {MONTH_LABELS_ES[event.month]} {event.year}
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

          {/* Session 3 (2026-05-21) — catalog v2 fan-out. A v2 row
              carries one ``accepts_documents`` entry per alternative
              doc type (e.g. comprobante bancario / CFDI / cédula /
              resumen for IMSS monthly). Render one disclosure per
              entry so the provider sees first-upload guidance for
              every accepted alternative independently. v1 rows have
              ``accepts_documents=[]`` and keep the legacy single
              disclosure unchanged. */}
          {event.accepts_documents.length > 0 ? (
            <div className="space-y-2">
              <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                Documentos aceptados
              </p>
              <p className="text-[12px] text-[color:var(--text-secondary)]">
                Esta obligación se satisface con cualquiera de los siguientes
                comprobantes. Sube el que tengas a la mano — el calendario
                marca la entrega como recibida en cuanto llega uno.
              </p>
              {event.accepts_documents.map((doc) => (
                <DocumentGuidanceDisclosure
                  key={doc.name}
                  anatomy={doc.anatomy}
                  where_to_obtain={doc.where_to_obtain}
                  common_errors={doc.common_errors}
                  summary_label={`Acerca de ${doc.name}`}
                />
              ))}
            </div>
          ) : (
            <DocumentGuidanceDisclosure
              anatomy={event.anatomy}
              where_to_obtain={event.where_to_obtain}
              common_errors={event.common_errors}
              summary_label="Acerca de este comprobante"
            />
          )}

          {event.submission_id && (
            <div className="flex items-start gap-2 rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)] px-3 py-2">
              <Tray
                className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[color:var(--text-secondary)]"
                weight="bold"
                aria-hidden="true"
              />
              <p className="text-[12px] leading-5 text-[color:var(--text-secondary)]">
                Ya enviaste un documento para este requisito. Toca abajo para revisarlo.
              </p>
            </div>
          )}

          {(() => {
            const action = drawerAction(event);
            const ActionIcon = action.icon;
            return (
              <Button
                asChild
                className="w-full"
                size="lg"
                variant={action.tone === "primary" ? "default" : "outline"}
              >
                <Link href={action.href}>
                  <ActionIcon className="h-4 w-4" weight="bold" aria-hidden="true" />
                  <span>{action.label}</span>
                  <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
                </Link>
              </Button>
            );
          })()}
        </div>
      </aside>
    </div>
  );
}

function drawerAction(event: CalendarEntry): {
  label: string;
  href: string;
  icon: Icon;
  tone: "primary" | "secondary";
} {
  const submissionHref = event.submission_id
    ? `/portal/submissions/${event.submission_id}`
    : event.href;
  switch (event.state) {
    case "approved":
      return {
        label: "Ver documento aprobado",
        href: submissionHref,
        icon: Eye,
        tone: "secondary",
      };
    case "in_review":
    case "uploaded":
      return {
        label: "Ver envío",
        href: submissionHref,
        icon: Eye,
        tone: "secondary",
      };
    case "rejected":
      return {
        label: "Revisar rechazo y corregir",
        href: submissionHref,
        icon: ArrowsClockwise,
        tone: "primary",
      };
    case "needs_review":
      return {
        label: "Revisar y corregir",
        href: submissionHref,
        icon: ArrowsClockwise,
        tone: "primary",
      };
    case "expired":
      return {
        label: "Subir documento actualizado",
        href: event.href,
        icon: CloudArrowUp,
        tone: "primary",
      };
    case "pending":
    case "empty":
    default:
      return {
        label: "Subir documento",
        href: event.href,
        icon: CloudArrowUp,
        tone: "primary",
      };
  }
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

function frequencyLabel(freq: CalendarEntry["frequency"]): string {
  switch (freq) {
    case "mensual":
      return "Mensual";
    case "bimestral":
      return "Bimestral";
    case "cuatrimestral":
      return "Cuatrimestral";
    case "anual":
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

const LEGEND_STATES: CalendarEntry["state"][] = [
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
    <section className="rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
          Leyenda
        </p>
        <ul className="flex flex-wrap gap-1.5">
          {LEGEND_STATES.map((state) => (
            <li key={state}>
              <DocStateBadge state={state} />
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

