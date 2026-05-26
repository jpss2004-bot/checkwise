"use client";

/**
 * Phase 7 / Slice N9 — notification center UX rebuild (client_admin).
 *
 * Three-tab layout (Pendientes / Todas / Resueltas) + category
 * filter chips + severity-aware left rail. Replaces the old
 * grouped-by-day stream so the bell stops feeling like a junk
 * drawer — the default tab only surfaces actionable items, the
 * info tier never inflates the in-page counter, and category
 * chips let an operator zoom in on one event family at a time.
 *
 * Auto-archive timers and entity-grouping live in the backend
 * (N9b) — both need server-side state we don't have yet. The
 * frontend prep here is forward-compatible: when those fields
 * land on the API response, this view absorbs them without a
 * structural rewrite.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Bell,
  CheckCircle,
  FileText,
  FileXls,
  Storefront,
  type Icon,
} from "@phosphor-icons/react";

import { EmptyState, Surface } from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  listClientNotifications,
  markAllClientNotificationsRead,
  markClientNotificationRead,
  type ClientNotificationItem,
  type NotificationCategory,
  type NotificationSeverity,
} from "@/lib/api/client";

import { ClientShell } from "../_shell";
import { VendorRef } from "@/components/checkwise/vendor-ref";

// ---------------------------------------------------------------------------
// Severity + category vocabularies
// ---------------------------------------------------------------------------

/**
 * Severity drives the left-rail accent + the right-side badge. The
 * "actionable" set (red + yellow) is what the bell counts and what
 * the Pendientes tab surfaces — info and green are read-only and
 * never inflate the badge.
 */
const SEVERITY_RAIL: Record<NotificationSeverity, string> = {
  red: "border-l-[color:var(--status-error-border)]",
  yellow: "border-l-[color:var(--status-warning-border)]",
  green: "border-l-[color:var(--status-success-border)]",
  info: "border-l-[color:var(--border-subtle)]",
};

const SEVERITY_BADGE: Record<
  NotificationSeverity,
  { variant: "success" | "warning" | "destructive" | "info"; label: string }
> = {
  red: { variant: "destructive", label: "Crítico" },
  yellow: { variant: "warning", label: "Importante" },
  green: { variant: "success", label: "Resuelto" },
  info: { variant: "info", label: "Informativo" },
};

function isActionable(severity: NotificationSeverity): boolean {
  return severity === "red" || severity === "yellow";
}

/**
 * N9b — category now lives on the row itself (server-side derived
 * at insert time). The frontend just reads ``row.category`` and
 * renders. The legacy ``categoryFor(notification_type)`` fallback
 * is kept for resilience against rows that predate the migration
 * default — they bucket to ``"other"`` via the server's coerce.
 */
const CATEGORY_LABELS: Record<NotificationCategory, string> = {
  renewal: "Renovaciones",
  reporting: "Reportes",
  verification: "Verificación",
  account: "Cuenta",
  admin: "Soporte",
  other: "Otros",
};

