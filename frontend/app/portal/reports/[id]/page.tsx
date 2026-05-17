"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowsClockwise,
  CheckCircle,
  FloppyDisk,
  WarningCircle,
} from "@phosphor-icons/react";

import { Canvas } from "@/components/checkwise/reports/canvas";
import { PortalAppShell } from "@/components/checkwise/portal/portal-app-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import {
  REPORT_AUDIENCE_LABEL,
  REPORT_STATUS_LABEL,
} from "@/lib/reports/constants";
import {
  ReportsApiError,
  createVersion,
  getReport,
  type ReportContent,
  type ReportRead,
} from "@/lib/api/reports";
import { withOnboardingGate } from "@/lib/session/with-onboarding-gate";
import type { PortalSession } from "@/lib/session/portal";

/**
 * Report editor route — Phase 3.2.
 *
 * Loads a report by id, mounts the Canvas, and lets the user manually
 * save versions. Autosave + version-history drawer arrive in Phase 3.5.
 *
 * The "Save version" button creates a new ReportVersion with the
 * current content. The page tracks an `isDirty` flag (set on canvas
 * change, cleared on save) so the button is meaningful.
 */

function EditorInner({ session }: { session: PortalSession }) {
  const params = useParams();
  const router = useRouter();
  const reportId = typeof params?.id === "string" ? params.id : "";

  const [report, setReport] = useState<ReportRead | null>(null);
  const [content, setContent] = useState<ReportContent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [isDirty, setIsDirty] = useState(false);

  // ─── Load ───────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getReport(reportId)
      .then((payload) => {
        if (cancelled) return;
        setReport(payload);
        setContent(payload.current_version?.content_json ?? {
          schema_version: 1,
          blocks: [],
          global: {},
        });
        setLoading(false);
      })
      .catch((e: ReportsApiError) => {
        if (cancelled) return;
        setError(
          e.status === 404
            ? "No encontramos este reporte (o no tienes acceso)."
            : `Error al cargar el reporte: ${e.message}`,
        );
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reportId]);

  const onCanvasChange = useCallback((next: ReportContent) => {
    setContent(next);
    setIsDirty(true);
  }, []);

  const saveVersion = useCallback(async () => {
    if (!content || !reportId) return;
    setSaving(true);
    try {
      const v = await createVersion(reportId, {
        content_json: content,
        label: null,
        generated_by: "user",
      });
      setSaving(false);
      setSavedAt(new Date());
      setIsDirty(false);
      // Reload metadata so version_number etc. are current.
      const fresh = await getReport(reportId);
      setReport(fresh);
      // Keep using local content so unsaved edits made during save persist.
      if (!isDirty) setContent(fresh.current_version?.content_json ?? content);
      // Surface the new version for assistive tech.
      console.info("[reports] saved version", v.version_number);
    } catch (e) {
      setSaving(false);
      const msg = e instanceof ReportsApiError ? e.message : "Error guardando versión.";
      setError(msg);
    }
  }, [content, reportId, isDirty]);

  // ─── Render states ──────────────────────────────────────────
  if (loading) {
    return (
      <PortalAppShell session={session}>
        <main className="mx-auto max-w-5xl space-y-4 px-5 py-6">
          <div className="h-10 animate-pulse rounded-sm bg-[color:var(--surface-sunken)]" />
          <div className="h-32 animate-pulse rounded-md bg-[color:var(--surface-sunken)]" />
          <div className="h-64 animate-pulse rounded-md bg-[color:var(--surface-sunken)]" />
        </main>
      </PortalAppShell>
    );
  }

  if (error || !report || !content) {
    return (
      <PortalAppShell session={session}>
        <main className="mx-auto max-w-3xl px-5 py-8">
          <Alert variant="warning">
            <AlertTitle className="flex items-center gap-2">
              <WarningCircle className="h-4 w-4" weight="bold" aria-hidden="true" />
              Reporte no disponible
            </AlertTitle>
            <AlertDescription>
              {error ?? "El reporte no pudo cargarse."}
            </AlertDescription>
          </Alert>
          <Button asChild variant="outline" size="sm" className="mt-4">
            <Link href="/portal/reports">
              <ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
              Volver a reportes
            </Link>
          </Button>
        </main>
      </PortalAppShell>
    );
  }

  const versionLabel = report.current_version
    ? `v${report.current_version.version_number}`
    : "—";

  return (
    <PortalAppShell session={session}>
      <main className="mx-auto max-w-5xl space-y-6 px-5 py-6">
        <PageHeader
          eyebrow="Reporte"
          title={report.title}
          description={report.description ?? "Sin descripción"}
          actions={
            <>
              <Button asChild variant="ghost" size="sm">
                <Link href="/portal/reports">
                  <ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
                  Volver
                </Link>
              </Button>
              <Button
                variant="default"
                size="sm"
                onClick={saveVersion}
                disabled={saving || !isDirty}
                title={isDirty ? "Guardar versión" : "Sin cambios pendientes"}
              >
                {saving ? (
                  <ArrowsClockwise
                    className="h-4 w-4 animate-spin"
                    weight="bold"
                    aria-hidden="true"
                  />
                ) : isDirty ? (
                  <FloppyDisk className="h-4 w-4" weight="bold" aria-hidden="true" />
                ) : (
                  <CheckCircle className="h-4 w-4" weight="bold" aria-hidden="true" />
                )}
                {saving
                  ? "Guardando…"
                  : isDirty
                    ? "Guardar versión"
                    : "Sin cambios"}
              </Button>
            </>
          }
        />

        <div className="cw-metadata-strip border-t border-b border-[color:var(--border-subtle)] py-3">
          <div>
            <span className="cw-eyebrow">Audiencia</span>
            <span className="text-[13px] text-[color:var(--text-primary)]">
              {REPORT_AUDIENCE_LABEL[report.audience]}
            </span>
          </div>
          <div>
            <span className="cw-eyebrow">Estado</span>
            <Badge
              variant={report.status === "active" ? "success" : "outline"}
            >
              {REPORT_STATUS_LABEL[report.status]}
            </Badge>
          </div>
          <div>
            <span className="cw-eyebrow">Versión</span>
            <span className="font-mono text-[13px] text-[color:var(--text-primary)]">
              {versionLabel}
            </span>
          </div>
          {savedAt && (
            <div>
              <span className="cw-eyebrow">Guardado</span>
              <span className="font-mono text-[11px] text-[color:var(--text-tertiary)]">
                {savedAt.toLocaleTimeString("es-MX", {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                })}
              </span>
            </div>
          )}
        </div>

        <Canvas content={content} editable={true} onChange={onCanvasChange} />
      </main>
    </PortalAppShell>
  );
}

export default withOnboardingGate(EditorInner);
