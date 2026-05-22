"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Bell,
  CheckCircle,
  FileText,
} from "@phosphor-icons/react";

import { PortalAppShell } from "@/components/checkwise/portal/portal-app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import {
  getProviderNotificationSummary,
  listProviderNotifications,
  markAllProviderNotificationsRead,
  markProviderNotificationRead,
  type ProviderNotificationItem,
} from "@/lib/api/portal";
import type { NotificationSeverity } from "@/lib/api/client";
import { withPortalSession } from "@/lib/session/with-portal-session";
import type { PortalSession } from "@/lib/session/portal";

// Phase 4 / Slice 4B — semáforo tone tokens. Kept duplicated with the
// client-side equivalent for now: the duplication cost is low (one
// 30-line map), the abstraction risk is real (shared modules across
// the client/portal divide tend to grow accidental coupling), and
// both pages can evolve independently.
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

function PortalNotificationsInner({ session }: { session: PortalSession }) {
  const [rows, setRows] = useState<ProviderNotificationItem[] | null>(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setRows(null);
    setError(null);
    listProviderNotifications(session, { limit: 100 })
      .then((data) => {
        if (cancelled) return;
        setRows(data.items);
        setUnreadCount(data.unread_count);
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

  const grouped = useMemo(() => groupByDay(rows ?? []), [rows]);

  async function markOne(row: ProviderNotificationItem) {
    if (row.read_at) return;
    try {
      const updated = await markProviderNotificationRead(session, row.id);
      setRows((current) =>
        current?.map((item) => (item.id === updated.id ? updated : item)) ??
        current,
      );
      setUnreadCount((value) => Math.max(0, value - 1));
    } catch {
      // Non-fatal — the link still navigates and the user can refresh.
    }
  }

  async function markAll() {
    try {
      await markAllProviderNotificationsRead(session);
      setRows((current) =>
        current?.map((item) => ({
          ...item,
          read_at: item.read_at ?? new Date().toISOString(),
        })) ?? current,
      );
      setUnreadCount(0);
    } catch {
      // Non-fatal — the user can re-trigger; the summary will reflect
      // reality on next fetch.
    }
  }

  // Background refresh so the bell + page stay in sync if a reviewer
  // decision lands while the tab is open. Best-effort.
  useEffect(() => {
    const handle = window.setInterval(() => {
      getProviderNotificationSummary(session)
        .then((s) => {
          setUnreadCount((current) =>
            current === s.unread_count ? current : s.unread_count,
          );
        })
        .catch(() => undefined);
    }, 60_000);
    return () => window.clearInterval(handle);
  }, [session]);

  return (
    <PortalAppShell session={session}>
      <main className="mx-auto max-w-4xl space-y-5 px-5 py-6">
        <PageHeader
          eyebrow="Tu bandeja"
          title="Notificaciones"
          description="Decisiones del revisor sobre tus documentos. Las nuevas aparecen marcadas como ‘Nueva’ y la acción te lleva directo a la entrega."
          actions={
            unreadCount > 0 ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={markAll}
              >
                <CheckCircle className="h-3.5 w-3.5" weight="bold" aria-hidden />
                Marcar leídas
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
              <p className="text-sm text-[color:var(--text-secondary)]">{error}</p>
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
        ) : rows.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center gap-2 p-8 text-center">
              <Bell
                className="h-6 w-6 text-[color:var(--text-tertiary)]"
                aria-hidden
              />
              <p className="text-base font-semibold text-[color:var(--text-primary)]">
                Sin notificaciones
              </p>
              <p className="text-sm text-[color:var(--text-secondary)]">
                Cuando un revisor apruebe, rechace o pida aclaraciones sobre
                tus cargas, lo verás aquí.
              </p>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between gap-2">
                <CardTitle className="flex items-center gap-2">
                  <Bell className="h-4 w-4" weight="bold" aria-hidden />
                  Novedades
                </CardTitle>
                <p className="font-mono text-[11px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  {unreadCount} sin leer
                </p>
              </div>
            </CardHeader>
            <CardContent>
              <ol className="space-y-7">
                {grouped.map((group) => (
                  <li key={group.key}>
                    <p className="mb-2 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                      {group.label}
                    </p>
                    <ul className="space-y-3">
                      {group.items.map((row) => (
                        <NotificationRow
                          key={row.id}
                          row={row}
                          onRead={() => markOne(row)}
                        />
                      ))}
                    </ul>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        )}
      </main>
    </PortalAppShell>
  );
}

function NotificationRow({
  row,
  onRead,
}: {
  row: ProviderNotificationItem;
  onRead: () => void;
}) {
  const tone = TONE_BY_SEVERITY[row.severity] ?? TONE_BY_SEVERITY.info;
  const unread = row.read_at === null;
  const content = (
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
        <FileText className="h-4 w-4" weight="bold" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-[13px] font-semibold text-[color:var(--text-primary)]">
            {row.title}
          </p>
          <Badge variant={tone.badge}>{tone.label}</Badge>
          {unread ? <Badge variant="brand">Nueva</Badge> : null}
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
      ) : (
        <button
          type="button"
          onClick={onRead}
          className="block w-full text-left"
        >
          {content}
        </button>
      )}
    </li>
  );
}

function NotificationsSkeleton() {
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-16 w-full animate-pulse rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)]"
            aria-hidden
          />
        ))}
      </CardContent>
    </Card>
  );
}

function groupByDay(rows: ProviderNotificationItem[]) {
  const map = new Map<string, ProviderNotificationItem[]>();
  for (const row of rows) {
    const day = new Date(row.created_at).toISOString().slice(0, 10);
    if (!map.has(day)) map.set(day, []);
    map.get(day)!.push(row);
  }
  return Array.from(map.entries())
    .sort((a, b) => (a[0] < b[0] ? 1 : -1))
    .map(([day, items]) => ({
      key: day,
      label: new Date(day + "T00:00:00").toLocaleDateString("es-MX", {
        weekday: "long",
        day: "2-digit",
        month: "long",
        year: "numeric",
      }),
      items,
    }));
}

export default withPortalSession(PortalNotificationsInner);
