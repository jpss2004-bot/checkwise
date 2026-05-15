"use client";

import { useEffect, useState } from "react";

import { ClientShell } from "../_shell";
import { getClientMe, getClientOverview, type ClientMe, type ClientOverview } from "@/lib/api/client";

export default function ClientDashboardPage() {
  const [me, setMe] = useState<ClientMe | null>(null);
  const [data, setData] = useState<ClientOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [clientId, setClientId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getClientMe()
      .then((meData) => {
        if (cancelled) return;
        setMe(meData);
        setClientId(meData.default_client_id);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Error al cargar identidad.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!clientId && !me) return;
    let cancelled = false;
    setError(null);
    getClientOverview(clientId ? { client_id: clientId } : undefined)
      .then((overview) => {
        if (!cancelled) setData(overview);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Error al cargar resumen.");
      });
    return () => {
      cancelled = true;
    };
  }, [clientId, me]);

  return (
    <ClientShell title="Resumen del cliente">
      {me && me.visible_client_ids.length > 1 ? (
        <div className="mb-4">
          <label className="text-xs font-medium uppercase text-muted-foreground">
            Cliente
          </label>
          <select
            value={clientId ?? ""}
            onChange={(e) => setClientId(e.target.value)}
            className="ml-2 h-8 rounded-md border border-border bg-white px-2 text-sm"
          >
            {me.visible_client_ids.map((cid) => (
              <option key={cid} value={cid}>
                {cid}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      {error ? (
        <p className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {error}
        </p>
      ) : !data ? (
        <p className="text-sm text-muted-foreground">Cargando…</p>
      ) : (
        <>
          <p className="mb-4 text-sm text-muted-foreground">
            <strong>{data.client_name}</strong> · cumplimiento {data.compliance_pct}%
          </p>
          <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Tile label="Proveedores" value={data.vendors_total} />
            <Tile label="Workspaces activos" value={data.active_workspaces_total} />
            <Tile label="Verde · al día" value={data.green_count} tone="green" />
            <Tile label="Amarillo · pendiente" value={data.yellow_count} tone="yellow" />
            <Tile label="Rojo · crítico" value={data.red_count} tone="red" />
            <Tile label="En revisión" value={data.pending_reviews_total} />
            <Tile
              label="Rechazos / aclaración"
              value={data.rejected_or_correction_total}
            />
            <Tile label="Faltantes" value={data.missing_required_total} />
            <Tile label="Vencen ≤14 días" value={data.due_soon_total} />
            <Tile label="Entregas recientes" value={data.recent_submissions_total} />
          </dl>
        </>
      )}
    </ClientShell>
  );
}

function Tile({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "green" | "yellow" | "red";
}) {
  const border =
    tone === "green"
      ? "border-emerald-300"
      : tone === "yellow"
        ? "border-amber-300"
        : tone === "red"
          ? "border-red-300"
          : "border-border";
  return (
    <div className={`rounded-md border bg-white p-4 ${border}`}>
      <dt className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-1 font-mono text-2xl font-semibold tabular-nums">{value}</dd>
    </div>
  );
}
