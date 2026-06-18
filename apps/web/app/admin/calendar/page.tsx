"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  ArrowsClockwise,
  CalendarBlank,
  CaretDown,
  CaretRight,
  Certificate,
  ClipboardText,
  FileText,
  Funnel,
  MagnifyingGlass,
  PencilSimpleLine,
  WarningOctagon,
} from "@phosphor-icons/react";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
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
  relativeDeadline,
  type CalendarRisk,
} from "@/components/checkwise/calendar/calendar-shared";
import {
  getAdminCalendarGrid,
  getAdminCalendarRenewals,
  getRollup,
  type AdminCalendarGrid,
  type AdminCalendarMonthStatus,
  type AdminCalendarObligation,
  type AdminCalendarRow,
  type AdminRenewals,
  type AdminRollup,
} from "@/lib/api/admin";
import { INSTITUTION_LABELS, MONTH_LABELS_ES, MONTH_LABELS_SHORT_ES } from "@/lib/api/portal";

const SEMAPHORE_RANK: Record<string, number> = { red: 0, yellow: 1, green: 2 };
const ROW_PAGE = 20;
const INSTITUTIONS = ["sat", "imss", "infonavit", "stps_repse"] as const;

/** Build the matrix cell map, optionally scoped to one institution (recolor +
 *  recount client-side — no refetch). */
function cellMap(
  grid: AdminCalendarGrid,
  institution: string | null,
): Map<string, ComplianceMatrixCell> {
  const map = new Map<string, ComplianceMatrixCell>();
  for (const c of grid.cells) {
    if (institution) {
      const inst = c.by_institution[institution];
      if (!inst || inst.count === 0) continue;
      map.set(`${c.row_id}-${c.month}`, {
        count: inst.count,
        worstRisk: inst.worst_risk as CalendarRisk,
      });
    } else {
      map.set(`${c.row_id}-${c.month}`, {
        count: c.count,
        worstRisk: c.worst_risk as CalendarRisk,
      });
    }
  }
  return map;
}

