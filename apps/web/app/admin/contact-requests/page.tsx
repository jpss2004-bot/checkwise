"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { Select } from "@/components/ui/select";

import { AdminShell } from "../_shell";
import {
  AdminApiError,
  type AdminContactRequest,
  type ContactRequestStatus,
  listContactRequests,
  updateContactRequestStatus,
} from "@/lib/api/admin";

/**
 * /admin/contact-requests — triage queue for the public landing-form
 * leads landed by `POST /api/v1/contact` (P0-3 follow-up).
 *
 * Default view shows newest first. Status filter narrows to one bucket.
 * Per-row dropdown updates the row's status (new → reviewed → contacted
 * → closed); the backend writes an audit_log row for each change.
 */

const STATUS_LABEL: Record<ContactRequestStatus, string> = {
  new: "Nueva",
  reviewed: "Revisada",
  contacted: "Contactada",
  closed: "Cerrada",
};

const STATUS_VARIANT: Record<
  ContactRequestStatus,
  "success" | "warning" | "info" | "outline"
> = {
  new: "info",
  reviewed: "warning",
  contacted: "success",
  closed: "outline",
};

const STATUS_ORDER: ContactRequestStatus[] = [
  "new",
  "reviewed",
  "contacted",
  "closed",
];

const PAGE_LIMIT = 50;

