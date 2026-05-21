"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowsClockwise,
  CheckCircle,
  DownloadSimple,
  FileXls,
  Files,
  Warning,
} from "@phosphor-icons/react";

import { AdminShell } from "../_shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  EmptyState,
  ErrorState,
  Skeleton,
} from "@/components/checkwise/portal/state-surfaces";
import {
  downloadClientMasterMetadata,
  downloadMetadataExport,
  getClientMasterMetadataPreview,
  getMetadataExportPreview,
  listMetadataExports,
  type ClientMasterMetadataPreview,
  type MetadataExportItem,
  type MetadataExportPreview,
  type MetadataExportSheetPreview,
} from "@/lib/api/admin";
import { cn } from "@/lib/utils";

type ResultFilter = "all" | "completed" | "skipped" | "failed";
type DetailMode = "document" | "master";

const RESULT_FILTERS: { value: ResultFilter; label: string }[] = [
  { value: "all", label: "Todos" },
  { value: "completed", label: "Listos" },
  { value: "skipped", label: "Sin mapping" },
  { value: "failed", label: "Fallidos" },
];

export default function AdminMetadataExportsPage() {
  const [items, setItems] = useState<MetadataExportItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailMode, setDetailMode] = useState<DetailMode | null>(null);
  const [documentPreview, setDocumentPreview] = useState<MetadataExportPreview | null>(null);
  const [masterPreview, setMasterPreview] = useState<ClientMasterMetadataPreview | null>(null);
  const [filter, setFilter] = useState<ResultFilter>("all");
  const [activeSheetIndex, setActiveSheetIndex] = useState(0);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [downloadingKey, setDownloadingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoadingList(true);
    setError(null);
    listMetadataExports({
      result: filter === "all" ? undefined : filter,
      limit: 100,
    })
      .then((payload) => {
        if (cancelled) return;
        setItems(payload.items);
        setSelectedId((current) =>
          current && payload.items.some((item) => item.id === current)
            ? current
            : payload.items[0]?.id ?? null,
        );
      })
      .catch(() => {
        if (!cancelled) setError("No pudimos cargar los exports de metadata.");
      })
      .finally(() => {
        if (!cancelled) setLoadingList(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filter, reloadKey]);

  const selectedItem = useMemo(
    () => items.find((item) => item.id === selectedId) ?? null,
    [items, selectedId],
  );

  useEffect(() => {
    if (!detailMode || !selectedItem) return;
    let cancelled = false;
    setLoadingPreview(true);
    setPreviewError(null);
    setActiveSheetIndex(0);
    setDocumentPreview(null);
    setMasterPreview(null);

    const request =
      detailMode === "master"
        ? selectedItem.client_id && selectedItem.master_available
          ? getClientMasterMetadataPreview(selectedItem.client_id)
          : Promise.reject(new Error("master-unavailable"))
        : selectedItem.preview_available
          ? getMetadataExportPreview(selectedItem.id)
          : Promise.reject(new Error("document-unavailable"));

    request
      .then((payload) => {
        if (cancelled) return;
        if (detailMode === "master") {
          setMasterPreview(payload as ClientMasterMetadataPreview);
        } else {
          setDocumentPreview(payload as MetadataExportPreview);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPreviewError(
            detailMode === "master"
              ? "No pudimos abrir el master de este cliente."
              : "No pudimos abrir el metadata de este documento.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingPreview(false);
      });

    return () => {
      cancelled = true;
    };
  }, [detailMode, selectedItem]);

  const retry = useCallback(() => setReloadKey((key) => key + 1), []);

  const sheets =
    detailMode === "master" ? masterPreview?.sheets : documentPreview?.sheets;
  const activeSheet = sheets?.[activeSheetIndex] ?? sheets?.[0] ?? null;

  async function onDownloadDocument(item: MetadataExportItem) {
    if (!item.preview_available) return;
    setDownloadingKey(`doc:${item.id}`);
    try {
      const blob = await downloadMetadataExport(item.id);
      downloadBlob(blob, filenameForDocument(item));
    } finally {
      setDownloadingKey(null);
    }
  }

  async function onDownloadMaster(item: MetadataExportItem) {
    if (!item.client_id || !item.master_available) return;
    setDownloadingKey(`master:${item.client_id}`);
    try {
      const blob = await downloadClientMasterMetadata(item.client_id);
      downloadBlob(blob, filenameForMaster(item));
    } finally {
      setDownloadingKey(null);
    }
  }

  return (
    <AdminShell
      title="Metadata documental"
      description="Exports automáticos de metadata por documento y master consolidado por cliente."
      actions={
        <Button type="button" variant="outline" size="sm" onClick={retry}>
          <ArrowsClockwise className="h-3.5 w-3.5" weight="bold" aria-hidden />
          Actualizar
        </Button>
      }
    >
      {detailMode && selectedItem ? (
        <MetadataDetail
          item={selectedItem}
          mode={detailMode}
          sheets={sheets ?? []}
          activeSheet={activeSheet}
          activeSheetIndex={activeSheetIndex}
          loading={loadingPreview}
          error={previewError}
          onBack={() => setDetailMode(null)}
          onSheetChange={setActiveSheetIndex}
          onDownload={() =>
            detailMode === "master"
              ? void onDownloadMaster(selectedItem)
              : void onDownloadDocument(selectedItem)
          }
          downloading={
            downloadingKey ===
            (detailMode === "master"
              ? `master:${selectedItem.client_id}`
              : `doc:${selectedItem.id}`)
          }
        />
      ) : (
        <MetadataList
          items={items}
          filter={filter}
          selectedId={selectedId}
          loading={loadingList}
          error={error}
          downloadingKey={downloadingKey}
          onFilterChange={setFilter}
          onSelect={setSelectedId}
          onRetry={retry}
          onOpenDocument={(item) => {
            setSelectedId(item.id);
            setDetailMode("document");
          }}
          onOpenMaster={(item) => {
            setSelectedId(item.id);
            setDetailMode("master");
          }}
          onDownloadDocument={(item) => void onDownloadDocument(item)}
          onDownloadMaster={(item) => void onDownloadMaster(item)}
        />
      )}
    </AdminShell>
  );
}

function MetadataList({
  items,
  filter,
  selectedId,
  loading,
  error,
  downloadingKey,
  onFilterChange,
  onSelect,
  onRetry,
  onOpenDocument,
  onOpenMaster,
  onDownloadDocument,
  onDownloadMaster,
}: {
  items: MetadataExportItem[];
  filter: ResultFilter;
  selectedId: string | null;
  loading: boolean;
  error: string | null;
  downloadingKey: string | null;
  onFilterChange: (filter: ResultFilter) => void;
  onSelect: (id: string) => void;
  onRetry: () => void;
  onOpenDocument: (item: MetadataExportItem) => void;
  onOpenMaster: (item: MetadataExportItem) => void;
  onDownloadDocument: (item: MetadataExportItem) => void;
  onDownloadMaster: (item: MetadataExportItem) => void;
}) {
  return (
    <section className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[color:var(--border-subtle)] px-5 py-3">
        <div>
          <p className="cw-eyebrow">Archivos generados</p>
          <h2 className="text-base font-semibold text-[color:var(--text-primary)]">
            Últimos uploads
          </h2>
        </div>
        <div className="flex flex-wrap gap-1">
          {RESULT_FILTERS.map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => onFilterChange(item.value)}
              className={cn(
                "rounded-md border px-2.5 py-1.5 text-[12px] font-medium transition-colors",
                filter === item.value
                  ? "border-[color:var(--border-brand)] bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]"
                  : "border-[color:var(--border-subtle)] text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)]",
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
      </header>

      {loading ? (
        <div className="space-y-3 p-5">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      ) : error ? (
        <div className="p-5">
          <ErrorState title="No pudimos cargar metadata" description={error} onRetry={onRetry} />
        </div>
      ) : items.length === 0 ? (
        <div className="p-8">
          <EmptyState
            icon={FileXls}
            title="Todavía no hay exports"
            description="Cuando un proveedor cargue un documento con mapping de metadata, el XLSX aparecerá aquí automáticamente."
            variant="muted"
          />
        </div>
      ) : (
        <div className="divide-y divide-[color:var(--border-subtle)]">
          {items.map((item) => (
            <article
              key={item.id}
              className={cn(
                "grid gap-4 px-5 py-4 transition-colors lg:grid-cols-[160px_minmax(0,1fr)_auto]",
                selectedId === item.id
                  ? "bg-[color:var(--surface-selected)]"
                  : "hover:bg-[color:var(--surface-hover)]",
              )}
              onMouseEnter={() => onSelect(item.id)}
            >
              <div>
                <ExportStatusBadge item={item} />
                <p className="mt-2 font-mono text-[11px] text-[color:var(--text-tertiary)]">
                  {formatDate(item.created_at)}
                </p>
              </div>
              <div className="min-w-0 space-y-2">
                <div>
                  <h3 className="truncate text-[15px] font-semibold text-[color:var(--text-primary)]">
                    {item.requirement_name ?? item.document_type_code ?? "Metadata export"}
                  </h3>
                  <p className="truncate font-mono text-[11px] text-[color:var(--text-tertiary)]">
                    {item.original_filename ?? item.latest_path ?? item.id}
                  </p>
                </div>
                <div className="grid gap-2 text-[12px] text-[color:var(--text-secondary)] sm:grid-cols-3">
                  <Field label="Cliente" value={item.client_name ?? "—"} />
                  <Field label="Proveedor" value={item.vendor_name ?? "—"} />
                  <Field label="Periodo" value={item.period_key ?? "alta"} mono />
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2 lg:justify-end">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!item.preview_available}
                  onClick={() => onOpenDocument(item)}
                >
                  <FileXls className="h-3.5 w-3.5" weight="bold" aria-hidden />
                  Ver metadata
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!item.master_available}
                  onClick={() => onOpenMaster(item)}
                >
                  <Files className="h-3.5 w-3.5" weight="bold" aria-hidden />
                  Master cliente
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label="Descargar XLSX del documento"
                  disabled={!item.preview_available}
                  loading={downloadingKey === `doc:${item.id}`}
                  onClick={() => onDownloadDocument(item)}
                >
                  <DownloadSimple className="h-4 w-4" weight="bold" aria-hidden />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label="Descargar master del cliente"
                  disabled={!item.master_available}
                  loading={downloadingKey === `master:${item.client_id}`}
                  onClick={() => onDownloadMaster(item)}
                >
                  <Files className="h-4 w-4" weight="bold" aria-hidden />
                </Button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function MetadataDetail({
  item,
  mode,
  sheets,
  activeSheet,
  activeSheetIndex,
  loading,
  error,
  downloading,
  onBack,
  onSheetChange,
  onDownload,
}: {
  item: MetadataExportItem;
  mode: DetailMode;
  sheets: MetadataExportSheetPreview[];
  activeSheet: MetadataExportSheetPreview | null;
  activeSheetIndex: number;
  loading: boolean;
  error: string | null;
  downloading: boolean;
  onBack: () => void;
  onSheetChange: (index: number) => void;
  onDownload: () => void;
}) {
  const title =
    mode === "master"
      ? `Master metadata · ${item.client_name ?? "Cliente"}`
      : item.requirement_name ?? item.document_type_code ?? "Metadata del documento";
  const path = mode === "master" ? item.master_path : item.latest_path;
  return (
    <section className="space-y-4">
      <div className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-5 py-4 shadow-xs">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-2">
            <Button type="button" variant="ghost" size="sm" onClick={onBack}>
              <ArrowLeft className="h-3.5 w-3.5" weight="bold" aria-hidden />
              Volver
            </Button>
            <div>
              <p className="cw-eyebrow">{mode === "master" ? "Master cliente" : "Documento"}</p>
              <h2 className="truncate text-xl font-semibold text-[color:var(--text-primary)]">
                {title}
              </h2>
              {path ? (
                <p className="mt-1 truncate font-mono text-[11px] text-[color:var(--text-tertiary)]">
                  {path}
                </p>
              ) : null}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <ExportStatusBadge item={item} />
            <Button type="button" variant="outline" size="sm" loading={downloading} onClick={onDownload}>
              <DownloadSimple className="h-3.5 w-3.5" weight="bold" aria-hidden />
              Descargar XLSX
            </Button>
          </div>
        </div>
        <div className="mt-4 grid gap-2 text-[12px] text-[color:var(--text-secondary)] sm:grid-cols-4">
          <Field label="Cliente" value={item.client_name ?? "—"} />
          <Field label="Proveedor" value={mode === "master" ? "Todos" : item.vendor_name ?? "—"} />
          <Field label="Periodo" value={mode === "master" ? "Consolidado" : item.period_key ?? "alta"} mono />
          <Field label="Archivo" value={mode === "master" ? "client_master_metadata.xlsx" : item.original_filename ?? "—"} />
        </div>
      </div>

      <div className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs">
        {loading ? (
          <div className="space-y-3 p-5">
            <Skeleton className="h-9 w-72" />
            <Skeleton className="h-[520px] w-full" />
          </div>
        ) : error ? (
          <div className="p-5">
            <ErrorState title="Preview no disponible" description={error} />
          </div>
        ) : activeSheet ? (
          <>
            <div className="flex flex-wrap gap-1 border-b border-[color:var(--border-subtle)] px-5 py-3">
              {sheets.map((sheet, index) => (
                <button
                  key={sheet.name}
                  type="button"
                  onClick={() => onSheetChange(index)}
                  className={cn(
                    "rounded-md border px-2.5 py-1.5 text-[12px] font-medium transition-colors",
                    activeSheetIndex === index
                      ? "border-[color:var(--border-brand)] bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]"
                      : "border-[color:var(--border-subtle)] text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)]",
                  )}
                >
                  {sheet.name}
                </button>
              ))}
            </div>
            <SheetPreviewTable sheet={activeSheet} />
          </>
        ) : (
          <div className="p-8">
            <EmptyState
              icon={FileXls}
              title="Workbook sin filas"
              description="El archivo existe, pero no devolvió filas para previsualizar."
              variant="muted"
            />
          </div>
        )}
      </div>
    </section>
  );
}

function SheetPreviewTable({ sheet }: { sheet: MetadataExportSheetPreview }) {
  const columnCount = Math.max(...sheet.rows.map((row) => row.length), 1);
  return (
    <div className="max-h-[70vh] overflow-auto">
      <table className="w-full border-collapse text-left text-[12px]">
        <tbody>
          {sheet.rows.map((row, rowIndex) => (
            <tr
              key={`${sheet.name}-${rowIndex}`}
              className={cn(
                "border-b border-[color:var(--border-subtle)]",
                rowIndex === 0
                  ? "sticky top-0 z-10 bg-[color:var(--surface-sunken)] font-semibold"
                  : "bg-[color:var(--surface-raised)]",
              )}
            >
              {Array.from({ length: columnCount }).map((_, colIndex) => (
                <td
                  key={colIndex}
                  className="min-w-36 max-w-[420px] px-3 py-2 align-top text-[color:var(--text-primary)]"
                >
                  {row[colIndex] || ""}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ExportStatusBadge({ item }: { item: MetadataExportItem }) {
  if (item.result === "completed" && item.file_exists) {
    return (
      <Badge variant="success">
        <CheckCircle className="h-3.5 w-3.5" weight="fill" aria-hidden />
        Listo
      </Badge>
    );
  }
  if (item.result === "failed") {
    return (
      <Badge variant="destructive">
        <Warning className="h-3.5 w-3.5" weight="fill" aria-hidden />
        Falló
      </Badge>
    );
  }
  return (
    <Badge variant="warning">
      <Warning className="h-3.5 w-3.5" weight="fill" aria-hidden />
      Revisar
    </Badge>
  );
}

function Field({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0 rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)]/40 px-3 py-2">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-[color:var(--text-tertiary)]">
        {label}
      </p>
      <p className={cn("truncate text-[12px] text-[color:var(--text-primary)]", mono && "font-mono")}>
        {value}
      </p>
    </div>
  );
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function filenameForDocument(item: MetadataExportItem) {
  const fromPath = item.latest_path?.split("/").at(-1);
  return fromPath || `${item.document_type_code ?? "metadata"}_${item.id}.xlsx`;
}

function filenameForMaster(item: MetadataExportItem) {
  const client = (item.client_name ?? "client").replace(/[^a-z0-9]+/gi, "_").toLowerCase();
  return `${client}_metadata_master.xlsx`;
}

function formatDate(value: string) {
  try {
    return new Intl.DateTimeFormat("es-MX", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return value;
  }
}
