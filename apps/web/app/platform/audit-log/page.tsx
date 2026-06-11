"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  CaretRight,
  Check,
  Copy,
  MagnifyingGlass,
  Robot,
  Tray,
  User,
} from "@phosphor-icons/react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  EmptyState,
  ErrorState,
  Skeleton,
} from "@/components/checkwise/portal/state-surfaces";
import { cn } from "@/lib/utils";

import { PlatformShell } from "../_shell";
import {
  type AdminAuditLogItem,
  listAuditLog,
} from "@/lib/api/admin";

const PAGE_SIZE = 50;

/** Seed list of common action prefixes; merged with the distinct
 *  actions of the currently loaded page for the <datalist>. */
const ACTION_SEEDS = [
  "admin.",
  "client.",
  "provider.",
  "reviewer.",
  "auth.",
];

/** Seed list of entity types; merged with distinct values loaded. */
const ENTITY_TYPE_SEEDS = [
  "user",
  "client",
  "vendor",
  "submission",
  "workspace",
  "requirement",
  "report",
];

const ACTOR_TYPES = [
  "internal_admin",
  "client_admin",
  "reviewer",
  "provider",
  "system",
];

type Filters = {
  actor_id: string;
  actor_type: string;
  action: string;
  entity_type: string;
  entity_id: string;
  date_from: string;
  date_to: string;
};

const EMPTY_FILTERS: Filters = {
  actor_id: "",
  actor_type: "",
  action: "",
  entity_type: "",
  entity_id: "",
  date_from: "",
  date_to: "",
};

