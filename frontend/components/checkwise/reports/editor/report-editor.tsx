"use client";

import {
  useCallback,
  useEffect,
  useState,
  type FormEvent,
} from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowsClockwise,
  CheckCircle,
  ChatCircle,
  CircleNotch,
  DownloadSimple,
  Eye,
  FloppyDisk,
  Sparkle,
  WarningCircle,
  X,
} from "@phosphor-icons/react";

import { Canvas } from "@/components/checkwise/reports/canvas";
import { ChatCopilot } from "@/components/checkwise/reports/chat-copilot";
import { ReportActionsContext } from "@/components/checkwise/reports/freshness-label";
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
  explainBlock,
  getReport,
  getReportsEngine,
  refreshReportData,
  regenerateBlock,
  type ReportContent,
  type ReportRead,
  type ReportsEngineInfo,
} from "@/lib/api/reports";
import { useReportGeneration } from "@/lib/reports/use-generation";

/**
 * Shared report editor body — R1.0.1.
 *
 * Renders the full editor (page header, AI prompt panel, canvas,
 * copilot) inside a max-w-5xl container. Designed to be dropped
 * into any of the three role shells (PortalAppShell, AdminShell,
 * ClientShell). The shell provides the chrome (nav, brand, footer);
 * this component provides the page content.
 *
 * Print route still mounts a separate, chrome-less view at
 * /portal/reports/[id]/print — not affected by this refactor.
 *
 * Props:
 * - reportId: required, the report being edited.
 * - backHref: where the "Volver" link points. Each shell points it
 *   at its own reports list (/portal/reports, /admin/reports,
 *   /client/reports) so the user never gets bounced into a
 *   different shell.
 * - printHref: where the "Imprimir" link points. The print view
 *   lives at /portal/reports/[id]/print and is the same for every
 *   shell (it has its own chrome).
 */
export interface ReportEditorProps {
  reportId: string;
  backHref: string;
  printHref: string;
}

