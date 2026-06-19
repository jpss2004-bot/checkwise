"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { CalendarBlank, Funnel, Info } from "@phosphor-icons/react";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Input } from "@/components/ui/input";
import {
  ErrorState,
  Skeleton,
} from "@/components/checkwise/portal/state-surfaces";

import { ClientShell } from "../_shell";
import { ObligationBlock } from "@/components/checkwise/calendar/obligation-block";
import {
  ComplianceMatrix,
  type ComplianceMatrixCell,
  type ComplianceMatrixRow,
} from "@/components/checkwise/calendar/compliance-matrix";
import type { CellPreviewItem } from "@/components/checkwise/calendar/matrix-cell-popover";
import {
  CLIENT_RISK_ORDER,
  SEMAPHORE_DOT,
  daysUntil,
  formatShortDate,
  monthOf,
  relativeDeadline,
  worstRisk,
} from "@/components/checkwise/calendar/client-calendar-shared";
import {
  getClientCalendar,
  listClientVendors,
  type ClientCalendar,
  type ClientCalendarItem,
  type ClientCalendarProvider,
  type ClientVendorListResponse,
} from "@/lib/api/client";
import { INSTITUTION_LABELS, MONTH_LABELS_ES } from "@/lib/api/portal";
import {
  CALENDAR_MAX_YEAR,
  CALENDAR_MIN_YEAR,
  parseCalendarYear,
} from "@/lib/calendar-year";
import { useUrlClientId } from "@/lib/workspace/use-url-client-id";

const TONE_TEXT: Record<"error" | "warning" | "info", string> = {
  error: "text-[color:var(--status-error-text)]",
  warning: "text-[color:var(--status-warning-text)]",
  info: "text-[color:var(--status-info-text)]",
};

const INSTITUTION_FILTERS: { code: string; label: string }[] = [
  { code: "all", label: "Todas" },
  { code: "sat", label: "SAT" },
  { code: "imss", label: "IMSS" },
  { code: "infonavit", label: "INFONAVIT" },
  { code: "stps_repse", label: "STPS / REPSE" },
];

// ``month: null`` means "this provider across the whole year" — the worklist
// you get by clicking a provider's row label (tier 5 provider-name drill).
type Selected = { month: number | null; vendorId: string | null } | null;

