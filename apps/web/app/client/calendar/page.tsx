"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { CalendarBlank, Funnel } from "@phosphor-icons/react";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Input } from "@/components/ui/input";
import {
  ErrorState,
  Skeleton,
} from "@/components/checkwise/portal/state-surfaces";

import { ClientShell } from "../_shell";
import { MonthCalendar } from "@/components/checkwise/calendar/month-calendar";
import { ObligationBlock } from "@/components/checkwise/calendar/obligation-block";
import { PortfolioMatrix } from "@/components/checkwise/calendar/portfolio-matrix";
import { ProviderReviewCard } from "@/components/checkwise/calendar/provider-review-card";
import {
  CLIENT_RISK_ORDER,
  daysUntil,
  formatLongDate,
  formatShortDate,
  monthOf,
  relativeDeadline,
} from "@/components/checkwise/calendar/client-calendar-shared";
import {
  getClientCalendar,
  listClientVendors,
  type ClientCalendar,
  type ClientCalendarItem,
  type ClientCalendarProvider,
  type ClientVendorListResponse,
} from "@/lib/api/client";
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

type ViewMode = "calendar" | "providers";

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
  const [viewMode, setViewMode] = useState<ViewMode>(() =>
    searchParams?.get("view") === "providers" ? "providers" : "calendar",
  );
  const [viewMonth, setViewMonth] = useState<number>(() =>
    today.getFullYear() === parseCalendarYear(searchParams?.get("year") ?? null)
      ? today.getMonth() + 1
      : 1,
  );
  const [selectedDay, setSelectedDay] = useState<number | null>(null);
  const [vendorsList, setVendorsList] =
    useState<ClientVendorListResponse | null>(null);
  const [openProviders, setOpenProviders] = useState<Set<string>>(new Set());
  const autoOpenedRef = useRef(false);

  const calendarHref = useMemo(() => {
    const params = new URLSearchParams();
    if (urlClientId) params.set("client_id", urlClientId);
    if (year !== new Date().getFullYear()) params.set("year", String(year));
    for (const vendorId of vendorFilter) params.append("vendor_id", vendorId);
    if (institutionFilter !== "all") params.set("inst", institutionFilter);
    if (viewMode === "providers") params.set("view", "providers");
    const qs = params.toString();
    return `/client/calendar${qs ? `?${qs}` : ""}`;
  }, [urlClientId, vendorFilter, year, institutionFilter, viewMode]);

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

  useEffect(() => {
    if (autoOpenedRef.current) return;
    if (data && data.providers.length > 0) {
      setOpenProviders(new Set([data.providers[0].vendor_id]));
      autoOpenedRef.current = true;
    }
  }, [data]);

  function toggleVendor(id: string) {
    setVendorFilter((prev) =>
      prev.includes(id) ? prev.filter((v) => v !== id) : [...prev, id],
    );
  }

  function toggleProvider(id: string) {
    setOpenProviders((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectProvider(id: string) {
    setViewMode("providers");
    setOpenProviders((prev) => new Set(prev).add(id));
    requestAnimationFrame(() => {
      document
        .getElementById(`provider-card-${id}`)
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function prevMonth() {
    if (viewMonth > 1) setViewMonth(viewMonth - 1);
    else {
      setYear(year - 1);
      setViewMonth(12);
    }
  }
  function nextMonth() {
    if (viewMonth < 12) setViewMonth(viewMonth + 1);
    else {
      setYear(year + 1);
      setViewMonth(1);
    }
  }
  function goToday() {
    setYear(today.getFullYear());
    setViewMonth(today.getMonth() + 1);
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

  const itemsByProvider = useMemo(() => {
    const map = new Map<string, ClientCalendarItem[]>();
    for (const item of filteredItems) {
      const list = map.get(item.vendor_id) ?? [];
      list.push(item);
      map.set(item.vendor_id, list);
    }
    return map;
  }, [filteredItems]);

  // Obligations of the displayed month, grouped by day-of-month.
  const itemsByDay = useMemo(() => {
    const map = new Map<number, ClientCalendarItem[]>();
    const prefix = `${year}-${String(viewMonth).padStart(2, "0")}-`;
    for (const item of filteredItems) {
      if (!item.deadline_iso.startsWith(prefix)) continue;
      const day = Number(item.deadline_iso.slice(8, 10));
      const list = map.get(day) ?? [];
      list.push(item);
      map.set(day, list);
    }
    return map;
  }, [filteredItems, year, viewMonth]);

  const isCurrentMonth =
    today.getFullYear() === year && today.getMonth() + 1 === viewMonth;

  // Pick a sensible default selected day when the month / filters change:
  // today if it has deadlines this month, else the first populated day.
  useEffect(() => {
    const days = [...itemsByDay.keys()].sort((a, b) => a - b);
    if (days.length === 0) {
      setSelectedDay(null);
      return;
    }
    if (isCurrentMonth && itemsByDay.has(today.getDate())) {
      setSelectedDay(today.getDate());
    } else {
      setSelectedDay(days[0]);
    }
  }, [itemsByDay, isCurrentMonth, today]);

  const visibleProviders = useMemo(() => {
    if (!data) return [] as ClientCalendarProvider[];
    if (institutionFilter === "all") return data.providers;
    return data.providers.filter((p) => itemsByProvider.has(p.vendor_id));
  }, [data, itemsByProvider, institutionFilter]);

  const strip = useMemo(() => {
    const atRisk = visibleProviders.filter(
      (p) => p.semaphore_level === "red",
    ).length;
    let overdue = 0;
    let dueSoon = 0;
    let next: { iso: string; vendor: string } | null = null;
    for (const item of filteredItems) {
      if (item.risk_level === "overdue") overdue += 1;
      else if (item.risk_level === "due_soon") dueSoon += 1;
      if (item.risk_level === "on_track") continue;
      const n = daysUntil(item.deadline_iso, today);
      if (n === null || n < 0) continue;
      if (!next || item.deadline_iso < next.iso) {
        next = { iso: item.deadline_iso, vendor: item.vendor_name };
      }
    }
    return { overdue, dueSoon, atRisk, next };
  }, [filteredItems, visibleProviders, today]);

  const currentMonthForMatrix =
    today.getFullYear() === year ? today.getMonth() + 1 : null;

  return (
    <ClientShell
      title="Calendario del cliente"
      description="Revisa los vencimientos de cumplimiento de tu portafolio mes a mes, con el detalle exacto de cada documento."
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
          ) : (
            <>
              <ViewToggle value={viewMode} onChange={setViewMode} />

              {viewMode === "calendar" ? (
                <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(320px,420px)]">
                  <Surface bodyClassName="p-4 sm:p-5">
                    <MonthCalendar
                      year={year}
                      month={viewMonth}
                      itemsByDay={itemsByDay}
                      today={today}
                      selectedDay={selectedDay}
                      onSelectDay={setSelectedDay}
                      onPrevMonth={prevMonth}
                      onNextMonth={nextMonth}
                      onToday={goToday}
                    />
                  </Surface>
                  <DayDetail
                    year={year}
                    month={viewMonth}
                    day={selectedDay}
                    items={selectedDay ? (itemsByDay.get(selectedDay) ?? []) : []}
                    today={today}
                    returnToHref={calendarHref}
                  />
                </div>
              ) : visibleProviders.length === 0 ? (
                <FilteredEmptyState onClear={() => setInstitutionFilter("all")} />
              ) : (
                <div className="space-y-6">
                  <div className="hidden lg:block">
                    <Surface
                      title={`Mapa de riesgo · ${year}`}
                      description="Vistazo anual de todo el portafolio. Toca un proveedor o una celda para abrir su revisión a detalle abajo."
                      bodyClassName="p-4"
                    >
                      <PortfolioMatrix
                        providers={visibleProviders}
                        itemsByCell={itemsByCell}
                        currentMonth={currentMonthForMatrix}
                        onSelectProvider={selectProvider}
                      />
                    </Surface>
                  </div>
                  <section className="space-y-3">
                    <div>
                      <h2 className="text-sm font-semibold text-[color:var(--text-primary)]">
                        Revisión por proveedor
                      </h2>
                      <p className="text-xs text-[color:var(--text-tertiary)]">
                        Ordenados por riesgo. Abre un proveedor para revisar sus
                        obligaciones a detalle.
                      </p>
                    </div>
                    {visibleProviders.map((p) => (
                      <ProviderReviewCard
                        key={p.vendor_id}
                        provider={p}
                        items={itemsByProvider.get(p.vendor_id) ?? []}
                        today={today}
                        returnToHref={calendarHref}
                        open={openProviders.has(p.vendor_id)}
                        onToggle={() => toggleProvider(p.vendor_id)}
                      />
                    ))}
                  </section>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </ClientShell>
  );
}

// ─── View toggle ────────────────────────────────────────────────

function ViewToggle({
  value,
  onChange,
}: {
  value: ViewMode;
  onChange: (v: ViewMode) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="Modo de vista"
      className="inline-flex rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-0.5"
    >
      {(
        [
          { id: "calendar", label: "Calendario" },
          { id: "providers", label: "Por proveedor" },
        ] as const
      ).map((opt) => {
        const active = value === opt.id;
        return (
          <button
            key={opt.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(opt.id)}
            className={
              "rounded-md px-4 py-1.5 text-sm font-medium transition-colors " +
              (active
                ? "bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]"
                : "text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)]")
            }
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

// ─── Selected-day detail ────────────────────────────────────────

function DayDetail({
  year,
  month,
  day,
  items,
  today,
  returnToHref,
}: {
  year: number;
  month: number;
  day: number | null;
  items: ClientCalendarItem[];
  today: Date;
  returnToHref: string;
}) {
  if (day === null || items.length === 0) {
    return (
      <Surface bodyClassName="flex min-h-[200px] items-center justify-center p-6 text-center">
        <p className="text-sm text-[color:var(--text-secondary)]">
          Este mes no tiene vencimientos. Usa ‹ › para cambiar de mes.
        </p>
      </Surface>
    );
  }

  const iso = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;

  // Group the day's obligations by provider, worst-first.
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
  const groups = [...byVendor.values()].sort(
    (a, b) => worstOf(a.items) - worstOf(b.items),
  );

  return (
    <Surface bodyClassName="p-4 sm:p-5">
      <div className="mb-3 border-b border-[color:var(--border-subtle)] pb-3">
        <p className="text-sm font-semibold text-[color:var(--text-primary)]">
          {formatLongDate(iso)}
        </p>
        <p className="text-xs text-[color:var(--text-tertiary)]">
          {relativeDeadline(iso, today).split(" · ")[0]} ·{" "}
          {items.length}{" "}
          {items.length === 1 ? "obligación" : "obligaciones"} ·{" "}
          {groups.length} {groups.length === 1 ? "proveedor" : "proveedores"}
        </p>
      </div>
      <div className="space-y-4">
        {groups.map((g) => (
          <section key={g.name}>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[color:var(--text-secondary)]">
              {g.name}
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
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Funnel
            className="h-3.5 w-3.5 text-[color:var(--text-tertiary)]"
            weight="bold"
            aria-hidden="true"
          />
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

        {hasVendors ? (
          <div className="flex flex-wrap gap-2 border-t border-[color:var(--border-subtle)] pt-3">
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
