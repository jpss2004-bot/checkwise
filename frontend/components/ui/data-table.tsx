"use client";

import { type ReactNode, useMemo, useState } from "react";
import { ArrowRight, Tray } from "@phosphor-icons/react";

import { cn } from "@/lib/utils";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import {
  EmptyState,
  ErrorState,
  Skeleton,
} from "@/components/checkwise/portal/state-surfaces";

/**
 * DataTable — shared roster primitive (V2.1 / Phase 5).
 *
 * Extracted from /admin/reviewer, which Phase 1 audit named the
 * "gold-standard" table. Used across /admin/{vendors,clients,
 * requirements,audit-log} and /client/{submissions,vendors}.
 *
 * Renders:
 *   - tabbed filter strip (optional)
 *   - sticky meta badge (optional)
 *   - real <table> with token chrome
 *   - row click → onRowClick(item)
 *   - skeleton / empty / filtered-empty / error states
 *
 * Intentionally simple: no sorting, no pagination, no row selection.
 * Phase 5 keeps it scoped to V2.1 needs.
 */

export type DataTableColumn<T> = {
  id: string;
  header: ReactNode;
  cell: (item: T) => ReactNode;
  width?: string;
  align?: "left" | "right";
  className?: string;
};

export type DataTableFilter<T, K extends string> = {
  key: K;
  label: string;
  match: (item: T) => boolean;
};

type DataTableProps<T, K extends string> = {
  items: T[] | null;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  columns: DataTableColumn<T>[];
  rowKey: (item: T) => string;
  onRowClick?: (item: T) => void;
  rowLabel?: (item: T) => string;
  emptyTitle?: string;
  emptyDescription?: string;
  filters?: DataTableFilter<T, K>[];
  initialFilter?: K;
  metaBadge?: ReactNode;
  ariaLabel?: string;
  caption?: string;
  className?: string;
  skeletonRows?: number;
};

