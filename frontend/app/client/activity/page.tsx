"use client";

import { useEffect, useState } from "react";

import { ClientShell } from "../_shell";
import {
  listClientActivity,
  type ClientActivityItem,
} from "@/lib/api/client";

export default function ClientActivityPage() {
  const [rows, setRows] = useState<ClientActivityItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listClientActivity({ limit: 100 })
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
  }, []);

  return (
    <ClientShell title="Actividad reciente">
      {error ? (
        <p className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {error}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-md border border-border bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Cuándo</th>
                <th className="px-3 py-2">Actor</th>
                <th className="px-3 py-2">Acción</th>
                <th className="px-3 py-2">Proveedor</th>
                <th className="px-3 py-2">Resumen</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 font-mono text-xs">
                    {new Date(row.occurred_at).toLocaleString("es-MX")}
                  </td>
                  <td className="px-3 py-2 text-xs">{row.actor_type}</td>
                  <td className="px-3 py-2 font-mono text-xs">{row.action}</td>
                  <td className="px-3 py-2 text-xs">{row.vendor_name ?? "—"}</td>
                  <td className="px-3 py-2 text-xs">{row.summary}</td>
                </tr>
              ))}
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-3 py-6 text-center text-xs text-muted-foreground">
                    Sin actividad reciente.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      )}
    </ClientShell>
  );
}
