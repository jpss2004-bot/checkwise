"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowsClockwise,
  CalendarBlank,
  CaretRight,
  CheckCircle,
  Clock,
  Funnel,
  WarningOctagon,
  type Icon,
} from "@phosphor-icons/react";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  ErrorState,
  Skeleton,
} from "@/components/checkwise/portal/state-surfaces";

import { ClientShell } from "../_shell";
import { ClientItemDrawer } from "@/components/checkwise/calendar/client-item-drawer";
import { PortfolioMatrix } from "@/components/checkwise/calendar/portfolio-matrix";
import {
  INSTITUTION_ICON,
  daysUntil,
  formatShortDate,
  itemStatusDisplay,
  monthOf,
  relativeDeadline,
} from "@/components/checkwise/calendar/client-calendar-shared";
import {
  getClientCalendar,
  listClientVendors,
  type ClientCalendar,
  type ClientCalendarItem,
  type ClientCalendarProvider,
  type ClientCalendarRisk,
  type ClientVendorListResponse,
} from "@/lib/api/client";
import { INSTITUTION_LABELS } from "@/lib/api/portal";
import {
  CALENDAR_MAX_YEAR,
  CALENDAR_MIN_YEAR,
  parseCalendarYear,
} from "@/lib/calendar-year";
import { useUrlClientId } from "@/lib/workspace/use-url-client-id";

// ─── Agenda bands ───────────────────────────────────────────────
// Ordered by what a portfolio overseer must act on first. Resolved
// obligations (on_track) never appear; in_review + upcoming collapse
// into a single informational "later" section.

type BandKey = "overdue" | "action_required" | "due_soon";

const BAND_META: Record<
  BandKey,
  { label: string; hint: string; icon: Icon; tone: "error" | "warning" }
> = {
  overdue: {
    label: "Vencidas",
    hint: "Fuera de plazo. El proveedor ya está en incumplimiento.",
    icon: WarningOctagon,
    tone: "error",
  },
  action_required: {
    label: "Requieren corrección",
    hint: "Rechazadas o con observaciones. El proveedor debe reemplazar el documento.",
    icon: ArrowsClockwise,
    tone: "warning",
  },
  due_soon: {
    label: "Vencen pronto · ≤14 días",
    hint: "Aún a tiempo. Da seguimiento antes de que caigan en incumplimiento.",
    icon: Clock,
    tone: "warning",
  },
};

const TONE_TEXT: Record<"error" | "warning" | "info", string> = {
  error: "text-[color:var(--status-error-text)]",
  warning: "text-[color:var(--status-warning-text)]",
  info: "text-[color:var(--status-info-text)]",
};

const TONE_CHIP: Record<"error" | "warning" | "info" | "neutral", string> = {
  error:
    "border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)]",
  warning:
    "border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)]",
  info: "border-[color:var(--status-info-border)] bg-[color:var(--status-info-bg)] text-[color:var(--status-info-text)]",
  neutral:
    "border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] text-[color:var(--text-tertiary)]",
};

const INSTITUTION_FILTERS: { code: string; label: string }[] = [
  { code: "all", label: "Todas" },
  { code: "sat", label: "SAT" },
  { code: "imss", label: "IMSS" },
  { code: "infonavit", label: "INFONAVIT" },
  { code: "stps_repse", label: "STPS / REPSE" },
];

