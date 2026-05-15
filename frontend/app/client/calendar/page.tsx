"use client";

import { useEffect, useState } from "react";

import { ClientShell } from "../_shell";
import { getClientCalendar, type ClientCalendar } from "@/lib/api/client";

export default function ClientCalendarPage() {
  const [year, setYear] = useState(new Date().getFullYear() || 2026);
  const [data, setData] = useState<ClientCalendar | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    getClientCalendar({ year })
      .then((cal) => {
        if (!cancelled) setData(cal);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Error al cargar calendario.");
      });
    return () => {
      cancelled = true;
    };
  }, [year]);

  return (
    <ClientShell title="Calendario del cliente">
      <div className="mb-4 flex items-center gap-3">
        <label className="text-xs font-medium uppercase text-muted-foreground">
          Año
        </label>
        <input
          type="number"
          min={2024}
          max={2030}
          value={year}
          onChange={(e) => setYear(Number(e.target.value))}
          className="h-9 w-24 rounded-md border border-border bg-white px-2 text-sm"
        />
      </div>

      {error ? (
        <p className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {error}
        </p>
      ) : !data ? (
        <p className="text-sm text-muted-foreground">Cargando…</p>
      ) : (
        <div className="overflow-x-auto rounded-md border border-border bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Mes</th>
                <th className="px-3 py-2">Proveedores</th>
                <th className="px-3 py-2">Total</th>
                <th className="px-3 py-2">Aprobados</th>
                <th className="px-3 py-2">Pendientes</th>
                <th className="px-3 py-2">Rechazos</th>
                <th className="px-3 py-2">Faltantes</th>
                <th className="px-3 py-2">Vencen ≤14d</th>
              </tr>
            </thead>
            <tbody>
              {data.months.map((m) => (
                <tr key={m.month} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 font-medium">{m.month_label}</td>
                  <td className="px-3 py-2 font-mono tabular-nums">{m.vendors_total}</td>
                  <td className="px-3 py-2 font-mono tabular-nums">{m.due_total}</td>
                  <td className="px-3 py-2 font-mono tabular-nums text-emerald-700">
                    {m.approved_total}
                  </td>
                  <td className="px-3 py-2 font-mono tabular-nums">{m.pending_total}</td>
                  <td className="px-3 py-2 font-mono tabular-nums text-red-700">
                    {m.rejected_or_correction_total}
                  </td>
                  <td className="px-3 py-2 font-mono tabular-nums text-amber-700">
                    {m.missing_total}
                  </td>
                  <td className="px-3 py-2 font-mono tabular-nums">{m.due_soon_total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </ClientShell>
  );
}
