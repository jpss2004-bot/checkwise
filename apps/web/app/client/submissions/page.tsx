"use client";

import { useEffect, useState } from "react";
import { ArrowsClockwise, ChatCircle, MagnifyingGlass } from "@phosphor-icons/react";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";

import { ClientShell } from "../_shell";
import {
  listClientSubmissions,
  listClientVendors,
  type ClientSubmissionItem,
  type ClientVendorRow,
} from "@/lib/api/client";
import { INSTITUTION_LABELS } from "@/lib/api/portal";

// Status options shown in the dropdown, in the order a reviewer thinks
// about them. ``""`` is the "all statuses" sentinel; the API receives
// ``status=`` omitted when this is selected. Labels mirror the same
// canonical Spanish copy the table uses.
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
  posible_mismatch: { variant: "warning", label: "Posible discrepancia" },
  vencido: { variant: "destructive", label: "Vencido" },
  pendiente: { variant: "secondary", label: "Pendiente" },
  no_aplica: { variant: "secondary", label: "N/A" },
  excepcion_legal: { variant: "info", label: "Excepción" },
};

// Order matches the reviewer workflow: actionable first, then resolved.
const STATUS_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "", label: "Todos los estados" },
  { value: "pendiente_revision", label: STATUS_META.pendiente_revision.label },
  { value: "requiere_aclaracion", label: STATUS_META.requiere_aclaracion.label },
  { value: "posible_mismatch", label: STATUS_META.posible_mismatch.label },
  { value: "rechazado", label: STATUS_META.rechazado.label },
  { value: "aprobado", label: STATUS_META.aprobado.label },
  { value: "vencido", label: STATUS_META.vencido.label },
  { value: "excepcion_legal", label: STATUS_META.excepcion_legal.label },
  { value: "no_aplica", label: STATUS_META.no_aplica.label },
];

// Institution dropdown options. Mirrors the canonical INSTITUTION_LABELS
// map exported by the portal API client so any future institution
// addition flows through a single source of truth.
const INSTITUTION_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "", label: "Todas las instituciones" },
  { value: "sat", label: INSTITUTION_LABELS.sat },
  { value: "imss", label: INSTITUTION_LABELS.imss },
  { value: "infonavit", label: INSTITUTION_LABELS.infonavit },
  { value: "stps_repse", label: INSTITUTION_LABELS.stps_repse },
  { value: "interno_cliente", label: INSTITUTION_LABELS.interno_cliente },
];

const PAGE_SIZE_OPTIONS = [25, 50, 100, 200, 500] as const;