export default function AdminContactRequestsPage() {
  const router = useRouter();
  const [rows, setRows] = useState<AdminContactRequest[] | null>(null);
  const [total, setTotal] = useState<number>(0);
  const [statusFilter, setStatusFilter] = useState<ContactRequestStatus | "">(
    "",
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  // A refresh always restarts from offset 0 (filter changes route
  // through here), so the loaded list and the derived offset
  // (rows.length) reset together.
  async function refresh(filter = statusFilter) {
    setLoading(true);
    setError(null);
    setLoadMoreError(null);
    try {
      const params: { status?: ContactRequestStatus; limit: number } = {
        limit: PAGE_LIMIT,
      };
      if (filter) params.status = filter;
      const data = await listContactRequests(params);
      setRows(data.items);
      setTotal(data.total);
    } catch (err) {
      if (err instanceof AdminApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      setError(
        err instanceof Error
          ? err.message
          : "Error al cargar las solicitudes de contacto.",
      );
      setRows(null);
    } finally {
      setLoading(false);
    }
  }

  // "Cargar más" — fetches the next offset page with the current
  // filter and APPENDS, so in-place row updates (status dropdown)
  // keep operating on already-loaded rows.
  async function loadMore() {
    if (!rows || loadingMore) return;
    setLoadingMore(true);
    setLoadMoreError(null);
    try {
      const params: {
        status?: ContactRequestStatus;
        limit: number;
        offset: number;
      } = { limit: PAGE_LIMIT, offset: rows.length };
      if (statusFilter) params.status = statusFilter;
      const data = await listContactRequests(params);
      setRows((current) => {
        if (!current) return data.items;
        const seen = new Set(current.map((row) => row.id));
        return [...current, ...data.items.filter((row) => !seen.has(row.id))];
      });
      setTotal(data.total);
    } catch (err) {
      if (err instanceof AdminApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      setLoadMoreError(
        err instanceof Error
          ? err.message
          : "No pudimos cargar más solicitudes.",
      );
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onStatusChange(
    id: string,
    next: ContactRequestStatus,
  ): Promise<void> {
    setUpdatingId(id);
    try {
      const updated = await updateContactRequestStatus(id, next);
      // If a status filter is active and the new status doesn't match,
      // the row no longer belongs in the current view — drop it and
      // adjust the total. Otherwise replace the row in place so the
      // badge + dropdown reflect the new status without a refetch.
      if (statusFilter && updated.status !== statusFilter) {
        setRows((current) =>
          current ? current.filter((row) => row.id !== id) : current,
        );
        setTotal((t) => Math.max(0, t - 1));
      } else {
        setRows((current) =>
          current
            ? current.map((row) => (row.id === id ? updated : row))
            : current,
        );
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "No pudimos actualizar el estado de la solicitud.",
      );
    } finally {
      setUpdatingId(null);
    }
  }

  const columns: DataTableColumn<AdminContactRequest>[] = [
    {
      id: "created_at",
      header: "Recibida",
      width: "150px",
      cell: (row) => (
        <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-secondary)]">
          {new Date(row.created_at).toLocaleString("es-MX", {
            dateStyle: "medium",
            timeStyle: "short",
          })}
        </span>
      ),
    },
    {
      id: "name",
      header: "Nombre · Empresa",
      cell: (row) => (
        <div className="flex flex-col">
          <span className="text-[13px] font-medium text-[color:var(--text-primary)]">
            {row.name}
          </span>
          {row.company ? (
            <span className="text-[11px] text-[color:var(--text-tertiary)]">
              {row.company}
            </span>
          ) : null}
        </div>
      ),
    },
    {
      id: "email",
      header: "Correo",
      cell: (row) => (
        <a
          href={`mailto:${row.email}`}
          className="break-all text-[12px] text-[color:var(--text-link)] hover:underline"
        >
          {row.email}
        </a>
      ),
    },
    {
      id: "role",
      header: "Interés",
      cell: (row) => (
        <span className="text-[11px] text-[color:var(--text-secondary)]">
          {row.role ?? "—"}
        </span>
      ),
    },
    {
      id: "message",
      header: "Mensaje",
      cell: (row) => (
        <p className="line-clamp-2 max-w-md text-[12px] text-[color:var(--text-secondary)]">
          {row.message || "—"}
        </p>
      ),
    },
    {
      id: "status",
      header: "Estado",
      width: "200px",
      cell: (row) => (
        <div className="flex items-center gap-2">
          <Badge variant={STATUS_VARIANT[row.status]}>
            {STATUS_LABEL[row.status]}
          </Badge>
          <Select
            aria-label={`Cambiar estado de ${row.name}`}
            value={row.status}
            disabled={updatingId === row.id}
            onChange={(e) =>
              onStatusChange(row.id, e.target.value as ContactRequestStatus)
            }
            className="h-8 text-[11px]"
          >
            {STATUS_ORDER.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABEL[s]}
              </option>
            ))}
          </Select>
        </div>
      ),
    },
  ];

  return (
    <AdminShell
      title="Solicitudes de contacto"
      description="Mensajes enviados desde el formulario público de la landing de CheckWise. Cada solicitud queda registrada con sello de tiempo y se mueve por el triage de nueva → contactada → cerrada."
      actions={
        <Button
          variant="outline"
          size="sm"
          onClick={() => refresh()}
          disabled={loading}
        >
          {loading ? "Actualizando…" : "Actualizar"}
        </Button>
      }
    >
      <section className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            Filtrar por estado
            <Select
              value={statusFilter}
              onChange={(e) => {
                const next = e.target.value as ContactRequestStatus | "";
                setStatusFilter(next);
                refresh(next);
              }}
              className="h-9 text-[12px]"
            >
              <option value="">Todas</option>
              {STATUS_ORDER.map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABEL[s]}
                </option>
              ))}
            </Select>
          </label>

          <div className="ml-auto font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            {loading
              ? "Cargando…"
              : rows
                ? `${rows.length} de ${total}${statusFilter ? " (filtrado)" : ""}`
                : "—"}
          </div>
        </div>

        <DataTable<AdminContactRequest>
          columns={columns}
          items={loading ? null : rows}
          loading={loading}
          error={error}
          onRetry={() => refresh()}
          rowKey={(row) => row.id}
          ariaLabel="Solicitudes de contacto"
          emptyTitle={
            statusFilter
              ? "No hay solicitudes en este estado"
              : "Aún no hay solicitudes"
          }
          emptyDescription={
            statusFilter
              ? "Ajusta el filtro de estado o vuelve a “Todas”."
              : "Cada vez que alguien envíe el formulario público de la landing, aparecerá aquí."
          }
        />

        {!loading && rows && rows.length < total ? (
          <div className="flex flex-col items-center gap-2 py-2">
            <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              Mostrando {rows.length} de {total}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={loadMore}
              loading={loadingMore}
            >
              Cargar más
            </Button>
            {loadMoreError ? (
              <p className="text-[12px] text-[color:var(--status-error-text)]">
                {loadMoreError}
              </p>
            ) : null}
          </div>
        ) : null}
      </section>
    </AdminShell>
  );
}
