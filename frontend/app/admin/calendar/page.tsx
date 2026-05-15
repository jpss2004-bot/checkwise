"use client";

import { useEffect, useState } from "react";

import { AdminShell } from "../_shell";
import {
  type AdminCalendar,
  type AdminPeriod,
  getAdminCalendar,
  listPeriods,
} from "@/lib/api/admin";

const MONTH_LABELS_SHORT = [
  "Ene",
  "Feb",
  "Mar",
  "Abr",
  "May",
  "Jun",
  "Jul",
  "Ago",
  "Sep",
  "Oct",
  "Nov",
  "Dic",
];

export default function AdminCalendarPage() {
  const [year, setYear] = useState<number>(new Date().getFullYear() || 2026);
  const [calendar, setCalendar] = useState<AdminCalendar | null>(null);
  const [periods, setPeriods] = useState<AdminPeriod[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    Promise.all([getAdminCalendar({ year }), listPeriods({ year })])
      .then(([cal, per]) => {
        if (cancelled) return;
        setCalendar(cal);
        setPeriods(per.items);
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
    <AdminShell title="Calendario operativo">
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
      ) : !calendar ? (
        <p className="text-sm text-muted-foreground">Cargando…</p>
      ) : (
        <section className="space-y-4">
          <div className="overflow-x-auto rounded-md border border-border bg-white">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Mes</th>
                  <th className="px-3 py-2">Obligaciones esperadas</th>
                  <th className="px-3 py-2">Por institución</th>
                </tr>
              </thead>
              <tbody>
                {calendar.months.map((m) => (
                  <tr key={m.month} className="border-b border-border last:border-0">
                    <td className="px-3 py-2 font-medium">
                      {MONTH_LABELS_SHORT[m.month - 1]}
                    </td>
                    <td className="px-3 py-2 font-mono tabular-nums">{m.expected_total}</td>
                    <td className="px-3 py-2 text-xs">
                      {m.institutions.length === 0
                        ? "—"
                        : m.institutions
                            .map((i) => `${i.institution}: ${i.expected}`)
                            .join(" · ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div>
            <h2 className="mb-2 text-sm font-semibold">Periodos en BD ({periods.length})</h2>
            <div className="overflow-x-auto rounded-md border border-border bg-white">
              <table className="w-full text-sm">
                <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">Código</th>
                    <th className="px-3 py-2">Period key</th>
                    <th className="px-3 py-2">Tipo</th>
                    <th className="px-3 py-2">Año</th>
                    <th className="px-3 py-2">Mes</th>
                  </tr>
                </thead>
                <tbody>
                  {periods.map((p) => (
                    <tr key={p.id} className="border-b border-border last:border-0">
                      <td className="px-3 py-2 font-mono text-xs">{p.code}</td>
                      <td className="px-3 py-2 font-mono text-xs">{p.period_key ?? "—"}</td>
                      <td className="px-3 py-2">{p.period_type}</td>
                      <td className="px-3 py-2">{p.year ?? "—"}</td>
                      <td className="px-3 py-2">{p.month ?? "—"}</td>
                    </tr>
                  ))}
                  {periods.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-3 py-6 text-center text-xs text-muted-foreground">
                        Sin periodos para el año seleccionado.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}
    </AdminShell>
  );
}
