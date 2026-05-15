"use client";

import { useEffect, useState } from "react";

import { AdminShell } from "../_shell";
import { getAdminOverview, type AdminOverview } from "@/lib/api/admin";

export default function AdminDashboardPage() {
  const [data, setData] = useState<AdminOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAdminOverview()
      .then((overview) => {
        if (!cancelled) setData(overview);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Error al cargar el resumen.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AdminShell title="Resumen operativo">
      {error ? (
        <p className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {error}
        </p>
      ) : !data ? (
        <p className="text-sm text-muted-foreground">Cargando…</p>
      ) : (
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Tile label="Clientes" value={data.clients_total} />
          <Tile label="Proveedores" value={data.vendors_total} />
          <Tile label="Workspaces activos" value={data.active_workspaces_total} />
          <Tile label="En revisión" value={data.pending_reviews_total} />
          <Tile
            label="Rechazos / aclaración"
            value={data.rejected_or_correction_total}
          />
          <Tile
            label="Submissions recientes"
            value={data.recent_submissions_total}
          />
          <Tile
            label="Eventos de auditoría recientes"
            value={data.recent_audit_events_total}
          />
        </dl>
      )}
    </AdminShell>
  );
}

function Tile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-border bg-white p-4">
      <dt className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-1 font-mono text-2xl font-semibold tabular-nums">
        {value}
      </dd>
    </div>
  );
}
