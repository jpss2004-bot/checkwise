"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Check,
  X as XIcon,
} from "@phosphor-icons/react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

import { AdminShell } from "../_shell";
import { VendorRef } from "@/components/checkwise/vendor-ref";
import {
  AdminApiError,
  type AdminCorrectionRequest,
  type CorrectionRequestStatus,
  approveCorrectionRequest,
  listCorrectionRequests,
  rejectCorrectionRequest,
} from "@/lib/api/admin";

/**
 * /admin/correction-requests — provider Tier B correction triage.
 *
 * Provider submissions land via POST /portal/.../correction-requests
 * as ``audit_log`` rows. This page is the admin counterpart:
 *
 *   - List rows (pending first, with status filter chips).
 *   - Approve auto-applies the proposed value to the matching
 *     Vendor column (contact_email / contact_phone / contact_name)
 *     and writes a sibling audit row.
 *   - Reject records the rejection note + sibling audit row, no
 *     change applied.
 *
 * Both decisions are idempotent on already-resolved rows.
 */

const STATUS_LABEL: Record<CorrectionRequestStatus, string> = {
  pending: "Pendiente",
  approved: "Aprobada",
  rejected: "Rechazada",
};

const STATUS_VARIANT: Record<
  CorrectionRequestStatus,
  "warning" | "success" | "outline"
> = {
  pending: "warning",
  approved: "success",
  rejected: "outline",
};

const FIELD_LABEL: Record<string, string> = {
  contact_email: "Correo de contacto",
  contact_phone: "Teléfono de contacto",
  contact_name: "Nombre de contacto",
};

const STATUS_ORDER: CorrectionRequestStatus[] = [
  "pending",
  "approved",
  "rejected",
];

const PAGE_LIMIT = 50;

