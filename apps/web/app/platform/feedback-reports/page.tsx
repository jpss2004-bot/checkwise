"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bug,
  ChatCenteredDots,
  CheckCircle,
  Eye,
  Hourglass,
  Lightbulb,
  Prohibit,
  Warning,
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
import { Field } from "@/components/ui/field";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

import { PlatformShell } from "../_shell";
import {
  type AdminFeedbackReport,
  type FeedbackKind,
  type FeedbackSlackDeliveryStatus,
  type FeedbackSource,
  type FeedbackStatus,
  getFeedbackReport,
  listFeedbackReports,
  updateFeedbackReportStatus,
} from "@/lib/api/admin";

/**
 * /admin/feedback-reports — triage queue for bug + improvement reports
 * captured by the Reportar launcher (POST /api/v1/feedback{,/public}).
 *
 * Each row is a persisted FeedbackReport. Status moves new → triaged
 * → in_progress → resolved (or wont_fix). The detail dialog shows the
 * screenshot (when one was attached), the captured console log, page
 * URL/viewport/UA, and Slack delivery status, then exposes the same
 * status transitions plus a resolution_note textarea.
 */

const STATUS_LABEL: Record<FeedbackStatus, string> = {
  new: "Nuevo",
  triaged: "Triaged",
  in_progress: "En progreso",
  resolved: "Resuelto",
  wont_fix: "Wont fix",
};

const STATUS_VARIANT: Record<
  FeedbackStatus,
  "success" | "warning" | "info" | "outline"
> = {
  new: "info",
  triaged: "warning",
  in_progress: "warning",
  resolved: "success",
  wont_fix: "outline",
};

const STATUS_ORDER: FeedbackStatus[] = [
  "new",
  "triaged",
  "in_progress",
  "resolved",
  "wont_fix",
];

const KIND_ORDER: FeedbackKind[] = ["bug", "improvement"];
const SOURCE_ORDER: FeedbackSource[] = ["authenticated", "public"];

const SLACK_LABEL: Record<FeedbackSlackDeliveryStatus, string> = {
  pending: "Pendiente",
  sent: "Enviado",
  failed: "Fallo",
  skipped: "Sin configurar",
};

const SLACK_VARIANT: Record<
  FeedbackSlackDeliveryStatus,
  "success" | "warning" | "info" | "outline"
> = {
  pending: "info",
  sent: "success",
  failed: "warning",
  skipped: "outline",
};

const PAGE_LIMIT = 50;

