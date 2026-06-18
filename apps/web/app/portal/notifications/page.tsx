"use client";

/**
 * Phase 7 / Slice N9c — provider portal notification center.
 *
 * Mirrors the client_admin UX shipped at N9a/N9b:
 *   - Three tabs (Pendientes / Todas / Resueltas) with counts.
 *   - Category filter chips derived from the server-side
 *     ``row.category`` value (N9b).
 *   - Severity-aware left rail per row + per-row severity badge.
 *   - "Nueva" pill only on actionable unread rows (red + yellow);
 *     info never inflates the bell.
 *   - Empty states are tab- and filter-aware.
 *
 * Bell-badge math: the portal shell will use
 * ``summary.unread_actionable_count`` once the parallel shell
 * change lands; this page sources its own counts from the list
 * response so both views stay in lockstep without a second
 * round-trip.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Bell,
  CheckCircle,
  FileText,
  type Icon as IconType,
} from "@phosphor-icons/react";

import { PortalAppShell } from "@/components/checkwise/portal/portal-app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import type { NotificationSeverity } from "@/lib/api/client";
import {
  listProviderNotifications,
  markAllProviderNotificationsRead,
  markProviderNotificationRead,
  type ProviderNotificationItem,
} from "@/lib/api/portal";
import { withPortalSession } from "@/lib/session/with-portal-session";
import type { PortalSession } from "@/lib/session/portal";

// ---------------------------------------------------------------------------
// Severity + category vocabularies (mirrors N9a — kept independent
// from the client side so each view can evolve without coupling).
// ---------------------------------------------------------------------------

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

type NotificationCategory = ProviderNotificationItem["category"];

const CATEGORY_LABELS: Record<NotificationCategory, string> = {
  renewal: "Renovaciones",
  reporting: "Reportes",
  verification: "Verificación",
  account: "Cuenta",
  admin: "Soporte",
  other: "Otros",
};

type TabKey = "pending" | "all" | "resolved";

const TAB_DEFINITIONS: { key: TabKey; label: string }[] = [
  { key: "pending", label: "Pendientes" },
  { key: "all", label: "Todas" },
  { key: "resolved", label: "Resueltas" },
];

function matchesTab(row: ProviderNotificationItem, tab: TabKey): boolean {
  if (tab === "all") return true;
  if (tab === "pending") {
    return row.read_at === null && isActionable(row.severity);
  }
  return row.read_at !== null;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function PortalNotificationsInner({ session }: { session: PortalSession }) {
  const [rows, setRows] = useState<ProviderNotificationItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [tab, setTab] = useState<TabKey>("pending");
  const [categoryFilter, setCategoryFilter] =
    useState<NotificationCategory | null>(null);
  const [markingAll, setMarkingAll] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setRows(null);
    setError(null);
    listProviderNotifications(session, { limit: 100 })
      .then((data) => {
        if (cancelled) return;
        setRows(data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(
          err instanceof Error
            ? err.message
            : "No pudimos cargar tus notificaciones.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [session, reloadKey]);

  // The bell + tab counts are owned by the portal shell, which already
  // polls the notification summary every 60 s. A second interval here only
  // duplicated that request (its result was discarded), so it was removed.

  const counts = useMemo(() => computeCounts(rows ?? []), [rows]);

  const visible = useMemo(() => {
    if (rows === null) return [];
    return rows
      .filter((row) => matchesTab(row, tab))
      .filter((row) =>
        categoryFilter ? row.category === categoryFilter : true,
      );
  }, [rows, tab, categoryFilter]);

  const categoryChips = useMemo(() => {
    if (rows === null) return [];
    const totals = new Map<NotificationCategory, number>();
    for (const row of rows) {
      if (!matchesTab(row, tab)) continue;
      totals.set(row.category, (totals.get(row.category) ?? 0) + 1);
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

  async function markOne(row: ProviderNotificationItem) {
    if (row.read_at) return;
    // Optimistic: mark read immediately so the click always produces feedback.
    const optimisticReadAt = new Date().toISOString();
    setRows((current) =>
      current?.map((item) =>
        item.id === row.id ? { ...item, read_at: optimisticReadAt } : item,
      ) ?? current,
    );
    try {
      const updated = await markProviderNotificationRead(session, row.id);
      setRows((current) =>
        current?.map((item) => (item.id === updated.id ? updated : item)) ??
        current,
      );
    } catch {
      // Roll back the optimistic update and tell the user.
      setRows((current) =>
        current?.map((item) =>
          item.id === row.id ? { ...item, read_at: row.read_at } : item,
        ) ?? current,
      );
      toast.error("No pudimos marcarla como leída.", {
        description: "Revisa tu conexión e inténtalo de nuevo.",
      });
    }
  }

  async function markAll() {
    if (markingAll) return;
    setMarkingAll(true);
    // Optimistic: flip everything to read immediately, snapshotting prior
    // state so we can roll back if the request fails.
    const snapshot = rows;
    const markedCount = (rows ?? []).filter(
      (item) => item.read_at === null,
    ).length;
    setRows((current) =>
      current?.map((item) => ({
        ...item,
        read_at: item.read_at ?? new Date().toISOString(),
      })) ?? current,
    );
    try {
      await markAllProviderNotificationsRead(session);
      toast.success(
        markedCount === 1
          ? "Marcamos 1 notificación como leída."
          : `Marcamos ${markedCount} notificaciones como leídas.`,
        { description: "Las encuentras en la pestaña Resueltas." },
      );
    } catch {
      setRows(snapshot);
      toast.error("No pudimos marcarlas como leídas.", {
        description: "Revisa tu conexión e inténtalo de nuevo.",
      });
    } finally {
      setMarkingAll(false);
    }
  }

  return (
    <PortalAppShell session={session}>
      <main className="mx-auto max-w-4xl space-y-5 px-5 py-6">
        <PageHeader
          eyebrow="Tu bandeja"
          title="Notificaciones"
          description="Avisos críticos primero. La pestaña Pendientes solo muestra lo que aún requiere tu atención."
          actions={
            counts.pending > 0 ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={markAll}
                disabled={markingAll}
              >
                <CheckCircle
                  className="h-3.5 w-3.5"
                  weight="bold"
                  aria-hidden
                />
                {markingAll ? "Marcando…" : "Marcar todas como leídas"}
              </Button>
            ) : null
          }
        />

        {error ? (
          <Card>
            <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
              <Bell
                className="h-6 w-6 text-[color:var(--text-tertiary)]"
                aria-hidden
              />
              <p className="text-sm text-[color:var(--text-secondary)]">
                {error}
              </p>
              <Button
                type="button"
                size="sm"
                onClick={() => setReloadKey((k) => k + 1)}
              >
                Reintentar
              </Button>
            </CardContent>
          </Card>
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
              <ol
                className="space-y-3"
                data-testid="portal-notification-list"
              >
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
      </main>
    </PortalAppShell>
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
    // Segmented filter, not a true tab/tabpanel pattern: selecting a segment
    // filters the list below rather than swapping panels, so we expose it as a
    // group of toggle buttons (aria-pressed) — matching the category chips.
    <div
      role="group"
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
            aria-pressed={selected}
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
          <span className="ml-1.5 rounded-full bg-[color:var(--surface-page)] px-1.5 py-0.5 text-[10px] font-semibold">
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
        "Cuando el revisor evalúe tus documentos o haya cambios en tu expediente, aparecerán aquí.",
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
    <Card>
      <CardContent className="flex flex-col items-center gap-2 p-8 text-center">
        <Bell
          className="h-6 w-6 text-[color:var(--text-tertiary)]"
          aria-hidden
        />
        <p className="text-base font-semibold text-[color:var(--text-primary)]">
          {base.title}
        </p>
        <p className="text-sm text-[color:var(--text-secondary)]">
          {description}
        </p>
      </CardContent>
    </Card>
  );
}

function NotificationRow({
  row,
  onRead,
}: {
  row: ProviderNotificationItem;
  onRead: () => void;
}) {
  const RowIcon: IconType = iconForType(row.notification_type);
  const unread = row.read_at === null;
  const rail = SEVERITY_RAIL[row.severity] ?? SEVERITY_RAIL.info;
  const badge = SEVERITY_BADGE[row.severity] ?? SEVERITY_BADGE.info;

  const content = (
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
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[color:var(--text-secondary)]",
          // Keep the chip a step apart from the row surface in both states:
          // read rows already sit on --surface-page, so a same-tone chip
          // disappears — drop it to --surface-sunken there.
          unread
            ? "bg-[color:var(--surface-page)]"
            : "bg-[color:var(--surface-sunken)]",
        )}
      >
        <RowIcon className="h-4 w-4" weight="bold" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-[13px] font-semibold text-[color:var(--text-primary)]">
            {row.title}
          </p>
          <Badge variant={badge.variant}>{badge.label}</Badge>
          {unread && isActionable(row.severity) ? (
            <Badge variant="brand">Nueva</Badge>
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
  );

  return (
    <li>
      {row.action_url ? (
        <Link href={row.action_url} onClick={onRead} className="block">
          {content}
        </Link>
      ) : unread ? (
        // No destination, but still has an unread state to toggle.
        <button
          type="button"
          onClick={onRead}
          className="block w-full text-left"
        >
          {content}
        </button>
      ) : (
        // Already read and nowhere to navigate — not actionable, so don't
        // announce it as a button.
        <div className="block">{content}</div>
      )}
    </li>
  );
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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function computeCounts(rows: ProviderNotificationItem[]) {
  let pending = 0;
  let resolved = 0;
  for (const row of rows) {
    if (matchesTab(row, "pending")) pending += 1;
    if (matchesTab(row, "resolved")) resolved += 1;
  }
  return { pending, all: rows.length, resolved };
}

function iconForType(type: string): IconType {
  if (type.startsWith("document_") || type.startsWith("submission")) {
    return FileText;
  }
  return Bell;
}

export default withPortalSession(PortalNotificationsInner);
