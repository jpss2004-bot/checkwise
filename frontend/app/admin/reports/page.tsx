"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  ChartLineUp,
  CircleNotch,
  FileText,
  Sparkle,
  Warning,
} from "@phosphor-icons/react";

import { AdminShell } from "../_shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  REPORT_AUDIENCE_LABEL,
  REPORT_STATUS_LABEL,
  type ReportAudience,
} from "@/lib/reports/constants";
import {
  ReportsApiError,
  createReportFromPreset,
  listPresets,
  listReports,
  type ReportPresetSummary,
  type ReportSummary,
} from "@/lib/api/reports";

/**
 * Admin Reports list — R1.0.
 *
 * Internal-team entry point. Shows the preset gallery (3 admin
 * presets in R1.0) and the operator's existing report list, both
 * filtered server-side by visible_audiences() so a role with no
 * reports access lands on a clean empty state instead of a CORS
 * error or a forbidden table.
 *
 * The editor itself still lives at /portal/reports/[id] — this slice
 * deliberately does not refactor that page; the admin route /admin/
 * reports/[id] redirects so we don't duplicate the 500-line editor.
 */
export default function AdminReportsPage() {
  const router = useRouter();
  const [presets, setPresets] = useState<ReportPresetSummary[] | null>(null);
  const [reports, setReports] = useState<ReportSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    Promise.all([listPresets(), listReports({ limit: 100 })])
      .then(([p, r]) => {
        if (cancelled) return;
        setPresets(p.items);
        setReports(r.items);
      })
      .catch((e: ReportsApiError) => {
        if (cancelled) return;
        setError(
          e.status === 401 || e.status === 403
            ? "No tienes acceso al motor de reportes."
            : `No pudimos cargar reportes: ${e.message}`,
        );
        setPresets([]);
        setReports([]);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const onUsePreset = useCallback(
    async (preset: ReportPresetSummary) => {
      if (creating) return;
      setCreating(preset.id);
      try {
        const r = await createReportFromPreset(preset.id);
        router.push(`/portal/reports/${r.id}`);
      } catch (e) {
        setCreating(null);
        setError(
          e instanceof ReportsApiError
            ? e.message
            : "Error creando el reporte.",
        );
      }
    },
    [creating, router],
  );

  return (
    <AdminShell
      title="Reportes"
      description="Centro de inteligencia operativa. Genera reportes internos sobre la bandeja de revisión, proveedores en riesgo y cumplimiento mensual."
    >
      {error && (
        <Alert variant="warning">
          <AlertTitle className="flex items-center gap-2">
            <Warning className="h-4 w-4" weight="bold" aria-hidden="true" />
            No se pudieron cargar los reportes
          </AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <section className="space-y-3">
        <header className="flex items-baseline justify-between">
          <h2 className="text-[14px] font-semibold tracking-tight text-[color:var(--text-primary)]">
            Plantillas operativas
          </h2>
          <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            {presets ? `${presets.length} disponibles` : "—"}
          </span>
        </header>

        {presets === null ? (
          <div className="flex items-center gap-2 py-6 text-[12px] text-[color:var(--text-tertiary)]">
            <CircleNotch
              className="h-4 w-4 animate-spin"
              weight="bold"
              aria-hidden="true"
            />
            Cargando plantillas…
          </div>
        ) : presets.length === 0 ? (
          <div className="rounded-md border border-dashed border-[color:var(--border-subtle)] px-4 py-6 text-[12px] text-[color:var(--text-tertiary)]">
            Tu rol todavía no tiene plantillas asignadas.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {presets.map((p) => (
              <PresetCard
                key={p.id}
                preset={p}
                creating={creating === p.id}
                disabled={creating !== null && creating !== p.id}
                onUse={() => onUsePreset(p)}
              />
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <header className="flex items-baseline justify-between">
          <h2 className="text-[14px] font-semibold tracking-tight text-[color:var(--text-primary)]">
            Reportes recientes
          </h2>
          <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            {reports ? `${reports.length} visibles` : "—"}
          </span>
        </header>

        {reports === null ? (
          <div className="flex items-center gap-2 py-6 text-[12px] text-[color:var(--text-tertiary)]">
            <CircleNotch
              className="h-4 w-4 animate-spin"
              weight="bold"
              aria-hidden="true"
            />
            Cargando reportes…
          </div>
        ) : reports.length === 0 ? (
          <EmptyReports />
        ) : (
          <div className="overflow-hidden border-t border-b border-[color:var(--border-default)]">
            <table className="min-w-full text-[13px]">
              <thead>
                <tr className="border-b border-[color:var(--border-subtle)]">
                  <th className="cw-eyebrow py-2 pr-4 text-left">Título</th>
                  <th className="cw-eyebrow py-2 pr-4 text-left">Audiencia</th>
                  <th className="cw-eyebrow py-2 pr-4 text-left">Estado</th>
                  <th className="cw-eyebrow py-2 pr-4 text-left">Actualizado</th>
                  <th className="cw-eyebrow py-2 text-right">Abrir</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((r) => (
                  <ReportRow key={r.id} report={r} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </AdminShell>
  );
}

function PresetCard({
  preset,
  creating,
  disabled,
  onUse,
}: {
  preset: ReportPresetSummary;
  creating: boolean;
  disabled: boolean;
  onUse: () => void;
}) {
  return (
    <article className="flex h-full flex-col gap-2 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-4 shadow-[var(--shadow-sm)]">
      <div className="flex items-center gap-2 text-[color:var(--text-ai)]">
        <Sparkle className="h-3.5 w-3.5" weight="fill" aria-hidden="true" />
        <span className="cw-eyebrow text-[color:var(--text-ai)]">
          {REPORT_AUDIENCE_LABEL[preset.audience]}
        </span>
      </div>
      <h3 className="text-[14px] font-semibold leading-tight text-[color:var(--text-primary)]">
        {preset.title}
      </h3>
      <p className="text-[12px] leading-relaxed text-[color:var(--text-secondary)]">
        {preset.description}
      </p>
      <Button
        type="button"
        size="sm"
        variant="default"
        className="mt-auto"
        onClick={onUse}
        disabled={disabled || creating}
      >
        {creating ? (
          <CircleNotch
            className="h-3.5 w-3.5 animate-spin"
            weight="bold"
            aria-hidden="true"
          />
        ) : (
          <Sparkle className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
        )}
        {creating ? "Creando…" : "Usar plantilla"}
      </Button>
    </article>
  );
}

function ReportRow({ report }: { report: ReportSummary }) {
  return (
    <tr className="border-b border-[color:var(--border-subtle)] last:border-0 hover:bg-[color:var(--surface-hover)]">
      <td className="py-3 pr-4">
        <Link
          href={`/portal/reports/${report.id}`}
          className="flex items-center gap-2 text-[13px] font-medium text-[color:var(--text-primary)] hover:underline"
        >
          <FileText
            className="h-4 w-4 text-[color:var(--text-tertiary)]"
            weight="regular"
            aria-hidden="true"
          />
          {report.title}
        </Link>
        {report.description && (
          <p className="mt-0.5 text-[11px] text-[color:var(--text-tertiary)]">
            {report.description}
          </p>
        )}
      </td>
      <td className="py-3 pr-4 text-[12px] text-[color:var(--text-secondary)]">
        {REPORT_AUDIENCE_LABEL[report.audience as ReportAudience]}
      </td>
      <td className="py-3 pr-4">
        <Badge variant={report.status === "active" ? "success" : "outline"}>
          {REPORT_STATUS_LABEL[report.status]}
        </Badge>
      </td>
      <td className="py-3 pr-4 font-mono text-[11px] text-[color:var(--text-tertiary)]">
        {new Date(report.updated_at).toLocaleString("es-MX", {
          dateStyle: "medium",
          timeStyle: "short",
        })}
      </td>
      <td className="py-3 text-right">
        <Link
          href={`/portal/reports/${report.id}`}
          aria-label={`Abrir ${report.title}`}
          className="inline-flex items-center justify-center rounded-sm p-1 text-[color:var(--text-tertiary)] hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]"
        >
          <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
        </Link>
      </td>
    </tr>
  );
}

function EmptyReports() {
  return (
    <div className="rounded-md border border-dashed border-[color:var(--border-subtle)] py-12 text-center">
      <ChartLineUp
        className="mx-auto mb-2 h-6 w-6 text-[color:var(--text-ai)]"
        weight="regular"
        aria-hidden="true"
      />
      <p className="text-[14px] font-semibold text-[color:var(--text-primary)]">
        Aún no hay reportes
      </p>
      <p className="mx-auto mt-2 max-w-md text-[12px] text-[color:var(--text-secondary)]">
        Usa una de las plantillas operativas arriba para crear el primero.
      </p>
    </div>
  );
}