export default function AdminFeedbackReportsPage() {
  const [rows, setRows] = useState<AdminFeedbackReport[] | null>(null);
  const [total, setTotal] = useState<number>(0);
  const [statusFilter, setStatusFilter] = useState<FeedbackStatus | "">("");
  const [kindFilter, setKindFilter] = useState<FeedbackKind | "">("");
  const [sourceFilter, setSourceFilter] = useState<FeedbackSource | "">("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const [detail, setDetail] = useState<AdminFeedbackReport | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // A refresh always restarts from offset 0 (filter changes route
  // through here), so the loaded list and the derived offset
  // (rows.length) reset together.
  async function refresh(
    overrides: {
      status?: FeedbackStatus | "";
      kind?: FeedbackKind | "";
      source?: FeedbackSource | "";
    } = {},
  ) {
    setLoading(true);
    setError(null);
    setLoadMoreError(null);
    const eff = {
      status: overrides.status !== undefined ? overrides.status : statusFilter,
      kind: overrides.kind !== undefined ? overrides.kind : kindFilter,
      source: overrides.source !== undefined ? overrides.source : sourceFilter,
    };
    try {
      const params: {
        status?: FeedbackStatus;
        kind?: FeedbackKind;
        source?: FeedbackSource;
        limit: number;
      } = { limit: PAGE_LIMIT };
      if (eff.status) params.status = eff.status;
      if (eff.kind) params.kind = eff.kind;
      if (eff.source) params.source = eff.source;
      const data = await listFeedbackReports(params);
      setRows(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Error al cargar los reportes de feedback.",
      );
      setRows(null);
    } finally {
      setLoading(false);
    }
  }

  // "Cargar más" — fetches the next offset page with the current
  // filters and APPENDS, so the detail dialog's in-place row updates
  // keep operating on already-loaded rows.
  async function loadMore() {
    if (!rows || loadingMore) return;
    setLoadingMore(true);
    setLoadMoreError(null);
    try {
      const params: {
        status?: FeedbackStatus;
        kind?: FeedbackKind;
        source?: FeedbackSource;
        limit: number;
        offset: number;
      } = { limit: PAGE_LIMIT, offset: rows.length };
      if (statusFilter) params.status = statusFilter;
      if (kindFilter) params.kind = kindFilter;
      if (sourceFilter) params.source = sourceFilter;
      const data = await listFeedbackReports(params);
      setRows((current) => {
        if (!current) return data.items;
        const seen = new Set(current.map((row) => row.id));
        return [...current, ...data.items.filter((row) => !seen.has(row.id))];
      });
      setTotal(data.total);
    } catch (err) {
      setLoadMoreError(
        err instanceof Error
          ? err.message
          : "No pudimos cargar más reportes.",
      );
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function openDetail(id: string) {
    setDetailLoading(true);
    try {
      const data = await getFeedbackReport(id);
      setDetail(data);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "No pudimos cargar el detalle del reporte.",
      );
    } finally {
      setDetailLoading(false);
    }
  }

  function closeDetail() {
    setDetail(null);
  }

  async function onStatusSubmit(
    next: FeedbackStatus,
    resolutionNote: string,
  ): Promise<void> {
    if (!detail) return;
    try {
      const updated = await updateFeedbackReportStatus(detail.id, {
        status: next,
        resolution_note: resolutionNote || null,
      });
      // Update list view if the row is still visible (apply same
      // filter rules contact-requests uses).
      setRows((current) =>
        current
          ? current
              .map((row) => (row.id === updated.id ? updated : row))
              .filter((row) =>
                statusFilter ? row.status === statusFilter : true,
              )
          : current,
      );
      if (statusFilter && updated.status !== statusFilter) {
        setTotal((t) => Math.max(0, t - 1));
      }
      setDetail(updated);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "No pudimos actualizar el estado del reporte.",
      );
    }
  }

  const columns: DataTableColumn<AdminFeedbackReport>[] = useMemo(
    () => [
      {
        id: "created_at",
        header: "Recibido",
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
        id: "kind",
        header: "Tipo",
        width: "110px",
        cell: (row) => (
          <span className="inline-flex items-center gap-1.5 text-[12px] text-[color:var(--text-primary)]">
            {row.kind === "bug" ? (
              <Bug
                className="h-3.5 w-3.5 text-[color:var(--status-warning-text)]"
                weight="bold"
                aria-hidden="true"
              />
            ) : (
              <Lightbulb
                className="h-3.5 w-3.5 text-[color:var(--text-teal)]"
                weight="bold"
                aria-hidden="true"
              />
            )}
            {row.kind === "bug" ? "Bug" : "Mejora"}
          </span>
        ),
      },
      {
        id: "source",
        header: "Origen",
        width: "110px",
        cell: (row) => (
          <Badge variant={row.is_public ? "outline" : "info"}>
            {row.is_public ? "Público" : "Interno"}
          </Badge>
        ),
      },
      {
        id: "from",
        header: "De",
        cell: (row) => (
          <div className="flex flex-col">
            <span className="text-[12px] font-medium text-[color:var(--text-primary)]">
              {row.user_email ?? row.contact_email ?? "Anónimo"}
            </span>
            {row.user_full_name ? (
              <span className="text-[11px] text-[color:var(--text-tertiary)]">
                {row.user_full_name}
              </span>
            ) : row.ip_hash ? (
              <span className="font-mono text-[10px] text-[color:var(--text-tertiary)]">
                ip:{row.ip_hash}
              </span>
            ) : null}
          </div>
        ),
      },
      {
        id: "description",
        header: "Descripción",
        cell: (row) => (
          <p className="line-clamp-2 max-w-md text-[12px] text-[color:var(--text-secondary)]">
            {row.description}
          </p>
        ),
      },
      {
        id: "path",
        header: "Página",
        width: "200px",
        cell: (row) => (
          <span className="font-mono text-[11px] text-[color:var(--text-secondary)]">
            {row.path ?? "—"}
          </span>
        ),
      },
      {
        id: "slack",
        header: "Slack",
        width: "120px",
        cell: (row) => (
          <Badge variant={SLACK_VARIANT[row.slack_delivery_status]}>
            {SLACK_LABEL[row.slack_delivery_status]}
          </Badge>
        ),
      },
      {
        id: "status",
        header: "Estado",
        width: "140px",
        cell: (row) => (
          <Badge variant={STATUS_VARIANT[row.status]}>
            {STATUS_LABEL[row.status]}
          </Badge>
        ),
      },
      {
        id: "actions",
        header: "",
        width: "60px",
        cell: (row) => (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => openDetail(row.id)}
            aria-label={`Ver detalle del reporte ${row.id}`}
          >
            <Eye className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          </Button>
        ),
      },
    ],
    [],
  );

  return (
    <PlatformShell
      title="Reportes de feedback"
      description="Bug reports y sugerencias enviadas desde el botón Reportar. Cada reporte queda persistido aquí (DB es la fuente de verdad) y opcionalmente notificado en #checkwise-feedback. Mueve los reportes por el flujo nuevo → triaged → en progreso → resuelto."
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
            Estado
            <Select
              value={statusFilter}
              onChange={(e) => {
                const next = e.target.value as FeedbackStatus | "";
                setStatusFilter(next);
                refresh({ status: next });
              }}
              className="h-9 text-[12px]"
            >
              <option value="">Todos</option>
              {STATUS_ORDER.map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABEL[s]}
                </option>
              ))}
            </Select>
          </label>

          <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            Tipo
            <Select
              value={kindFilter}
              onChange={(e) => {
                const next = e.target.value as FeedbackKind | "";
                setKindFilter(next);
                refresh({ kind: next });
              }}
              className="h-9 text-[12px]"
            >
              <option value="">Todos</option>
              {KIND_ORDER.map((k) => (
                <option key={k} value={k}>
                  {k === "bug" ? "Bug" : "Mejora"}
                </option>
              ))}
            </Select>
          </label>

          <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            Origen
            <Select
              value={sourceFilter}
              onChange={(e) => {
                const next = e.target.value as FeedbackSource | "";
                setSourceFilter(next);
                refresh({ source: next });
              }}
              className="h-9 text-[12px]"
            >
              <option value="">Todos</option>
              {SOURCE_ORDER.map((s) => (
                <option key={s} value={s}>
                  {s === "authenticated" ? "Interno" : "Público"}
                </option>
              ))}
            </Select>
          </label>

          <div className="ml-auto font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            {loading
              ? "Cargando…"
              : rows
                ? `${rows.length} de ${total}${
                    statusFilter || kindFilter || sourceFilter
                      ? " (filtrado)"
                      : ""
                  }`
                : "—"}
          </div>
        </div>

        {error ? (
          <div className="flex items-start gap-2 rounded-md border border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] px-4 py-3 text-[12px] text-[color:var(--status-error-text)]">
            <Warning className="mt-0.5 h-3.5 w-3.5" weight="fill" aria-hidden="true" />
            <span>{error}</span>
          </div>
        ) : null}

        {!loading && rows && rows.length === 0 ? (
          <EmptyState
            anyFilterActive={Boolean(statusFilter || kindFilter || sourceFilter)}
            onClearFilters={() => {
              setStatusFilter("");
              setKindFilter("");
              setSourceFilter("");
              refresh({ status: "", kind: "", source: "" });
            }}
          />
        ) : null}

        {rows && rows.length > 0 ? (
          <DataTable<AdminFeedbackReport>
            columns={columns}
            items={rows}
            rowKey={(row) => row.id}
            ariaLabel="Reportes de feedback"
          />
        ) : null}

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

      <FeedbackDetailDialog
        report={detail}
        loading={detailLoading}
        onClose={closeDetail}
        onSubmit={onStatusSubmit}
      />
    </PlatformShell>
  );
}

