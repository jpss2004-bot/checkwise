"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ChatTeardrop,
  CheckCircle,
  ClockClockwise,
  FileText,
  Gear,
  Storefront,
  User,
  type Icon,
} from "@phosphor-icons/react";

import {
  EmptyState,
  Surface,
} from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import {
  ErrorState,
  Skeleton,
} from "@/components/checkwise/portal/state-surfaces";

import { ClientShell } from "../_shell";
import { VendorRef } from "@/components/checkwise/vendor-ref";
import {
  activityActionLabel,
  activityActorLabel,
} from "@/lib/constants/activity-labels";
import {
  listClientActivity,
  type ClientActivityItem,
} from "@/lib/api/client";
import { formatDateTime } from "@/lib/format/datetime";
import { useUrlClientId } from "@/lib/workspace/use-url-client-id";

/**
 * Activity feed — vertical timeline grouped by day. Replaces the
 * flat table with a feed pattern that scans the way most operators
 * actually read it.
 */
export default function ClientActivityPage() {
  const urlClientId = useUrlClientId();
  const [rows, setRows] = useState<ClientActivityItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setRows(null);
    setError(null);
    listClientActivity({
      ...(urlClientId ? { client_id: urlClientId } : {}),
      limit: 200,
    })
      .then((data) => {
        if (!cancelled) setRows(data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Error al cargar actividad.");
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey, urlClientId]);

  const groups = useMemo(() => groupByDay(rows ?? []), [rows]);

  return (
    <ClientShell
      title="Actividad reciente"
      description="Bitácora de eventos en tus proveedores: cargas, revisiones, cambios de estado, notas."
    >
      {error ? (
        <ErrorState
          title="No pudimos cargar la actividad"
          description={error}
          onRetry={() => setReloadKey((k) => k + 1)}
        />
      ) : rows === null ? (
        <ActivitySkeleton />
      ) : rows.length === 0 ? (
        <Surface>
          <EmptyState
            icon={ClockClockwise}
            title="Sin actividad reciente"
            description="No hay eventos registrados para este cliente."
          />
        </Surface>
      ) : (
        <Surface
          title="Cronología"
          icon={ClockClockwise}
          description={`${rows.length} evento${rows.length === 1 ? "" : "s"} en los últimos días.`}
        >
          <ol className="space-y-7">
            {groups.map((g) => (
              <li key={g.day} className="space-y-3">
                <p className="cw-eyebrow">{g.label}</p>
                <ul className="relative space-y-3 border-l border-[color:var(--border-subtle)] pl-5">
                  {g.items.map((row) => (
                    <ActivityRow key={row.id} row={row} />
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

function ActivityRow({ row }: { row: ClientActivityItem }) {
  const { icon, tone } = pickIcon(row);
  const IconComponent = icon;
  return (
    <li className="relative">
      <span
        aria-hidden="true"
        className={`absolute -left-[28px] top-0.5 flex h-5 w-5 items-center justify-center rounded-full ${tone}`}
      >
        <IconComponent className="h-3 w-3" weight="bold" />
      </span>
      <div className="rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-[13px] text-[color:var(--text-primary)]">
            {row.summary}
          </p>
          <span className="font-mono text-[10px] text-[color:var(--text-tertiary)]">
            {new Date(row.occurred_at).toLocaleTimeString("es-MX", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          <Badge variant="outline">{activityActorLabel(row.actor_type)}</Badge>
          <span className="text-[11px] text-[color:var(--text-tertiary)]">
            {activityActionLabel(row.action)}
          </span>
          {row.vendor_id && row.vendor_name ? (
            <VendorRef vendorId={row.vendor_id} vendorName={row.vendor_name}>
              <Badge variant="brand">{row.vendor_name}</Badge>
            </VendorRef>
          ) : row.vendor_name ? (
            <Badge variant="brand">{row.vendor_name}</Badge>
          ) : null}
        </div>
      </div>
    </li>
  );
}

function ActivitySkeleton() {
  return (
    <Surface title="Cronología" icon={ClockClockwise}>
      <ol className="space-y-6" aria-busy="true" aria-live="polite">
        <span className="sr-only">Cargando actividad…</span>
        {Array.from({ length: 3 }).map((_, gi) => (
          <li key={gi} className="space-y-3">
            <Skeleton className="h-3 w-40" />
            <ul className="relative space-y-3 border-l border-[color:var(--border-subtle)] pl-5">
              {Array.from({ length: 3 }).map((_, ri) => (
                <li key={ri} className="rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-3">
                  <Skeleton className="h-3 w-9/12" />
                  <Skeleton className="mt-2 h-3 w-4/12" />
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </Surface>
  );
}

function pickIcon(row: ClientActivityItem): {
  icon: Icon;
  tone: string;
} {
  const action = row.action.toLowerCase();
  if (action.includes("approved") || action.includes("aprob"))
    return {
      icon: CheckCircle,
      tone: "bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]",
    };
  if (action.includes("reject") || action.includes("rechaz"))
    return {
      icon: FileText,
      tone: "bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)]",
    };
  if (action.includes("submission") || action.includes("upload"))
    return {
      icon: FileText,
      tone: "bg-[color:var(--status-info-bg)] text-[color:var(--status-info-text)]",
    };
  if (action.includes("comment") || action.includes("note"))
    return {
      icon: ChatTeardrop,
      tone: "bg-[color:var(--surface-teal-muted)] text-[color:var(--text-teal)]",
    };
  if (action.includes("vendor"))
    return {
      icon: Storefront,
      tone: "bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]",
    };
  if (action.includes("user") || row.actor_type === "user")
    return {
      icon: User,
      tone: "bg-[color:var(--surface-sunken)] text-[color:var(--text-secondary)]",
    };
  return {
    icon: Gear,
    tone: "bg-[color:var(--surface-sunken)] text-[color:var(--text-secondary)]",
  };
}

/**
 * Mexico-local `YYYY-MM-DD` key for an instant. `toISOString().slice(0,10)`
 * buckets by the UTC day, so a late-evening MX event (e.g. 23:30 local =
 * 05:30 next-day UTC) lands under the wrong day; `en-CA` + America/Mexico_City
 * yields a stable ISO-shaped key on the user-perceived calendar day.
 */
function mxDayKey(occurredAt: string): string {
  return new Date(occurredAt).toLocaleDateString("en-CA", {
    timeZone: "America/Mexico_City",
  });
}

function groupByDay(rows: ClientActivityItem[]): Array<{
  day: string;
  label: string;
  items: ClientActivityItem[];
}> {
  const map = new Map<string, ClientActivityItem[]>();
  for (const row of rows) {
    const day = mxDayKey(row.occurred_at);
    const list = map.get(day) ?? [];
    list.push(row);
    map.set(day, list);
  }
  return [...map.entries()].map(([day, items]) => ({
    day,
    // `day` is a bare YYYY-MM-DD; formatDateTime renders it as that exact
    // calendar date (no UTC day shift), so heading and bucket key agree.
    label: formatDateTime(day, {
      weekday: "long",
      day: "2-digit",
      month: "long",
      year: "numeric",
    }),
    items,
  }));
}
