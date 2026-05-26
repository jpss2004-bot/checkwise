"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Bell,
  CheckCircle,
  FileText,
  FileXls,
  Storefront,
} from "@phosphor-icons/react";

import {
  EmptyState,
  Surface,
} from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  listClientNotifications,
  markAllClientNotificationsRead,
  markClientNotificationRead,
  type ClientNotificationItem,
  type NotificationSeverity,
} from "@/lib/api/client";

import { ClientShell } from "../_shell";
import { VendorRef } from "@/components/checkwise/vendor-ref";

// Phase 4 / Slice 4A — render the semáforo per row. Every notification
// carries an explicit ``severity`` set by the backend emitter; the
// frontend maps each value to a triple of (unread border+bg, read
// border+bg, icon bg, Badge variant, label) so the row's color tracks
// the row's meaning, not its read state.
type NotificationTone = {
  unreadClass: string;
  readClass: string;
  iconBg: string;
  badge: "success" | "warning" | "destructive" | "info";
  label: string;
};

const TONE_BY_SEVERITY: Record<NotificationSeverity, NotificationTone> = {
  green: {
    unreadClass:
      "border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)]",
    readClass:
      "border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]",
    iconBg:
      "bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]",
    badge: "success",
    label: "Aprobado",
  },
  yellow: {
    unreadClass:
      "border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)]",
    readClass:
      "border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]",
    iconBg:
      "bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)]",
    badge: "warning",
    label: "Pendiente",
  },
  red: {
    unreadClass:
      "border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)]",
    readClass:
      "border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]",
    iconBg:
      "bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)]",
    badge: "destructive",
    label: "Atención",
  },
  info: {
    unreadClass:
      "border-[color:var(--border-brand)] bg-[color:var(--surface-brand-muted)]",
    readClass:
      "border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]",
    iconBg:
      "bg-[color:var(--surface-raised)] text-[color:var(--text-teal)]",
    badge: "info",
    label: "Aviso",
  },
};

export default function ClientNotificationsPage() {
  const [rows, setRows] = useState<ClientNotificationItem[] | null>(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setRows(null);
    setError(null);
    listClientNotifications({ limit: 100 })
      .then((data) => {
        if (cancelled) return;
        setRows(data.items);
        setUnreadCount(data.unread_count);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Error al cargar notificaciones.");
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const grouped = useMemo(() => groupByDay(rows ?? []), [rows]);

  async function markOne(row: ClientNotificationItem) {
    if (row.read_at) return;
    const updated = await markClientNotificationRead(row.id);
    setRows((current) =>
      current?.map((item) => (item.id === updated.id ? updated : item)) ?? current,
    );
    setUnreadCount((value) => Math.max(0, value - 1));
  }

  async function markAll() {
    await markAllClientNotificationsRead();
    setRows((current) =>
      current?.map((item) => ({
        ...item,
        read_at: item.read_at ?? new Date().toISOString(),
      })) ?? current,
    );
    setUnreadCount(0);
  }

  return (
    <ClientShell
      title="Notificaciones"
      description="Novedades importantes de tus proveedores: cargas recibidas, metadata lista y decisiones de revision."
      actions={
        unreadCount > 0 ? (
          <Button type="button" size="sm" variant="outline" onClick={markAll}>
            <CheckCircle className="h-3.5 w-3.5" weight="bold" aria-hidden />
            Marcar leidas
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
            <Button type="button" size="sm" onClick={() => setReloadKey((k) => k + 1)}>
              Reintentar
            </Button>
          </div>
        </Surface>
      ) : rows === null ? (
        <NotificationsSkeleton />
      ) : rows.length === 0 ? (
        <Surface>
          <EmptyState
            icon={Bell}
            title="Sin notificaciones"
            description="Cuando un proveedor cargue documentos o haya avances, apareceran aqui."
          />
        </Surface>
      ) : (
        <Surface
          title="Novedades"
          icon={Bell}
          description={`${unreadCount} sin leer`}
        >
          <ol className="space-y-7">
            {grouped.map((group) => (
              <li key={group.day} className="space-y-3">
                <p className="cw-eyebrow">{group.label}</p>
                <ul className="space-y-3">
                  {group.items.map((row) => (
                    <NotificationRow key={row.id} row={row} onRead={() => markOne(row)} />
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        </Surface>
      )}
    </ClientShell>
  );
}

function NotificationRow({
  row,
  onRead,
}: {
  row: ClientNotificationItem;
  onRead: () => void;
}) {
  const Icon = iconForType(row.notification_type);
  const unread = row.read_at === null;
  const tone = TONE_BY_SEVERITY[row.severity] ?? TONE_BY_SEVERITY.info;

  // Item 5 — when the notification is tied to a vendor, the vendor
  // badge becomes its own link to the expediente. The rest of the
  // card still navigates to ``action_url`` (typically the filtered
  // submissions list) so the dual destinations live side-by-side
  // without nesting anchors.
  return (
    <li>
      <div
        className={
          "flex gap-3 rounded-md border p-3 transition-colors " +
          (unread ? tone.unreadClass : tone.readClass)
        }
      >
        <span
          className={
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-md " +
            tone.iconBg
          }
        >
          <Icon className="h-4 w-4" weight="bold" aria-hidden />
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
            <Badge variant={tone.badge}>{tone.label}</Badge>
            {unread ? <Badge variant="brand">Nueva</Badge> : null}
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

function iconForType(type: string) {
  if (type === "provider_uploaded") return Storefront;
  if (type === "metadata_ready") return FileXls;
  if (type.startsWith("document_")) return FileText;
  return Bell;
}

function groupByDay(rows: ClientNotificationItem[]) {
  const map = new Map<string, ClientNotificationItem[]>();
  for (const row of rows) {
    const day = new Date(row.created_at).toISOString().slice(0, 10);
    const list = map.get(day) ?? [];
    list.push(row);
    map.set(day, list);
  }
  return [...map.entries()].map(([day, items]) => ({
    day,
    label: new Date(day).toLocaleDateString("es-MX", {
      weekday: "long",
      day: "2-digit",
      month: "long",
      year: "numeric",
    }),
    items,
  }));
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