export function DataTable<T, K extends string = string>({
  items,
  loading = false,
  error = null,
  onRetry,
  columns,
  rowKey,
  onRowClick,
  rowLabel,
  emptyTitle = "Sin resultados",
  emptyDescription = "Cuando haya registros aparecerán aquí.",
  filters,
  initialFilter,
  metaBadge,
  ariaLabel,
  caption,
  className,
  skeletonRows = 5,
}: DataTableProps<T, K>) {
  const [filter, setFilter] = useState<K | "all">(
    (initialFilter as K | "all" | undefined) ?? "all",
  );

  const counts = useMemo<Record<string, number>>(() => {
    const acc: Record<string, number> = { all: items?.length ?? 0 };
    if (!filters || !items) return acc;
    for (const f of filters) acc[f.key] = 0;
    for (const item of items) {
      for (const f of filters) if (f.match(item)) acc[f.key] += 1;
    }
    return acc;
  }, [items, filters]);

  const visible = useMemo(() => {
    if (!items) return [];
    if (!filters || filter === "all") return items;
    const f = filters.find((x) => x.key === filter);
    return f ? items.filter(f.match) : items;
  }, [items, filters, filter]);

  if (loading) {
    return <DataTableSkeleton rows={skeletonRows} columns={columns.length} />;
  }

  if (error) {
    return (
      <ErrorState
        title="No pudimos cargar esta sección"
        description={error}
        onRetry={onRetry}
      />
    );
  }

  if (!items || items.length === 0) {
    return (
      <EmptyState
        icon={Tray}
        title={emptyTitle}
        description={emptyDescription}
        variant="muted"
      />
    );
  }

  return (
    <section
      aria-label={ariaLabel}
      className={cn(
        "cw-fade-up rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs",
        className,
      )}
    >
      {(filters && filters.length > 0) || metaBadge ? (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[color:var(--border-subtle)] px-5 py-3">
          {filters && filters.length > 0 ? (
            <Tabs
              value={filter}
              onValueChange={(v) => setFilter(v as K | "all")}
            >
              <TabsList>
                <TabsTrigger value="all">
                  <span>Todos</span>
                  <span className="ml-1.5 font-mono text-[10px] tabular-nums opacity-70">
                    {counts.all ?? 0}
                  </span>
                </TabsTrigger>
                {filters.map((f) => (
                  <TabsTrigger key={f.key} value={f.key}>
                    <span>{f.label}</span>
                    <span className="ml-1.5 font-mono text-[10px] tabular-nums opacity-70">
                      {counts[f.key] ?? 0}
                    </span>
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          ) : (
            <span />
          )}
          {metaBadge ? (
            typeof metaBadge === "string" ? (
              <Badge variant="outline" className="whitespace-nowrap">
                {metaBadge}
              </Badge>
            ) : (
              metaBadge
            )
          ) : null}
        </header>
      ) : null}

      {visible.length === 0 ? (
        <div className="px-5 py-10">
          <EmptyState
            icon={Tray}
            title="Sin resultados en este filtro"
            description="Cambia el filtro para ver otros registros."
            variant="muted"
          />
        </div>
      ) : (
        <Table>
          {caption ? (
            <caption className="sr-only">{caption}</caption>
          ) : null}
          <TableHeader>
            <TableRow>
              {columns.map((col) => (
                <TableHead
                  key={col.id}
                  style={col.width ? { width: col.width } : undefined}
                  className={cn(
                    col.align === "right" ? "text-right" : undefined,
                    col.className,
                  )}
                >
                  {col.header}
                </TableHead>
              ))}
              {onRowClick ? (
                <TableHead className="w-[40px]" aria-label="Abrir" />
              ) : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {visible.map((item) => (
              <DataTableRow
                key={rowKey(item)}
                item={item}
                columns={columns}
                onRowClick={onRowClick}
                rowLabel={rowLabel}
              />
            ))}
          </TableBody>
        </Table>
      )}
    </section>
  );
}

function DataTableRow<T>({
  item,
  columns,
  onRowClick,
  rowLabel,
}: {
  item: T;
  columns: DataTableColumn<T>[];
  onRowClick?: (item: T) => void;
  rowLabel?: (item: T) => string;
}) {
  const clickable = Boolean(onRowClick);
  return (
    <TableRow
      onClick={clickable ? () => onRowClick?.(item) : undefined}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onRowClick?.(item);
              }
            }
          : undefined
      }
      tabIndex={clickable ? 0 : undefined}
      role={clickable ? "link" : undefined}
      aria-label={clickable && rowLabel ? rowLabel(item) : undefined}
      className={cn(
        clickable &&
          "group cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[color:var(--border-focus)]/40",
      )}
    >
      {columns.map((col) => (
        <TableCell
          key={col.id}
          className={cn(
            col.align === "right" ? "text-right" : undefined,
            col.className,
          )}
        >
          {col.cell(item)}
        </TableCell>
      ))}
      {onRowClick ? (
        <TableCell className="text-right">
          <ArrowRight
            className="ml-auto h-4 w-4 text-[color:var(--text-tertiary)] transition-transform duration-fast group-hover:translate-x-0.5"
            weight="bold"
            aria-hidden
          />
        </TableCell>
      ) : null}
    </TableRow>
  );
}

function DataTableSkeleton({
  rows = 5,
  columns = 5,
}: {
  rows?: number;
  columns?: number;
}) {
  return (
    <section
      aria-busy="true"
      className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs"
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-[color:var(--border-subtle)] px-5 py-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-7 w-24 rounded-md" />
        ))}
      </header>
      <div className="divide-y divide-[color:var(--border-subtle)]">
        {Array.from({ length: rows }).map((_, i) => (
          <div
            key={i}
            className="grid items-center gap-3 px-5 py-3"
            style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
          >
            {Array.from({ length: columns }).map((_, j) => (
              <Skeleton
                key={j}
                className={cn(
                  "h-4",
                  j === 0 ? "w-24" : j === columns - 1 ? "w-12" : "w-full",
                )}
              />
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}