export default function AdminAuditLogPage() {
  const [rows, setRows] = useState<AdminAuditLogItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState(false);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  // Filters in effect for the loaded list — editing the form doesn't
  // change pagination params until "Aplicar filtros" is pressed.
  const [applied, setApplied] = useState<Filters>(EMPTY_FILTERS);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  async function refresh(next = filters) {
    setLoading(true);
    setError(null);
    setLoadMoreError(false);
    setExpanded(new Set());
    try {
      const data = await listAuditLog({
        ...next,
        limit: PAGE_SIZE,
        offset: 0,
      });
      setRows(data.items);
      setTotal(data.total);
      setApplied(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar audit log.");
      setRows(null);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }

  async function loadMore() {
    if (!rows || loadingMore) return;
    setLoadingMore(true);
    setLoadMoreError(false);
    try {
      const data = await listAuditLog({
        ...applied,
        limit: PAGE_SIZE,
        offset: rows.length,
      });
      setRows((prev) => [...(prev ?? []), ...data.items]);
      setTotal(data.total);
    } catch {
      setLoadMoreError(true);
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggleRow(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // Datalist / select options: static seeds + distinct values from the
  // currently loaded page (keeps the controls honest as data grows).
  const actionOptions = useMemo(() => {
    const set = new Set(ACTION_SEEDS);
    for (const row of rows ?? []) set.add(row.action);
    return Array.from(set).sort();
  }, [rows]);

  const entityTypeOptions = useMemo(() => {
    const set = new Set(ENTITY_TYPE_SEEDS);
    for (const row of rows ?? []) set.add(row.entity_type);
    if (filters.entity_type) set.add(filters.entity_type);
    return Array.from(set).sort();
  }, [rows, filters.entity_type]);

  const actorTypeOptions = useMemo(() => {
    const set = new Set(ACTOR_TYPES);
    if (filters.actor_type) set.add(filters.actor_type);
    return Array.from(set);
  }, [filters.actor_type]);

  return (
    <PlatformShell
      title="Audit log"
      description="Bitácora completa de eventos del sistema. Cada cambio firma el actor, la acción, la entidad y el diff antes/después."
    >
      <div className="space-y-5">
        <section
          aria-label="Filtros"
          className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs"
        >
          <header className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] px-5 py-3">
            <MagnifyingGlass
              className="h-3.5 w-3.5 text-[color:var(--text-tertiary)]"
              weight="bold"
              aria-hidden
            />
            <p className="cw-eyebrow">Filtros</p>
          </header>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              refresh();
            }}
            className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-4"
          >
            <div className="space-y-1">
              <Label htmlFor="al-actor-type">Tipo de actor</Label>
              <Select
                id="al-actor-type"
                value={filters.actor_type}
                onChange={(e) =>
                  setFilters({ ...filters, actor_type: e.target.value })
                }
                className="h-10 text-[13px]"
              >
                <option value="">Todos</option>
                {actorTypeOptions.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="al-action">Acción</Label>
              <Input
                id="al-action"
                value={filters.action}
                onChange={(e) => setFilters({ ...filters, action: e.target.value })}
                placeholder="admin."
                className="font-mono"
                list="al-action-options"
                aria-describedby="al-action-hint"
              />
              <datalist id="al-action-options">
                {actionOptions.map((a) => (
                  <option key={a} value={a} />
                ))}
              </datalist>
              <p
                id="al-action-hint"
                className="text-[11px] text-[color:var(--text-tertiary)]"
              >
                Coincide por prefijo: «admin.user» encuentra admin.user_disabled…
              </p>
            </div>
            <div className="space-y-1">
              <Label htmlFor="al-entity">Tipo de entidad</Label>
              <Select
                id="al-entity"
                value={filters.entity_type}
                onChange={(e) =>
                  setFilters({ ...filters, entity_type: e.target.value })
                }
                className="h-10 text-[13px]"
              >
                <option value="">Todos</option>
                {entityTypeOptions.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="al-entid">ID de entidad</Label>
              <Input
                id="al-entid"
                value={filters.entity_id}
                onChange={(e) =>
                  setFilters({ ...filters, entity_id: e.target.value })
                }
                className="font-mono"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="al-actorid">ID de actor</Label>
              <Input
                id="al-actorid"
                value={filters.actor_id}
                onChange={(e) =>
                  setFilters({ ...filters, actor_id: e.target.value })
                }
                className="font-mono"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="al-from">Desde</Label>
              <Input
                id="al-from"
                type="date"
                value={filters.date_from}
                onChange={(e) =>
                  setFilters({ ...filters, date_from: e.target.value })
                }
                max={filters.date_to || undefined}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="al-to">Hasta</Label>
              <Input
                id="al-to"
                type="date"
                value={filters.date_to}
                onChange={(e) =>
                  setFilters({ ...filters, date_to: e.target.value })
                }
                min={filters.date_from || undefined}
              />
            </div>
            <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-1">
              <Button type="submit" size="sm" loading={loading}>
                Aplicar filtros
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={loading}
                onClick={() => {
                  setFilters(EMPTY_FILTERS);
                  refresh(EMPTY_FILTERS);
                }}
              >
                Limpiar
              </Button>
            </div>
          </form>
        </section>

        {loading ? (
          <AuditLogSkeleton />
        ) : error ? (
          <ErrorState
            title="No pudimos cargar esta sección"
            description={error}
            onRetry={() => refresh()}
          />
        ) : !rows || rows.length === 0 ? (
          <EmptyState
            icon={Tray}
            title="Sin eventos"
            description="No hay eventos para los filtros aplicados."
            variant="muted"
          />
        ) : (
          <section
            aria-label="Eventos del audit log"
            className="cw-fade-up rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs"
          >
            <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[color:var(--border-subtle)] px-5 py-3">
              <p className="cw-eyebrow">Eventos</p>
              <Badge variant="outline" className="whitespace-nowrap">
                {total} eventos
              </Badge>
            </header>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[36px]">
                    <span className="sr-only">Detalle</span>
                  </TableHead>
                  <TableHead style={{ width: "170px" }}>Cuándo</TableHead>
                  <TableHead>Actor</TableHead>
                  <TableHead>Acción</TableHead>
                  <TableHead style={{ width: "120px" }}>Entidad</TableHead>
                  <TableHead style={{ width: "150px" }}>ID</TableHead>
                  <TableHead style={{ width: "110px" }}>Fuente</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <AuditLogRow
                    key={row.id}
                    row={row}
                    expanded={expanded.has(row.id)}
                    onToggle={() => toggleRow(row.id)}
                  />
                ))}
              </TableBody>
            </Table>
            <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-[color:var(--border-subtle)] px-5 py-3">
              <p className="text-[12px] tabular-nums text-[color:var(--text-secondary)]">
                Mostrando {rows.length} de {total} eventos
              </p>
              {rows.length < total ? (
                <div className="flex items-center gap-3">
                  {loadMoreError ? (
                    <span className="text-[12px] text-[color:var(--status-error-text)]">
                      No pudimos cargar más. Intenta de nuevo.
                    </span>
                  ) : null}
                  <Button
                    variant="outline"
                    size="sm"
                    loading={loadingMore}
                    onClick={loadMore}
                  >
                    Cargar más
                  </Button>
                </div>
              ) : null}
            </footer>
          </section>
        )}
      </div>
    </PlatformShell>
  );
}

// ---------------------------------------------------------------------------
// Rows
// ---------------------------------------------------------------------------

function AuditLogRow({
  row,
  expanded,
  onToggle,
}: {
  row: AdminAuditLogItem;
  expanded: boolean;
  onToggle: () => void;
}) {
  const detailId = `audit-detail-${row.id}`;
  return (
    <Fragment>
      <TableRow
        onClick={onToggle}
        className="cursor-pointer"
        aria-label={`Evento ${row.action}`}
      >
        <TableCell className="align-middle">
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls={detailId}
            aria-label={expanded ? "Ocultar detalle" : "Ver detalle"}
            onClick={(e) => {
              e.stopPropagation();
              onToggle();
            }}
            className="flex h-6 w-6 items-center justify-center rounded-sm text-[color:var(--text-tertiary)] transition-colors hover:bg-[color:var(--surface-sunken)] hover:text-[color:var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40"
          >
            <CaretRight
              className={cn(
                "h-3.5 w-3.5 transition-transform duration-fast",
                expanded && "rotate-90",
              )}
              weight="bold"
              aria-hidden
            />
          </button>
        </TableCell>
        <TableCell>
          <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-secondary)]">
            {new Date(row.created_at).toLocaleString("es-MX")}
          </span>
        </TableCell>
        <TableCell>
          <ActorChip
            actorType={row.actor_type}
            actorId={row.actor_id}
            actorEmail={row.actor_email}
          />
        </TableCell>
        <TableCell>
          <code className="rounded-sm bg-[color:var(--surface-sunken)] px-1.5 py-0.5 font-mono text-[11px] text-[color:var(--text-primary)]">
            {row.action}
          </code>
        </TableCell>
        <TableCell>
          <Badge variant="outline">{row.entity_type}</Badge>
        </TableCell>
        <TableCell>
          <span className="flex items-center gap-1">
            <span
              className="font-mono text-[11px] tabular-nums text-[color:var(--text-tertiary)]"
              title={row.entity_id}
            >
              {row.entity_id.slice(0, 8)}…
            </span>
            <CopyIdButton value={row.entity_id} />
          </span>
        </TableCell>
        <TableCell>
          <span className="text-[11px] text-[color:var(--text-secondary)]">
            {(row.event_metadata?.source as string | undefined) ?? "—"}
          </span>
        </TableCell>
      </TableRow>
      {expanded ? (
        <TableRow className="bg-[color:var(--surface-sunken)]/50 hover:bg-[color:var(--surface-sunken)]/50">
          <TableCell colSpan={7} className="px-5 py-4" id={detailId}>
            <DiffPanel row={row} />
          </TableCell>
        </TableRow>
      ) : null}
    </Fragment>
  );
}

