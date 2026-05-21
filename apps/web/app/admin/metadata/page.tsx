"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowsClockwise,
  CheckCircle,
  DownloadSimple,
  Eye,
  FileXls,
  Warning,
} from "@phosphor-icons/react";

import { AdminShell } from "../_shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  EmptyState,
  ErrorState,
  Skeleton,
} from "@/components/checkwise/portal/state-surfaces";
import {
  downloadMetadataExport,
  getMetadataExportPreview,
  listMetadataExports,
  type MetadataExportItem,
  type MetadataExportPreview,
} from "@/lib/api/admin";
import { cn } from "@/lib/utils";

type ResultFilter = "all" | "completed" | "skipped" | "failed";

const RESULT_FILTERS: { value: ResultFilter; label: string }[] = [
  { value: "all", label: "Todos" },
  { value: "completed", label: "Listos" },
  { value: "skipped", label: "Sin mapping" },
  { value: "failed", label: "Fallidos" },
];

export default function AdminMetadataExportsPage() {
  const [items, setItems] = useState<MetadataExportItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [preview, setPreview] = useState<MetadataExportPreview | null>(null);
  const [filter, setFilter] = useState<ResultFilter>("all");
  const [activeSheetIndex, setActiveSheetIndex] = useState(0);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
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
        const currentStillVisible = payload.items.some((item) => item.id === selectedId);
        const nextSelected =
          currentStillVisible
            ? selectedId
            : payload.items.find((item) => item.preview_available)?.id ??
              payload.items[0]?.id ??
              null;
        setSelectedId(nextSelected);
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
  }, [filter, reloadKey, selectedId]);

  useEffect(() => {
    if (!selectedId) {
      setPreview(null);
      return;
    }
    const selected = items.find((item) => item.id === selectedId);
    if (!selected?.preview_available) {
      setPreview(null);
      setPreviewError(selected?.reason ?? "Este export todavía no tiene XLSX para previsualizar.");
      return;
    }
    let cancelled = false;
    setLoadingPreview(true);
    setPreviewError(null);
    setActiveSheetIndex(0);
    getMetadataExportPreview(selectedId)
      .then((payload) => {
        if (!cancelled) setPreview(payload);
      })
      .catch(() => {
        if (!cancelled) setPreviewError("No pudimos abrir el preview del XLSX.");
      })
      .finally(() => {
        if (!cancelled) setLoadingPreview(false);
      });
    return () => {
      cancelled = true;
    };
  }, [items, selectedId]);

  const selectedItem = useMemo(
    () => items.find((item) => item.id === selectedId) ?? null,
    [items, selectedId],
  );

  const activeSheet = preview?.sheets[activeSheetIndex] ?? preview?.sheets[0] ?? null;

  const retry = useCallback(() => setReloadKey((key) => key + 1), []);

  async function onDownload(item: MetadataExportItem) {
    if (!item.preview_available) return;
    setDownloadingId(item.id);
    try {
      const blob = await downloadMetadataExport(item.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filenameFor(item);
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } finally {
      setDownloadingId(null);
    }
  }

  return (
    <AdminShell
      title="Metadata documental"
      description="Exports XLSX generados automáticamente cuando los proveedores suben documentos. Revisa, previsualiza y descarga el archivo que LegalShelf puede compartir."
      actions={
        <Button type="button" variant="outline" size="sm" onClick={retry}>
          <ArrowsClockwise className="h-3.5 w-3.5" weight="bold" aria-hidden />
          Actualizar
        </Button>
      }
    >
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.05fr)_minmax(420px,0.95fr)]">
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
                  onClick={() => setFilter(item.value)}
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

          {loadingList ? (
            <div className="space-y-3 p-5">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-28 w-full" />
              <Skeleton className="h-28 w-full" />
            </div>
          ) : error ? (
            <div className="p-5">
              <ErrorState
                title="No pudimos cargar metadata"
                description={error}
                onRetry={retry}
              />
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
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[128px]">Estado</TableHead>
                  <TableHead>Documento</TableHead>
                  <TableHead>Cliente · proveedor</TableHead>
                  <TableHead className="w-[124px]">Periodo</TableHead>
                  <TableHead className="w-[104px]">Acción</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow
                    key={item.id}
                    onClick={() => setSelectedId(item.id)}
                    className={cn(
                      "cursor-pointer",
                      selectedId === item.id && "bg-[color:var(--surface-selected)]",
                    )}
                  >
                    <TableCell>
                      <ExportStatusBadge item={item} />
                    </TableCell>
                    <TableCell>
                      <div className="min-w-0 space-y-1">
                        <p className="truncate font-medium">
                          {item.requirement_name ?? item.document_type_code ?? "Metadata export"}
                        </p>
                        <p className="truncate font-mono text-[11px] text-[color:var(--text-tertiary)]">
                          {item.original_filename ?? item.latest_path ?? item.id}
                        </p>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="min-w-0 space-y-1">
                        <p className="truncate">{item.client_name ?? "Cliente sin nombre"}</p>
                        <p className="truncate text-[12px] text-[color:var(--text-secondary)]">
                          {item.vendor_name ?? "Proveedor sin nombre"}
                        </p>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="font-mono text-[12px]">
                        {item.period_key ?? "alta"}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          aria-label="Previsualizar metadata"
                          onClick={(event) => {
                            event.stopPropagation();
                            setSelectedId(item.id);
                          }}
                        >
                          <Eye className="h-4 w-4" weight="bold" aria-hidden />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          aria-label="Descargar XLSX"
                          disabled={!item.preview_available}
                          loading={downloadingId === item.id}
                          onClick={(event) => {
                            event.stopPropagation();
                            void onDownload(item);
                          }}
                        >
                          <DownloadSimple className="h-4 w-4" weight="bold" aria-hidden />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </section>

        <section className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs">
          <header className="border-b border-[color:var(--border-subtle)] px-5 py-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="cw-eyebrow">Preview XLSX</p>
                <h2 className="truncate text-base font-semibold text-[color:var(--text-primary)]">
                  {selectedItem?.requirement_name ??
                    selectedItem?.document_type_code ??
                    "Selecciona un export"}
                </h2>
              </div>
              {selectedItem ? <ExportStatusBadge item={selectedItem} /> : null}
            </div>
            {selectedItem?.latest_path ? (
              <p className="mt-2 truncate font-mono text-[11px] text-[color:var(--text-tertiary)]">
                {selectedItem.latest_path}
              </p>
            ) : null}
          </header>

          {!selectedItem ? (
            <div className="p-8">
              <EmptyState
                icon={FileXls}
                title="Selecciona un workbook"
                description="Aquí verás las pestañas del archivo generado para LegalShelf."
                variant="muted"
              />
            </div>
          ) : loadingPreview ? (
            <div className="space-y-3 p-5">
              <Skeleton className="h-9 w-72" />
              <Skeleton className="h-80 w-full" />
            </div>
          ) : previewError ? (
            <div className="p-5">
              <ErrorState
                title="Preview no disponible"
                description={previewError}
                onRetry={selectedItem.preview_available ? retry : undefined}
              />
            </div>
          ) : activeSheet ? (
            <div className="space-y-4 p-5">
              <div className="flex flex-wrap gap-1">
                {preview?.sheets.map((sheet, index) => (
                  <button
                    key={sheet.name}
                    type="button"
                    onClick={() => setActiveSheetIndex(index)}
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
              <div className="max-h-[560px] overflow-auto rounded-md border border-[color:var(--border-subtle)]">
                <table className="w-full border-collapse text-left text-[12px]">
                  <tbody>
                    {activeSheet.rows.map((row, rowIndex) => (
                      <tr
                        key={`${activeSheet.name}-${rowIndex}`}
                        className={cn(
                          "border-b border-[color:var(--border-subtle)]",
                          rowIndex === 0
                            ? "bg-[color:var(--surface-sunken)] font-semibold"
                            : "bg-[color:var(--surface-raised)]",
                        )}
                      >
                        {Array.from({ length: Math.max(row.length, 1) }).map((_, colIndex) => (
                          <td
                            key={colIndex}
                            className="min-w-28 max-w-80 px-3 py-2 align-top text-[color:var(--text-primary)]"
                          >
                            {row[colIndex] || ""}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
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
        </section>
      </div>
    </AdminShell>
  );
}

function ExportStatusBadge({ item }: { item: MetadataExportItem }) {
  if (item.result === "completed" && item.file_exists) {
    return (
      <Badge variant="outline" className="border-emerald-200 bg-emerald-50 text-emerald-800">
        <CheckCircle className="h-3.5 w-3.5" weight="fill" aria-hidden />
        Listo
      </Badge>
    );
  }
  if (item.result === "failed") {
    return (
      <Badge variant="outline" className="border-red-200 bg-red-50 text-red-800">
        <Warning className="h-3.5 w-3.5" weight="fill" aria-hidden />
        Falló
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-900">
      <Warning className="h-3.5 w-3.5" weight="fill" aria-hidden />
      Revisar
    </Badge>
  );
}

function filenameFor(item: MetadataExportItem) {
  const fromPath = item.latest_path?.split("/").at(-1);
  return fromPath || `${item.document_type_code ?? "metadata"}_${item.id}.xlsx`;
}