export function ReportEditor({
  reportId,
  backHref,
  printHref,
}: ReportEditorProps) {
  const [report, setReport] = useState<ReportRead | null>(null);
  const [content, setContent] = useState<ReportContent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [isDirty, setIsDirty] = useState(false);

  // ─── AI generation ──────────────────────────────────────────
  const [aiOpen, setAiOpen] = useState(false);
  const [aiPrompt, setAiPrompt] = useState("");
  const gen = useReportGeneration(reportId);

  // ─── LLM backend probe ─────────────────────────────────────
  // Honest signal: if the backend has no ANTHROPIC_API_KEY the
  // factory falls back to the deterministic mock and `name` is
  // "mock". Surface a banner so the operator never confuses canned
  // text with real AI output.
  const [engine, setEngine] = useState<ReportsEngineInfo | null>(null);
  useEffect(() => {
    let cancelled = false;
    getReportsEngine()
      .then((info) => {
        if (!cancelled) setEngine(info);
      })
      .catch(() => {
        // Non-fatal: a stale or unauthenticated probe just hides the
        // banner; it never blocks the editor.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // ─── Copilot chat (right rail) ─────────────────────────────
  const [chatOpen, setChatOpen] = useState(false);

  // ─── Per-block actions ────────────────────────────────────
  const [regeneratingBlockId, setRegeneratingBlockId] = useState<string | null>(
    null,
  );
  const [explanation, setExplanation] = useState<{
    blockId: string;
    text: string;
  } | null>(null);

  const onRegenerateBlock = useCallback(
    async (blockId: string) => {
      setRegeneratingBlockId(blockId);
      try {
        await regenerateBlock(reportId, blockId);
        const fresh = await getReport(reportId);
        setReport(fresh);
        if (fresh.current_version) {
          setContent(fresh.current_version.content_json);
          setIsDirty(false);
        }
      } catch (e) {
        const msg =
          e instanceof ReportsApiError ? e.message : "Error al regenerar.";
        setError(msg);
      } finally {
        setRegeneratingBlockId(null);
      }
    },
    [reportId],
  );

  // ─── P1.7 — Refresh data (no LLM) ──────────────────────────
  // "Actualizar con datos de hoy": re-runs every block's deterministic
  // data fetcher and persists a new ReportVersion. ai_summary text is
  // preserved verbatim (no LLM). After the round-trip we reload the
  // report so the canvas re-renders with the fresh `data` payloads and
  // the per-block freshness labels update.
  const [refreshingData, setRefreshingData] = useState(false);
  const [lastRefreshAt, setLastRefreshAt] = useState<Date | null>(null);

  const onRefreshData = useCallback(async () => {
    if (refreshingData) return;
    setRefreshingData(true);
    setError(null);
    try {
      const resp = await refreshReportData(reportId);
      const fresh = await getReport(reportId);
      setReport(fresh);
      if (fresh.current_version) {
        setContent(fresh.current_version.content_json);
        setIsDirty(false);
      }
      setLastRefreshAt(new Date(resp.fetched_at));
    } catch (e) {
      setError(
        e instanceof ReportsApiError
          ? `No pudimos actualizar los datos: ${e.message}`
          : "No pudimos actualizar los datos.",
      );
    } finally {
      setRefreshingData(false);
    }
  }, [refreshingData, reportId]);

  const onExplainBlockClicked = useCallback(
    async (blockId: string) => {
      setExplanation({ blockId, text: "Generando explicación…" });
      try {
        const resp = await explainBlock(reportId, blockId);
        setExplanation({ blockId, text: resp.explanation });
      } catch (e) {
        const msg =
          e instanceof ReportsApiError ? e.message : "Error al explicar.";
        setExplanation({ blockId, text: `❌ ${msg}` });
      }
    },
    [reportId],
  );

  const onGenerateSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      if (!aiPrompt.trim()) return;
      await gen.startGeneration(aiPrompt.trim());
    },
    [aiPrompt, gen],
  );

  // When generation completes, swap the editor's content over to the
  // streamed result + reload the report metadata so version_number
  // reflects the new persisted version.
  useEffect(() => {
    if (gen.state.status === "done" && gen.state.content) {
      setContent(gen.state.content);
      setIsDirty(false);
      getReport(reportId)
        .then(setReport)
        .catch(() => {});
    }
  }, [gen.state.status, gen.state.content, reportId]);

  // ─── Load ───────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getReport(reportId)
      .then((payload) => {
        if (cancelled) return;
        setReport(payload);
        const loaded = payload.current_version?.content_json ?? {
          schema_version: 1,
          blocks: [],
          global: {},
        };
        setContent(loaded);
        // R1.0: preset-created reports park their recommended prompt
        // on global.recommended_prompt. Pre-fill + auto-open the AI
        // panel so "Use template" → Enter is one click.
        const rec = (loaded as { global?: { recommended_prompt?: unknown } })
          .global?.recommended_prompt;
        if (
          typeof rec === "string" &&
          rec.trim() &&
          (loaded.blocks?.length ?? 0) === 0
        ) {
          setAiPrompt(rec);
          setAiOpen(true);
        }
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
      const fresh = await getReport(reportId);
      setReport(fresh);
      if (!isDirty) setContent(fresh.current_version?.content_json ?? content);
      console.info("[reports] saved version", v.version_number);
    } catch (e) {
      setSaving(false);
      const msg =
        e instanceof ReportsApiError ? e.message : "Error guardando versión.";
      setError(msg);
    }
  }, [content, reportId, isDirty]);

  // ─── Render states ──────────────────────────────────────────
  if (loading) {
    return (
      <div className="mx-auto max-w-5xl space-y-4 px-5 py-6">
        <div className="h-10 animate-pulse rounded-sm bg-[color:var(--surface-sunken)]" />
        <div className="h-32 animate-pulse rounded-md bg-[color:var(--surface-sunken)]" />
        <div className="h-64 animate-pulse rounded-md bg-[color:var(--surface-sunken)]" />
      </div>
    );
  }

  if (error || !report || !content) {
    return (
      <div className="mx-auto max-w-3xl px-5 py-8">
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
          <Link href={backHref}>
            <ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
            Volver a reportes
          </Link>
        </Button>
      </div>
    );
  }

  const versionLabel = report.current_version
    ? `v${report.current_version.version_number}`
    : "—";

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-5 py-6">
      <PageHeader
        eyebrow="Reporte"
        title={report.title}
        description={report.description ?? "Sin descripción"}
        actions={
          <>
            <Button asChild variant="ghost" size="sm">
              <Link href={backHref}>
                <ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
                Volver
              </Link>
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setAiOpen((open) => !open)}
              disabled={
                gen.state.status === "planning" ||
                gen.state.status === "streaming" ||
                gen.state.status === "saving"
              }
              title="Generar con IA a partir de un prompt"
            >
              <Sparkle className="h-4 w-4" weight="bold" aria-hidden="true" />
              Generar con IA
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setChatOpen((open) => !open)}
              title="Abrir / cerrar copiloto"
            >
              <ChatCircle className="h-4 w-4" weight="bold" aria-hidden="true" />
              Copiloto
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={onRefreshData}
              disabled={refreshingData}
              title="Re-ejecutar los lectores de datos canónicos sin tocar la IA"
            >
              {refreshingData ? (
                <ArrowsClockwise
                  className="h-4 w-4 animate-spin"
                  weight="bold"
                  aria-hidden="true"
                />
              ) : (
                <ArrowsClockwise
                  className="h-4 w-4"
                  weight="bold"
                  aria-hidden="true"
                />
              )}
              {refreshingData ? "Actualizando…" : "Actualizar con datos de hoy"}
            </Button>
            <Button
              asChild
              variant="ghost"
              size="sm"
              title="Abrir vista previa imprimible en una pestaña nueva"
            >
              <Link href={printHref} target="_blank" rel="noopener noreferrer">
                <Eye className="h-4 w-4" weight="bold" aria-hidden="true" />
                Vista previa PDF
              </Link>
            </Button>
            <Button
              asChild
              variant="ghost"
              size="sm"
              title="Abrir vista de impresión y disparar Guardar como PDF"
            >
              <Link
                href={`${printHref}?autoprint=1`}
                target="_blank"
                rel="noopener noreferrer"
              >
                <DownloadSimple
                  className="h-4 w-4"
                  weight="bold"
                  aria-hidden="true"
                />
                Descargar PDF
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
          <Badge variant={report.status === "active" ? "success" : "outline"}>
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
        {gen.state.status !== "idle" && (
          <div>
            <span className="cw-eyebrow">IA</span>
            <GenerationBadge status={gen.state.status} />
          </div>
        )}
        {lastRefreshAt && (
          <div>
            <span className="cw-eyebrow">Datos</span>
            <span className="font-mono text-[11px] text-[color:var(--text-tertiary)]">
              {lastRefreshAt.toLocaleTimeString("es-MX", {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              })}
            </span>
          </div>
        )}
      </div>

      {aiOpen && (
        <form
          onSubmit={onGenerateSubmit}
          className="cw-fade-up flex flex-col gap-3 rounded-md border border-[color:var(--status-ai-border)] bg-[color:var(--status-ai-bg)] p-4"
        >
          <div className="flex items-start gap-2 text-[13px] text-[color:var(--text-ai)]">
            <Sparkle
              className="mt-0.5 h-4 w-4 shrink-0"
              weight="fill"
              aria-hidden="true"
            />
            <p>
              Describe el reporte que necesitas. La IA selecciona los bloques,
              trae los datos y redacta el resumen ejecutivo. El plan se ejecuta
              dentro del workspace; ningún dato cruza tenant.
            </p>
          </div>
          <textarea
            value={aiPrompt}
            onChange={(e) => setAiPrompt(e.target.value)}
            placeholder="ej. Genera un resumen REPSE de mayo 2026 para los proveedores con SAT pendiente."
            rows={3}
            className="w-full resize-none rounded-sm border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2 text-[14px] text-[color:var(--text-primary)] outline-none focus:border-[color:var(--border-focus)]"
          />
          <div className="flex items-center gap-2">
            <Button
              type="submit"
              size="sm"
              disabled={
                !aiPrompt.trim() ||
                gen.state.status === "planning" ||
                gen.state.status === "streaming" ||
                gen.state.status === "saving"
              }
            >
              {gen.state.status === "planning" ||
              gen.state.status === "streaming" ||
              gen.state.status === "saving" ? (
                <CircleNotch
                  className="h-4 w-4 animate-spin"
                  weight="bold"
                  aria-hidden="true"
                />
              ) : (
                <Sparkle className="h-4 w-4" weight="bold" aria-hidden="true" />
              )}
              {gen.state.status === "planning"
                ? "Planeando…"
                : gen.state.status === "streaming"
                  ? "Generando…"
                  : gen.state.status === "saving"
                    ? "Guardando…"
                    : "Generar reporte"}
            </Button>
            {(gen.state.status === "streaming" ||
              gen.state.status === "planning") && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={gen.cancel}
              >
                <X className="h-4 w-4" weight="bold" aria-hidden="true" />
                Cancelar
              </Button>
            )}
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => {
                gen.reset();
                setAiOpen(false);
                setAiPrompt("");
              }}
            >
              Cerrar
            </Button>
            {gen.state.error && (
              <span className="text-[12px] text-[color:var(--status-error-text)]">
                {gen.state.error}
              </span>
            )}
          </div>
        </form>
      )}

      {explanation && (
        <div className="cw-fade-up rounded-md border border-[color:var(--status-ai-border)] bg-[color:var(--status-ai-bg)] p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="cw-eyebrow text-[color:var(--text-ai)]">
              Explicación · bloque {explanation.blockId.slice(0, 8)}
            </span>
            <button
              type="button"
              onClick={() => setExplanation(null)}
              aria-label="Cerrar explicación"
              className="rounded-sm p-1 text-[color:var(--text-tertiary)] hover:bg-[color:var(--surface-hover)]"
            >
              <X className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            </button>
          </div>
          <p className="cw-prose text-[13px] leading-relaxed text-[color:var(--text-primary)]">
            {explanation.text}
          </p>
        </div>
      )}

      {engine?.backend === "mock" && (
        <Alert variant="warning">
          <AlertTitle className="flex items-center gap-2">
            <WarningCircle className="h-4 w-4" weight="bold" aria-hidden="true" />
            Generación con IA no configurada en este entorno
          </AlertTitle>
          <AlertDescription>
            El motor de IA está en modo mock determinista (no hay
            <code className="mx-1 rounded-sm bg-[color:var(--surface-sunken)] px-1 font-mono text-[11px]">
              ANTHROPIC_API_KEY
            </code>
            configurada en el backend). Las acciones de IA (Generar, Copiloto,
            Regenerar, Explicar) producen texto canned para que la interfaz siga
            funcionando; verifícalo antes de compartir.
          </AlertDescription>
        </Alert>
      )}

      <ReportActionsContext.Provider
        value={{ onRefreshData, refreshingData }}
      >
        <div className="flex gap-0">
          <div className="flex-1">
            <Canvas
              content={content}
              editable={true}
              onChange={onCanvasChange}
              regeneratingBlockId={regeneratingBlockId}
              onRegenerateBlock={onRegenerateBlock}
              onExplainBlock={onExplainBlockClicked}
            />
          </div>
          {chatOpen && (
            <ChatCopilot
              reportId={reportId}
              content={content}
              onClose={() => setChatOpen(false)}
            />
          )}
        </div>
      </ReportActionsContext.Provider>
    </div>
  );
}