function ActorChip({
  actorType,
  actorId,
  actorEmail,
}: {
  actorType: string;
  actorId: string | null;
  actorEmail: string | null;
}) {
  const isBot = actorType.includes("system") || actorType.includes("bot");
  const IconComponent = isBot ? Robot : User;
  return (
    <div className="flex items-center gap-2">
      <span
        className={
          "flex h-6 w-6 shrink-0 items-center justify-center rounded-full " +
          (isBot
            ? "bg-[color:var(--surface-teal-muted)] text-[color:var(--text-teal)]"
            : "bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]")
        }
        aria-hidden="true"
      >
        <IconComponent className="h-3 w-3" weight="bold" />
      </span>
      <div className="min-w-0">
        {actorEmail ? (
          <p
            className="max-w-[200px] truncate font-mono text-[11px] text-[color:var(--text-primary)]"
            title={actorEmail}
          >
            {actorEmail}
          </p>
        ) : actorId ? (
          <p className="flex items-center gap-1">
            <span
              className="font-mono text-[11px] tabular-nums text-[color:var(--text-primary)]"
              title={actorId}
            >
              {actorId.slice(0, 8)}…
            </span>
            <CopyIdButton value={actorId} />
          </p>
        ) : null}
        <p className="text-[10px] text-[color:var(--text-tertiary)]">
          {actorType}
        </p>
      </div>
    </div>
  );
}

function CopyIdButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      title="Copiar ID completo"
      aria-label="Copiar ID completo"
      onClick={async (e) => {
        e.stopPropagation();
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          // Clipboard unavailable (permissions/insecure context): no-op.
        }
      }}
      className="inline-flex shrink-0 items-center gap-0.5 rounded-sm p-0.5 text-[color:var(--text-tertiary)] transition-colors hover:bg-[color:var(--surface-sunken)] hover:text-[color:var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40"
    >
      {copied ? (
        <>
          <Check
            className="h-3 w-3 text-[color:var(--status-success-text)]"
            weight="bold"
            aria-hidden
          />
          <span className="text-[10px] text-[color:var(--status-success-text)]">
            Copiado
          </span>
        </>
      ) : (
        <Copy className="h-3 w-3" weight="bold" aria-hidden />
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Before/after diff (pure presentation, no lib)
// ---------------------------------------------------------------------------

type DiffKind = "added" | "removed" | "changed" | "unchanged";

type DiffEntry = {
  key: string;
  kind: DiffKind;
  before: unknown;
  after: unknown;
};

function buildDiff(
  before: Record<string, unknown>,
  after: Record<string, unknown>,
): DiffEntry[] {
  const keys = Array.from(
    new Set([...Object.keys(before), ...Object.keys(after)]),
  ).sort();
  return keys.map((key) => {
    const inBefore = key in before;
    const inAfter = key in after;
    let kind: DiffKind;
    if (!inBefore) kind = "added";
    else if (!inAfter) kind = "removed";
    else if (JSON.stringify(before[key]) === JSON.stringify(after[key]))
      kind = "unchanged";
    else kind = "changed";
    return { key, kind, before: before[key], after: after[key] };
  });
}

const DIFF_KEY_TONE: Record<DiffKind, string> = {
  added: "text-[color:var(--status-success-text)]",
  removed: "text-[color:var(--status-error-text)]",
  changed: "text-[color:var(--status-warning-text)]",
  unchanged: "text-[color:var(--text-tertiary)]",
};

const DIFF_KIND_LABEL: Record<DiffKind, string> = {
  added: "agregado",
  removed: "eliminado",
  changed: "modificado",
  unchanged: "sin cambio",
};

function DiffPanel({ row }: { row: AdminAuditLogItem }) {
  const { before, after, event_metadata } = row;

  if (before && after) {
    return (
      <DiffList
        title="Diff antes / después"
        entries={buildDiff(before, after)}
      />
    );
  }
  if (after) {
    return (
      <KeyValueList
        title="Valores al crear"
        data={after}
        keyTone={DIFF_KEY_TONE.added}
      />
    );
  }
  if (before) {
    return (
      <KeyValueList
        title="Valores antes de eliminar"
        data={before}
        keyTone={DIFF_KEY_TONE.removed}
      />
    );
  }
  if (event_metadata && Object.keys(event_metadata).length > 0) {
    return <KeyValueList title="Metadata del evento" data={event_metadata} />;
  }
  return (
    <p className="text-[12px] text-[color:var(--text-tertiary)]">
      Este evento no registró diff ni metadata adicional.
    </p>
  );
}

function DiffList({ title, entries }: { title: string; entries: DiffEntry[] }) {
  if (entries.length === 0) {
    return (
      <p className="text-[12px] text-[color:var(--text-tertiary)]">
        Sin campos en el diff.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      <p className="cw-eyebrow">{title}</p>
      <dl className="space-y-1">
        {entries.map((entry) => (
          <div
            key={entry.key}
            className="grid grid-cols-[minmax(120px,200px)_1fr] items-start gap-x-3 gap-y-0.5"
          >
            <dt
              className={cn(
                "flex items-center gap-1.5 font-mono text-[11px] font-medium",
                DIFF_KEY_TONE[entry.kind],
              )}
            >
              {entry.key}
              {entry.kind !== "unchanged" ? (
                <span className="text-[9px] font-normal uppercase tracking-wide opacity-80">
                  {DIFF_KIND_LABEL[entry.kind]}
                </span>
              ) : null}
            </dt>
            <dd
              className={cn(
                "flex flex-wrap items-center gap-1.5",
                entry.kind === "unchanged" && "opacity-60",
              )}
            >
              {entry.kind === "added" ? (
                <DiffValue value={entry.after} />
              ) : entry.kind === "removed" ? (
                <DiffValue value={entry.before} strike />
              ) : (
                <>
                  <DiffValue
                    value={entry.before}
                    strike={entry.kind === "changed"}
                  />
                  <ArrowRight
                    className="h-3 w-3 shrink-0 text-[color:var(--text-tertiary)]"
                    weight="bold"
                    aria-hidden
                  />
                  <DiffValue value={entry.after} />
                </>
              )}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function KeyValueList({
  title,
  data,
  keyTone,
}: {
  title: string;
  data: Record<string, unknown>;
  keyTone?: string;
}) {
  const keys = Object.keys(data).sort();
  if (keys.length === 0) {
    return (
      <p className="text-[12px] text-[color:var(--text-tertiary)]">
        Sin campos registrados.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      <p className="cw-eyebrow">{title}</p>
      <dl className="space-y-1">
        {keys.map((key) => (
          <div
            key={key}
            className="grid grid-cols-[minmax(120px,200px)_1fr] items-start gap-x-3"
          >
            <dt
              className={cn(
                "font-mono text-[11px] font-medium",
                keyTone ?? "text-[color:var(--text-secondary)]",
              )}
            >
              {key}
            </dt>
            <dd>
              <DiffValue value={data[key]} />
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

const VALUE_MAX_CHARS = 120;

/** Stringify a diff value (scalar or nested) and truncate long ones,
 *  exposing the full text via the title attribute. */
function DiffValue({ value, strike = false }: { value: unknown; strike?: boolean }) {
  const text =
    value === undefined ? "—" : (JSON.stringify(value) ?? String(value));
  const truncated =
    text.length > VALUE_MAX_CHARS
      ? `${text.slice(0, VALUE_MAX_CHARS)}…`
      : text;
  return (
    <span
      title={text.length > VALUE_MAX_CHARS ? text : undefined}
      className={cn(
        "break-all font-mono text-[11px] text-[color:var(--text-primary)]",
        strike && "line-through opacity-70",
      )}
    >
      {truncated}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function AuditLogSkeleton() {
  return (
    <section
      aria-busy="true"
      className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs"
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-[color:var(--border-subtle)] px-5 py-3">
        <Skeleton className="h-7 w-24 rounded-md" />
        <Skeleton className="ml-auto h-5 w-20 rounded-full" />
      </header>
      <div className="divide-y divide-[color:var(--border-subtle)]">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="grid items-center gap-3 px-5 py-3"
            style={{ gridTemplateColumns: "repeat(6, minmax(0, 1fr))" }}
          >
            {Array.from({ length: 6 }).map((_, j) => (
              <Skeleton
                key={j}
                className={cn("h-4", j === 0 ? "w-24" : "w-full")}
              />
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}