function EmptyState({
  anyFilterActive,
  onClearFilters,
}: {
  anyFilterActive: boolean;
  onClearFilters: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-[color:var(--border-subtle)] px-6 py-12 text-center">
      <ChatCenteredDots
        className="h-8 w-8 text-[color:var(--text-tertiary)]"
        weight="regular"
        aria-hidden="true"
      />
      <h3 className="text-[14px] font-semibold text-[color:var(--text-primary)]">
        {anyFilterActive
          ? "No hay reportes con estos filtros"
          : "Aún no hay reportes"}
      </h3>
      <p className="max-w-prose text-[12px] text-[color:var(--text-secondary)]">
        {anyFilterActive
          ? "Ajusta los filtros o vuelve a “Todos”."
          : "Cada vez que alguien use el botón Reportar (interno o en la landing), aparecerá aquí."}
      </p>
      {anyFilterActive ? (
        <Button variant="outline" size="sm" onClick={onClearFilters}>
          Quitar filtros
        </Button>
      ) : null}
    </div>
  );
}

function FeedbackDetailDialog({
  report,
  loading,
  onClose,
  onSubmit,
}: {
  report: AdminFeedbackReport | null;
  loading: boolean;
  onClose: () => void;
  onSubmit: (next: FeedbackStatus, resolutionNote: string) => Promise<void>;
}) {
  const [draftStatus, setDraftStatus] = useState<FeedbackStatus>("new");
  const [draftNote, setDraftNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (report) {
      setDraftStatus(report.status);
      setDraftNote(report.resolution_note ?? "");
    }
  }, [report]);

  const open = Boolean(report) || loading;
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !submitting) onClose();
      }}
    >
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {report?.kind === "bug" ? (
              <Bug
                className="h-4 w-4 text-[color:var(--status-warning-text)]"
                weight="bold"
                aria-hidden="true"
              />
            ) : (
              <Lightbulb
                className="h-4 w-4 text-[color:var(--text-teal)]"
                weight="bold"
                aria-hidden="true"
              />
            )}
            <span>
              {report?.kind === "bug" ? "Bug report" : "Sugerencia de mejora"}
            </span>
            {report?.is_public ? (
              <Badge variant="outline">Público</Badge>
            ) : (
              <Badge variant="info">Interno</Badge>
            )}
          </DialogTitle>
          <DialogDescription>
            {report ? (
              <>
                Recibido{" "}
                {new Date(report.created_at).toLocaleString("es-MX", {
                  dateStyle: "medium",
                  timeStyle: "short",
                })}{" "}
                · ID{" "}
                <span className="font-mono">{report.id.slice(0, 8)}…</span>
              </>
            ) : (
              "Cargando…"
            )}
          </DialogDescription>
        </DialogHeader>

        {report ? (
          <div className="flex flex-col gap-4">
            <section>
              <h4 className="mb-1.5 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                Descripción
              </h4>
              <p className="whitespace-pre-wrap text-[13px] leading-6 text-[color:var(--text-primary)]">
                {report.description}
              </p>
            </section>

            <dl className="grid grid-cols-1 gap-x-4 gap-y-2 text-[12px] sm:grid-cols-2">
              <DetailField label="De">
                {report.user_email ?? report.contact_email ?? "—"}
                {report.user_full_name ? ` · ${report.user_full_name}` : ""}
              </DetailField>
              <DetailField label="Roles">
                {report.user_roles ?? "—"}
              </DetailField>
              <DetailField label="Página">
                {report.url ? (
                  <a
                    href={report.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono text-[color:var(--text-link)] hover:underline"
                  >
                    {report.path ?? report.url}
                  </a>
                ) : (
                  <span className="font-mono">{report.path ?? "—"}</span>
                )}
              </DetailField>
              <DetailField label="Viewport · UA">
                <span className="font-mono">
                  {report.viewport ?? "—"} · {report.user_agent ?? "—"}
                </span>
              </DetailField>
              <DetailField label="IP hash">
                <span className="font-mono">{report.ip_hash ?? "—"}</span>
              </DetailField>
              <DetailField label="Slack">
                <span className="inline-flex items-center gap-2">
                  <Badge variant={SLACK_VARIANT[report.slack_delivery_status]}>
                    {SLACK_LABEL[report.slack_delivery_status]}
                  </Badge>
                  {report.slack_message_ts ? (
                    <span className="font-mono text-[10px] text-[color:var(--text-tertiary)]">
                      ts={report.slack_message_ts}
                    </span>
                  ) : null}
                </span>
              </DetailField>
              {report.slack_delivery_error ? (
                <DetailField label="Slack error" full>
                  <span className="font-mono text-[11px] text-[color:var(--status-warning-text)]">
                    {report.slack_delivery_error}
                  </span>
                </DetailField>
              ) : null}
            </dl>

            {report.screenshot_url ? (
              <section>
                <h4 className="mb-1.5 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  Captura
                  {report.screenshot_size_bytes ? (
                    <span className="ml-2 text-[color:var(--text-secondary)]">
                      ({Math.round(report.screenshot_size_bytes / 1024)} KB)
                    </span>
                  ) : null}
                </h4>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={report.screenshot_url}
                  alt="Captura adjunta al reporte"
                  className="max-h-[420px] w-full rounded-md border border-[color:var(--border-subtle)] object-contain"
                />
              </section>
            ) : report.screenshot_storage_key ? (
              <p className="text-[12px] text-[color:var(--text-tertiary)]">
                Captura almacenada en{" "}
                <span className="font-mono">{report.screenshot_storage_key}</span>{" "}
                — esta vista previa requiere un backend de almacenamiento con
                URLs presignadas (S3/R2).
              </p>
            ) : (
              <p className="text-[12px] text-[color:var(--text-tertiary)]">
                Sin captura adjunta.
              </p>
            )}

            {report.console_logs ? (
              <section>
                <h4 className="mb-1.5 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  Consola (últimos errores)
                </h4>
                <pre className="max-h-48 overflow-auto rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)] p-3 font-mono text-[11px] leading-5 text-[color:var(--text-secondary)]">
                  {report.console_logs}
                </pre>
              </section>
            ) : null}

            <section className="rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-3">
              <h4 className="mb-2 flex items-center gap-2 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                <Hourglass className="h-3 w-3" weight="bold" aria-hidden="true" />
                Triage
              </h4>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Field label="Nuevo estado" htmlFor="feedback-detail-status">
                  <Select
                    id="feedback-detail-status"
                    value={draftStatus}
                    onChange={(e) =>
                      setDraftStatus(e.target.value as FeedbackStatus)
                    }
                  >
                    {STATUS_ORDER.map((s) => (
                      <option key={s} value={s}>
                        {STATUS_LABEL[s]}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field
                  label="Nota (opcional)"
                  htmlFor="feedback-detail-note"
                  helper="Visible para todo el equipo en el triage."
                >
                  <Textarea
                    id="feedback-detail-note"
                    rows={2}
                    value={draftNote}
                    onChange={(e) => setDraftNote(e.target.value)}
                    maxLength={4000}
                  />
                </Field>
              </div>
              {report.triaged_at ? (
                <p className="mt-2 font-mono text-[10px] text-[color:var(--text-tertiary)]">
                  Triaged{" "}
                  {new Date(report.triaged_at).toLocaleString("es-MX", {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })}{" "}
                  · por <span>{report.triaged_by_user_id?.slice(0, 8)}…</span>
                </p>
              ) : null}
            </section>
          </div>
        ) : (
          <div className="py-12 text-center text-[12px] text-[color:var(--text-tertiary)]">
            Cargando reporte…
          </div>
        )}

        <DialogFooter>
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            disabled={submitting}
          >
            Cerrar
          </Button>
          <Button
            type="button"
            loading={submitting}
            disabled={!report || submitting}
            onClick={async () => {
              setSubmitting(true);
              try {
                await onSubmit(draftStatus, draftNote);
              } finally {
                setSubmitting(false);
              }
            }}
          >
            {draftStatus === "resolved" ? (
              <CheckCircle
                className="h-3.5 w-3.5"
                weight="bold"
                aria-hidden="true"
              />
            ) : draftStatus === "wont_fix" ? (
              <Prohibit
                className="h-3.5 w-3.5"
                weight="bold"
                aria-hidden="true"
              />
            ) : null}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DetailField({
  label,
  children,
  full = false,
}: {
  label: string;
  children: React.ReactNode;
  full?: boolean;
}) {
  return (
    <div className={full ? "sm:col-span-2" : undefined}>
      <dt className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        {label}
      </dt>
      <dd className="text-[12px] text-[color:var(--text-primary)]">{children}</dd>
    </div>
  );
}