function categoryFor(row: ClientNotificationItem): NotificationCategory {
  return row.category;
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

type TabKey = "pending" | "all" | "resolved";

const TAB_DEFINITIONS: { key: TabKey; label: string }[] = [
  { key: "pending", label: "Pendientes" },
  { key: "all", label: "Todas" },
  { key: "resolved", label: "Resueltas" },
];

function matchesTab(row: ClientNotificationItem, tab: TabKey): boolean {
  if (tab === "all") return true;
  if (tab === "pending") {
    return row.read_at === null && isActionable(row.severity);
  }
  // "resolved" — items the user (or the system) closed out. At N9a
  // we use the read flag as the proxy; N9b will fold in
  // auto-resolution by entity state change.
  return row.read_at !== null;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ClientNotificationsPage() {
  const [rows, setRows] = useState<ClientNotificationItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [tab, setTab] = useState<TabKey>("pending");
  const [categoryFilter, setCategoryFilter] =
    useState<NotificationCategory | null>(null);

  useEffect(() => {
    let cancelled = false;
    setRows(null);
    setError(null);
    listClientNotifications({ limit: 100 })
      .then((data) => {
        if (cancelled) return;
        setRows(data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(
          err instanceof Error
            ? err.message
            : "Error al cargar notificaciones.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  // ---- Derived state -----------------------------------------------------
  const counts = useMemo(() => computeCounts(rows ?? []), [rows]);

  const visible = useMemo(() => {
    if (rows === null) return [];
    return rows
      .filter((row) => matchesTab(row, tab))
      .filter((row) =>
        categoryFilter ? categoryFor(row) === categoryFilter : true,
      );
  }, [rows, tab, categoryFilter]);

  const categoryChips = useMemo(() => {
    if (rows === null) return [];
    const totals = new Map<NotificationCategory, number>();
    for (const row of rows) {
      if (!matchesTab(row, tab)) continue;
      const cat = categoryFor(row);
      totals.set(cat, (totals.get(cat) ?? 0) + 1);
    }
    const order: NotificationCategory[] = [
      "renewal",
      "reporting",
      "verification",
      "account",
      "admin",
      "other",
    ];
    return order
      .filter((cat) => (totals.get(cat) ?? 0) > 0)
      .map((cat) => ({ category: cat, count: totals.get(cat) ?? 0 }));
  }, [rows, tab]);

  async function markOne(row: ClientNotificationItem) {
    if (row.read_at) return;
    const updated = await markClientNotificationRead(row.id);
    setRows((current) =>
      current?.map((item) => (item.id === updated.id ? updated : item)) ??
      current,
    );
  }

  async function markAll() {
    await markAllClientNotificationsRead();
    setRows((current) =>
      current?.map((item) => ({
        ...item,
        read_at: item.read_at ?? new Date().toISOString(),
      })) ?? current,
    );
  }

  return (
    <ClientShell
      title="Notificaciones"
      description="Avisos críticos primero. La pestaña Pendientes solo muestra lo que aún requiere tu atención."
      actions={
        counts.pending > 0 ? (
          <Button type="button" size="sm" variant="outline" onClick={markAll}>
            <CheckCircle
              className="h-3.5 w-3.5"
              weight="bold"
              aria-hidden
            />
            Marcar todas como leídas
          </Button>
        ) : null
      }
    >
      {error ? (
        <Surface>
          <EmptyState
            icon={Bell}
            title="No pudimos cargar las notificaciones"
            description={error}
          />
          <div className="mt-4">
            <Button
              type="button"
              size="sm"
              onClick={() => setReloadKey((k) => k + 1)}
            >
              Reintentar
            </Button>
          </div>
        </Surface>
      ) : rows === null ? (
        <NotificationsSkeleton />
      ) : (
        <div className="flex flex-col gap-4">
          <TabBar active={tab} onSelect={setTab} counts={counts} />
          {categoryChips.length > 1 ? (
            <CategoryChipRow
              chips={categoryChips}
              active={categoryFilter}
              onSelect={setCategoryFilter}
            />
          ) : null}
          {visible.length === 0 ? (
            <TabEmptyState tab={tab} category={categoryFilter} />
          ) : (
            <ol className="space-y-3" data-testid="notification-list">
              {visible.map((row) => (
                <NotificationRow
                  key={row.id}
                  row={row}
                  onRead={() => markOne(row)}
                />
              ))}
            </ol>
          )}
        </div>
      )}
    </ClientShell>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function TabBar({
  active,
  onSelect,
  counts,
}: {
  active: TabKey;
  onSelect: (tab: TabKey) => void;
  counts: { pending: number; all: number; resolved: number };
}) {
  return (
    <div
      role="tablist"
      aria-label="Filtrar notificaciones"
      className="flex items-center gap-1 rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-1"
    >
      {TAB_DEFINITIONS.map(({ key, label }) => {
        const selected = active === key;
        const count = counts[key];
        return (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onSelect(key)}
            className={cn(
              "flex flex-1 items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition",
              selected
                ? "bg-[color:var(--surface-teal-muted)] text-[color:var(--text-primary)]"
                : "text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)]",
            )}
          >
            <span>{label}</span>
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-[11px] font-semibold",
                selected
                  ? "bg-[color:var(--surface-raised)] text-[color:var(--text-primary)]"
                  : "bg-[color:var(--surface-page)] text-[color:var(--text-secondary)]",
              )}
            >
              {count}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function CategoryChipRow({
  chips,
  active,
  onSelect,
}: {
  chips: { category: NotificationCategory; count: number }[];
  active: NotificationCategory | null;
  onSelect: (next: NotificationCategory | null) => void;
}) {
  return (
    <div
      role="toolbar"
      aria-label="Filtrar por categoría"
      className="flex flex-wrap items-center gap-2"
    >
      <Chip selected={active === null} onClick={() => onSelect(null)}>
        Todas las categorías
      </Chip>
      {chips.map(({ category, count }) => (
        <Chip
          key={category}
          selected={active === category}
          onClick={() =>
            onSelect(active === category ? null : category)
          }
        >
          {CATEGORY_LABELS[category]}
          <span className="ml-1.5 rounded-full bg-black/5 px-1.5 py-0.5 text-[10px] font-semibold">
            {count}
          </span>
        </Chip>
      ))}
    </div>
  );
}

function Chip({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cn(
        "inline-flex items-center rounded-full border px-3 py-1 text-[12px] font-medium transition",
        selected
          ? "border-[color:var(--border-strong)] bg-[color:var(--surface-teal-muted)] text-[color:var(--text-primary)]"
          : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)]",
      )}
    >
      {children}
    </button>
  );
}

function TabEmptyState({
  tab,
  category,
}: {
  tab: TabKey;
  category: NotificationCategory | null;
}) {
  const messages: Record<TabKey, { title: string; description: string }> = {
    pending: {
      title: "Sin pendientes",
      description:
        "No tienes avisos críticos ni importantes sin leer. Buen trabajo.",
    },
    all: {
      title: "Sin notificaciones",
      description:
        "Cuando un proveedor cargue documentos o haya avances, aparecerán aquí.",
    },
    resolved: {
      title: "Aún no hay resueltas",
      description:
        "Cuando marques una notificación como leída o se resuelva sola, aparecerá aquí.",
    },
  };
  const base = messages[tab];
  const description = category
    ? `${base.description} (Filtro: ${CATEGORY_LABELS[category]}.)`
    : base.description;
  return (
    <Surface>
      <EmptyState icon={Bell} title={base.title} description={description} />
    </Surface>
  );
}

function NotificationRow({
  row,
  onRead,
}: {
  row: ClientNotificationItem;
  onRead: () => void;
}) {
  const RowIcon = iconForType(row.notification_type);
  const unread = row.read_at === null;
  const rail = SEVERITY_RAIL[row.severity] ?? SEVERITY_RAIL.info;
  const badge = SEVERITY_BADGE[row.severity] ?? SEVERITY_BADGE.info;

  return (
    <li>
      <div
        className={cn(
          "flex gap-3 rounded-md border border-l-4 p-3 transition-colors",
          rail,
          unread
            ? "bg-[color:var(--surface-raised)]"
            : "bg-[color:var(--surface-page)]",
        )}
      >
        <span
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-md",
            "bg-[color:var(--surface-page)] text-[color:var(--text-secondary)]",
          )}
        >
          <RowIcon className="h-4 w-4" weight="bold" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[13px] font-semibold text-[color:var(--text-primary)]">
              {row.action_url ? (
                <Link
                  href={row.action_url}
                  onClick={onRead}
                  className="hover:underline"
                >
                  {row.title}
                </Link>
              ) : (
                <button
                  type="button"
                  onClick={onRead}
                  className="text-left hover:underline"
                >
                  {row.title}
                </button>
              )}
            </p>
            <Badge variant={badge.variant}>{badge.label}</Badge>
            {unread && isActionable(row.severity) ? (
              <Badge variant="brand">Nueva</Badge>
            ) : null}
            {row.vendor_id && row.vendor_name ? (
              <VendorRef
                vendorId={row.vendor_id}
                vendorName={row.vendor_name}
              >
                <Badge variant="outline">{row.vendor_name}</Badge>
              </VendorRef>
            ) : row.vendor_name ? (
              <Badge variant="outline">{row.vendor_name}</Badge>
            ) : null}
          </div>
          <p className="mt-1 text-[12px] leading-relaxed text-[color:var(--text-secondary)]">
            {row.body}
          </p>
          <p className="mt-2 font-mono text-[10px] text-[color:var(--text-tertiary)]">
            {new Date(row.created_at).toLocaleString("es-MX")}
          </p>
        </div>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function computeCounts(rows: ClientNotificationItem[]) {
  let pending = 0;
  let resolved = 0;
  for (const row of rows) {
    if (matchesTab(row, "pending")) pending += 1;
    if (matchesTab(row, "resolved")) resolved += 1;
  }
  return { pending, all: rows.length, resolved };
}

function iconForType(type: string): Icon {
  if (type === "provider_uploaded") return Storefront;
  if (type === "metadata_ready") return FileXls;
  if (type.startsWith("document_")) return FileText;
  return Bell;
}

function NotificationsSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 5 }).map((_, index) => (
        <div
          key={index}
          className="h-24 animate-pulse rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]"
        />
      ))}
    </div>
  );
}
