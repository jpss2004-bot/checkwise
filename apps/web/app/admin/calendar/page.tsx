"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  CalendarBlank,
  ClipboardText,
  PencilSimpleLine,
  WarningOctagon,
} from "@phosphor-icons/react";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Input } from "@/components/ui/input";
import {
  ErrorState,
  Skeleton,
} from "@/components/checkwise/portal/state-surfaces";

import { AdminShell } from "../_shell";
import {
  ComplianceMatrix,
  type ComplianceMatrixCell,
  type ComplianceMatrixRow,
} from "@/components/checkwise/calendar/compliance-matrix";
import { AdminObligationBlock } from "@/components/checkwise/calendar/admin-obligation-block";
import {
  RISK_ORDER,
  SEMAPHORE_DOT,
  type CalendarRisk,
} from "@/components/checkwise/calendar/calendar-shared";
import {
  getAdminCalendarGrid,
  getRollup,
  type AdminCalendarGrid,
  type AdminCalendarObligation,
  type AdminCalendarRow,
  type AdminRollup,
} from "@/lib/api/admin";
import { MONTH_LABELS_ES, MONTH_LABELS_SHORT_ES } from "@/lib/api/portal";

const SEMAPHORE_RANK: Record<string, number> = { red: 0, yellow: 1, green: 2 };

function cellMap(grid: AdminCalendarGrid): Map<string, ComplianceMatrixCell> {
  const map = new Map<string, ComplianceMatrixCell>();
  for (const c of grid.cells) {
    map.set(`${c.row_id}-${c.month}`, {
      count: c.count,
      worstRisk: c.worst_risk as CalendarRisk,
    });
  }
  return map;
}

