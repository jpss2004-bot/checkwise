"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  DownloadSimple,
  Info,
  Package,
  Sparkle,
} from "@phosphor-icons/react";

import { ClientShell } from "../_shell";
import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { PeriodPicker } from "@/components/checkwise/period-picker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  CaretDown,
  CaretRight,
} from "@phosphor-icons/react";
import {
  clientAuditPackageZipUrl,
  downloadClientAuditPackageZipPost,
  getClientAuditPackagePreview,
  getClientAuditPackageTree,
  listClientVendors,
  type AuditPackageFilters,
  type AuditPackagePreview,
  type AuditPackageTreeNode,
  type AuditPackageTreeResponse,
  type ClientVendorListResponse,
} from "@/lib/api/client";
import { downloadAuthenticatedFile, saveBlob } from "@/lib/api/download";
import { INSTITUTION_LABELS } from "@/lib/api/portal";
import { useUrlClientId } from "@/lib/workspace/use-url-client-id";

/**
 * /client/auditoria
 *
 * Junta 2026-05-23 — when an inspector arrives at the client's
 * office, the client_admin needs to deliver a single ZIP scoped to
 * exactly what the inspector asked for. The page composes the
 * filter set, shows a live preview of the resulting package, and
 * issues the download as a top-level navigation against
 * ``GET /api/v1/client/audit-package.zip``.
 *
 * Defaults:
 * - statuses = ["aprobado"] (auditors want legally compliant
 *   evidence; "en revisión" / "rechazado" only ship when the
 *   client_admin explicitly opts in via the avanzado toggle).
 * - vendor_ids = empty (all providers in the portfolio).
 * - period range = current calendar year by default.
 */

const INSTITUTION_OPTIONS = ["sat", "imss", "infonavit", "stps_repse"] as const;

const STATUS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "aprobado", label: "Aprobado" },
  { value: "pendiente_revision", label: "En revisión humana" },
  { value: "rechazado", label: "Requiere corrección" },
  { value: "requiere_aclaracion", label: "Necesita aclaración" },
  { value: "excepcion_legal", label: "Excepción legal" },
];

// One-click preset → resolves to a period_from / period_to range
// using canonical period_key strings (YYYY-Mxx for months).
type PresetKey = "current-month" | "last-quarter" | "ytd" | "last-fiscal-year";

const PRESET_LABELS: Record<PresetKey, string> = {
  "current-month": "Este mes",
  "last-quarter": "Último trimestre",
  ytd: "Año en curso",
  "last-fiscal-year": "Último año fiscal",
};

function resolvePreset(key: PresetKey, today: Date): { from: string; to: string } {
  const y = today.getFullYear();
  const m = today.getMonth() + 1; // 1..12
  const fmt = (yy: number, mm: number) =>
    `${yy}-M${String(mm).padStart(2, "0")}`;
  switch (key) {
    case "current-month":
      return { from: fmt(y, m), to: fmt(y, m) };
    case "last-quarter": {
      // Three full months ending last month.
      const endM = m === 1 ? 12 : m - 1;
      const endY = m === 1 ? y - 1 : y;
      const startMRaw = endM - 2;
      const startY = startMRaw <= 0 ? endY - 1 : endY;
      const startM = ((startMRaw - 1 + 12) % 12) + 1;
      return { from: fmt(startY, startM), to: fmt(endY, endM) };
    }
    case "ytd":
      return { from: fmt(y, 1), to: fmt(y, m) };
    case "last-fiscal-year":
      return { from: fmt(y - 1, 1), to: fmt(y - 1, 12) };
  }
}