export default function ClientSubmissionsPage() {
  const [rows, setRows] = useState<ClientSubmissionItem[] | null>(null);
  const [vendors, setVendors] = useState<ClientVendorRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState({
    vendor_id: "",
    status: "",
    institution: "",
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
        institution: filters.institution || undefined,
        period_key: filters.period_key || undefined,
        limit: filters.limit,
      });
      setRows(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar entregas.");
      setRows(null);
    } finally {
      setLoading(false);
    }
  }

  // Load the vendor list ONCE so the dropdown can render names instead
  // of raw UUIDs. ``listClientVendors`` is the same endpoint the
  // vendors page uses, scoped to the active client.
  useEffect(() => {
    let cancelled = false;
    listClientVendors()
      .then((data) => {
        if (cancelled) return;
        setVendors(data.items);
      })
      .catch(() => {
        // Non-fatal — the dropdown just shows the "all proveedores"
        // option and the table still renders.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sortedVendors = [...vendors].sort((a, b) =>
    a.vendor_name.localeCompare(b.vendor_name, "es"),
  );

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
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
          >
            <FilterField label="Proveedor">
              <Select
                value={filters.vendor_id}
                onChange={(e) =>
                  setFilters({ ...filters, vendor_id: e.target.value })
                }
              >
                <option value="">Todos los proveedores</option>
                {sortedVendors.map((v) => (
                  <option key={v.vendor_id} value={v.vendor_id}>
                    {v.vendor_name}
                  </option>
                ))}
              </Select>
            </FilterField>
            <FilterField label="Estado">
              <Select
                value={filters.status}
                onChange={(e) =>
                  setFilters({ ...filters, status: e.target.value })
                }
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </Select>
            </FilterField>
            <FilterField label="Institución">
              <Select
                value={filters.institution}
                onChange={(e) =>
                  setFilters({ ...filters, institution: e.target.value })
                }
              >
                {INSTITUTION_OPTIONS.map((i) => (
                  <option key={i.value} value={i.value}>
                    {i.label}
                  </option>
                ))}
              </Select>
            </FilterField>
            <FilterField label="Periodo">
              <Input
                value={filters.period_key}
                onChange={(e) =>
                  setFilters({ ...filters, period_key: e.target.value })
                }
                placeholder="2026-M05"
              />
            </FilterField>
            <div className="sm:col-span-2 lg:col-span-4">
              <Button type="submit" size="sm" loading={loading}>
                <MagnifyingGlass className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
                Aplicar filtros
              </Button>
            </div>
          </form>
        </Surface>

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] px-4 py-2">
          <p className="font-mono text-[11px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            {rows?.length ?? 0} entregas mostradas
          </p>
          <label className="inline-flex items-center gap-2 text-[12px] text-[color:var(--text-secondary)]">
            <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              Mostrar
            </span>
            <Select
              value={String(filters.limit)}
              onChange={(e) => {
                const next = Number(e.target.value) || 100;
                setFilters((prev) => ({ ...prev, limit: next }));
                // Refresh immediately when the page size changes —
                // matches the user expectation of an inline pager.
                window.setTimeout(refresh, 0);
              }}
              className="h-8 w-20 py-0 text-[12px]"
            >
              {PAGE_SIZE_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
            <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              por página
            </span>
          </label>
        </div>

        <DataTable<ClientSubmissionItem>
          items={rows}
          loading={loading}
          error={error}
          onRetry={refresh}
          columns={SUBMISSIONS_COLUMNS}
          rowKey={(row) => row.submission_id}
          ariaLabel="Entregas del portafolio"
          emptyTitle="Sin entregas con esos filtros"
          emptyDescription="Modifica los filtros para ver más resultados."
          metaBadge={`${rows?.length ?? 0} entregas`}
          skeletonRows={8}
        />
      </div>
    </ClientShell>
  );
}

const SUBMISSIONS_COLUMNS: DataTableColumn<ClientSubmissionItem>[] = [
  {
    id: "when",
    header: "Cuándo",
    width: "140px",
    cell: (row) => (
      <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-secondary)]">
        {new Date(row.submitted_at).toLocaleString("es-MX", {
          day: "2-digit",
          month: "short",
          hour: "2-digit",
          minute: "2-digit",
        })}
      </span>
    ),
  },
  {
    id: "vendor",
    header: "Proveedor",
    cell: (row) => (
      <p className="text-[13px] font-medium text-[color:var(--text-primary)]">
        {row.vendor_name}
      </p>
    ),
  },
  {
    id: "institution",
    header: "Institución",
    width: "120px",
    cell: (row) => (
      <span className="text-[12px] text-[color:var(--text-secondary)]">
        {row.institution
          ? INSTITUTION_LABELS[row.institution] ?? row.institution
          : "—"}
      </span>
    ),
  },
  {
    id: "requirement",
    header: "Requisito",
    cell: (row) => (
      <span className="text-[12px] text-[color:var(--text-primary)]">
        {row.requirement_name ?? row.requirement_code ?? "—"}
      </span>
    ),
  },
  {
    id: "period",
    header: "Periodo",
    width: "100px",
    cell: (row) => (
      <span className="font-mono text-[11px] tabular-nums">
        {row.period_key ?? "—"}
      </span>
    ),
  },
  {
    id: "status",
    header: "Estado",
    width: "140px",
    cell: (row) => {
      const meta = STATUS_META[row.status] ?? {
        variant: "secondary" as const,
        label: row.status,
      };
      return <Badge variant={meta.variant}>{meta.label}</Badge>;
    },
  },
  {
    id: "file",
    header: "Archivo / Nota",
    cell: (row) => (
      <div className="text-[11px]">
        {row.filename ? (
          <p className="truncate text-[color:var(--text-primary)]">
            {row.filename}
          </p>
        ) : null}
        {row.reviewer_note ? (
          <p className="mt-0.5 flex items-center gap-1 truncate text-[color:var(--text-secondary)]">
            <ChatCircle
              className="h-3 w-3 shrink-0 text-[color:var(--text-tertiary)]"
              weight="bold"
              aria-hidden
            />
            {row.reviewer_note}
          </p>
        ) : null}
        {!row.filename && !row.reviewer_note ? "—" : null}
      </div>
    ),
  },
  {
    id: "lineage",
    header: "Intentos",
    width: "200px",
    cell: (row) => (
      <LineageBadges
        supersedes={row.supersedes_submission_id}
        supersededBy={row.superseded_by_submission_id}
      />
    ),
  },
];

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

// Phase 3 / Slice 3A — the previous version of this cell displayed the
// truncated supersedes/superseded_by submission UUIDs ("↓ a1b2c3d4"),
// which are operational identifiers a client should never need. The
// canonical fact we want to surface is "this is a re-upload" or "this
// was already replaced" — show that in plain Spanish.
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
    <div className="flex flex-col gap-1">
      {supersedes ? (
        <span className="inline-flex w-fit items-center gap-1 rounded-full bg-[color:var(--surface-sunken)] px-2 py-0.5 text-[10px] font-medium text-[color:var(--text-secondary)]">
          <ArrowsClockwise
            className="h-3 w-3 shrink-0"
            weight="bold"
            aria-hidden="true"
          />
          Reemplaza intento anterior
        </span>
      ) : null}
      {supersededBy ? (
        <span className="inline-flex w-fit items-center gap-1 rounded-full bg-[color:var(--surface-sunken)] px-2 py-0.5 text-[10px] font-medium text-[color:var(--text-secondary)]">
          <ArrowsClockwise
            className="h-3 w-3 shrink-0"
            weight="bold"
            aria-hidden="true"
          />
          Reemplazado por intento posterior
        </span>
      ) : null}
    </div>
  );
}