export default function AdminCalendarPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [today] = useState(() => new Date());
  const thisYear = new Date().getFullYear() || 2026;

  const [year, setYear] = useState<number>(() => {
    const y = Number(searchParams?.get("year"));
    return y >= 2021 && y <= 2030 ? y : thisYear;
  });
  const currentMonth = today.getFullYear() === year ? today.getMonth() + 1 : 1;

  const [overview, setOverview] = useState<AdminCalendarGrid | null>(null);
  const [rollup, setRollup] = useState<AdminRollup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  const [selectedMonth, setSelectedMonth] = useState<number>(() => {
    const m = Number(searchParams?.get("month"));
    return m >= 1 && m <= 12 ? m : currentMonth;
  });
  const [institution, setInstitution] = useState<string | null>(() => {
    const i = searchParams?.get("inst");
    return i && INSTITUTIONS.includes(i as (typeof INSTITUTIONS)[number]) ? i : null;
  });
  const [showAllClients, setShowAllClients] = useState(false);
  const [rowLimit, setRowLimit] = useState(ROW_PAGE);

  const [detailClientId, setDetailClientId] = useState<string | null>(
    () => searchParams?.get("client") ?? null,
  );
  const [detail, setDetail] = useState<AdminCalendarGrid | null>(null);
  const [selectedProviderId, setSelectedProviderId] = useState<string | null>(null);

  // ── URL-persist (shareable planning links) ─────────────────────
  const calendarHref = useMemo(() => {
    const p = new URLSearchParams();
    if (year !== thisYear) p.set("year", String(year));
    if (institution) p.set("inst", institution);
    if (detailClientId) p.set("client", detailClientId);
    if (selectedMonth !== currentMonth) p.set("month", String(selectedMonth));
    const qs = p.toString();
    return `/admin/calendar${qs ? `?${qs}` : ""}`;
  }, [year, institution, detailClientId, selectedMonth, currentMonth, thisYear]);

  useEffect(() => {
    router.replace(calendarHref, { scroll: false });
  }, [calendarHref, router]);

  // ── Overview fetch (per year) ──────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    setError(null);
    setOverview(null);
    Promise.all([getAdminCalendarGrid({ year }), getRollup()])
      .then(([g, r]) => {
        if (cancelled) return;
        setOverview(g);
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
  }, [year, reloadKey]);

  // ── Detail fetch (one client) ──────────────────────────────────
  useEffect(() => {
    if (!detailClientId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetail(null);
    getAdminCalendarGrid({ year, client_id: detailClientId })
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch(() => {
        if (!cancelled) setDetailClientId(null);
      });
    return () => {
      cancelled = true;
    };
  }, [detailClientId, year]);

  function enterClient(id: string, month?: number) {
    if (month) setSelectedMonth(month);
    setSelectedProviderId(null);
    setDetailClientId(id);
    requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  }
  function exitClient() {
    setDetailClientId(null);
    setSelectedProviderId(null);
  }
  async function refreshOverview() {
    setRefreshing(true);
    try {
      setOverview(await getAdminCalendarGrid({ year, refresh: true }));
    } catch {
      // leave the existing (stale) data in place on failure
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    setRowLimit(ROW_PAGE);
  }, [year, showAllClients, institution]);

  const inClient = Boolean(detailClientId);

  // ── Portfolio-view derived data ────────────────────────────────
  const sortedClients = useMemo<AdminCalendarRow[]>(() => {
    if (!overview) return [];
    const rows = [...overview.rows];
    rows.sort(
      (a, b) =>
        (SEMAPHORE_RANK[a.semaphore_level] ?? 3) -
          (SEMAPHORE_RANK[b.semaphore_level] ?? 3) ||
        a.compliance_pct - b.compliance_pct ||
        a.name.localeCompare(b.name),
    );
    return showAllClients
      ? rows
      : rows.filter((r) => r.semaphore_level !== "green");
  }, [overview, showAllClients]);

  const portfolioCells = useMemo(
    () => (overview ? cellMap(overview, institution) : new Map<string, ComplianceMatrixCell>()),
    [overview, institution],
  );
  // With an institution filter, only show client rows that have a cell that
  // month-or-any for that institution (keeps the grid relevant).
  const scopedClients = useMemo<AdminCalendarRow[]>(() => {
    if (!institution) return sortedClients;
    const withInst = new Set<string>();
    for (const c of overview?.cells ?? []) {
      if (c.by_institution[institution]) withInst.add(c.row_id);
    }
    return sortedClients.filter((r) => withInst.has(r.id));
  }, [sortedClients, overview, institution]);

  const portfolioRows = useMemo<ComplianceMatrixRow[]>(
    () =>
      scopedClients.slice(0, rowLimit).map((r) => ({
        id: r.id,
        name: r.name,
        semaphore_level: r.semaphore_level,
        subtitle: rowSubtitle(r),
      })),
    [scopedClients, rowLimit],
  );

  const hiddenGreen = useMemo(() => {
    if (showAllClients || !overview) return 0;
    return overview.rows.filter((r) => r.semaphore_level === "green").length;
  }, [overview, showAllClients]);

  const clientsThisMonth = useMemo(() => {
    if (!overview) return [];
    const nameById = new Map(overview.rows.map((r) => [r.id, r]));
    return overview.cells
      .filter((c) => c.month === selectedMonth)
      .map((c) => {
        const scoped = institution ? c.by_institution[institution] : null;
        const count = institution ? (scoped?.count ?? 0) : c.count;
        const worstRisk = (institution ? scoped?.worst_risk : c.worst_risk) as
          | CalendarRisk
          | undefined;
        return { client: nameById.get(c.row_id), count, worstRisk };
      })
      .filter((x) => x.client && x.count > 0 && x.worstRisk)
      .sort(
        (a, b) =>
          (RISK_ORDER[a.worstRisk as CalendarRisk] ?? 9) -
            (RISK_ORDER[b.worstRisk as CalendarRisk] ?? 9) || b.count - a.count,
      );
  }, [overview, selectedMonth, institution]);

  const monthStatus: AdminCalendarMonthStatus | null = useMemo(
    () => overview?.month_status?.find((s) => s.month === selectedMonth) ?? null,
    [overview, selectedMonth],
  );

  // ── Client-view derived data ───────────────────────────────────
  const providerRows = useMemo<ComplianceMatrixRow[]>(() => {
    if (!detail) return [];
    return [...detail.rows]
      .sort(
        (a, b) =>
          (SEMAPHORE_RANK[a.semaphore_level] ?? 3) -
            (SEMAPHORE_RANK[b.semaphore_level] ?? 3) ||
          a.compliance_pct - b.compliance_pct ||
          a.name.localeCompare(b.name),
      )
      .map((r) => ({
        id: r.id,
        name: r.name,
        semaphore_level: r.semaphore_level,
        subtitle: rowSubtitle(r),
      }));
  }, [detail]);
  const providerCells = useMemo(
    () => (detail ? cellMap(detail, institution) : new Map<string, ComplianceMatrixCell>()),
    [detail, institution],
  );
  const clientObligations = useMemo<AdminCalendarObligation[]>(() => {
    if (!detail) return [];
    return detail.obligations.filter(
      (o) =>
        o.due_month === selectedMonth &&
        (!institution || o.institution === institution) &&
        (!selectedProviderId || o.vendor_id === selectedProviderId),
    );
  }, [detail, selectedMonth, selectedProviderId, institution]);

  return (
    <AdminShell
      title="Calendario operativo"
      description="El año de cumplimiento de toda la cartera. Toca un mes para ver su resumen, y entra a un cliente para ver el detalle de sus obligaciones."
      actions={<YearPicker year={year} onYear={setYear} />}
    >
      {error ? (
        <ErrorState
          title="No pudimos cargar el calendario"
          description={error}
          onRetry={() => setReloadKey((k) => k + 1)}
        />
      ) : !overview || !rollup ? (
        <CalendarSkeleton />
      ) : inClient ? (
        // ─────────────── Single-client view ───────────────
        <div className="space-y-6">
          <button
            type="button"
            onClick={exitClient}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-[color:var(--text-brand)] hover:underline"
          >
            <ArrowLeft className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            Volver a la cartera
          </button>

          <InstitutionChips value={institution} onChange={setInstitution} />

          {!detail ? (
            <>
              <Skeleton className="h-72 w-full rounded-lg" />
              <Skeleton className="h-48 w-full rounded-lg" />
            </>
          ) : (
            <>
              <Surface
                title={`${detail.client_name ?? "Cliente"} · ${year}`}
                description="Proveedores de este cliente por mes. Toca un mes o un proveedor para ver el detalle abajo."
                bodyClassName="p-4"
              >
                {providerRows.length === 0 ? (
                  <p className="px-2 py-8 text-center text-sm text-[color:var(--text-secondary)]">
                    Este cliente no tiene proveedores con obligaciones este año.
                  </p>
                ) : (
                  <ComplianceMatrix
                    rows={providerRows}
                    cells={providerCells}
                    currentMonth={today.getFullYear() === year ? currentMonth : null}
                    rowHeader="Proveedor"
                    selected={{ rowId: selectedProviderId, month: selectedMonth }}
                    onSelectCell={(rowId, month) => {
                      setSelectedMonth(month);
                      setSelectedProviderId(rowId);
                    }}
                    onSelectMonth={(month) => {
                      setSelectedMonth(month);
                      setSelectedProviderId(null);
                    }}
                    onSelectRow={(rowId) => setSelectedProviderId(rowId)}
                  />
                )}
              </Surface>

              <ObligationDetail
                title={`${MONTH_LABELS_ES[selectedMonth]} ${year}${selectedProviderId ? "" : " · todos los proveedores"}`}
                obligations={clientObligations}
                today={today}
              />
            </>
          )}
        </div>
      ) : (
        // ─────────────── Portfolio view ───────────────
        <div className="space-y-6">
          <TriageBand overview={overview} rollup={rollup} />

          <ForecastWaveStrip
            overview={overview}
            institution={institution}
            currentMonth={today.getFullYear() === year ? currentMonth : null}
            selectedMonth={selectedMonth}
            onSelectMonth={setSelectedMonth}
          />

          <Surface
            title={`Cartera ${year}`}
            description="Cada cliente por mes. Toca un mes para su resumen, o entra a un cliente para ver sus obligaciones."
            actions={
              <div className="flex flex-wrap items-center gap-2">
                <FreshnessChip
                  snapshotAt={overview.snapshot_at}
                  refreshing={refreshing}
                  onRefresh={refreshOverview}
                />
                <ClientPicker clients={sortedClients} onPick={enterClient} />
                <ScopeToggle
                  showAll={showAllClients}
                  hiddenGreen={hiddenGreen}
                  onToggle={() => setShowAllClients((v) => !v)}
                />
              </div>
            }
            bodyClassName="p-4"
          >
            <div className="mb-3">
              <InstitutionChips value={institution} onChange={setInstitution} />
            </div>
            {portfolioRows.length === 0 ? (
              <EmptyGrid
                showAll={showAllClients}
                institution={institution}
                onShowAll={() => setShowAllClients(true)}
                onClearInstitution={() => setInstitution(null)}
              />
            ) : (
              <>
                <ComplianceMatrix
                  rows={portfolioRows}
                  cells={portfolioCells}
                  currentMonth={today.getFullYear() === year ? currentMonth : null}
                  rowHeader="Cliente"
                  selected={{ rowId: null, month: selectedMonth }}
                  onSelectCell={(clientId, month) => enterClient(clientId, month)}
                  onSelectMonth={setSelectedMonth}
                  onSelectRow={(clientId) => enterClient(clientId)}
                />
                <PaginationFooter
                  shown={portfolioRows.length}
                  filtered={scopedClients.length}
                  total={overview.clients_total ?? sortedClients.length}
                  onMore={() => setRowLimit((n) => n + ROW_PAGE)}
                />
              </>
            )}
          </Surface>

          <MonthSummary
            month={selectedMonth}
            year={year}
            status={monthStatus}
            institution={institution}
            clientsThisMonth={clientsThisMonth}
            onPickClient={(id) => enterClient(id, selectedMonth)}
          />

          <RenewalLane year={year} today={today} />
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

function YearPicker({ year, onYear }: { year: number; onYear: (y: number) => void }) {
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

// ─── Institution filter chips ───────────────────────────────────

function InstitutionChips({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (v: string | null) => void;
}) {
  const opts: { code: string | null; label: string }[] = [
    { code: null, label: "Todas" },
    ...INSTITUTIONS.map((c) => ({ code: c, label: INSTITUTION_LABELS[c] ?? c })),
  ];
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Funnel
        className="h-3.5 w-3.5 text-[color:var(--text-tertiary)]"
        weight="bold"
        aria-hidden="true"
      />
      {opts.map((o) => {
        const active = value === o.code;
        return (
          <button
            key={o.code ?? "all"}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(o.code)}
            className={
              "rounded-full border px-3 py-1 text-xs font-medium transition-colors " +
              (active
                ? "border-[color:var(--border-brand)] bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]"
                : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)]")
            }
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

// ─── Client picker (jump straight to a client) ──────────────────

function ClientPicker({
  clients,
  onPick,
}: {
  clients: AdminCalendarRow[];
  onPick: (id: string) => void;
}) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const matches = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const base = needle
      ? clients.filter((c) => c.name.toLowerCase().includes(needle))
      : clients;
    return base.slice(0, 8);
  }, [clients, q]);

  return (
    <div className="relative">
      <div className="flex items-center gap-1.5 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2.5 py-1.5">
        <MagnifyingGlass
          className="h-3.5 w-3.5 text-[color:var(--text-tertiary)]"
          weight="bold"
          aria-hidden="true"
        />
        <input
          type="text"
          value={q}
          placeholder="Ir a un cliente…"
          aria-label="Buscar cliente"
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          className="w-40 bg-transparent text-xs text-[color:var(--text-primary)] outline-none placeholder:text-[color:var(--text-tertiary)]"
        />
      </div>
      {open && matches.length > 0 ? (
        <ul className="absolute right-0 z-20 mt-1 max-h-72 w-64 overflow-auto rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] py-1 shadow-[var(--shadow-md)]">
          {matches.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onMouseDown={() => onPick(c.id)}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-[color:var(--surface-hover)]"
              >
                <span aria-hidden="true" className={"h-2 w-2 shrink-0 rounded-full " + dotFor(c.semaphore_level)} />
                <span className="min-w-0 flex-1 truncate text-[color:var(--text-primary)]">
                  {c.name}
                </span>
                <span className="font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
                  {c.compliance_pct}%
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function dotFor(level: string): string {
  return SEMAPHORE_DOT[level as "red" | "yellow" | "green"] ?? SEMAPHORE_DOT.yellow;
}

function relativeSince(iso: string): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 1) return "hace un momento";
  if (mins < 60) return `hace ${mins} min`;
  return `hace ${Math.round(mins / 60)} h`;
}

function FreshnessChip({
  snapshotAt,
  refreshing,
  onRefresh,
}: {
  snapshotAt: string | null;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const label = snapshotAt ? `Actualizado ${relativeSince(snapshotAt)}` : "En vivo";
  return (
    <button
      type="button"
      onClick={onRefresh}
      disabled={refreshing}
      title="Recalcular el resumen de la cartera"
      className="inline-flex items-center gap-1.5 rounded-full border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-1.5 text-xs font-medium text-[color:var(--text-secondary)] transition-colors hover:bg-[color:var(--surface-hover)] disabled:opacity-60"
    >
      <ArrowsClockwise
        className={"h-3.5 w-3.5 motion-reduce:animate-none " + (refreshing ? "animate-spin" : "")}
        weight="bold"
        aria-hidden="true"
      />
      {refreshing ? "Actualizando…" : label}
    </button>
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

function PaginationFooter({
  shown,
  filtered,
  total,
  onMore,
}: {
  shown: number;
  filtered: number;
  total: number;
  onMore: () => void;
}) {
  return (
    <div className="mt-3 flex items-center justify-between gap-3 border-t border-[color:var(--border-subtle)] pt-3">
      <p className="text-[11px] text-[color:var(--text-tertiary)]">
        Mostrando {shown} de {filtered}
        {filtered !== total ? ` (${total} en total)` : ""}
      </p>
      {shown < filtered ? (
        <button
          type="button"
          onClick={onMore}
          className="text-xs font-medium text-[color:var(--text-brand)] hover:underline"
        >
          Mostrar más
        </button>
      ) : null}
    </div>
  );
}

// ─── Triage band ────────────────────────────────────────────────

function TriageBand({
  overview,
  rollup,
}: {
  overview: AdminCalendarGrid;
  rollup: AdminRollup;
}) {
  const slaAtRisk =
    rollup.queue.age_buckets.over_72h + rollup.queue.age_buckets.over_7d;
  return (
    <div>
      <p className="mb-2 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        En la cartera
      </p>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <TriageTile value={overview.triage.overdue_total} label="Vencido (año)" tone="error" icon={WarningOctagon} />
        <TriageTile value={overview.triage.due_7d_total} label="Vence ≤ 7 días" tone="warning" />
        <TriageTile value={slaAtRisk} label="SLA revisión > 72 h" tone="neutral" icon={ClipboardText} href="/admin/reviewer" />
        <TriageTile value={rollup.inbox.correction_requests_pending} label="Correcciones" tone="neutral" icon={PencilSimpleLine} href="/admin/correction-requests" />
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
}: {
  value: number;
  label: string;
  tone: "error" | "warning" | "neutral";
  icon?: typeof WarningOctagon;
  href?: string;
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
        {href ? <ArrowRight className="h-3 w-3 opacity-60" weight="bold" aria-hidden="true" /> : null}
      </p>
    </>
  );
  const className =
    "block rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-4 py-3.5 text-left";
  return href ? (
    <Link href={href} className={className + " transition-colors hover:bg-[color:var(--surface-hover)]"}>
      {body}
    </Link>
  ) : (
    <div className={className}>{body}</div>
  );
}

// ─── Forecast wave strip ────────────────────────────────────────

function ForecastWaveStrip({
  overview,
  institution,
  currentMonth,
  selectedMonth,
  onSelectMonth,
}: {
  overview: AdminCalendarGrid;
  institution: string | null;
  currentMonth: number | null;
  selectedMonth: number | null;
  onSelectMonth: (month: number) => void;
}) {
  const totals = overview.forecast.map((f) =>
    institution ? (f.by_institution[institution] ?? 0) : f.total,
  );
  const max = Math.max(1, ...totals);
  return (
    <Surface
      title="Onda de carga del año"
      description="Obligaciones esperadas por mes en toda la cartera. Toca un mes para ver su resumen."
      bodyClassName="p-4"
    >
      <div className="flex items-end gap-1.5" style={{ height: 96 }}>
        {overview.forecast.map((f, i) => {
          const total = totals[i];
          const isCurrent = currentMonth === f.month;
          const isSelected = selectedMonth === f.month;
          const h = total === 0 ? 3 : Math.round(12 + (total / max) * 72);
          const insts = Object.entries(f.by_institution)
            .map(([k, v]) => `${k.toUpperCase()}: ${v}`)
            .join(" · ");
          return (
            <button
              key={f.month}
              type="button"
              onClick={() => onSelectMonth(f.month)}
              aria-pressed={isSelected}
              title={`${MONTH_LABELS_ES[f.month]}: ${total} esperadas${!institution && insts ? ` · ${insts}` : ""}`}
              className="group flex flex-1 flex-col items-center justify-end gap-1 rounded-md px-0.5 py-1 hover:bg-[color:var(--surface-hover)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]"
            >
              <span className="font-mono text-[9px] tabular-nums text-[color:var(--text-tertiary)]">
                {total || ""}
              </span>
              <span
                aria-hidden="true"
                style={{ height: h }}
                className={
                  "w-full max-w-[26px] rounded-sm transition-colors motion-reduce:transition-none " +
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
                  (isCurrent ? "text-[color:var(--text-brand)]" : "text-[color:var(--text-tertiary)]")
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

// ─── Month summary (gap + who's in this month) ──────────────────

function MonthSummary({
  month,
  year,
  status,
  institution,
  clientsThisMonth,
  onPickClient,
}: {
  month: number;
  year: number;
  status: AdminCalendarMonthStatus | null;
  institution: string | null;
  clientsThisMonth: {
    client: AdminCalendarRow | undefined;
    count: number;
    worstRisk: CalendarRisk | undefined;
  }[];
  onPickClient: (id: string) => void;
}) {
  const scoped = institution ? status?.by_institution[institution] : null;
  const expected = institution ? (scoped?.expected ?? 0) : (status?.expected ?? 0);
  const delivered = institution ? (scoped?.delivered ?? 0) : (status?.delivered ?? 0);
  const outstanding = expected - delivered;
  const institutions =
    status && !institution
      ? Object.entries(status.by_institution).sort((a, b) => b[1].expected - a[1].expected)
      : [];

  const instLabel = institution ? ` · ${INSTITUTION_LABELS[institution] ?? institution}` : "";

  return (
    <div id="admin-calendar-detail" className="scroll-mt-4">
      <Surface
        title={`${MONTH_LABELS_ES[month]} ${year} · resumen de la cartera${instLabel}`}
        description="Esperadas vs. entregadas este mes. Entra a un cliente para ver sus obligaciones."
        bodyClassName="p-4 sm:p-5"
      >
        {expected === 0 ? (
          <p className="px-1 py-6 text-center text-sm text-[color:var(--text-secondary)]">
            Sin obligaciones en {MONTH_LABELS_ES[month]}
            {institution ? ` para ${INSTITUTION_LABELS[institution] ?? institution}` : ""}.
          </p>
        ) : (
          <div className="space-y-5">
            <div className="grid grid-cols-3 gap-3">
              <SummaryStat label="Esperadas" value={expected} tone="neutral" />
              <SummaryStat label="Entregadas" value={delivered} tone="success" />
              <SummaryStat label="Pendientes" value={outstanding} tone={outstanding > 0 ? "warning" : "neutral"} />
            </div>

            {institutions.length > 0 ? (
              <div className="space-y-2">
                <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  Por institución
                </p>
                {institutions.map(([inst, v]) => {
                  const pct = v.expected ? Math.round((v.delivered / v.expected) * 100) : 0;
                  return (
                    <div key={inst} className="flex items-center gap-3">
                      <span className="w-28 shrink-0 text-xs text-[color:var(--text-secondary)]">
                        {INSTITUTION_LABELS[inst] ?? inst}
                      </span>
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-[color:var(--surface-page)]">
                        <div className="h-full rounded-full bg-[color:var(--status-success-text)]" style={{ width: `${pct}%` }} />
                      </div>
                      <span className="w-20 shrink-0 text-right font-mono text-[11px] tabular-nums text-[color:var(--text-tertiary)]">
                        {v.delivered}/{v.expected}
                      </span>
                    </div>
                  );
                })}
              </div>
            ) : null}

            {clientsThisMonth.length > 0 ? (
              <div className="space-y-2 border-t border-[color:var(--border-subtle)] pt-4">
                <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  Clientes con obligaciones este mes ({clientsThisMonth.length})
                </p>
                <ul className="flex flex-wrap gap-2">
                  {clientsThisMonth.map(({ client, count }) =>
                    client ? (
                      <li key={client.id}>
                        <button
                          type="button"
                          onClick={() => onPickClient(client.id)}
                          className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-1.5 text-xs hover:bg-[color:var(--surface-hover)]"
                        >
                          <span aria-hidden="true" className={"h-2 w-2 shrink-0 rounded-full " + dotFor(client.semaphore_level)} />
                          <span className="max-w-[180px] truncate text-[color:var(--text-primary)]">
                            {client.name}
                          </span>
                          <span className="font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
                            {count}
                          </span>
                          <ArrowRight className="h-3 w-3 text-[color:var(--text-tertiary)]" weight="bold" aria-hidden="true" />
                        </button>
                      </li>
                    ) : null,
                  )}
                </ul>
              </div>
            ) : null}
          </div>
        )}
      </Surface>
    </div>
  );
}

function SummaryStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "success" | "warning" | "neutral";
}) {
  return (
    <div className="rounded-md bg-[color:var(--surface-page)] px-4 py-3">
      <p className={"font-mono text-2xl font-semibold tabular-nums leading-none " + (TRIAGE_TONE[tone] ?? "")}>
        {value}
      </p>
      <p className="mt-1 text-[11px] text-[color:var(--text-secondary)]">{label}</p>
    </div>
  );
}

// ─── Renewals lane (contract expiries + credential renewals) ─────

function RenewalLane({ year, today }: { year: number; today: Date }) {
  const [data, setData] = useState<AdminRenewals | null>(null);
  const [open, setOpen] = useState(false);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setLoadError(false);
    getAdminCalendarRenewals({ horizon_days: 90 })
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [year]);

  const total = (data?.contracts.length ?? 0) + (data?.credentials.length ?? 0);
  const Caret = open ? CaretDown : CaretRight;

  return (
    <section className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-5 py-3.5 text-left"
      >
        <div className="flex items-center gap-2">
          <Caret className="h-3.5 w-3.5 text-[color:var(--text-tertiary)]" weight="bold" aria-hidden="true" />
          <div>
            <h3 className="text-[13px] font-semibold text-[color:var(--text-primary)]">
              Renovaciones y vencimientos de fecha exacta
            </h3>
            <p className="mt-0.5 text-[11px] text-[color:var(--text-tertiary)]">
              Contratos por vencer y credenciales por renovar (CSF, REPSE,
              registro patronal) — fuera de la cuadrícula del día 17.
            </p>
          </div>
        </div>
        <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-tertiary)]">
          {data ? total : loadError ? "—" : "…"}
        </span>
      </button>
      {open ? (
        <div className="border-t border-[color:var(--border-subtle)] p-5">
          {loadError ? (
            <p className="text-sm text-[color:var(--text-secondary)]">
              No se pudieron cargar las renovaciones.
            </p>
          ) : !data ? (
            <Skeleton className="h-24 w-full rounded-md" />
          ) : total === 0 ? (
            <p className="text-sm text-[color:var(--text-secondary)]">
              Sin contratos ni credenciales próximos a vencer en los próximos 90
              días.
            </p>
          ) : (
            <div className="grid gap-6 lg:grid-cols-2">
              <RenewalGroup
                icon={FileText}
                title="Contratos por vencer"
                empty="Sin contratos por vencer."
                rows={data.contracts.map((c) => ({
                  key: `${c.vendor_id}-${c.end_date}`,
                  vendorId: c.vendor_id,
                  vendorName: c.vendor_name,
                  clientName: c.client_name,
                  detail: relativeDeadline(c.end_date, today).split(" · ")[0],
                  badge: c.status,
                }))}
              />
              <RenewalGroup
                icon={Certificate}
                title="Credenciales por renovar"
                empty="Sin credenciales por renovar."
                rows={data.credentials.map((c, i) => ({
                  key: `${c.vendor_id}-${c.requirement_code}-${i}`,
                  vendorId: c.vendor_id,
                  vendorName: c.vendor_name,
                  clientName: c.client_name,
                  detail: c.title,
                  badge: c.status,
                }))}
              />
            </div>
          )}
          {data?.truncated ? (
            <p className="mt-4 text-[11px] text-[color:var(--text-tertiary)]">
              La cartera excede el límite de escaneo de credenciales; se muestran
              los primeros proveedores.
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function RenewalGroup({
  icon: Icon,
  title,
  empty,
  rows,
}: {
  icon: typeof FileText;
  title: string;
  empty: string;
  rows: {
    key: string;
    vendorId: string;
    vendorName: string;
    clientName: string | null;
    detail: string;
    badge: string;
  }[];
}) {
  return (
    <div>
      <h4 className="mb-2 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        <Icon className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
        {title} ({rows.length})
      </h4>
      {rows.length === 0 ? (
        <p className="text-xs text-[color:var(--text-secondary)]">{empty}</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((r) => (
            <li
              key={r.key}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-3.5 py-2.5"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium text-[color:var(--text-primary)]">
                  {r.vendorName}
                </p>
                {r.clientName ? (
                  <p className="truncate text-[11px] text-[color:var(--text-tertiary)]">{r.clientName}</p>
                ) : null}
              </div>
              <span className="whitespace-nowrap text-[12px] text-[color:var(--text-secondary)]">
                {r.detail}
              </span>
              <Badge variant={r.badge === "overdue" ? "destructive" : "warning"}>
                {r.badge === "overdue" ? "Vencido" : r.badge === "due_soon" ? "Pronto" : "Próximo"}
              </Badge>
              <Link
                href={`/admin/vendors/${r.vendorId}`}
                className="inline-flex items-center gap-1 whitespace-nowrap text-[12px] font-medium text-[color:var(--text-link)] hover:underline"
              >
                Ver proveedor
                <ArrowRight className="h-3 w-3" weight="bold" aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ─── Obligation detail (one client) ─────────────────────────────

function ObligationDetail({
  title,
  obligations,
  today,
}: {
  title: string;
  obligations: AdminCalendarObligation[];
  today: Date;
}) {
  const groups = useMemo(() => {
    const byVendor = new Map<string, { vendorName: string; items: AdminCalendarObligation[] }>();
    for (const o of obligations) {
      const g = byVendor.get(o.vendor_id) ?? { vendorName: o.vendor_name, items: [] };
      g.items.push(o);
      byVendor.set(o.vendor_id, g);
    }
    const worstOf = (items: AdminCalendarObligation[]) =>
      Math.min(...items.map((i) => RISK_ORDER[i.risk_level as CalendarRisk] ?? 9));
    return [...byVendor.values()].sort((a, b) => worstOf(a.items) - worstOf(b.items));
  }, [obligations]);

  return (
    <Surface bodyClassName="p-4 sm:p-5">
      <div className="mb-4 border-b border-[color:var(--border-subtle)] pb-3">
        <p className="text-sm font-semibold text-[color:var(--text-primary)]">{title}</p>
        <p className="text-xs text-[color:var(--text-tertiary)]">
          {obligations.length} {obligations.length === 1 ? "obligación" : "obligaciones"}
          {groups.length ? ` · ${groups.length} ${groups.length === 1 ? "proveedor" : "proveedores"}` : ""}
        </p>
      </div>
      {groups.length === 0 ? (
        <p className="px-1 py-6 text-center text-sm text-[color:var(--text-secondary)]">
          Sin obligaciones en este mes para la selección.
        </p>
      ) : (
        <div className="space-y-5">
          {groups.map((g) => (
            <section key={g.vendorName}>
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-[color:var(--text-primary)]">
                <span aria-hidden="true" className={"h-2.5 w-2.5 shrink-0 rounded-full " + SEMAPHORE_DOT[worstDot(g.items)]} />
                {g.vendorName}
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
    </Surface>
  );
}

function worstDot(items: AdminCalendarObligation[]): "red" | "yellow" | "green" {
  const worst = Math.min(...items.map((i) => RISK_ORDER[i.risk_level as CalendarRisk] ?? 9));
  if (worst <= 1) return "red";
  if (worst <= 2) return "yellow";
  return "green";
}

// ─── Empty + loading states ─────────────────────────────────────

function EmptyGrid({
  showAll,
  institution,
  onShowAll,
  onClearInstitution,
}: {
  showAll: boolean;
  institution: string | null;
  onShowAll: () => void;
  onClearInstitution: () => void;
}) {
  if (institution) {
    return (
      <div className="flex flex-col items-center gap-2 px-4 py-12 text-center">
        <p className="text-[13px] font-medium text-[color:var(--text-primary)]">
          Ningún cliente con obligaciones de {INSTITUTION_LABELS[institution] ?? institution}
        </p>
        <button
          type="button"
          onClick={onClearInstitution}
          className="mt-1 text-xs font-medium text-[color:var(--text-brand)] hover:underline"
        >
          Quitar filtro de institución
        </button>
      </div>
    );
  }
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