export default function ClientAuditoriaPage() {
  const urlClientId = useUrlClientId();
  const today = useMemo(() => new Date(), []);

  // Default range: Year-to-date so the live counter shows something
  // useful on first load without forcing the user to think.
  const ytd = useMemo(() => resolvePreset("ytd", today), [today]);

  const [periodFrom, setPeriodFrom] = useState<string>(ytd.from);
  const [periodTo, setPeriodTo] = useState<string>(ytd.to);
  const [institutions, setInstitutions] = useState<string[]>([]);
  const [vendorIds, setVendorIds] = useState<string[]>([]);
  const [statuses, setStatuses] = useState<string[]>(["aprobado"]);
  const [advancedStatusOpen, setAdvancedStatusOpen] = useState(false);

  const [vendorsList, setVendorsList] =
    useState<ClientVendorListResponse | null>(null);
  const [preview, setPreview] = useState<AuditPackagePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // Item 2 — tree picker state. ``tree`` is the candidate set the
  // filters resolved to; ``selectedIds`` is the user's whitelist. A
  // null whitelist means "ship everything in the tree" (legacy filter
  // mode); an empty Set means "user explicitly deselected
  // everything"; otherwise we POST the explicit subset.
  const [tree, setTree] = useState<AuditPackageTreeResponse | null>(null);
  const [treeLoading, setTreeLoading] = useState(false);
  const [treeError, setTreeError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string> | null>(null);
  // Ephemeral notice shown when a filter change discards a manual
  // selection, so the reset doesn't read as silent data loss (audit F7).
  const [selectionCleared, setSelectionCleared] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // Vendor catalog — fetched once, used for the multi-select chips
  // and to map vendor_id → vendor_name on the preview breakdown.
  useEffect(() => {
    let cancelled = false;
    listClientVendors(urlClientId ? { client_id: urlClientId } : undefined)
      .then((data) => {
        if (cancelled) return;
        setVendorsList(data);
      })
      .catch(() => {
        if (cancelled) return;
        // Silent fallback — the page is still usable without the
        // vendor list (defaults to all-vendors).
        setVendorsList({ items: [], total: 0, summary: null } as never);
      });
    return () => {
      cancelled = true;
    };
  }, [urlClientId]);

  // Live preview + tree fetch — refetch whenever any filter changes.
  // ``selectedIds`` is reset to null (= "all in tree") on every
  // re-fetch so a stale whitelist from the previous filter set never
  // leaks into the next composition.
  useEffect(() => {
    let cancelled = false;
    setPreviewLoading(true);
    setPreviewError(null);
    setTreeLoading(true);
    setTreeError(null);
    const filters: AuditPackageFilters = {
      client_id: urlClientId,
      period_from: periodFrom || null,
      period_to: periodTo || null,
      institutions,
      statuses,
      vendor_ids: vendorIds,
    };
    getClientAuditPackagePreview(filters)
      .then((data) => {
        if (cancelled) return;
        setPreview(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setPreviewError(
          err instanceof Error
            ? err.message
            : "No pudimos calcular el paquete con esos filtros.",
        );
      })
      .finally(() => {
        if (!cancelled) setPreviewLoading(false);
      });
    getClientAuditPackageTree(filters)
      .then((data) => {
        if (cancelled) return;
        setTree(data);
        setSelectedIds((prev) => {
          // Only notify when the user had actually narrowed the set; a
          // reset from the default "all" is invisible and needs no notice.
          if (prev !== null) setSelectionCleared(true);
          return null;
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setTreeError(
          err instanceof Error
            ? err.message
            : "No pudimos cargar la lista de documentos.",
        );
        setTree(null);
      })
      .finally(() => {
        if (!cancelled) setTreeLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [periodFrom, periodTo, institutions, vendorIds, statuses, urlClientId]);

  // Auto-dismiss the "selection reset" notice after a few seconds.
  useEffect(() => {
    if (!selectionCleared) return;
    const t = window.setTimeout(() => setSelectionCleared(false), 6000);
    return () => window.clearTimeout(t);
  }, [selectionCleared]);

  // Filter-only fallback URL (GET) used when the user has NOT tweaked
  // the per-document selection. Both paths fetch with the Bearer
  // header — a top-level navigation cannot carry the staff JWT and
  // the endpoint has no cookie fallback (audit 2026-06-12).
  const downloadUrl = clientAuditPackageZipUrl({
    client_id: urlClientId,
    period_from: periodFrom || null,
    period_to: periodTo || null,
    institutions,
    statuses,
    vendor_ids: vendorIds,
  });

  // Effective selection: when the user has touched the tree, use the
  // explicit Set; otherwise treat "no selection state" as "all from
  // the tree".
  const treeAllIds = useMemo(
    () => new Set((tree?.items ?? []).map((i) => i.submission_id)),
    [tree],
  );
  const effectiveSelection: Set<string> = selectedIds ?? treeAllIds;
  const selectionCount = effectiveSelection.size;
  // Bytes only for the selected subset so the cap message is honest.
  const selectionBytes = useMemo(() => {
    if (!tree) return 0;
    let total = 0;
    for (const item of tree.items) {
      if (effectiveSelection.has(item.submission_id)) total += item.size_bytes;
    }
    return total;
  }, [tree, effectiveSelection]);
  const overFileCap = tree ? selectionCount > tree.file_cap : false;
  const overBytesCap = tree ? selectionBytes > tree.bytes_cap : false;

  const downloadDisabled =
    previewLoading ||
    treeLoading ||
    downloading ||
    selectionCount === 0 ||
    overFileCap ||
    overBytesCap;

  async function onDownloadClick() {
    if (downloadDisabled || !tree) return;
    // If the user did not touch the tree, fall back to the legacy
    // filter-only GET so bookmarks and old behaviour stay live.
    const everythingSelected =
      selectedIds === null ||
      (selectedIds.size === treeAllIds.size &&
        Array.from(treeAllIds).every((id) => selectedIds.has(id)));
    setDownloading(true);
    setDownloadError(null);
    try {
      if (everythingSelected) {
        await downloadAuthenticatedFile(downloadUrl, "auditoria.zip");
      } else {
        const { blob, filename } = await downloadClientAuditPackageZipPost({
          client_id: urlClientId,
          period_from: periodFrom || null,
          period_to: periodTo || null,
          institutions,
          statuses,
          vendor_ids: vendorIds,
          submission_ids: Array.from(effectiveSelection),
        });
        saveBlob(blob, filename);
      }
    } catch (err) {
      setDownloadError(
        err instanceof Error
          ? err.message
          : "No pudimos preparar la descarga.",
      );
    } finally {
      setDownloading(false);
    }
  }

  function toggleInst(code: string) {
    setInstitutions((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code],
    );
  }
  function toggleVendor(id: string) {
    setVendorIds((prev) =>
      prev.includes(id) ? prev.filter((v) => v !== id) : [...prev, id],
    );
  }
  function toggleStatus(value: string) {
    setStatuses((prev) =>
      prev.includes(value)
        ? prev.filter((s) => s !== value)
        : [...prev, value],
    );
  }
  function applyPreset(key: PresetKey) {
    const r = resolvePreset(key, today);
    setPeriodFrom(r.from);
    setPeriodTo(r.to);
  }

  return (
    <ClientShell>
      <div className="space-y-6">
        <header className="space-y-3">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-[color:var(--text-tertiary)]">
            <Link
              href="/client/vendors"
              className="inline-flex items-center gap-1 hover:text-[color:var(--text-primary)]"
            >
              <ArrowLeft className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
              Volver a proveedores
            </Link>
          </div>
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]">
              <Package className="h-5 w-5" weight="bold" aria-hidden="true" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)]">
                Paquete para auditoría
              </h1>
              <p className="mt-1 max-w-3xl text-sm text-[color:var(--text-secondary)]">
                Cuando llegue un inspector, arma aquí un ZIP con los
                documentos exactos que te está pidiendo: filtra por
                periodo, institución y proveedor. El paquete incluye un{" "}
                <strong>INDICE.pdf</strong> con el detalle de cada
                archivo, ideal para entregarlo por correo, USB o
                WhatsApp.
              </p>
            </div>
          </div>
        </header>

        <Surface title="Periodo" icon={Sparkle}>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label>Desde</Label>
              <PeriodPicker
                value={periodFrom}
                onChange={setPeriodFrom}
                allowEmpty={false}
              />
            </div>
            <div className="space-y-1">
              <Label>Hasta</Label>
              <PeriodPicker
                value={periodTo}
                onChange={setPeriodTo}
                allowEmpty={false}
              />
            </div>
          </div>
          <p className="mt-2 text-xs text-[color:var(--text-tertiary)]">
            Elige la granularidad (mes, bimestre, cuatrimestre o año
            fiscal) y el rango. Usa los atajos para los periodos más
            comunes.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {(Object.keys(PRESET_LABELS) as PresetKey[]).map((key) => (
              <Button
                key={key}
                type="button"
                size="sm"
                variant="outline"
                onClick={() => applyPreset(key)}
              >
                {PRESET_LABELS[key]}
              </Button>
            ))}
          </div>
        </Surface>

        <Surface title="Institución" icon={Sparkle}>
          <p className="text-xs text-[color:var(--text-tertiary)]">
            Selecciona qué autoridades cubre el paquete. Sin
            selección significa <strong>todas</strong>.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {INSTITUTION_OPTIONS.map((code) => {
              const active = institutions.includes(code);
              return (
                <button
                  type="button"
                  key={code}
                  onClick={() => toggleInst(code)}
                  className={
                    "rounded-full border px-3 py-1.5 text-xs font-medium transition " +
                    (active
                      ? "border-[color:var(--interactive-primary)] bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]"
                      : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-secondary)] hover:border-[color:var(--border-strong)]")
                  }
                  aria-pressed={active}
                >
                  {INSTITUTION_LABELS[code] ?? code}
                </button>
              );
            })}
          </div>
        </Surface>

        <Surface title="Proveedores" icon={Sparkle}>
          <p className="text-xs text-[color:var(--text-tertiary)]">
            Limita el paquete a proveedores específicos. Sin selección
            significa <strong>todos los proveedores</strong> en tu
            cartera.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {(vendorsList?.items ?? []).map((v) => {
              const active = vendorIds.includes(v.vendor_id);
              return (
                <button
                  type="button"
                  key={v.vendor_id}
                  onClick={() => toggleVendor(v.vendor_id)}
                  className={
                    "rounded-full border px-3 py-1.5 text-xs font-medium transition " +
                    (active
                      ? "border-[color:var(--interactive-primary)] bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]"
                      : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-secondary)] hover:border-[color:var(--border-strong)]")
                  }
                  aria-pressed={active}
                >
                  {v.vendor_name}
                </button>
              );
            })}
            {vendorsList && vendorsList.items.length === 0 ? (
              <p className="text-xs text-[color:var(--text-tertiary)]">
                Aún no tienes proveedores registrados. El paquete
                quedaría vacío.
              </p>
            ) : null}
          </div>
        </Surface>

        <Surface title="Avanzado" icon={Sparkle}>
          <button
            type="button"
            className="text-xs font-medium text-[color:var(--text-brand)] underline-offset-2 hover:underline"
            onClick={() => setAdvancedStatusOpen((v) => !v)}
            aria-expanded={advancedStatusOpen}
          >
            {advancedStatusOpen
              ? "Ocultar estados avanzados"
              : "Mostrar estados avanzados"}
          </button>
          <p className="mt-2 text-xs text-[color:var(--text-tertiary)]">
            Por defecto el paquete solo incluye documentos{" "}
            <strong>aprobados</strong> — es lo que un auditor espera
            ver. Habilita otros estados solo si necesitas demostrar
            trabajo en curso.
          </p>
          {advancedStatusOpen ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {STATUS_OPTIONS.map((opt) => {
                const active = statuses.includes(opt.value);
                return (
                  <button
                    type="button"
                    key={opt.value}
                    onClick={() => toggleStatus(opt.value)}
                    className={
                      "rounded-full border px-3 py-1.5 text-xs font-medium transition " +
                      (active
                        ? "border-[color:var(--interactive-primary)] bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]"
                        : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-secondary)] hover:border-[color:var(--border-strong)]")
                    }
                    aria-pressed={active}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          ) : null}
        </Surface>

        <Surface title="Resumen del paquete" icon={Info}>
          {previewLoading ? (
            <p className="text-sm text-[color:var(--text-tertiary)]">
              Calculando…
            </p>
          ) : previewError ? (
            <p className="text-sm text-[color:var(--status-error-text)]">
              {previewError}
            </p>
          ) : preview ? (
            <div className="space-y-3">
              <p className="text-base font-semibold text-[color:var(--text-primary)]">
                {preview.file_count} documento
                {preview.file_count === 1 ? "" : "s"} ·{" "}
                {preview.vendor_count} proveedor
                {preview.vendor_count === 1 ? "" : "es"} ·{" "}
                {formatBytes(preview.total_bytes)}
              </p>
              <div className="flex flex-wrap gap-2 text-xs">
                {preview.institution_breakdown.map((row) => (
                  <Badge key={row.institution} variant="info">
                    {INSTITUTION_LABELS[row.institution] ?? row.institution}{" "}
                    · {row.file_count}
                  </Badge>
                ))}
              </div>
              {preview.over_file_cap ? (
                <p className="text-sm text-[color:var(--status-error-text)]">
                  Supera el límite de {preview.file_cap} documentos por
                  descarga. Acota el rango o las instituciones.
                </p>
              ) : null}
              {preview.over_bytes_cap ? (
                <p className="text-sm text-[color:var(--status-error-text)]">
                  Supera el límite de{" "}
                  {Math.round(preview.bytes_cap / (1024 * 1024))} MB.
                  Acota el rango o las instituciones.
                </p>
              ) : null}
              {preview.file_count === 0 && !previewLoading ? (
                <p className="text-sm text-[color:var(--text-tertiary)]">
                  Ningún documento cumple los filtros aplicados. Revisa
                  el rango de periodo o los estados incluidos.
                </p>
              ) : null}
            </div>
          ) : null}
        </Surface>

        <Surface
          title="Selecciona los documentos"
          icon={Info}
          description="Los filtros de arriba acotan la lista. Aquí puedes ticar o destacar cada documento individualmente — todo lo seleccionado entra al ZIP."
          actions={
            tree && tree.items.length > 0 ? (
              <div className="flex gap-2 text-xs">
                <button
                  type="button"
                  className="font-medium text-[color:var(--text-brand)] hover:underline"
                  onClick={() => setSelectedIds(new Set(treeAllIds))}
                >
                  Seleccionar todo
                </button>
                <span className="text-[color:var(--text-tertiary)]">·</span>
                <button
                  type="button"
                  className="font-medium text-[color:var(--text-secondary)] hover:underline"
                  onClick={() => setSelectedIds(new Set())}
                >
                  Limpiar
                </button>
              </div>
            ) : null
          }
        >
          {selectionCleared ? (
            <div
              role="status"
              className="mb-3 flex items-center justify-between gap-3 rounded-md border border-[color:var(--text-brand)] px-3 py-2 text-xs text-[color:var(--text-secondary)]"
            >
              <span>
                Cambiaste los filtros, así que reiniciamos tu selección a
                «todos los documentos del resultado».
              </span>
              <button
                type="button"
                className="shrink-0 font-medium text-[color:var(--text-brand)] underline"
                onClick={() => setSelectionCleared(false)}
              >
                Entendido
              </button>
            </div>
          ) : null}
          {treeLoading ? (
            <p className="text-sm text-[color:var(--text-tertiary)]">
              Cargando documentos…
            </p>
          ) : treeError ? (
            <p className="text-sm text-[color:var(--status-error-text)]">
              {treeError}
            </p>
          ) : !tree || tree.items.length === 0 ? (
            <p className="text-sm text-[color:var(--text-tertiary)]">
              Ningún documento coincide con los filtros aplicados.
            </p>
          ) : (
            <DocumentTree
              tree={tree}
              selected={effectiveSelection}
              setSelected={(next) => setSelectedIds(new Set(next))}
            />
          )}
        </Surface>

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-sm">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[color:var(--text-primary)]">
              ¿Listo para entregárselo al auditor?
            </p>
            <p className="mt-1 text-xs text-[color:var(--text-tertiary)]">
              El ZIP se descarga con un INDICE.pdf en la raíz y los
              archivos organizados por proveedor, institución y
              periodo.
            </p>
          </div>
          <div className="flex flex-col items-end gap-1">
            <Button
              type="button"
              disabled={downloadDisabled}
              size="lg"
              onClick={onDownloadClick}
            >
              <DownloadSimple
                className="h-4 w-4"
                weight="bold"
                aria-hidden="true"
              />
              {downloading
                ? "Preparando…"
                : `Descargar ${selectionCount} documento${selectionCount === 1 ? "" : "s"}`}
              <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
            </Button>
            {downloadError ? (
              <p className="text-[11px] text-[color:var(--status-error-text)]">
                {downloadError}
              </p>
            ) : null}
            {overFileCap ? (
              <p className="text-[11px] text-[color:var(--status-error-text)]">
                Supera el límite de {tree?.file_cap} documentos. Deselecciona algunos.
              </p>
            ) : null}
            {overBytesCap ? (
              <p className="text-[11px] text-[color:var(--status-error-text)]">
                Supera el límite de {Math.round((tree?.bytes_cap ?? 0) / (1024 * 1024))} MB.
              </p>
            ) : null}
          </div>
        </div>
      </div>
    </ClientShell>
  );
}

// ─── Tree picker (item 2) ────────────────────────────────────────

type TreeNode = AuditPackageTreeNode;

type GroupedTree = Array<{
  vendor_id: string;
  vendor_name: string;
  institutions: Array<{
    institution_code: string;
    institution_name: string;
    periods: Array<{ period_key: string; docs: TreeNode[] }>;
  }>;
}>;

function buildGroupedTree(items: TreeNode[]): GroupedTree {
  const byVendor = new Map<string, TreeNode[]>();
  for (const it of items) {
    const arr = byVendor.get(it.vendor_id) ?? [];
    arr.push(it);
    byVendor.set(it.vendor_id, arr);
  }
  const vendors = Array.from(byVendor.entries())
    .map(([vid, rows]) => {
      const name = rows[0]?.vendor_name ?? vid;
      const byInst = new Map<string, TreeNode[]>();
      for (const r of rows) {
        const arr = byInst.get(r.institution_code) ?? [];
        arr.push(r);
        byInst.set(r.institution_code, arr);
      }
      const institutions = Array.from(byInst.entries())
        .map(([code, instRows]) => {
          const instName = instRows[0]?.institution_name ?? code;
          const byPeriod = new Map<string, TreeNode[]>();
          for (const r of instRows) {
            const k = r.period_key || "sin-periodo";
            const arr = byPeriod.get(k) ?? [];
            arr.push(r);
            byPeriod.set(k, arr);
          }
          const periods = Array.from(byPeriod.entries())
            .map(([period_key, docs]) => ({ period_key, docs }))
            .sort((a, b) => a.period_key.localeCompare(b.period_key));
          return {
            institution_code: code,
            institution_name: instName,
            periods,
          };
        })
        .sort((a, b) => {
          // Item 1 follow-up — pin the synthetic onboarding groups to the
          // top of each vendor's subtree in a fixed order: "Contrato" first,
          // then "Documentación Corporativa", then the real institutions
          // alphabetically. The auditor expects the expediente artefacts
          // first; the explicit pin keeps a future copy change from silently
          // burying them.
          const PINNED = ["contrato", "corporativo"];
          const aRank = PINNED.indexOf(a.institution_code);
          const bRank = PINNED.indexOf(b.institution_code);
          if (aRank !== -1 || bRank !== -1) {
            if (aRank === -1) return 1;
            if (bRank === -1) return -1;
            if (aRank !== bRank) return aRank - bRank;
          }
          return a.institution_name.localeCompare(b.institution_name, "es");
        });
      return { vendor_id: vid, vendor_name: name, institutions };
    })
    .sort((a, b) => a.vendor_name.localeCompare(b.vendor_name, "es"));
  return vendors;
}

function DocumentTree({
  tree,
  selected,
  setSelected,
}: {
  tree: AuditPackageTreeResponse;
  selected: Set<string>;
  setSelected: (next: Set<string>) => void;
}) {
  const grouped = useMemo(() => buildGroupedTree(tree.items), [tree.items]);

  function toggleIds(ids: string[], next: boolean) {
    const out = new Set(selected);
    if (next) {
      for (const id of ids) out.add(id);
    } else {
      for (const id of ids) out.delete(id);
    }
    setSelected(out);
  }

  return (
    <ul className="space-y-1.5">
      {grouped.map((vendor) => {
        const vendorDocIds = vendor.institutions.flatMap((i) =>
          i.periods.flatMap((p) => p.docs.map((d) => d.submission_id)),
        );
        const allOn = vendorDocIds.every((id) => selected.has(id));
        const someOn =
          !allOn && vendorDocIds.some((id) => selected.has(id));
        return (
          <TreeBranch
            key={vendor.vendor_id}
            label={vendor.vendor_name}
            count={vendorDocIds.length}
            checkedState={allOn ? "checked" : someOn ? "indeterminate" : "off"}
            onToggle={() => toggleIds(vendorDocIds, !allOn)}
            level={0}
          >
            {vendor.institutions.map((inst) => {
              const instDocIds = inst.periods.flatMap((p) =>
                p.docs.map((d) => d.submission_id),
              );
              const iAll = instDocIds.every((id) => selected.has(id));
              const iSome = !iAll && instDocIds.some((id) => selected.has(id));
              return (
                <TreeBranch
                  key={inst.institution_code}
                  label={inst.institution_name}
                  count={instDocIds.length}
                  checkedState={iAll ? "checked" : iSome ? "indeterminate" : "off"}
                  onToggle={() => toggleIds(instDocIds, !iAll)}
                  level={1}
                >
                  {inst.periods.map((p) => {
                    const pIds = p.docs.map((d) => d.submission_id);
                    const pAll = pIds.every((id) => selected.has(id));
                    const pSome = !pAll && pIds.some((id) => selected.has(id));
                    return (
                      <TreeBranch
                        key={p.period_key}
                        label={p.period_key}
                        count={p.docs.length}
                        checkedState={
                          pAll ? "checked" : pSome ? "indeterminate" : "off"
                        }
                        onToggle={() => toggleIds(pIds, !pAll)}
                        level={2}
                        defaultExpanded={false}
                      >
                        {p.docs.map((d) => (
                          <TreeLeaf
                            key={d.submission_id}
                            doc={d}
                            checked={selected.has(d.submission_id)}
                            onToggle={() =>
                              toggleIds([d.submission_id], !selected.has(d.submission_id))
                            }
                          />
                        ))}
                      </TreeBranch>
                    );
                  })}
                </TreeBranch>
              );
            })}
          </TreeBranch>
        );
      })}
    </ul>
  );
}

function TriCheckbox({
  state,
  onChange,
}: {
  state: "off" | "checked" | "indeterminate";
  onChange: () => void;
}) {
  // A native checkbox with the indeterminate property reflected via
  // a ref-effect; keeps native keyboard semantics for accessibility.
  return (
    <input
      type="checkbox"
      aria-checked={state === "indeterminate" ? "mixed" : state === "checked"}
      checked={state === "checked"}
      onChange={onChange}
      ref={(el) => {
        if (el) el.indeterminate = state === "indeterminate";
      }}
      className="h-3.5 w-3.5 cursor-pointer accent-[color:var(--interactive-primary)]"
    />
  );
}

function TreeBranch({
  label,
  count,
  checkedState,
  onToggle,
  children,
  level,
  defaultExpanded = true,
}: {
  label: string;
  count: number;
  checkedState: "off" | "checked" | "indeterminate";
  onToggle: () => void;
  children: React.ReactNode;
  level: number;
  defaultExpanded?: boolean;
}) {
  const [open, setOpen] = useState(defaultExpanded);
  const Caret = open ? CaretDown : CaretRight;
  const indent = level * 16;
  return (
    <li>
      <div
        className="flex items-center gap-2 rounded-sm px-1.5 py-1 text-[13px] hover:bg-[color:var(--surface-hover)]"
        style={{ paddingLeft: indent + 6 }}
      >
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-label={open ? `Contraer ${label}` : `Expandir ${label}`}
          className="inline-flex h-5 w-5 items-center justify-center rounded text-[color:var(--text-tertiary)] hover:text-[color:var(--text-primary)]"
        >
          <Caret className="h-3 w-3" weight="bold" aria-hidden="true" />
        </button>
        <TriCheckbox state={checkedState} onChange={onToggle} />
        <span
          className={
            level === 0
              ? "font-medium text-[color:var(--text-primary)]"
              : level === 1
                ? "text-[color:var(--text-primary)]"
                : "font-mono text-[12px] text-[color:var(--text-secondary)]"
          }
        >
          {label}
        </span>
        <span className="font-mono text-[10px] text-[color:var(--text-tertiary)]">
          ({count})
        </span>
      </div>
      {open ? <ul className="space-y-0.5">{children}</ul> : null}
    </li>
  );
}

function TreeLeaf({
  doc,
  checked,
  onToggle,
}: {
  doc: AuditPackageTreeNode;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <li>
      <label
        className="flex items-center gap-2 rounded-sm px-1.5 py-1 text-[12px] hover:bg-[color:var(--surface-hover)]"
        style={{ paddingLeft: 3 * 16 + 26 }}
      >
        <TriCheckbox
          state={checked ? "checked" : "off"}
          onChange={onToggle}
        />
        <span className="min-w-0 truncate text-[color:var(--text-primary)]">
          {doc.requirement_name}
        </span>
        <span className="ml-auto flex shrink-0 items-center gap-2 text-[color:var(--text-tertiary)]">
          <span className="font-mono text-[10px]">{formatBytes(doc.size_bytes)}</span>
          <Badge variant="outline">{doc.status}</Badge>
        </span>
      </label>
    </li>
  );
}

function formatBytes(total: number): string {
  if (total >= 1024 * 1024) {
    return `${(total / (1024 * 1024)).toFixed(1)} MB`;
  }
  if (total >= 1024) {
    return `${(total / 1024).toFixed(1)} KB`;
  }
  return `${total} B`;
}