export default function AdminCorrectionRequestsPage() {
  const router = useRouter();
  const [rows, setRows] = useState<AdminCorrectionRequest[] | null>(null);
  const [total, setTotal] = useState<number>(0);
  const [statusFilter, setStatusFilter] = useState<
    CorrectionRequestStatus | ""
  >("pending");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const [resolveTarget, setResolveTarget] = useState<{
    row: AdminCorrectionRequest;
    decision: "approve" | "reject";
  } | null>(null);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // A refresh always restarts from offset 0 (filter changes route
  // through here), so the loaded list and the derived offset
  // (rows.length) reset together. The status filter is applied
  // server-side, so `total` is already scoped to the active filter.
  async function refresh(filter: CorrectionRequestStatus | "" = statusFilter) {
    setLoading(true);
    setError(null);
    setLoadMoreError(null);
    try {
      const params: { status?: CorrectionRequestStatus; limit: number } = {
        limit: PAGE_LIMIT,
      };
      if (filter) params.status = filter;
      const data = await listCorrectionRequests(params);
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
          : "Error al cargar las solicitudes de corrección.",
      );
      setRows(null);
    } finally {
      setLoading(false);
    }
  }

  // "Cargar más" — fetches the next offset page with the current
  // filter and APPENDS, so the approve/reject dialogs keep operating
  // on already-loaded rows.
  async function loadMore() {
    if (!rows || loadingMore) return;
    setLoadingMore(true);
    setLoadMoreError(null);
    try {
      const params: {
        status?: CorrectionRequestStatus;
        limit: number;
        offset: number;
      } = { limit: PAGE_LIMIT, offset: rows.length };
      if (statusFilter) params.status = statusFilter;
      const data = await listCorrectionRequests(params);
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

  function openResolveDialog(
    row: AdminCorrectionRequest,
    decision: "approve" | "reject",
  ) {
    setResolveTarget({ row, decision });
    setNote("");
  }

  async function confirmResolve() {
    if (!resolveTarget) return;
    setSubmitting(true);
    setError(null);
    try {
      const { row, decision } = resolveTarget;
      const updated =
        decision === "approve"
          ? await approveCorrectionRequest(row.id, note)
          : await rejectCorrectionRequest(row.id, note);
      // If a status filter is active and the new status no longer
      // matches, drop the row from the visible list. Otherwise
      // replace in place so the badge + buttons reflect resolution
      // without a refetch.
      if (statusFilter && updated.status !== statusFilter) {
        setRows((current) =>
          current ? current.filter((r) => r.id !== row.id) : current,
        );
        setTotal((t) => Math.max(0, t - 1));
      } else {
        setRows((current) =>
          current
            ? current.map((r) => (r.id === row.id ? updated : r))
            : current,
        );
      }
      setResolveTarget(null);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "No pudimos resolver la solicitud.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const columns: DataTableColumn<AdminCorrectionRequest>[] = [
    {
      id: "submitted_at",
      header: "Recibida",
      width: "150px",
      cell: (row) => (
        <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-secondary)]">
          {new Date(row.submitted_at).toLocaleString("es-MX", {
            dateStyle: "medium",
            timeStyle: "short",
          })}
        </span>
      ),
    },
    {
      id: "provider",
      header: "Proveedor",
      cell: (row) => (
        <div className="flex flex-col">
          <span className="text-[13px] font-medium text-[color:var(--text-primary)]">
            {row.vendor_id && row.vendor_name ? (
              <VendorRef
                vendorId={row.vendor_id}
                vendorName={row.vendor_name}
                clientId={row.client_id ?? undefined}
                surface="admin"
              />
            ) : (
              row.vendor_name ?? row.user_name ?? "—"
            )}
          </span>
          <span className="text-[11px] text-[color:var(--text-tertiary)]">
            {row.user_email ?? row.user_name ?? "Usuario del proveedor"}
          </span>
          {row.client_name ? (
            <span className="text-[10px] font-mono uppercase tracking-wide text-[color:var(--text-tertiary)]">
              Cliente: {row.client_name}
            </span>
          ) : null}
        </div>
      ),
    },
    {
      id: "field",
      header: "Campo",
      cell: (row) => (
        <span className="text-[12px] text-[color:var(--text-primary)]">
          {FIELD_LABEL[row.field] ?? row.field}
        </span>
      ),
    },
    {
      id: "values",
      header: "Cambio propuesto",
      cell: (row) => (
        <div className="flex flex-col text-[12px]">
          <span className="text-[color:var(--text-tertiary)]">
            <span className="font-mono text-[10px] uppercase tracking-wide">
              Actual
            </span>{" "}
            {row.current_value || "—"}
          </span>
          <span className="text-[color:var(--text-primary)]">
            <span className="font-mono text-[10px] uppercase tracking-wide">
              Propuesto
            </span>{" "}
            <strong>{row.proposed_value || "—"}</strong>
          </span>
        </div>
      ),
    },
    {
      id: "reason",
      header: "Razón / mensaje",
      cell: (row) => (
        <div className="max-w-md space-y-1">
          <p className="text-[12px] text-[color:var(--text-primary)]">
            {row.reason || "—"}
          </p>
          {row.message ? (
            <p className="line-clamp-2 text-[11px] text-[color:var(--text-tertiary)]">
              {row.message}
            </p>
          ) : null}
        </div>
      ),
    },
    {
      id: "status",
      header: "Estado",
      width: "210px",
      cell: (row) => {
        const isResolved = row.status !== "pending";
        return (
          <div className="flex flex-col items-start gap-1.5">
            <Badge variant={STATUS_VARIANT[row.status]}>
              {STATUS_LABEL[row.status]}
            </Badge>
            {isResolved ? (
              row.resolution_note ? (
                <p className="line-clamp-2 max-w-[180px] text-[10px] text-[color:var(--text-tertiary)]">
                  {row.resolution_note}
                </p>
              ) : null
            ) : (
              <div className="flex gap-1.5">
                <Button
                  size="sm"
                  variant="default"
                  className="h-7 px-2 text-[11px]"
                  onClick={() => openResolveDialog(row, "approve")}
                >
                  <Check
                    className="h-3 w-3"
                    weight="bold"
                    aria-hidden="true"
                  />
                  Aprobar
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 px-2 text-[11px]"
                  onClick={() => openResolveDialog(row, "reject")}
                >
                  <XIcon
                    className="h-3 w-3"
                    weight="bold"
                    aria-hidden="true"
                  />
                  Rechazar
                </Button>
              </div>
            )}
          </div>
        );
      },
    },
  ];

  return (
    <AdminShell
      title="Solicitudes de corrección"
      description="Cambios de datos de contacto (Tier B) que los proveedores piden desde su portal. Aprobar aplica la corrección al registro del proveedor; rechazar la cierra sin cambios. Toda decisión queda en el audit log."
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
                const next = e.target.value as
                  | CorrectionRequestStatus
                  | "";
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

        <DataTable<AdminCorrectionRequest>
          columns={columns}
          items={loading ? null : rows}
          loading={loading}
          error={error}
          onRetry={() => refresh()}
          rowKey={(row) => row.id}
          ariaLabel="Solicitudes de corrección"
          emptyTitle={
            statusFilter === "pending"
              ? "No hay solicitudes pendientes"
              : statusFilter
                ? "No hay solicitudes en este estado"
                : "Aún no hay solicitudes"
          }
          emptyDescription="Cuando un proveedor pida cambiar su correo, teléfono o nombre de contacto desde su portal, la solicitud aparecerá aquí."
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

      <Dialog
        open={resolveTarget !== null}
        onOpenChange={(open) => {
          if (!open) setResolveTarget(null);
        }}
      >
        <DialogContent>
          {resolveTarget ? (
            <>
              <DialogHeader>
                <DialogTitle>
                  {resolveTarget.decision === "approve"
                    ? "Aprobar corrección"
                    : "Rechazar corrección"}
                </DialogTitle>
                <DialogDescription>
                  {resolveTarget.decision === "approve"
                    ? `Se aplicará "${resolveTarget.row.proposed_value}" al campo ${
                        FIELD_LABEL[resolveTarget.row.field] ??
                        resolveTarget.row.field
                      } del proveedor ${resolveTarget.row.vendor_name ?? "—"}.`
                    : `La solicitud quedará archivada como rechazada y no se aplicará al registro de ${resolveTarget.row.vendor_name ?? "—"}.`}
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-3 text-[12px]">
                <div className="rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)] p-3">
                  <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                    Razón del proveedor
                  </p>
                  <p className="mt-1 text-[color:var(--text-primary)]">
                    {resolveTarget.row.reason || "—"}
                  </p>
                  {resolveTarget.row.message ? (
                    <p className="mt-2 text-[color:var(--text-secondary)]">
                      {resolveTarget.row.message}
                    </p>
                  ) : null}
                </div>

                <label className="flex flex-col gap-1">
                  <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                    Nota interna (opcional)
                  </span>
                  <Textarea
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    rows={3}
                    placeholder={
                      resolveTarget.decision === "approve"
                        ? "Por ejemplo: confirmado por correo con el proveedor."
                        : "Por qué se rechaza la solicitud — útil para el siguiente revisor."
                    }
                  />
                </label>
              </div>

              <DialogFooter>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setResolveTarget(null)}
                  disabled={submitting}
                >
                  Cancelar
                </Button>
                <Button
                  type="button"
                  variant={
                    resolveTarget.decision === "approve" ? "default" : "outline"
                  }
                  onClick={confirmResolve}
                  loading={submitting}
                >
                  {resolveTarget.decision === "approve"
                    ? "Aprobar y aplicar"
                    : "Rechazar solicitud"}
                </Button>
              </DialogFooter>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </AdminShell>
  );
}
