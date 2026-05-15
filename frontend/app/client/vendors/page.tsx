"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { ClientShell } from "../_shell";
import {
  listClientVendors,
  type ClientVendorRow,
} from "@/lib/api/client";

const LEVELS = ["", "green", "yellow", "red"] as const;

export default function ClientVendorsPage() {
  const [rows, setRows] = useState<ClientVendorRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [level, setLevel] = useState<string>("");

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const data = await listClientVendors({
        search: search || undefined,
        semaphore_level: (level || undefined) as
          | "green"
          | "yellow"
          | "red"
          | undefined,
      });
      setRows(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar proveedores.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <ClientShell title="Proveedores">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          refresh();
        }}
        className="mb-4 flex flex-wrap items-end gap-3"
      >
        <div className="min-w-[200px]">
          <label className="text-xs font-medium uppercase text-muted-foreground">
            Buscar
          </label>
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Nombre o RFC"
          />
        </div>
        <div>
          <label className="text-xs font-medium uppercase text-muted-foreground">
            Semáforo
          </label>
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value)}
            className="h-9 rounded-md border border-border bg-white px-2 text-sm"
          >
            {LEVELS.map((l) => (
              <option key={l} value={l}>
                {l || "(todos)"}
              </option>
            ))}
          </select>
        </div>
        <Button type="submit" size="sm" loading={loading}>
          Aplicar
        </Button>
      </form>

      {error ? (
        <p className="mb-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {error}
        </p>
      ) : null}

      <div className="overflow-x-auto rounded-md border border-border bg-white">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-3 py-2">Proveedor</th>
              <th className="px-3 py-2">RFC</th>
              <th className="px-3 py-2">Semáforo</th>
              <th className="px-3 py-2">% cumplido</th>
              <th className="px-3 py-2">En revisión</th>
              <th className="px-3 py-2">Faltantes</th>
              <th className="px-3 py-2">Rechazos</th>
              <th className="px-3 py-2">Vencen pronto</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.vendor_id} className="border-b border-border last:border-0">
                <td className="px-3 py-2 font-medium">{row.vendor_name}</td>
                <td className="px-3 py-2 font-mono text-xs">{row.vendor_rfc ?? "—"}</td>
                <td className="px-3 py-2">
                  <SemaphorePill level={row.semaphore_level} />
                </td>
                <td className="px-3 py-2 font-mono tabular-nums">
                  {row.compliance_pct}%
                </td>
                <td className="px-3 py-2 tabular-nums">{row.pending_reviews_count}</td>
                <td className="px-3 py-2 tabular-nums">{row.missing_required_count}</td>
                <td className="px-3 py-2 tabular-nums">
                  {row.rejected_or_correction_count}
                </td>
                <td className="px-3 py-2 tabular-nums">{row.due_soon_count}</td>
                <td className="px-3 py-2 text-right">
                  <Button asChild size="sm" variant="outline">
                    <Link href={`/client/vendors/${row.vendor_id}`}>Ver</Link>
                  </Button>
                </td>
              </tr>
            ))}
            {!loading && rows.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-3 py-6 text-center text-xs text-muted-foreground">
                  Sin proveedores con esos filtros.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </ClientShell>
  );
}

function SemaphorePill({ level }: { level: "green" | "yellow" | "red" }) {
  const tone =
    level === "green"
      ? "bg-emerald-100 text-emerald-800 border-emerald-300"
      : level === "yellow"
        ? "bg-amber-100 text-amber-800 border-amber-300"
        : "bg-red-100 text-red-800 border-red-300";
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${tone}`}>
      {level}
    </span>
  );
}
