"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { ClientShell } from "../_shell";
import {
  listClientSubmissions,
  type ClientSubmissionItem,
} from "@/lib/api/client";

export default function ClientSubmissionsPage() {
  const [rows, setRows] = useState<ClientSubmissionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState({
    vendor_id: "",
    status: "",
    requirement_code: "",
    period_key: "",
    limit: 100,
  });

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const data = await listClientSubmissions({
        vendor_id: filters.vendor_id || undefined,
        status: filters.status || undefined,
        requirement_code: filters.requirement_code || undefined,
        period_key: filters.period_key || undefined,
        limit: filters.limit,
      });
      setRows(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar entregas.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <ClientShell title="Entregas">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          refresh();
        }}
        className="mb-4 grid gap-3 rounded-md border border-border bg-muted/30 p-4 sm:grid-cols-3 lg:grid-cols-5"
      >
        <div>
          <label className="text-xs font-medium uppercase text-muted-foreground">
            Vendor ID
          </label>
          <Input
            value={filters.vendor_id}
            onChange={(e) => setFilters({ ...filters, vendor_id: e.target.value })}
          />
        </div>
        <div>
          <label className="text-xs font-medium uppercase text-muted-foreground">
            Estado
          </label>
          <Input
            value={filters.status}
            onChange={(e) => setFilters({ ...filters, status: e.target.value })}
            placeholder="pendiente_revision"
          />
        </div>
        <div>
          <label className="text-xs font-medium uppercase text-muted-foreground">
            Requirement code
          </label>
          <Input
            value={filters.requirement_code}
            onChange={(e) => setFilters({ ...filters, requirement_code: e.target.value })}
          />
        </div>
        <div>
          <label className="text-xs font-medium uppercase text-muted-foreground">
            Period key
          </label>
          <Input
            value={filters.period_key}
            onChange={(e) => setFilters({ ...filters, period_key: e.target.value })}
            placeholder="2026-B1"
          />
        </div>
        <div>
          <label className="text-xs font-medium uppercase text-muted-foreground">
            Límite
          </label>
          <Input
            type="number"
            min={1}
            max={500}
            value={filters.limit}
            onChange={(e) => setFilters({ ...filters, limit: Number(e.target.value) || 100 })}
          />
        </div>
        <div className="sm:col-span-3 lg:col-span-5">
          <Button type="submit" size="sm" loading={loading}>
            Filtrar
          </Button>
        </div>
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
              <th className="px-3 py-2">Cuándo</th>
              <th className="px-3 py-2">Proveedor</th>
              <th className="px-3 py-2">Requisito</th>
              <th className="px-3 py-2">Periodo</th>
              <th className="px-3 py-2">Estado</th>
              <th className="px-3 py-2">Archivo</th>
              <th className="px-3 py-2">Nota revisor</th>
              <th className="px-3 py-2">Lineage</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.submission_id} className="border-b border-border align-top last:border-0">
                <td className="px-3 py-2 font-mono text-xs">
                  {new Date(row.submitted_at).toLocaleString("es-MX")}
                </td>
                <td className="px-3 py-2">{row.vendor_name}</td>
                <td className="px-3 py-2 text-xs">
                  {row.requirement_name ?? row.requirement_code ?? "—"}
                </td>
                <td className="px-3 py-2 font-mono text-xs">{row.period_key ?? "—"}</td>
                <td className="px-3 py-2">{row.status}</td>
                <td className="px-3 py-2 text-xs">{row.filename ?? "—"}</td>
                <td className="px-3 py-2 text-xs">{row.reviewer_note ?? "—"}</td>
                <td className="px-3 py-2 text-[10px] font-mono">
                  {row.supersedes_submission_id ? (
                    <div>↓ reemplaza {row.supersedes_submission_id.slice(0, 8)}…</div>
                  ) : null}
                  {row.superseded_by_submission_id ? (
                    <div>↑ reemplazada por {row.superseded_by_submission_id.slice(0, 8)}…</div>
                  ) : null}
                  {!row.supersedes_submission_id && !row.superseded_by_submission_id
                    ? "—"
                    : null}
                </td>
              </tr>
            ))}
            {!loading && rows.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center text-xs text-muted-foreground">
                  Sin entregas con esos filtros.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </ClientShell>
  );
}