export default function AdminCalendarPage() {
  const [today] = useState(() => new Date());
  const [year, setYear] = useState<number>(
    () => new Date().getFullYear() || 2026,
  );
  const currentMonth = today.getFullYear() === year ? today.getMonth() + 1 : 1;

  const [grid, setGrid] = useState<AdminCalendarGrid | null>(null);
  const [rollup, setRollup] = useState<AdminRollup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  // Selection drives the detail panel: a month (whole portfolio that month),
  // or a row (client/provider) within that month. ``selectedMonth`` also
  // refetches the top grid so we have that month's obligations.
  const [selectedMonth, setSelectedMonth] = useState<number>(currentMonth);
  const [selectedRowId, setSelectedRowId] = useState<string | null>(null);
  const [showAllClients, setShowAllClients] = useState(false);

  // Drill: when set, the grid shows one client's providers×months (its full
  // obligation set comes with it, so selection within the drill is local).
  const [drillClientId, setDrillClientId] = useState<string | null>(null);
  const [drill, setDrill] = useState<AdminCalendarGrid | null>(null);

  // Top-level grid + rollup: refetch on year / selectedMonth / reload.
  useEffect(() => {
    let cancelled = false;
    setError(null);
    Promise.all([
      getAdminCalendarGrid({ year, month: selectedMonth }),
      getRollup(),
    ])
      .then(([g, r]) => {
        if (cancelled) return;
        setGrid(g);
        setRollup(r);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(
          err instanceof Error ? err.message : "Error al cargar el calendario.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [year, selectedMonth, reloadKey]);

  // Drill fetch when a client is selected.
  useEffect(() => {
    if (!drillClientId) {
      setDrill(null);
      return;
    }
    let cancelled = false;
    setDrill(null);
    getAdminCalendarGrid({ year, client_id: drillClientId })
      .then((d) => {
        if (!cancelled) setDrill(d);
      })
      .catch(() => {
        if (!cancelled) setDrillClientId(null);
      });
    return () => {
      cancelled = true;
    };
  }, [drillClientId, year]);

  function scrollToDetail() {
    requestAnimationFrame(() => {
      document
        .getElementById("admin-calendar-detail")
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function selectMonth(month: number) {
    setSelectedMonth(month);
    setSelectedRowId(null);
    scrollToDetail();
  }

  function selectCell(rowId: string, month: number) {
    setSelectedMonth(month);
    setSelectedRowId(rowId);
    scrollToDetail();
  }

  const inDrill = Boolean(drillClientId);
  const activeGrid = inDrill ? drill : grid;

  // Rows for the matrix. Top level: clients, worst-first, optionally only the
  // at-risk ones (the dashboard already lists every client). Drill: providers.
  const matrixRows = useMemo<ComplianceMatrixRow[]>(() => {
    if (!activeGrid) return [];
    const rows = [...activeGrid.rows];
    rows.sort(
      (a, b) =>
        (SEMAPHORE_RANK[a.semaphore_level] ?? 3) -
          (SEMAPHORE_RANK[b.semaphore_level] ?? 3) ||
        a.compliance_pct - b.compliance_pct ||
        a.name.localeCompare(b.name),
    );
    const scoped =
      inDrill || showAllClients
        ? rows
        : rows.filter((r) => r.semaphore_level !== "green");
    return scoped.map((r) => ({
      id: r.id,
      name: r.name,
      semaphore_level: r.semaphore_level,
      subtitle: rowSubtitle(r),
    }));
  }, [activeGrid, inDrill, showAllClients]);

  const matrixCells = useMemo(
    () =>
      activeGrid ? cellMap(activeGrid) : new Map<string, ComplianceMatrixCell>(),
    [activeGrid],
  );

  const hiddenGreen = useMemo(() => {
    if (inDrill || showAllClients || !grid) return 0;
    return grid.rows.filter((r) => r.semaphore_level === "green").length;
  }, [grid, inDrill, showAllClients]);

  // Obligations behind the current selection. At the top level we hold only
  // the selected month's obligations (across the portfolio); on drill we hold
  // the whole client and filter by month locally.
  const detailObligations = useMemo<AdminCalendarObligation[]>(() => {
    if (!activeGrid) return [];
    let obs = activeGrid.obligations;
    if (inDrill) obs = obs.filter((o) => o.due_month === selectedMonth);
    if (selectedRowId) {
      obs = obs.filter((o) =>
        inDrill ? o.vendor_id === selectedRowId : o.client_id === selectedRowId,
      );
    }
    return obs;
  }, [activeGrid, inDrill, selectedMonth, selectedRowId]);

  return (
    <AdminShell
      title="Calendario operativo"
      description="El año de cumplimiento de toda la cartera: clientes en las filas, meses en las columnas, el color marca lo más crítico que vence ese mes. Entra a un cliente para ver sus proveedores."
      actions={<YearPicker year={year} onYear={setYear} />}
    >
      {error ? (
        <ErrorState
          title="No pudimos cargar el calendario"
          description={error}
          onRetry={() => setReloadKey((k) => k + 1)}
        />
      ) : !grid || !rollup ? (
        <CalendarSkeleton />
      ) : (
        <div className="space-y-6">
          <TriageBand grid={grid} rollup={rollup} />

          <ForecastWaveStrip
            grid={grid}
            currentMonth={today.getFullYear() === year ? currentMonth : null}
            selectedMonth={inDrill ? null : selectedMonth}
            onSelectMonth={selectMonth}
          />

          <Surface
            title={
              inDrill ? `${drill?.client_name ?? "Cliente"} · ${year}` : `Cartera ${year}`
            }
            description={
              inDrill
                ? "Proveedores de este cliente por mes. Vuelve a la cartera para comparar clientes."
                : "Cada cliente por mes. Entra a un cliente para ver sus proveedores, o toca un mes para ver todo lo que vence."
            }
            actions={
              inDrill ? (
                <button
                  type="button"
                  onClick={() => {
                    setDrillClientId(null);
                    setSelectedRowId(null);
                  }}
                  className="inline-flex items-center gap-1 text-xs font-medium text-[color:var(--text-brand)] hover:underline"
                >
                  <ArrowLeft className="h-3 w-3" weight="bold" aria-hidden="true" />
                  Volver a la cartera
                </button>
              ) : (
                <ScopeToggle
                  showAll={showAllClients}
                  hiddenGreen={hiddenGreen}
                  onToggle={() => setShowAllClients((v) => !v)}
                />
              )
            }
            bodyClassName="p-4"
          >
            {!activeGrid ? (
              <Skeleton className="h-64 w-full rounded-lg" />
            ) : matrixRows.length === 0 ? (
              <EmptyGrid
                showAll={showAllClients}
                onShowAll={() => setShowAllClients(true)}
              />
            ) : (
              <ComplianceMatrix
                rows={matrixRows}
                cells={matrixCells}
                currentMonth={today.getFullYear() === year ? currentMonth : null}
                rowHeader={inDrill ? "Proveedor" : "Cliente"}
                selected={{ rowId: selectedRowId, month: selectedMonth }}
                onSelectCell={selectCell}
                onSelectMonth={selectMonth}
                onSelectRow={
                  inDrill
                    ? (rowId) => selectCell(rowId, selectedMonth)
                    : (rowId) => {
                        setDrillClientId(rowId);
                        setSelectedRowId(null);
                      }
                }
              />
            )}
          </Surface>

          <div id="admin-calendar-detail" className="scroll-mt-4">
            <DetailPanel
              obligations={detailObligations}
              monthLabel={MONTH_LABELS_ES[selectedMonth]}
              year={year}
              scopeLabel={inDrill ? (drill?.client_name ?? null) : null}
              today={today}
              truncated={grid.truncated}
            />
          </div>
        </div>
      )}
    </AdminShell>
  );
}

function rowSubtitle(r: AdminCalendarRow): string {
  if (r.overdue_count > 0) return `${r.compliance_pct}% · ${r.overdue_count} vencido`;
  if (r.due_soon_count > 0)
    return `${r.compliance_pct}% · ${r.due_soon_count} por vencer`;
  return `${r.compliance_pct}% al día`;
}

// ─── Year picker ────────────────────────────────────────────────

function YearPicker({
  year,
  onYear,
}: {
  year: number;
  onYear: (y: number) => void;
}) {
  return (
    <label className="flex items-center gap-2 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-1 text-xs">
      <CalendarBlank
        className="h-3.5 w-3.5 text-[color:var(--text-secondary)]"
        weight="bold"
        aria-hidden="true"
      />
      <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        Año
      </span>
      <Input
        type="number"
        min={2021}
        max={2030}
        value={year}
        onChange={(e) => onYear(Number(e.target.value))}
        className="h-7 w-20 border-0 bg-transparent p-0 font-mono text-sm font-semibold focus-visible:ring-0"
      />
    </label>
  );
}

function ScopeToggle({
  showAll,
  hiddenGreen,
  onToggle,
}: {
  showAll: boolean;
  hiddenGreen: number;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={!showAll}
      className="inline-flex items-center gap-1.5 rounded-full border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-1.5 text-xs font-medium text-[color:var(--text-secondary)] transition-colors hover:bg-[color:var(--surface-hover)]"
    >
      {showAll
        ? "Mostrando todos los clientes"
        : `Solo en riesgo${hiddenGreen ? ` · ${hiddenGreen} al día ocultos` : ""}`}
    </button>
  );
}

// ─── Triage band (Esta semana) ──────────────────────────────────

function TriageBand({
  grid,
  rollup,
}: {
  grid: AdminCalendarGrid;
  rollup: AdminRollup;
}) {
  const slaAtRisk =
    rollup.queue.age_buckets.over_72h + rollup.queue.age_buckets.over_7d;
  const corrections = rollup.inbox.correction_requests_pending;
  return (
    <div>
      <p className="mb-2 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        Esta semana
      </p>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <TriageTile
          value={grid.triage.overdue_total}
          label="Vencido"
          tone="error"
          icon={WarningOctagon}
          scrollTo="admin-calendar-detail"
        />
        <TriageTile
          value={grid.triage.due_7d_total}
          label="Vence ≤ 7 días"
          tone="warning"
          scrollTo="admin-calendar-detail"
        />
        <TriageTile
          value={slaAtRisk}
          label="SLA revisión > 72 h"
          tone="neutral"
          icon={ClipboardText}
          href="/admin/reviewer"
        />
        <TriageTile
          value={corrections}
          label="Correcciones"
          tone="neutral"
          icon={PencilSimpleLine}
          href="/admin/correction-requests"
        />
      </div>
    </div>
  );
}

const TRIAGE_TONE: Record<string, string> = {
  error: "text-[color:var(--status-error-text)]",
  warning: "text-[color:var(--status-warning-text)]",
  neutral: "text-[color:var(--text-primary)]",
};

function TriageTile({
  value,
  label,
  tone,
  icon: Icon,
  href,
  scrollTo,
}: {
  value: number;
  label: string;
  tone: "error" | "warning" | "neutral";
  icon?: typeof WarningOctagon;
  href?: string;
  scrollTo?: string;
}) {
  const body = (
    <>
      <p
        className={
          "font-mono text-3xl font-semibold tabular-nums leading-none " +
          (value > 0 ? TRIAGE_TONE[tone] : "text-[color:var(--text-tertiary)]")
        }
      >
        {value}
      </p>
      <p className="mt-1.5 inline-flex items-center gap-1 text-[12px] text-[color:var(--text-secondary)]">
        {Icon ? <Icon className="h-3.5 w-3.5" weight="bold" aria-hidden="true" /> : null}
        {label}
        {href ? (
          <ArrowRight className="h-3 w-3 opacity-60" weight="bold" aria-hidden="true" />
        ) : null}
      </p>
    </>
  );
  const className =
    "block rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-4 py-3.5 text-left transition-colors hover:bg-[color:var(--surface-hover)]";
  if (href) {
    return (
      <Link href={href} className={className}>
        {body}
      </Link>
    );
  }
  return (
    <button
      type="button"
      onClick={() =>
        scrollTo &&
        document.getElementById(scrollTo)?.scrollIntoView({ behavior: "smooth" })
      }
      className={className}
    >
      {body}
    </button>
  );
}

// ─── Forecast wave strip ────────────────────────────────────────

function ForecastWaveStrip({
  grid,
  currentMonth,
  selectedMonth,
  onSelectMonth,
}: {
  grid: AdminCalendarGrid;
  currentMonth: number | null;
  selectedMonth: number | null;
  onSelectMonth: (month: number) => void;
}) {
  const max = Math.max(1, ...grid.forecast.map((f) => f.total));
  return (
    <Surface
      title="Onda de carga del año"
      description="Obligaciones esperadas por mes en toda la cartera. Toca un mes para ver su detalle."
      bodyClassName="p-4"
    >
      <div className="flex items-end gap-1.5" style={{ height: 96 }}>
        {grid.forecast.map((f) => {
          const isCurrent = currentMonth === f.month;
          const isSelected = selectedMonth === f.month;
          const h = f.total === 0 ? 3 : Math.round(12 + (f.total / max) * 72);
          const insts = Object.entries(f.by_institution)
            .map(([k, v]) => `${k.toUpperCase()}: ${v}`)
            .join(" · ");
          return (
            <button
              key={f.month}
              type="button"
              onClick={() => onSelectMonth(f.month)}
              aria-pressed={isSelected}
              title={`${MONTH_LABELS_ES[f.month]}: ${f.total} esperadas${insts ? ` · ${insts}` : ""}`}
              className="group flex flex-1 flex-col items-center justify-end gap-1 rounded-md px-0.5 py-1 hover:bg-[color:var(--surface-hover)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]"
            >
              <span className="font-mono text-[9px] tabular-nums text-[color:var(--text-tertiary)]">
                {f.total || ""}
              </span>
              <span
                aria-hidden="true"
                style={{ height: h }}
                className={
                  "w-full max-w-[26px] rounded-sm transition-colors " +
                  (isSelected
                    ? "bg-[color:var(--interactive-primary)]"
                    : isCurrent
                      ? "bg-[color:var(--text-secondary)]"
                      : "bg-[color:var(--border-strong)] group-hover:bg-[color:var(--text-tertiary)]")
                }
              />
              <span
                className={
                  "text-[10px] font-medium uppercase tracking-wide " +
                  (isCurrent
                    ? "text-[color:var(--text-brand)]"
                    : "text-[color:var(--text-tertiary)]")
                }
              >
                {MONTH_LABELS_SHORT_ES[f.month - 1]}
              </span>
            </button>
          );
        })}
      </div>
    </Surface>
  );
}

// ─── Detail panel ───────────────────────────────────────────────

function DetailPanel({
  obligations,
  monthLabel,
  year,
  scopeLabel,
  today,
  truncated,
}: {
  obligations: AdminCalendarObligation[];
  monthLabel: string;
  year: number;
  scopeLabel: string | null;
  today: Date;
  truncated: boolean;
}) {
  // Group by client → provider, each group sorted worst-first.
  const groups = useMemo(() => {
    const byKey = new Map<
      string,
      { clientName: string; vendorName: string; items: AdminCalendarObligation[] }
    >();
    for (const o of obligations) {
      const key = `${o.client_id}::${o.vendor_id}`;
      const g = byKey.get(key) ?? {
        clientName: o.client_name,
        vendorName: o.vendor_name,
        items: [],
      };
      g.items.push(o);
      byKey.set(key, g);
    }
    const worstOf = (items: AdminCalendarObligation[]) =>
      Math.min(...items.map((i) => RISK_ORDER[i.risk_level as CalendarRisk] ?? 9));
    return [...byKey.values()].sort((a, b) => worstOf(a.items) - worstOf(b.items));
  }, [obligations]);

  const title = scopeLabel
    ? `${scopeLabel} · ${monthLabel} ${year}`
    : `${monthLabel} ${year} · toda la cartera`;

  return (
    <Surface bodyClassName="p-4 sm:p-5">
      <div className="mb-4 border-b border-[color:var(--border-subtle)] pb-3">
        <p className="text-sm font-semibold text-[color:var(--text-primary)]">{title}</p>
        <p className="text-xs text-[color:var(--text-tertiary)]">
          {obligations.length}{" "}
          {obligations.length === 1 ? "obligación" : "obligaciones"}
          {groups.length
            ? ` · ${groups.length} ${groups.length === 1 ? "proveedor" : "proveedores"}`
            : ""}
        </p>
      </div>

      {groups.length === 0 ? (
        <p className="px-1 py-6 text-center text-sm text-[color:var(--text-secondary)]">
          Sin obligaciones en esta selección.
        </p>
      ) : (
        <div className="space-y-5">
          {groups.map((g) => (
            <section key={`${g.clientName}-${g.vendorName}`}>
              <h3 className="mb-2 flex flex-wrap items-baseline gap-x-2 text-sm font-semibold text-[color:var(--text-primary)]">
                <span className="flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className={
                      "h-2.5 w-2.5 shrink-0 rounded-full " + SEMAPHORE_DOT[worstDot(g.items)]
                    }
                  />
                  {g.vendorName}
                </span>
                <span className="text-xs font-normal text-[color:var(--text-tertiary)]">
                  {g.clientName}
                </span>
                <span className="font-mono text-[11px] font-normal tabular-nums text-[color:var(--text-tertiary)]">
                  {g.items.length}
                </span>
              </h3>
              <ul className="space-y-2">
                {g.items
                  .slice()
                  .sort(
                    (a, b) =>
                      (RISK_ORDER[a.risk_level as CalendarRisk] ?? 9) -
                      (RISK_ORDER[b.risk_level as CalendarRisk] ?? 9),
                  )
                  .map((o) => (
                    <AdminObligationBlock
                      key={`${o.vendor_id}-${o.requirement_name}-${o.period_key ?? ""}`}
                      obligation={o}
                      today={today}
                    />
                  ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      {truncated ? (
        <p className="mt-4 text-[11px] text-[color:var(--text-tertiary)]">
          La cartera excede el límite de escaneo; se muestran los primeros
          clientes.
        </p>
      ) : null}
    </Surface>
  );
}

function worstDot(items: AdminCalendarObligation[]): "red" | "yellow" | "green" {
  const worst = Math.min(
    ...items.map((i) => RISK_ORDER[i.risk_level as CalendarRisk] ?? 9),
  );
  if (worst <= 1) return "red";
  if (worst <= 2) return "yellow";
  return "green";
}

// ─── Empty + loading states ─────────────────────────────────────

function EmptyGrid({
  showAll,
  onShowAll,
}: {
  showAll: boolean;
  onShowAll: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-12 text-center">
      <p className="text-[13px] font-medium text-[color:var(--text-primary)]">
        {showAll ? "Sin clientes en la cartera" : "Ningún cliente en riesgo"}
      </p>
      <p className="max-w-md text-[12px] text-[color:var(--text-secondary)]">
        {showAll
          ? "Aún no hay clientes con proveedores activos."
          : "Toda la cartera está al día este año."}
      </p>
      {!showAll ? (
        <button
          type="button"
          onClick={onShowAll}
          className="mt-1 text-xs font-medium text-[color:var(--text-brand)] hover:underline"
        >
          Mostrar todos los clientes
        </button>
      ) : null}
    </div>
  );
}

function CalendarSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-live="polite">
      <span className="sr-only">Cargando calendario operativo…</span>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-20 w-full rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-28 w-full rounded-lg" />
      <Skeleton className="h-72 w-full rounded-lg" />
      <Skeleton className="h-40 w-full rounded-lg" />
    </div>
  );
}
