"use client";

import { useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  UploadCloud,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  INSTITUTION_LABELS,
  MONTH_LABELS_ES,
  type CalendarItem,
  type CalendarPayload,
  type RequirementStatus,
} from "@/lib/portal-client";
import { RequirementStatusBadge } from "./requirement-status-badge";

const ATTENTION_STATUSES: RequirementStatus[] = [
  "rechazado",
  "vencido",
  "posible_mismatch",
  "requiere_aclaracion",
];

type RecommendedAction = {
  key: string;
  month: number;
  institution: string;
  item: CalendarItem;
};

type CalendarOverviewData = {
  attention: number;
  dueThisMonth: number | null;
  expected: number;
  received: number;
  covered: number;
  isComplete: boolean;
};

type Props = {
  data: CalendarPayload;
};

export function ComplianceCalendar({ data }: Props) {
  const initial = currentMonthIndex();
  const [selected, setSelected] = useState<number>(initial);

  const nowMonth = useMemo(() => resolveCurrentMonth(data.year), [data.year]);
  const overview = useMemo(() => summarizeCalendar(data, nowMonth), [data, nowMonth]);
  const actions = useMemo(
    () => buildRecommendedActions(data, nowMonth),
    [data, nowMonth],
  );

  const month = data.months.find((m) => m.month === selected) ?? data.months[0];

  return (
    <div className="space-y-5">
      <CalendarOverview overview={overview} />
      {actions.length > 0 ? <RecommendedActionsCard actions={actions} /> : null}

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <CardTitle>Calendario {data.year}</CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                Obligaciones REPSE mes a mes: SAT mensual, IMSS mensual, INFONAVIT bimestral,
                Acuses cuatrimestrales y declaración anual.
              </p>
            </div>
            <Badge variant="outline">
              {data.persona_type === "moral" ? "Persona Moral" : "Persona Física"}
            </Badge>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {data.months.map((m) => (
              <button
                key={m.month}
                type="button"
                onClick={() => setSelected(m.month)}
                className={`rounded-md border px-3 py-1.5 text-xs ${
                  selected === m.month
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-white hover:bg-muted"
                }`}
              >
                <span className="font-semibold">{MONTH_LABELS_ES[m.month]}</span>
                <span className="ml-2 opacity-80">
                  {m.received}/{m.expected}
                </span>
              </button>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          <div className="mb-4 flex items-center justify-between">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setSelected((s) => Math.max(1, s - 1))}
              disabled={selected === 1}
            >
              <ChevronLeft className="h-4 w-4" aria-hidden="true" /> Mes anterior
            </Button>
            <h3 className="text-lg font-semibold">
              {MONTH_LABELS_ES[month.month]} {data.year}
            </h3>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setSelected((s) => Math.min(12, s + 1))}
              disabled={selected === 12}
            >
              Siguiente mes <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>

          {month.institutions.length === 0 ? (
            <p className="rounded-md border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
              Sin obligaciones recurrentes para este mes.
            </p>
          ) : (
            <div className="space-y-4">
              {month.institutions.map((inst) => (
                <section
                  key={inst.institution}
                  className="rounded-md border border-border bg-white p-4"
                  data-institution={inst.institution}
                >
                  <header className="flex flex-wrap items-center justify-between gap-2">
                    <h4 className="text-sm font-semibold">
                      {INSTITUTION_LABELS[inst.institution] ?? inst.institution}
                    </h4>
                    <span className="text-xs text-muted-foreground">
                      {inst.received} de {inst.expected} entregados
                    </span>
                  </header>
                  <ul className="mt-3 space-y-2">
                    {inst.items.map((item) => {
                      const uploadHref = buildCalendarUploadHref(inst.institution, item);
                      return (
                        <li
                          key={item.code}
                          className="flex flex-col gap-2 rounded-md border border-border/70 px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
                        >
                          <div className="min-w-0">
                            <p className="text-sm font-medium">{item.name}</p>
                            <p className="text-xs text-muted-foreground">{item.period_label}</p>
                          </div>
                          <div className="flex items-center gap-2">
                            <RequirementStatusBadge status={item.status} />
                            <Button asChild size="sm" variant="outline">
                              <Link href={uploadHref}>
                                <UploadCloud className="h-4 w-4" aria-hidden="true" />
                                {item.status === "pendiente" ? "Cargar" : "Recargar"}
                              </Link>
                            </Button>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function CalendarOverview({ overview }: { overview: CalendarOverviewData }) {
  const attentionActive = overview.attention > 0;
  const dueActive = (overview.dueThisMonth ?? 0) > 0;

  return (
    <section
      className="grid grid-cols-1 gap-3 sm:grid-cols-3"
      aria-label="Resumen del calendario"
    >
      <OverviewTile
        tone={
          attentionActive
            ? "border-amber-300 bg-amber-50"
            : "border-border bg-white"
        }
        icon={
          attentionActive ? (
            <AlertTriangle className="h-4 w-4 text-amber-700" aria-hidden="true" />
          ) : (
            <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" />
          )
        }
        label="Atención requerida"
        labelTone={attentionActive ? "text-amber-800" : "text-muted-foreground"}
        value={`${overview.attention}`}
        helper={
          attentionActive
            ? overview.attention === 1
              ? "documento que requiere acción"
              : "documentos que requieren acción"
            : "sin pendientes urgentes"
        }
      />
      <OverviewTile
        tone={dueActive ? "border-primary/30 bg-primary/5" : "border-border bg-white"}
        icon={<CalendarDays className="h-4 w-4 text-primary" aria-hidden="true" />}
        label="Vence este mes"
        labelTone={dueActive ? "text-primary" : "text-muted-foreground"}
        value={overview.dueThisMonth === null ? "—" : `${overview.dueThisMonth}`}
        helper={
          overview.dueThisMonth === null
            ? "fuera del año en curso"
            : overview.dueThisMonth === 0
              ? "nada vence este mes"
              : overview.dueThisMonth === 1
                ? "obligación por entregar"
                : "obligaciones por entregar"
        }
      />
      <CoverageTile overview={overview} />
    </section>
  );
}

function OverviewTile({
  tone,
  icon,
  label,
  labelTone,
  value,
  helper,
}: {
  tone: string;
  icon: ReactNode;
  label: string;
  labelTone: string;
  value: string;
  helper: string;
}) {
  return (
    <div className={`rounded-md border p-4 ${tone}`}>
      <div className={`flex items-center gap-2 text-xs font-medium uppercase tracking-wide ${labelTone}`}>
        {icon}
        <span>{label}</span>
      </div>
      <p className="mt-2 text-2xl font-semibold tabular-nums">{value}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{helper}</p>
    </div>
  );
}

function CoverageTile({ overview }: { overview: CalendarOverviewData }) {
  const tone = overview.isComplete
    ? "border-emerald-200 bg-emerald-50"
    : "border-border bg-white";
  const labelTone = overview.isComplete ? "text-emerald-800" : "text-muted-foreground";
  const fill = overview.isComplete ? "bg-emerald-500" : "bg-primary";
  return (
    <div className={`rounded-md border p-4 ${tone}`}>
      <div className={`flex items-center gap-2 text-xs font-medium uppercase tracking-wide ${labelTone}`}>
        <ShieldCheck
          className={`h-4 w-4 ${overview.isComplete ? "text-emerald-600" : "text-primary"}`}
          aria-hidden="true"
        />
        <span>Cubierto</span>
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <p className="text-2xl font-semibold tabular-nums">{overview.covered}%</p>
        <p className="text-xs text-muted-foreground tabular-nums">
          {overview.received}/{overview.expected}
        </p>
      </div>
      <div
        className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={overview.covered}
        aria-label="Avance del calendario anual"
      >
        <div
          className={`h-full rounded-full transition-[width] duration-500 ease-out ${fill}`}
          style={{ width: `${overview.covered}%` }}
        />
      </div>
    </div>
  );
}

function RecommendedActionsCard({ actions }: { actions: RecommendedAction[] }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
          <CardTitle>Acciones recomendadas hoy</CardTitle>
          <span className="text-xs text-muted-foreground">
            {actions.length === 1
              ? "1 prioridad"
              : `${actions.length} prioridades`}
          </span>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          Empezamos por lo que requiere atención y por lo que vence este mes. Al abrir un
          documento, el formulario llega con tu contexto bloqueado.
        </p>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {actions.map((entry) => {
            const needsAttention = ATTENTION_STATUSES.includes(entry.item.status);
            const href = buildCalendarUploadHref(entry.institution, entry.item);
            const ctaLabel = needsAttention ? "Resolver" : "Cargar";
            return (
              <li
                key={entry.key}
                className={`flex flex-col gap-2 rounded-md border p-3 sm:flex-row sm:items-center sm:justify-between ${
                  needsAttention
                    ? "border-amber-300 bg-amber-50"
                    : "border-border bg-white"
                }`}
              >
                <div className="flex items-start gap-3">
                  <div
                    className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                      needsAttention
                        ? "bg-amber-500 text-white"
                        : "bg-primary text-primary-foreground"
                    }`}
                  >
                    {needsAttention ? (
                      <AlertTriangle className="h-4 w-4" aria-hidden="true" />
                    ) : (
                      <UploadCloud className="h-4 w-4" aria-hidden="true" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{entry.item.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {INSTITUTION_LABELS[entry.institution] ?? entry.institution}
                      {" · "}
                      {MONTH_LABELS_ES[entry.month]}
                      {" · "}
                      {entry.item.period_label}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <RequirementStatusBadge status={entry.item.status} />
                  <Button asChild size="sm">
                    <Link href={href} aria-label={`${ctaLabel} ${entry.item.name}`}>
                      <UploadCloud className="h-4 w-4" aria-hidden="true" />
                      {ctaLabel}
                    </Link>
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

function summarizeCalendar(
  data: CalendarPayload,
  nowMonth: number | null,
): CalendarOverviewData {
  let attention = 0;
  let dueThisMonth: number | null = nowMonth === null ? null : 0;
  let expected = 0;
  let received = 0;
  for (const m of data.months) {
    expected += m.expected;
    received += m.received;
    for (const inst of m.institutions) {
      for (const item of inst.items) {
        if (ATTENTION_STATUSES.includes(item.status)) {
          attention += 1;
        }
        if (
          dueThisMonth !== null &&
          nowMonth !== null &&
          m.month === nowMonth &&
          item.status === "pendiente"
        ) {
          dueThisMonth += 1;
        }
      }
    }
  }
  const covered = expected === 0 ? 0 : Math.round((received / expected) * 100);
  return {
    attention,
    dueThisMonth,
    expected,
    received,
    covered,
    isComplete: expected > 0 && received >= expected,
  };
}

function buildRecommendedActions(
  data: CalendarPayload,
  nowMonth: number | null,
): RecommendedAction[] {
  const attention: RecommendedAction[] = [];
  const currentMonthPending: RecommendedAction[] = [];
  const otherPending: RecommendedAction[] = [];
  for (const m of data.months) {
    for (const inst of m.institutions) {
      for (const item of inst.items) {
        const entry: RecommendedAction = {
          key: `${m.month}-${inst.institution}-${item.code}`,
          month: m.month,
          institution: inst.institution,
          item,
        };
        if (ATTENTION_STATUSES.includes(item.status)) {
          attention.push(entry);
        } else if (item.status === "pendiente") {
          if (nowMonth !== null && m.month === nowMonth) {
            currentMonthPending.push(entry);
          } else if (nowMonth === null || m.month >= nowMonth) {
            otherPending.push(entry);
          }
        }
      }
    }
  }
  attention.sort((a, b) => a.month - b.month);
  otherPending.sort((a, b) => a.month - b.month);
  return [...attention, ...currentMonthPending, ...otherPending].slice(0, 3);
}

function buildCalendarUploadHref(institution: string, item: CalendarItem): string {
  // Emit both canonical keys (preferred by the wizard + backend) and the
  // legacy name + label (still accepted during the deprecation window).
  const params = new URLSearchParams({
    requirement: item.name,
    requirement_code: item.code,
    institution,
    load_type: item.frequency,
    period_label: item.period_label,
    period_key: item.period_key,
  });
  return `/portal/upload?${params.toString()}`;
}

function resolveCurrentMonth(year: number): number | null {
  if (typeof window === "undefined") {
    return null;
  }
  const today = new Date();
  if (today.getFullYear() !== year) {
    return null;
  }
  return today.getMonth() + 1;
}

function currentMonthIndex(): number {
  if (typeof window === "undefined") {
    return 1;
  }
  return new Date().getMonth() + 1;
}
