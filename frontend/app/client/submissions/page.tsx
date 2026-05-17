"use client";

import { useEffect, useState } from "react";
import { Files, MagnifyingGlass } from "@phosphor-icons/react";

import { EmptyState, Surface } from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { ClientShell } from "../_shell";
import {
  listClientSubmissions,
  type ClientSubmissionItem,
} from "@/lib/api/client";

const STATUS_META: Record<
  string,
  { variant: "success" | "warning" | "info" | "destructive" | "secondary"; label: string }
> = {
  aprobado: { variant: "success", label: "Aprobado" },
  rechazado: { variant: "destructive", label: "Rechazado" },
  requiere_aclaracion: { variant: "warning", label: "Aclaración" },
  pendiente_revision: { variant: "info", label: "En revisión" },
  recibido: { variant: "info", label: "Recibido" },
  prevalidado: { variant: "info", label: "Prevalidado" },
  posible_mismatch: { variant: "warning", label: "Mismatch" },
  vencido: { variant: "destructive", label: "Vencido" },
  pendiente: { variant: "secondary", label: "Pendiente" },
  no_aplica: { variant: "secondary", label: "N/A" },
  excepcion_legal: { variant: "info", label: "Excepción" },
};

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
    <ClientShell
      title="Entregas"
      description="Búsqueda y filtrado sobre todas las cargas hechas por los proveedores."
    >
      <div className="space-y-5">
        <Surface title="Filtros">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              refresh();
            }}
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5"
          >
            <FilterField label="Vendor ID">
              <Input
                value={filters.vendor_id}
                onChange={(e) => setFilters({ ...filters, vendor_id: e.target.value })}
              />
            </FilterField>
            <FilterField label="Estado">
              <Input
                value={filters.status}
                onChange={(e) => setFilters({ ...filters, status: e.target.value })}
                placeholder="aprobado, pendiente_revision…"
              />
            </FilterField>
            <FilterField label="Requirement code">
              <Input
                value={filters.requirement_code}
                onChange={(e) =>
                  setFilters({ ...filters, requirement_code: e.target.value })
                }
              />
            </FilterField>
            <FilterField label="Periodo">
              <Input
                value={filters.period_key}
                onChange={(e) => setFilters({ ...filters, period_key: e.target.value })}
                placeholder="2026-M05"
              />
            </FilterField>
            <FilterField label="Límite">
              <Input
                type="number"
                min={1}
                max={500}
                value={filters.limit}
                onChange={(e) =>
                  setFilters({ ...filters, limit: Number(e.target.value) || 100 })
                }
              />
            </FilterField>
            <div className="sm:col-span-2 lg:col-span-5">
              <Button type="submit" size="sm" loading={loading}>
                <MagnifyingGlass className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
                Aplicar filtros
              </Button>
            </div>
          </form>
        </Surface>

        {error ? (
          <p className="rounded-md border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] p-3 text-sm text-[color:var(--status-warning-text)]">
            {error}
          </p>
        ) : null}

        <Surface
          title={`Resultados (${rows.length})`}
          bodyClassName="p-0"
        >
          {rows.length === 0 && !loading ? (
            <div className="p-8">
              <EmptyState
                icon={Files}
                title="Sin entregas con esos filtros"
                description="Modifica los filtros para ver más resultados."
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] text-left font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  <tr>
                    <th className="px-3 py-2.5">Cuándo</th>
                    <th className="px-3 py-2.5">Proveedor</th>
                    <th className="px-3 py-2.5">Requisito</th>
                    <th className="px-3 py-2.5">Periodo</th>
                    <th className="px-3 py-2.5">Estado</th>
                    <th className="px-3 py-2.5">Archivo / Nota</th>
                    <th className="px-3 py-2.5">Lineage</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const meta = STATUS_META[row.status] ?? {
                      variant: "secondary" as const,
                      label: row.status,
                    };
                    return (
                      <tr
                        key={row.submission_id}
                        className="border-b border-[color:var(--border-subtle)] align-top last:border-0 hover:bg-[color:var(--surface-hover)]"
                      >
                        <td className="px-3 py-2.5 font-mono text-[11px] text-[color:var(--text-secondary)]">
                          {new Date(row.submitted_at).toLocaleString("es-MX", {
                            day: "2-digit",
                            month: "short",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </td>
                        <td className="px-3 py-2.5">
                          <p className="text-[13px] font-medium text-[color:var(--text-primary)]">
                            {row.vendor_name}
                          </p>
                          <p className="font-mono text-[10px] text-[color:var(--text-tertiary)]">
                            {row.vendor_id.slice(0, 8)}…
                          </p>
                        </td>
                        <td className="px-3 py-2.5 text-[12px] text-[color:var(--text-primary)]">
                          {row.requirement_name ?? row.requirement_code ?? "—"}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-[11px]">
                          {row.period_key ?? "—"}
                        </td>
                        <td className="px-3 py-2.5">
                          <Badge variant={meta.variant}>{meta.label}</Badge>
                        </td>
                        <td className="px-3 py-2.5 text-[11px]">
                          {row.filename ? (
                            <p className="truncate text-[color:var(--text-primary)]">
                              {row.filename}
                            </p>
                          ) : null}
                          {row.reviewer_note ? (
                            <p className="mt-0.5 truncate text-[color:var(--text-secondary)]">
                              💬 {row.reviewer_note}
                            </p>
                          ) : null}
                          {!row.filename && !row.reviewer_note ? "—" : null}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-[10px]">
                          <LineageBadges
                            supersedes={row.supersedes_submission_id}
                            supersededBy={row.superseded_by_submission_id}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Surface>
      </div>
    </ClientShell>
  );
}

function FilterField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className="block font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        {label}
      </span>
      {children}
    </label>
  );
}

function LineageBadges({
  supersedes,
  supersededBy,
}: {
  supersedes: string | null;
  supersededBy: string | null;
}) {
  if (!supersedes && !supersededBy) {
    return <span className="text-[color:var(--text-tertiary)]">—</span>;
  }
  return (
    <div className="space-y-1">
      {supersedes ? (
        <span className="inline-flex items-center gap-1 rounded-full bg-[color:var(--surface-sunken)] px-1.5 py-0.5 text-[color:var(--text-secondary)]">
          ↓ {supersedes.slice(0, 8)}
        </span>
      ) : null}
      {supersededBy ? (
        <span className="inline-flex items-center gap-1 rounded-full bg-[color:var(--surface-sunken)] px-1.5 py-0.5 text-[color:var(--text-secondary)]">
          ↑ {supersededBy.slice(0, 8)}
        </span>
      ) : null}
    </div>
  );
}
