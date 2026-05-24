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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  clientAuditPackageZipUrl,
  getClientAuditPackagePreview,
  listClientVendors,
  type AuditPackageFilters,
  type AuditPackagePreview,
  type ClientVendorListResponse,
} from "@/lib/api/client";
import { INSTITUTION_LABELS } from "@/lib/api/portal";

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

  // Vendor catalog — fetched once, used for the multi-select chips
  // and to map vendor_id → vendor_name on the preview breakdown.
  useEffect(() => {
    let cancelled = false;
    listClientVendors()
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
  }, []);

  // Live preview — refetch whenever any filter changes. Debounce is
  // not necessary because the user interacts via discrete clicks
  // (chips / toggles) rather than free typing.
  useEffect(() => {
    let cancelled = false;
    setPreviewLoading(true);
    setPreviewError(null);
    const filters: AuditPackageFilters = {
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
    return () => {
      cancelled = true;
    };
  }, [periodFrom, periodTo, institutions, vendorIds, statuses]);

  const downloadUrl = clientAuditPackageZipUrl({
    period_from: periodFrom || null,
    period_to: periodTo || null,
    institutions,
    statuses,
    vendor_ids: vendorIds,
  });

  const downloadDisabled =
    previewLoading ||
    !preview ||
    preview.file_count === 0 ||
    preview.over_file_cap ||
    preview.over_bytes_cap;

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
              <Label htmlFor="audit-from">Desde (AAAA-Mxx)</Label>
              <Input
                id="audit-from"
                value={periodFrom}
                onChange={(e) => setPeriodFrom(e.target.value)}
                placeholder="2026-M01"
                aria-describedby="audit-period-helper"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="audit-to">Hasta (AAAA-Mxx)</Label>
              <Input
                id="audit-to"
                value={periodTo}
                onChange={(e) => setPeriodTo(e.target.value)}
                placeholder="2026-M12"
                aria-describedby="audit-period-helper"
              />
            </div>
          </div>
          <p
            id="audit-period-helper"
            className="mt-2 text-xs text-[color:var(--text-tertiary)]"
          >
            El formato canónico es <code>AAAA-Mxx</code> para meses,{" "}
            <code>AAAA-Bx</code> para bimestres y <code>AAAA-A</code>{" "}
            para el año fiscal completo. Usa los atajos para los rangos
            más comunes.
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
          <Button asChild disabled={downloadDisabled} size="lg">
            <a
              href={downloadDisabled ? "#" : downloadUrl}
              target="_blank"
              rel="noreferrer"
              aria-disabled={downloadDisabled}
              tabIndex={downloadDisabled ? -1 : undefined}
              onClick={(e) => {
                if (downloadDisabled) e.preventDefault();
              }}
            >
              <DownloadSimple className="h-4 w-4" weight="bold" aria-hidden="true" />
              Descargar paquete para auditoría
              <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
            </a>
          </Button>
        </div>
      </div>
    </ClientShell>
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
