"use client";

import { useMemo, useState } from "react";
import {
  ArrowLeft,
  Buildings,
  Funnel,
  Scales,
  ShieldCheck,
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
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { INSTITUTION_LABELS, MONTH_LABELS_SHORT_ES } from "@/lib/api/portal";
import type { DocumentStateCode } from "@/lib/types";

const INSTITUTION_ICON: Record<CalendarInstitutionCode, Icon> = {
  sat: Scales,
  imss: Buildings,
  infonavit: Buildings,
  stps_repse: ShieldCheck,
};

const CURRENT_MONTH = 5;
const YEAR = 2026;

type Slot = {
  obligation: string;
  state: DocumentStateCode;
};

function makeEntry(
  inst: CalendarInstitutionCode,
  month: number,
  slot: Slot,
  idx: number,
): CalendarEntry {
  return {
    id: `${inst}-${month}-${idx}-${slot.obligation}`,
    year: YEAR,
    month,
    institution: inst,
    obligation: slot.obligation,
    required_document: slot.obligation,
    deadline_iso: `${YEAR}-${String(month).padStart(2, "0")}-17`,
    state: slot.state,
    suggested_action: "Sube el comprobante o programa una revisión.",
    frequency: "mensual",
    href: "#",
    submission_id: null,
    filename: null,
    submitted_at: null,
    anatomy: "",
    where_to_obtain: "",
    common_errors: [],
    accepts_documents: [],
  };
}

function buildMockEvents(): CalendarEntry[] {
  const entries: CalendarEntry[] = [];

  const satMonthly: Slot[] = [
    { obligation: "Declaración ISR mensual", state: "approved" },
    { obligation: "Pago IVA", state: "approved" },
    { obligation: "Retenciones honorarios", state: "approved" },
    { obligation: "DIOT", state: "approved" },
  ];
  const satCurrent: Slot[] = [
    { obligation: "Declaración ISR mensual", state: "in_review" },
    { obligation: "Pago IVA", state: "uploaded" },
    { obligation: "Retenciones honorarios", state: "pending" },
    { obligation: "DIOT", state: "pending" },
    { obligation: "Constancia situación fiscal", state: "needs_review" },
  ];
  const satPending: Slot[] = [
    { obligation: "Declaración ISR mensual", state: "pending" },
    { obligation: "Pago IVA", state: "pending" },
    { obligation: "Retenciones honorarios", state: "pending" },
    { obligation: "DIOT", state: "pending" },
  ];

  for (let m = 1; m <= 12; m++) {
    let slots: Slot[];
    if (m < CURRENT_MONTH) {
      slots = m === 2
        ? [
            ...satMonthly.slice(0, 3),
            { obligation: "DIOT", state: "rejected" as DocumentStateCode },
          ]
        : satMonthly;
    } else if (m === CURRENT_MONTH) {
      slots = satCurrent;
    } else {
      slots = satPending;
    }
    slots.forEach((s, i) => entries.push(makeEntry("sat", m, s, i)));
  }

  const imssSlots: Slot[] = [
    { obligation: "Cédula SUA mensual", state: "approved" },
    { obligation: "Comprobante pago IMSS", state: "approved" },
    { obligation: "Carta liberación IMSS", state: "approved" },
  ];
  const imssCurrent: Slot[] = [
    { obligation: "Cédula SUA mensual", state: "uploaded" },
    { obligation: "Comprobante pago IMSS", state: "pending" },
    { obligation: "Carta liberación IMSS", state: "pending" },
  ];
  const imssPast: Slot[] = [
    { obligation: "Cédula SUA mensual", state: "approved" },
    { obligation: "Comprobante pago IMSS", state: "approved" },
    { obligation: "Carta liberación IMSS", state: "expired" },
  ];
  for (let m = 1; m <= 12; m++) {
    let slots: Slot[];
    if (m === 3) slots = imssPast;
    else if (m < CURRENT_MONTH) slots = imssSlots;
    else if (m === CURRENT_MONTH) slots = imssCurrent;
    else slots = [
      { obligation: "Cédula SUA mensual", state: "pending" as DocumentStateCode },
      { obligation: "Comprobante pago IMSS", state: "pending" as DocumentStateCode },
      { obligation: "Carta liberación IMSS", state: "pending" as DocumentStateCode },
    ];
    slots.forEach((s, i) => entries.push(makeEntry("imss", m, s, i)));
  }

  const infBimestralMonths = [1, 3, 5, 7, 9, 11];
  const infSlots = (state: DocumentStateCode): Slot[] => [
    { obligation: "Cédula INFONAVIT bimestral", state },
    { obligation: "Comprobante pago INFONAVIT", state },
    { obligation: "Aviso de retención", state },
  ];
  for (const m of infBimestralMonths) {
    let state: DocumentStateCode;
    if (m < CURRENT_MONTH) state = "approved";
    else if (m === CURRENT_MONTH) state = "in_review";
    else state = "pending";
    infSlots(state).forEach((s, i) => entries.push(makeEntry("infonavit", m, s, i)));
  }

  entries.push(
    makeEntry("stps_repse", 1, { obligation: "Aviso REPSE Q1", state: "approved" }, 0),
    makeEntry("stps_repse", 4, { obligation: "Padrón REPSE actualizado", state: "approved" }, 0),
    makeEntry("stps_repse", CURRENT_MONTH, { obligation: "Aviso REPSE Q2", state: "approved" }, 0),
    makeEntry("stps_repse", 9, { obligation: "Aviso REPSE Q3", state: "pending" }, 0),
  );

  return entries;
}

const LEGEND_STATES: DocumentStateCode[] = [
  "approved",
  "in_review",
  "uploaded",
  "pending",
  "needs_review",
  "rejected",
  "expired",
  "empty",
];

const VALID: ReadonlySet<string> = new Set(["sat", "imss", "infonavit", "stps_repse"]);

export default function CalendarPreviewPage() {
  const events = useMemo(() => buildMockEvents(), []);
  const [filterInstitution, setFilterInstitution] = useState<
    CalendarInstitutionCode | "all"
  >("all");
  const [, setSelectedId] = useState<string | null>(null);

  const filteredEvents = useMemo(() => {
    if (filterInstitution === "all") return events;
    return events.filter((e) => e.institution === filterInstitution);
  }, [filterInstitution, events]);

  const eventsByCell = useMemo(() => {
    const m = new Map<string, CalendarEntry[]>();
    for (const e of filteredEvents) {
      const k = `${e.institution}-${e.month}`;
      const list = m.get(k) ?? [];
      list.push(e);
      m.set(k, list);
    }
    return m;
  }, [filteredEvents]);

  const eventsByInstitution = useMemo(() => {
    const m = new Map<CalendarInstitutionCode, CalendarEntry[]>();
    for (const inst of CALENDAR_INSTITUTIONS) m.set(inst, []);
    for (const e of filteredEvents) m.get(e.institution)?.push(e);
    return m;
  }, [filteredEvents]);

  const visibleInstitutions =
    filterInstitution === "all"
      ? CALENDAR_INSTITUTIONS
      : CALENDAR_INSTITUTIONS.filter((i) => i === filterInstitution);

  const counts: Record<CalendarInstitutionCode | "all", number> = {
    all: events.length,
    sat: events.filter((e) => e.institution === "sat").length,
    imss: events.filter((e) => e.institution === "imss").length,
    infonavit: events.filter((e) => e.institution === "infonavit").length,
    stps_repse: events.filter((e) => e.institution === "stps_repse").length,
  };

  const options: { value: CalendarInstitutionCode | "all"; label: string }[] = [
    { value: "all", label: "Todas" },
    { value: "sat", label: "SAT" },
    { value: "imss", label: "IMSS" },
    { value: "infonavit", label: "INFONAVIT" },
    { value: "stps_repse", label: "STPS / REPSE" },
  ];

  return (
    <main className="mx-auto w-full max-w-screen-2xl space-y-6 px-5 py-8 sm:px-6 lg:px-8 2xl:px-10">
      <div className="rounded-lg border border-dashed border-[color:var(--border-default)] bg-[color:var(--surface-sunken)] px-4 py-2 text-[11px] text-[color:var(--text-secondary)]">
        <strong className="font-semibold">Dev preview</strong> · Datos sintéticos. Hoy = mayo {YEAR}. Esta ruta es solo para QA visual; no afecta el calendario real.
      </div>

      <PageHeader
        eyebrow={`Calendario REPSE · ${YEAR}`}
        title="Tu año de cumplimiento de un vistazo"
        description="Cada celda muestra las obligaciones de ese mes; pasa el cursor para ver el detalle o toca para abrir la siguiente acción."
        actions={
          <Button asChild variant="outline" size="sm">
            <a href="/portal/dashboard">
              <ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
              Dashboard
            </a>
          </Button>
        }
      />

      <div role="tablist" className="flex flex-wrap items-center gap-2">
        <Funnel
          className="h-3.5 w-3.5 text-[color:var(--text-tertiary)]"
          weight="bold"
          aria-hidden="true"
        />
        {options.map((opt) => {
          const active = filterInstitution === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setFilterInstitution(opt.value)}
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

      <section
        className="cw-fade-up overflow-x-auto rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs"
        aria-label="Cuadrícula del calendario"
      >
        <table className="w-full min-w-[860px] border-collapse text-sm">
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
                const isCurrent = monthNum === CURRENT_MONTH;
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
                    className="sticky left-0 z-10 min-w-[240px] border-r border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-4 py-3 text-left align-middle"
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
                    const isCurrent = month === CURRENT_MONTH;
                    const isPast = month < CURRENT_MONTH;
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
      {/* keep VALID referenced for future filter-validation parity */}
      <span hidden>{VALID.size}</span>
    </main>
  );
}
