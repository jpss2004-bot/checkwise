"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  ChartLineUp,
  CircleNotch,
  FileText,
  Plus,
  Sparkle,
  Warning,
} from "@phosphor-icons/react";

import { PortalAppShell } from "@/components/checkwise/portal/portal-app-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import {
  REPORT_AUDIENCE_LABEL,
  REPORT_STATUS_LABEL,
  type ReportAudience,
} from "@/lib/reports/constants";
import {
  ReportsApiError,
  createReport,
  listReports,
  type ReportSummary,
} from "@/lib/api/reports";
import { withOnboardingGate } from "@/lib/session/with-onboarding-gate";
import type { PortalSession } from "@/lib/session/portal";

/**
 * Reports list view — Phase 3.2.
 *
 * Replaces the V1.5 mock-data card grid. Reads real reports from the
 * 3.1 backend, surfaces a "New report" CTA that creates an empty
 * report and routes into the editor.
 *
 * The 3.3 chat-first creation flow will replace this CTA with the
 * copilot landing surface; until then we ship a minimal create form
 * so 3.2 is self-contained.
 */
function ReportsListInner({ session }: { session: PortalSession }) {
  const router = useRouter();
  const [reports, setReports] = useState<ReportSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newOpen, setNewOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");

  useEffect(() => {
    let cancelled = false;
    listReports({ limit: 100 })
      .then((payload) => {
        if (cancelled) return;
        setReports(payload.items);
        setError(null);
      })
      .catch((e: ReportsApiError) => {
        if (cancelled) return;
        if (e.status === 401 || e.status === 403) {
          setError(
            "Tu sesión de proveedor todavía no tiene acceso al motor de reportes. " +
              "El equipo legal de CheckWise puede activarlo desde el panel de admin.",
          );
        } else {
          setError(`No pudimos cargar tus reportes: ${e.message}`);
        }
        setReports([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const onCreate = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      if (!newTitle.trim() || creating) return;
      setCreating(true);
      try {
        const r = await createReport({
          title: newTitle.trim(),
          description: null,
          audience: "internal_only",
          initial_content_json: {
            schema_version: 1,
            blocks: [],
            global: {},
          },
        });
        router.push(`/portal/reports/${r.id}`);
      } catch (e2) {
        setCreating(false);
        const msg =
          e2 instanceof ReportsApiError ? e2.message : "Error creando el reporte.";
        setError(msg);
      }
    },
    [newTitle, creating, router],
  );

  return (
    <PortalAppShell session={session}>
      <main className="mx-auto max-w-5xl space-y-6 px-5 py-6">
        <PageHeader
          eyebrow="Centro de cumplimiento"
          title="Reportes"
          description="Centro de inteligencia de cumplimiento. Genera, edita y comparte reportes ejecutivos."
          actions={
            <Button
              variant="default"
              size="sm"
              onClick={() => setNewOpen((open) => !open)}
            >
              <Plus className="h-4 w-4" weight="bold" aria-hidden="true" />
              Nuevo reporte
            </Button>
          }
        />

        {newOpen && (
          <form
            onSubmit={onCreate}
            className="cw-fade-up flex flex-col gap-3 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-4 shadow-[var(--shadow-sm)] sm:flex-row sm:items-center"
          >
            <input
              type="text"
              placeholder="Título del reporte (ej. Resumen REPSE — mayo 2026)"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              autoFocus
              className="flex-1 rounded-sm border border-[color:var(--border-default)] bg-[color:var(--surface-page)] px-3 py-1.5 text-[14px] text-[color:var(--text-primary)] outline-none focus:border-[color:var(--border-focus)]"
            />
            <Button type="submit" size="sm" disabled={!newTitle.trim() || creating}>
              {creating ? (
                <CircleNotch
                  className="h-4 w-4 animate-spin"
                  weight="bold"
                  aria-hidden="true"
                />
              ) : (
                <Sparkle className="h-4 w-4" weight="bold" aria-hidden="true" />
              )}
              {creating ? "Creando…" : "Crear y abrir"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setNewOpen(false);
                setNewTitle("");
              }}
            >
              Cancelar
            </Button>
          </form>
        )}

        {error && (
          <Alert variant="warning">
            <AlertTitle className="flex items-center gap-2">
              <Warning className="h-4 w-4" weight="bold" aria-hidden="true" />
              No se pudieron cargar los reportes
            </AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {!error && reports !== null && reports.length === 0 && (
          <EmptyState onNew={() => setNewOpen(true)} />
        )}

        {!error && reports && reports.length > 0 && (
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

        {!error && reports === null && (
          <div className="space-y-2 py-8 text-center text-[13px] text-[color:var(--text-tertiary)]">
            <CircleNotch
              className="mx-auto h-5 w-5 animate-spin"
              weight="bold"
              aria-hidden="true"
            />
            Cargando reportes…
          </div>
        )}
      </main>
    </PortalAppShell>
  );
}

export default withOnboardingGate(ReportsListInner);

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

function EmptyState({ onNew }: { onNew: () => void }) {
  return (
    <div className="rounded-md border border-dashed border-[color:var(--border-subtle)] py-16 text-center">
      <ChartLineUp
        className="mx-auto mb-2 h-6 w-6 text-[color:var(--text-ai)]"
        weight="regular"
        aria-hidden="true"
      />
      <p className="text-[15px] font-semibold text-[color:var(--text-primary)]">
        Aún no hay reportes
      </p>
      <p className="mx-auto mt-2 max-w-md text-[13px] text-[color:var(--text-secondary)]">
        Cuando crees tu primer reporte aparecerá aquí. En la próxima fase podrás
        pedirle al copiloto que arme uno a partir de tus datos.
      </p>
      <Button variant="default" size="sm" className="mt-4" onClick={onNew}>
        <Plus className="h-4 w-4" weight="bold" aria-hidden="true" />
        Crear primer reporte
      </Button>
    </div>
  );
}