export default function ClientCalendarPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlClientId = useUrlClientId();
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
  const [vendorsList, setVendorsList] =
    useState<ClientVendorListResponse | null>(null);
  const [showLater, setShowLater] = useState(false);
  const [drawerItems, setDrawerItems] = useState<ClientCalendarItem[] | null>(
    null,
  );

  // ``today`` is read once per mount; the calendar is not a live ticker.
  const [today] = useState(() => new Date());

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

  // Vendor narrowing is server-side; institution narrowing is client-side
  // (the payload already carries every institution).
  const filteredItems = useMemo(() => {
    if (!data) return [] as ClientCalendarItem[];
    const all = data.months.flatMap((m) => m.items);
    if (institutionFilter === "all") return all;
    return all.filter((i) => i.institution === institutionFilter);
  }, [data, institutionFilter]);

  // Item counts per institution (before the institution filter) for chip badges.
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

  const agenda = useMemo(() => {
    const bands: Record<BandKey, ClientCalendarItem[]> & {
      later: ClientCalendarItem[];
    } = { overdue: [], action_required: [], due_soon: [], later: [] };
    for (const item of filteredItems) {
      const r: ClientCalendarRisk | null = item.risk_level;
      if (r === "overdue") bands.overdue.push(item);
      else if (r === "action_required") bands.action_required.push(item);
      else if (r === "due_soon") bands.due_soon.push(item);
      else if (r === "in_review" || r === "upcoming") bands.later.push(item);
      // "on_track" (resolved) is intentionally dropped from the agenda.
    }
    const byDeadline = (a: ClientCalendarItem, b: ClientCalendarItem) =>
      a.deadline_iso.localeCompare(b.deadline_iso);
    for (const key of Object.keys(bands) as (keyof typeof bands)[]) {
      bands[key].sort(byDeadline);
    }
    return bands;
  }, [filteredItems]);

  // Matrix inputs, derived from the filtered items.
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

  const strip = useMemo(() => {
    const atRisk = visibleProviders.filter(
      (p) => p.semaphore_level === "red",
    ).length;
    let next: { iso: string; vendor: string } | null = null;
    for (const item of filteredItems) {
      if (item.risk_level === "on_track") continue;
      const n = daysUntil(item.deadline_iso, today);
      if (n === null || n < 0) continue; // only upcoming, not overdue
      if (!next || item.deadline_iso < next.iso) {
        next = { iso: item.deadline_iso, vendor: item.vendor_name };
      }
    }
    return {
      overdue: agenda.overdue.length,
      dueSoon: agenda.due_soon.length,
      atRisk,
      next,
    };
  }, [agenda, visibleProviders, filteredItems, today]);

  const currentMonth =
    today.getFullYear() === year ? today.getMonth() + 1 : null;
  const actionableTotal =
    agenda.overdue.length +
    agenda.action_required.length +
    agenda.due_soon.length;

  return (
    <ClientShell
      title="Calendario del cliente"
      description="Lo que debes atender en tu portafolio, ordenado por urgencia: qué está vencido, qué vence pronto y qué proveedor te pone en riesgo."
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
              {actionableTotal === 0 ? (
                <AllClearState filtered={institutionFilter !== "all"} />
              ) : (
                <Surface
                  title="Por atender"
                  description="Toca una obligación para ver el detalle, abrir el expediente del proveedor o empaquetar el periodo."
                  bodyClassName="p-0"
                >
                  <div className="divide-y divide-[color:var(--border-subtle)]">
                    {(Object.keys(BAND_META) as BandKey[]).map((key) =>
                      agenda[key].length > 0 ? (
                        <AgendaBand
                          key={key}
                          bandKey={key}
                          items={agenda[key]}
                          today={today}
                          onOpen={setDrawerItems}
                        />
                      ) : null,
                    )}
                    {agenda.later.length > 0 ? (
                      <LaterBand
                        items={agenda.later}
                        today={today}
                        open={showLater}
                        onToggle={() => setShowLater((v) => !v)}
                        onOpen={setDrawerItems}
                      />
                    ) : null}
                  </div>
                </Surface>
              )}

              {visibleProviders.length > 0 ? (
                <Surface
                  title={`Mapa de riesgo · ${year}`}
                  description="Cada celda muestra el estado más crítico de ese proveedor en el mes. Toca una celda para ver sus obligaciones."
                  bodyClassName="p-3 lg:p-4"
                >
                  <PortfolioMatrix
                    providers={visibleProviders}
                    itemsByCell={itemsByCell}
                    currentMonth={currentMonth}
                    onOpenCell={(items) =>
                      items.length > 0 ? setDrawerItems(items) : undefined
                    }
                    returnToHref={calendarHref}
                  />
                </Surface>
              ) : null}
            </>
          )}
        </div>
      )}

      {drawerItems && drawerItems.length > 0 ? (
        <ClientItemDrawer
          items={drawerItems}
          year={year}
          today={today}
          returnToHref={calendarHref}
          onClose={() => setDrawerItems(null)}
        />
      ) : null}
    </ClientShell>
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
    <div className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-4 py-3">
      <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        {label}
      </p>
      <p
        className={
          "mt-1 font-mono text-2xl font-semibold tabular-nums " +
          (muted ? "text-[color:var(--text-secondary)]" : TONE_TEXT[tone])
        }
      >
        {value}
      </p>
      {sub ? (
        <p className="mt-0.5 truncate text-[11px] text-[color:var(--text-tertiary)]">
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
        {/* Institution axis */}
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

        {/* Vendor axis */}
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

// ─── Agenda bands ───────────────────────────────────────────────

function AgendaBand({
  bandKey,
  items,
  today,
  onOpen,
}: {
  bandKey: BandKey;
  items: ClientCalendarItem[];
  today: Date;
  onOpen: (items: ClientCalendarItem[]) => void;
}) {
  const meta = BAND_META[bandKey];
  const BandIcon = meta.icon;
  return (
    <section>
      <header className="flex items-center gap-2 bg-[color:var(--surface-page)] px-4 py-2.5">
        <BandIcon
          className={"h-4 w-4 " + TONE_TEXT[meta.tone]}
          weight="fill"
          aria-hidden="true"
        />
        <h3 className="text-[13px] font-semibold text-[color:var(--text-primary)]">
          {meta.label}
        </h3>
        <span
          className={
            "rounded-full border px-2 py-0.5 font-mono text-[10px] tabular-nums " +
            TONE_CHIP[meta.tone]
          }
        >
          {items.length}
        </span>
        <span className="hidden truncate text-[11px] text-[color:var(--text-tertiary)] sm:inline">
          {meta.hint}
        </span>
      </header>
      <AgendaRows items={items} today={today} onOpen={onOpen} />
    </section>
  );
}

const AGENDA_BAND_CAP = 8;

/** Row list for one band, capped so a heavily non-compliant portfolio
 *  (hundreds of overdue obligations) doesn't render as an endless wall.
 *  "Ver N más" reveals the rest in place. */
function AgendaRows({
  items,
  today,
  onOpen,
}: {
  items: ClientCalendarItem[];
  today: Date;
  onOpen: (items: ClientCalendarItem[]) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? items : items.slice(0, AGENDA_BAND_CAP);
  const hidden = items.length - visible.length;
  return (
    <>
      <ul className="divide-y divide-[color:var(--border-subtle)]">
        {visible.map((item) => (
          <AgendaRow
            key={`${item.vendor_id}-${item.requirement_code ?? item.requirement_name}-${item.period_key ?? ""}`}
            item={item}
            today={today}
            onOpen={onOpen}
          />
        ))}
      </ul>
      {items.length > AGENDA_BAND_CAP ? (
        <div className="border-t border-[color:var(--border-subtle)] px-4 py-2">
          <button
            type="button"
            onClick={() => setShowAll((v) => !v)}
            className="text-xs font-medium text-[color:var(--text-brand)] hover:underline"
          >
            {showAll ? "Ver menos" : `Ver ${hidden} más`}
          </button>
        </div>
      ) : null}
    </>
  );
}

function LaterBand({
  items,
  today,
  open,
  onToggle,
  onOpen,
}: {
  items: ClientCalendarItem[];
  today: Date;
  open: boolean;
  onToggle: () => void;
  onOpen: (items: ClientCalendarItem[]) => void;
}) {
  return (
    <section>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center gap-2 bg-[color:var(--surface-page)] px-4 py-2.5 text-left hover:bg-[color:var(--surface-hover)]"
      >
        <CaretRight
          className={
            "h-3.5 w-3.5 text-[color:var(--text-tertiary)] transition-transform " +
            (open ? "rotate-90" : "")
          }
          weight="bold"
          aria-hidden="true"
        />
        <h3 className="text-[13px] font-semibold text-[color:var(--text-primary)]">
          Próximas y en revisión
        </h3>
        <span
          className={
            "rounded-full border px-2 py-0.5 font-mono text-[10px] tabular-nums " +
            TONE_CHIP.neutral
          }
        >
          {items.length}
        </span>
        <span className="hidden text-[11px] text-[color:var(--text-tertiary)] sm:inline">
          A tiempo o ya con el revisor. No requieren acción inmediata.
        </span>
      </button>
      {open ? (
        <AgendaRows items={items} today={today} onOpen={onOpen} />
      ) : null}
    </section>
  );
}

function AgendaRow({
  item,
  today,
  onOpen,
}: {
  item: ClientCalendarItem;
  today: Date;
  onOpen: (items: ClientCalendarItem[]) => void;
}) {
  const InstitutionIcon = INSTITUTION_ICON[item.institution];
  const institutionLabel =
    INSTITUTION_LABELS[item.institution] ?? item.institution;
  const statusDisplay = itemStatusDisplay(item);
  const overdue = item.risk_level === "overdue";

  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen([item])}
        className="flex w-full flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 text-left transition-colors hover:bg-[color:var(--surface-hover)] focus:outline-none focus-visible:bg-[color:var(--surface-hover)]"
      >
        <div className="min-w-[180px] flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-[13px] font-semibold text-[color:var(--text-primary)]">
              {item.vendor_name}
            </span>
            <Badge variant={statusDisplay.variant}>{statusDisplay.label}</Badge>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[color:var(--text-secondary)]">
            {InstitutionIcon ? (
              <InstitutionIcon
                className="h-3.5 w-3.5 shrink-0 text-[color:var(--text-brand)]"
                weight="bold"
                aria-hidden="true"
              />
            ) : null}
            <span className="font-medium text-[color:var(--text-primary)]">
              {item.requirement_name}
            </span>
            <span className="text-[color:var(--text-tertiary)]">·</span>
            <span>{institutionLabel}</span>
            <span className="text-[color:var(--text-tertiary)]">·</span>
            <span className="font-mono text-[10px] text-[color:var(--text-tertiary)]">
              {item.period_label}
            </span>
          </div>
        </div>

        <p
          className={
            "min-w-[150px] text-xs font-medium tabular-nums " +
            (overdue
              ? "text-[color:var(--status-error-text)]"
              : "text-[color:var(--text-secondary)]")
          }
        >
          {relativeDeadline(item.deadline_iso, today)}
        </p>

        <CaretRight
          className="h-4 w-4 shrink-0 text-[color:var(--text-tertiary)]"
          weight="bold"
          aria-hidden="true"
        />
      </button>
    </li>
  );
}

// ─── Empty + loading states ─────────────────────────────────────

function AllClearState({ filtered }: { filtered: boolean }) {
  return (
    <section className="rounded-lg border border-dashed border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] px-6 py-10 text-center">
      <CheckCircle
        className="mx-auto h-8 w-8 text-[color:var(--status-success-text)]"
        weight="fill"
        aria-hidden="true"
      />
      <p className="mt-3 font-mono text-[10px] uppercase tracking-wide text-[color:var(--status-success-text)]">
        Todo al día
      </p>
      <p className="mt-1 text-sm text-[color:var(--text-primary)]">
        {filtered
          ? "Ningún proveedor tiene obligaciones vencidas, por corregir o por vencer con los filtros actuales."
          : "Ningún proveedor de tu portafolio tiene obligaciones vencidas, por corregir o por vencer. Te avisaremos cuando aparezca la próxima."}
      </p>
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
    <div className="space-y-5" aria-busy="true" aria-live="polite">
      <span className="sr-only">Cargando calendario…</span>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-20 w-full rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-24 w-full rounded-lg" />
      <Skeleton className="h-80 w-full rounded-lg" />
    </div>
  );
}