export default function ClientCalendarPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlClientId = useUrlClientId();
  const [today] = useState(() => new Date());

  const [year, setYear] = useState(() =>
    parseCalendarYear(searchParams?.get("year") ?? null),
  );
  const [data, setData] = useState<ClientCalendar | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [vendorFilter, setVendorFilter] = useState<string[]>(() =>
    searchParams?.getAll("vendor_id") ?? [],
  );
  const [institutionFilter, setInstitutionFilter] = useState<string>(() => {
    const v = searchParams?.get("inst") ?? "all";
    return INSTITUTION_FILTERS.some((o) => o.code === v) ? v : "all";
  });
  const [selected, setSelected] = useState<Selected>(null);
  const [vendorsList, setVendorsList] =
    useState<ClientVendorListResponse | null>(null);

  const calendarHref = useMemo(() => {
    const params = new URLSearchParams();
    if (urlClientId) params.set("client_id", urlClientId);
    if (year !== new Date().getFullYear()) params.set("year", String(year));
    for (const vendorId of vendorFilter) params.append("vendor_id", vendorId);
    if (institutionFilter !== "all") params.set("inst", institutionFilter);
    const qs = params.toString();
    return `/client/calendar${qs ? `?${qs}` : ""}`;
  }, [urlClientId, vendorFilter, year, institutionFilter]);

  useEffect(() => {
    router.replace(calendarHref, { scroll: false });
  }, [calendarHref, router]);

  useEffect(() => {
    let cancelled = false;
    listClientVendors(urlClientId ? { client_id: urlClientId } : undefined)
      .then((res) => {
        if (!cancelled) setVendorsList(res);
      })
      .catch(() => {
        if (!cancelled) setVendorsList({ items: [], total: 0 } as never);
      });
    return () => {
      cancelled = true;
    };
  }, [urlClientId]);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    getClientCalendar({
      year,
      vendor_ids: vendorFilter,
      ...(urlClientId ? { client_id: urlClientId } : {}),
    })
      .then((cal) => {
        if (!cancelled) setData(cal);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(
          err instanceof Error ? err.message : "Error al cargar calendario.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [year, vendorFilter, urlClientId]);

  function toggleVendor(id: string) {
    setVendorFilter((prev) =>
      prev.includes(id) ? prev.filter((v) => v !== id) : [...prev, id],
    );
  }

  function selectAndScroll(next: NonNullable<Selected>) {
    setSelected(next);
    requestAnimationFrame(() => {
      document
        .getElementById("selection-detail")
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  // Vendor narrowing is server-side; institution narrowing is client-side.
  const filteredItems = useMemo(() => {
    if (!data) return [] as ClientCalendarItem[];
    const all = data.months.flatMap((m) => m.items);
    if (institutionFilter === "all") return all;
    return all.filter((i) => i.institution === institutionFilter);
  }, [data, institutionFilter]);

  const institutionCounts = useMemo(() => {
    const counts: Record<string, number> = { all: 0 };
    if (!data) return counts;
    for (const m of data.months) {
      for (const i of m.items) {
        counts.all += 1;
        counts[i.institution] = (counts[i.institution] ?? 0) + 1;
      }
    }
    return counts;
  }, [data]);

  const itemsByCell = useMemo(() => {
    const map = new Map<string, ClientCalendarItem[]>();
    for (const item of filteredItems) {
      const key = `${item.vendor_id}-${monthOf(item)}`;
      const list = map.get(key) ?? [];
      list.push(item);
      map.set(key, list);
    }
    return map;
  }, [filteredItems]);

  const visibleProviders = useMemo(() => {
    if (!data) return [] as ClientCalendarProvider[];
    if (institutionFilter === "all") return data.providers;
    const withItems = new Set(filteredItems.map((i) => i.vendor_id));
    return data.providers.filter((p) => withItems.has(p.vendor_id));
  }, [data, filteredItems, institutionFilter]);

  // Adapt the client data to the shared ComplianceMatrix shape: providers are
  // the rows, and each cell carries a precomputed count + worst risk.
  const matrixRows = useMemo<ComplianceMatrixRow[]>(
    () =>
      visibleProviders.map((p) => ({
        id: p.vendor_id,
        name: p.vendor_name,
        semaphore_level: p.semaphore_level,
        subtitle: `${p.compliance_pct}% al día`,
      })),
    [visibleProviders],
  );

  const matrixCells = useMemo(() => {
    const map = new Map<string, ComplianceMatrixCell>();
    for (const [key, items] of itemsByCell) {
      map.set(key, {
        count: items.length,
        worstRisk: worstRisk(items) ?? "on_track",
      });
    }
    return map;
  }, [itemsByCell]);

  // Per-cell obligation preview for the matrix hover/focus popover — worst-first
  // so the most urgent obligation in a busy provider-month leads. Same cell key
  // as `matrixCells` so the matrix lines them up.
  const cellItems = useMemo(() => {
    const map = new Map<string, CellPreviewItem[]>();
    for (const [key, items] of itemsByCell) {
      const preview: CellPreviewItem[] = items
        .slice()
        .sort(
          (a, b) =>
            CLIENT_RISK_ORDER[a.risk_level ?? "on_track"] -
            CLIENT_RISK_ORDER[b.risk_level ?? "on_track"],
        )
        .map((item) => ({
          key: `${item.vendor_id}-${item.requirement_code ?? item.requirement_name}-${item.period_key ?? ""}`,
          label: item.requirement_name,
          risk: item.risk_level ?? "on_track",
          deadline: formatShortDate(item.deadline_iso),
          sublabel: `${INSTITUTION_LABELS[item.institution] ?? item.institution} · ${item.period_label}`,
        }));
      map.set(key, preview);
    }
    return map;
  }, [itemsByCell]);

  // Default selection when the data / filter context changes: the current
  // month across all providers, else the first month that has anything.
  useEffect(() => {
    const monthsWithItems = new Set(filteredItems.map(monthOf));
    if (monthsWithItems.size === 0) {
      setSelected(null);
      return;
    }
    const cm = today.getFullYear() === year ? today.getMonth() + 1 : null;
    const month =
      cm && monthsWithItems.has(cm) ? cm : Math.min(...monthsWithItems);
    setSelected({ month, vendorId: null });
  }, [filteredItems, year, today]);

  const selectionItems = useMemo(() => {
    if (!selected) return [] as ClientCalendarItem[];
    return filteredItems.filter(
      (i) =>
        (selected.month === null || monthOf(i) === selected.month) &&
        (selected.vendorId === null || i.vendor_id === selected.vendorId),
    );
  }, [filteredItems, selected]);

  const strip = useMemo(() => {
    let overdue = 0;
    let dueSoon = 0;
    let next: { iso: string; vendor: string } | null = null;
    // B4 — providers at risk *within the active scope*. When an institution
    // filter is on, a provider that is red only because of, say, SAT must not
    // count under an INFONAVIT filter; tally the distinct vendors carrying a
    // critical (overdue / action_required) obligation in the filtered set.
    const atRiskVendors = new Set<string>();
    for (const item of filteredItems) {
      if (item.risk_level === "overdue") overdue += 1;
      else if (item.risk_level === "due_soon") dueSoon += 1;
      if (
        item.risk_level === "overdue" ||
        item.risk_level === "action_required"
      ) {
        atRiskVendors.add(item.vendor_id);
      }
      if (item.risk_level === "on_track") continue;
      const n = daysUntil(item.deadline_iso, today);
      if (n === null || n < 0) continue;
      if (!next || item.deadline_iso < next.iso) {
        next = { iso: item.deadline_iso, vendor: item.vendor_name };
      }
    }
    // Unfiltered, keep the portfolio semaphore-red headline (the count the
    // dashboard and vendors list show); filtered, use the scoped tally.
    const atRisk =
      institutionFilter === "all"
        ? visibleProviders.filter((p) => p.semaphore_level === "red").length
        : atRiskVendors.size;
    return { overdue, dueSoon, atRisk, next };
  }, [filteredItems, visibleProviders, institutionFilter, today]);

  const currentMonthForMatrix =
    today.getFullYear() === year ? today.getMonth() + 1 : null;

  return (
    <ClientShell
      title="Calendario del cliente"
      description="El año de cumplimiento de tu portafolio. Cada proveedor por mes; toca un mes o una celda para ver el detalle de los documentos."
      actions={
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
            min={CALENDAR_MIN_YEAR}
            max={CALENDAR_MAX_YEAR}
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="h-7 w-20 border-0 bg-transparent p-0 font-mono text-sm font-semibold focus-visible:ring-0"
          />
        </label>
      }
    >
      {error ? (
        <ErrorState
          title="No pudimos cargar el calendario"
          description={error}
          onRetry={() => setYear((y) => y)}
        />
      ) : !data ? (
        <CalendarSkeleton />
      ) : (
        <div className="space-y-6">
          <RiskStrip strip={strip} today={today} />

          <Filters
            vendorsList={vendorsList}
            vendorFilter={vendorFilter}
            onToggleVendor={toggleVendor}
            onClearVendors={() => setVendorFilter([])}
            institutionFilter={institutionFilter}
            onInstitution={setInstitutionFilter}
            institutionCounts={institutionCounts}
          />

          {data.providers.length === 0 ? (
            <NoProvidersState />
          ) : visibleProviders.length === 0 ? (
            <FilteredEmptyState onClear={() => setInstitutionFilter("all")} />
          ) : (
            <>
              <Surface
                title={`Calendario ${year}`}
                description="Proveedores en las filas, meses en las columnas. El color marca el estado más crítico de cada mes."
                bodyClassName="p-4"
              >
                <CalendarHelp />
                <ComplianceMatrix
                  rows={matrixRows}
                  cells={matrixCells}
                  cellItems={cellItems}
                  currentMonth={currentMonthForMatrix}
                  selected={
                    selected && selected.month !== null
                      ? { rowId: selected.vendorId, month: selected.month }
                      : null
                  }
                  onSelectCell={(rowId, month) =>
                    selectAndScroll({ month, vendorId: rowId })
                  }
                  onSelectMonth={(month) =>
                    selectAndScroll({ month, vendorId: null })
                  }
                  onSelectRow={(rowId) =>
                    selectAndScroll({ month: null, vendorId: rowId })
                  }
                />
              </Surface>

              <div id="selection-detail" className="scroll-mt-4">
                <SelectionDetail
                  selected={selected}
                  items={selectionItems}
                  providers={visibleProviders}
                  year={year}
                  today={today}
                  returnToHref={calendarHref}
                />
              </div>
            </>
          )}
        </div>
      )}
    </ClientShell>
  );
}

// ─── Selection detail (grouped by provider) ─────────────────────

function SelectionDetail({
  selected,
  items,
  providers,
  year,
  today,
  returnToHref,
}: {
  selected: Selected;
  items: ClientCalendarItem[];
  providers: ClientCalendarProvider[];
  year: number;
  today: Date;
  returnToHref: string;
}) {
  if (!selected) {
    return (
      <Surface bodyClassName="p-6 text-center">
        <p className="text-sm text-[color:var(--text-secondary)]">
          Selecciona un mes o una celda en el calendario para ver el detalle.
        </p>
      </Surface>
    );
  }

  const semaphoreByVendor = new Map(
    providers.map((p) => [p.vendor_id, p.semaphore_level]),
  );

  const byVendor = new Map<
    string,
    { name: string; items: ClientCalendarItem[] }
  >();
  for (const item of items) {
    const g = byVendor.get(item.vendor_id) ?? {
      name: item.vendor_name,
      items: [],
    };
    g.items.push(item);
    byVendor.set(item.vendor_id, g);
  }
  const worstOf = (list: ClientCalendarItem[]) =>
    Math.min(...list.map((i) => CLIENT_RISK_ORDER[i.risk_level ?? "on_track"]));
  const groups = [...byVendor.entries()]
    .map(([vendorId, g]) => ({ vendorId, ...g }))
    .sort((a, b) => worstOf(a.items) - worstOf(b.items));

  // ``month === null`` is the whole-year provider worklist (row-label drill).
  const periodLabel =
    selected.month === null
      ? `Todo ${year}`
      : `${MONTH_LABELS_ES[selected.month]} ${year}`;
  const title =
    selected.vendorId === null
      ? `${periodLabel} · todo el portafolio`
      : `${byVendor.get(selected.vendorId)?.name ?? "Proveedor"} · ${periodLabel}`;

  return (
    <Surface bodyClassName="p-4 sm:p-5">
      <div className="mb-4 border-b border-[color:var(--border-subtle)] pb-3">
        <p className="text-sm font-semibold text-[color:var(--text-primary)]">
          {title}
        </p>
        <p className="text-xs text-[color:var(--text-tertiary)]">
          {items.length} {items.length === 1 ? "obligación" : "obligaciones"}
          {selected.vendorId === null
            ? ` · ${groups.length} ${groups.length === 1 ? "proveedor" : "proveedores"}`
            : ""}
        </p>
      </div>

      {groups.length === 0 ? (
        <p className="text-sm text-[color:var(--text-secondary)]">
          Sin obligaciones en esta selección.
        </p>
      ) : (
        <div className="space-y-5">
          {groups.map((g) => (
            <section key={g.vendorId}>
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-[color:var(--text-primary)]">
                <span
                  aria-hidden="true"
                  className={
                    "h-2.5 w-2.5 shrink-0 rounded-full " +
                    SEMAPHORE_DOT[semaphoreByVendor.get(g.vendorId) ?? "yellow"]
                  }
                />
                {g.name}
                <span className="font-mono text-[11px] font-normal tabular-nums text-[color:var(--text-tertiary)]">
                  {g.items.length}
                </span>
              </h3>
              <ul className="space-y-2.5">
                {g.items
                  .slice()
                  .sort(
                    (a, b) =>
                      CLIENT_RISK_ORDER[a.risk_level ?? "on_track"] -
                      CLIENT_RISK_ORDER[b.risk_level ?? "on_track"],
                  )
                  .map((item) => (
                    <ObligationBlock
                      key={`${item.vendor_id}-${item.requirement_code ?? item.requirement_name}-${item.period_key ?? ""}`}
                      item={item}
                      today={today}
                      returnToHref={returnToHref}
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

// ─── Risk strip ─────────────────────────────────────────────────

function RiskStrip({
  strip,
  today,
}: {
  strip: {
    overdue: number;
    dueSoon: number;
    atRisk: number;
    next: { iso: string; vendor: string } | null;
  };
  today: Date;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <StatTile
        label="Vencidas"
        value={String(strip.overdue)}
        tone={strip.overdue > 0 ? "error" : "info"}
        muted={strip.overdue === 0}
      />
      <StatTile
        label="Vencen ≤14 d"
        value={String(strip.dueSoon)}
        tone={strip.dueSoon > 0 ? "warning" : "info"}
        muted={strip.dueSoon === 0}
      />
      <StatTile
        label="Proveedores en riesgo"
        value={String(strip.atRisk)}
        tone={strip.atRisk > 0 ? "error" : "info"}
        muted={strip.atRisk === 0}
      />
      <StatTile
        label="Próximo vencimiento"
        value={strip.next ? formatShortDate(strip.next.iso) : "—"}
        sub={
          strip.next
            ? `${relativeDeadline(strip.next.iso, today).split(" · ")[0]} · ${strip.next.vendor}`
            : "Nada por vencer"
        }
        tone="info"
        muted={!strip.next}
      />
    </div>
  );
}

function StatTile({
  label,
  value,
  sub,
  tone,
  muted,
}: {
  label: string;
  value: string;
  sub?: string;
  tone: "error" | "warning" | "info";
  muted?: boolean;
}) {
  return (
    <div className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-4 py-3.5">
      <p className="text-[11px] font-medium uppercase tracking-wide text-[color:var(--text-secondary)]">
        {label}
      </p>
      <p
        className={
          "mt-1.5 font-mono text-3xl font-semibold tabular-nums " +
          (muted ? "text-[color:var(--text-secondary)]" : TONE_TEXT[tone])
        }
      >
        {value}
      </p>
      {sub ? (
        <p className="mt-1 truncate text-xs text-[color:var(--text-tertiary)]">
          {sub}
        </p>
      ) : null}
    </div>
  );
}

// ─── Calendar help ──────────────────────────────────────────────

// The three click targets (cell, month header, provider row) were only
// discoverable via hover titles — no up-front explanation (2nd-review note
// 3.3). A collapsible key spells them out without crowding the grid.
function CalendarHelp() {
  return (
    <details className="mb-3 rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-3 py-2">
      <summary className="flex cursor-pointer list-none items-center gap-2 text-[11px] font-medium text-[color:var(--text-secondary)]">
        <Info className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
        ¿Cómo leer el calendario?
      </summary>
      <ul className="mt-2 space-y-1 text-[11px] leading-4 text-[color:var(--text-secondary)]">
        <li>
          Cada celda es un proveedor en un mes; el color marca su estado más
          crítico.
        </li>
        <li>
          Toca una <strong>celda</strong> para ver los documentos de ese
          proveedor en ese mes.
        </li>
        <li>
          Toca el <strong>nombre del mes</strong> (encabezado) para ver ese mes
          en todos los proveedores.
        </li>
        <li>
          Toca el <strong>nombre del proveedor</strong> (fila) para ver su año
          completo.
        </li>
      </ul>
    </details>
  );
}

// ─── Filters ────────────────────────────────────────────────────

function Filters({
  vendorsList,
  vendorFilter,
  onToggleVendor,
  onClearVendors,
  institutionFilter,
  onInstitution,
  institutionCounts,
}: {
  vendorsList: ClientVendorListResponse | null;
  vendorFilter: string[];
  onToggleVendor: (id: string) => void;
  onClearVendors: () => void;
  institutionFilter: string;
  onInstitution: (code: string) => void;
  institutionCounts: Record<string, number>;
}) {
  const hasVendors = !vendorsList || vendorsList.items.length > 0;
  return (
    <Surface
      title="Filtrar"
      description={
        vendorFilter.length === 0
          ? "Mostrando todo el portafolio. Acota por proveedor o por institución."
          : `Filtrando por ${vendorFilter.length} proveedor${vendorFilter.length === 1 ? "" : "es"}.`
      }
      actions={
        vendorFilter.length > 0 || institutionFilter !== "all" ? (
          <button
            type="button"
            className="text-xs font-medium text-[color:var(--text-brand)] hover:underline"
            onClick={() => {
              onClearVendors();
              onInstitution("all");
            }}
          >
            Limpiar filtros
          </button>
        ) : null
      }
    >
      <div className="space-y-4">
        {/* Institución — single-select; the two filters used to sit in one
            undifferentiated chip wall that read as confusing (2nd-review
            notes 3.1/3.2). Labeled sections + behavior hints, mirroring the
            audit package's segmented filters. */}
        <div className="space-y-2">
          <div className="flex items-baseline justify-between gap-2">
            <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              <Funnel className="h-3 w-3" weight="bold" aria-hidden="true" />
              Institución
            </span>
            <span className="text-[11px] text-[color:var(--text-tertiary)]">
              Una autoridad a la vez
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
          {INSTITUTION_FILTERS.map((opt) => {
            const active = institutionFilter === opt.code;
            const count =
              opt.code === "all"
                ? institutionCounts.all
                : (institutionCounts[opt.code] ?? 0);
            return (
              <button
                key={opt.code}
                type="button"
                aria-pressed={active}
                onClick={() => onInstitution(opt.code)}
                className={
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors " +
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
                  {count}
                </span>
              </button>
            );
          })}
          </div>
        </div>

        {/* Proveedor — multi-select; behavior differs from the single-select
            institution chips above, so it gets its own labeled section. */}
        {hasVendors ? (
          <div className="space-y-2 border-t border-[color:var(--border-subtle)] pt-3">
            <div className="flex items-baseline justify-between gap-2">
              <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                Proveedor
              </span>
              <span className="text-[11px] text-[color:var(--text-tertiary)]">
                Elige uno o varios · vacío = todos
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              {(vendorsList?.items ?? []).map((v) => {
                const active = vendorFilter.includes(v.vendor_id);
                return (
                  <button
                    type="button"
                    key={v.vendor_id}
                    onClick={() => onToggleVendor(v.vendor_id)}
                    aria-pressed={active}
                    className={
                      "rounded-full border px-3 py-1.5 text-xs font-medium transition " +
                      (active
                        ? "border-[color:var(--interactive-primary)] bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]"
                        : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-secondary)] hover:border-[color:var(--border-strong)]")
                    }
                  >
                    {v.vendor_name}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
    </Surface>
  );
}

// ─── Empty + loading states ─────────────────────────────────────

function FilteredEmptyState({ onClear }: { onClear: () => void }) {
  return (
    <section className="rounded-lg border border-dashed border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-6 py-10 text-center">
      <p className="text-sm text-[color:var(--text-primary)]">
        Ningún proveedor tiene obligaciones de esta institución en el año.
      </p>
      <button
        type="button"
        onClick={onClear}
        className="mt-3 text-xs font-medium text-[color:var(--text-brand)] hover:underline"
      >
        Quitar filtro de institución
      </button>
    </section>
  );
}

function NoProvidersState() {
  return (
    <section className="rounded-lg border border-dashed border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-6 py-10 text-center">
      <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        Sin proveedores
      </p>
      <p className="mt-2 text-sm text-[color:var(--text-primary)]">
        Aún no tienes proveedores registrados en este cliente.
      </p>
    </section>
  );
}

function CalendarSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-live="polite">
      <span className="sr-only">Cargando calendario…</span>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-28 w-full rounded-lg" />
      <Skeleton className="h-96 w-full rounded-lg" />
    </div>
  );
}