function GenerationBadge({
  status,
}: {
  status: "planning" | "streaming" | "saving" | "done" | "error" | "cancelled";
}) {
  switch (status) {
    case "planning":
      return (
        <span className="inline-flex items-center gap-1 font-mono text-[11px] text-[color:var(--text-ai)]">
          <CircleNotch
            className="h-3 w-3 animate-spin"
            weight="bold"
            aria-hidden="true"
          />
          planeando
        </span>
      );
    case "streaming":
      return (
        <span className="inline-flex items-center gap-1 font-mono text-[11px] text-[color:var(--text-ai)]">
          <Sparkle
            className="h-3 w-3 animate-pulse"
            weight="fill"
            aria-hidden="true"
          />
          generando
        </span>
      );
    case "saving":
      return (
        <span className="inline-flex items-center gap-1 font-mono text-[11px] text-[color:var(--text-ai)]">
          <CircleNotch
            className="h-3 w-3 animate-spin"
            weight="bold"
            aria-hidden="true"
          />
          guardando
        </span>
      );
    case "done":
      return (
        <span className="inline-flex items-center gap-1 font-mono text-[11px] text-[color:var(--status-success-text)]">
          <CheckCircle className="h-3 w-3" weight="fill" aria-hidden="true" />
          listo
        </span>
      );
    case "error":
      return (
        <span className="inline-flex items-center gap-1 font-mono text-[11px] text-[color:var(--status-error-text)]">
          <WarningCircle className="h-3 w-3" weight="fill" aria-hidden="true" />
          error
        </span>
      );
    case "cancelled":
      return (
        <span className="inline-flex items-center gap-1 font-mono text-[11px] text-[color:var(--text-tertiary)]">
          <X className="h-3 w-3" weight="bold" aria-hidden="true" />
          cancelado
        </span>
      );
  }
}
