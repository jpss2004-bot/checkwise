"use client";

import { CheckCircle, FilePdf } from "@phosphor-icons/react";

/**
 * Report-export progress overlay.
 *
 * Shown while a PDF export is being rendered server-side for Download or
 * Vista previa. Server PDF rendering can take several seconds (longer on a
 * cold start), so a bare button spinner under-communicates — this surfaces
 * the real export phase (queued → rendering → finalizing) so the user
 * knows work is happening and nothing is stuck. Phases mirror the export
 * row's status; "backend truth", not a fake timer.
 *
 * Register: product. Teal carries the "Wise"/generation moment; navy scrim
 * for structure; motion clarifies state (no decorative glow/gradient).
 */

export type ExportPhase = "queued" | "rendering" | "finalizing";

const STEPS: { key: ExportPhase; label: string }[] = [
  { key: "queued", label: "En cola" },
  { key: "rendering", label: "Renderizando el documento" },
  { key: "finalizing", label: "Finalizando" },
];

const PHASE_INDEX: Record<ExportPhase, number> = {
  queued: 0,
  rendering: 1,
  finalizing: 2,
};

export function ReportExportOverlay({
  open,
  mode,
  phase,
}: {
  open: boolean;
  mode: "download" | "preview";
  phase: ExportPhase;
}) {
  if (!open) return null;
  const activeIndex = PHASE_INDEX[phase];
  const title =
    mode === "download" ? "Generando tu PDF" : "Preparando la vista previa";

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={title}
      className="cw-fade-in fixed inset-0 z-[100] flex items-center justify-center p-4"
      style={{ background: "hsl(var(--navy-950) / 0.55)" }}
    >
      <div className="cw-fade-up w-full max-w-sm rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-[0_24px_60px_-24px_hsl(var(--navy-950)/0.45)]">
        <div className="flex items-center gap-3">
          <span className="cw-pulse-soft inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-[color:var(--surface-ai-muted)] text-[color:var(--text-ai)]">
            <FilePdf className="h-5 w-5" weight="duotone" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-[color:var(--text-ai)]">
              CheckWise · Reporte
            </p>
            <h2 className="text-[15px] font-semibold tracking-tight text-[color:var(--text-primary)]">
              {title}
            </h2>
          </div>
        </div>

        {/* Indeterminate sweep — the render has no reliable percentage, so
            we signal liveness rather than fake a number. */}
        <div className="mt-5 h-1 overflow-hidden rounded-full bg-[color:var(--surface-sunken)]">
          <div className="cw-indeterminate h-full w-2/5 rounded-full bg-[color:var(--interactive-ai)]" />
        </div>

        <ol className="mt-5 space-y-2.5">
          {STEPS.map((step, i) => {
            const done = i < activeIndex;
            const current = i === activeIndex;
            return (
              <li key={step.key} className="flex items-center gap-2.5">
                <span
                  aria-hidden="true"
                  className={
                    done
                      ? "inline-flex h-4 w-4 items-center justify-center rounded-full text-[color:var(--text-ai)]"
                      : current
                        ? "cw-pulse-soft inline-flex h-4 w-4 items-center justify-center rounded-full border-2 border-[color:var(--border-ai)]"
                        : "inline-flex h-4 w-4 items-center justify-center rounded-full border-2 border-[color:var(--border-default)]"
                  }
                >
                  {done ? (
                    <CheckCircle className="h-4 w-4" weight="fill" />
                  ) : null}
                </span>
                <span
                  className={
                    current
                      ? "text-[13px] font-medium text-[color:var(--text-primary)]"
                      : done
                        ? "text-[13px] text-[color:var(--text-secondary)]"
                        : "text-[13px] text-[color:var(--text-tertiary)]"
                  }
                >
                  {step.label}
                </span>
              </li>
            );
          })}
        </ol>

        <p className="mt-5 text-[12px] leading-relaxed text-[color:var(--text-tertiary)]">
          La primera descarga puede tardar unos segundos mientras
          preparamos el motor de render. No cierres esta ventana.
        </p>
      </div>
    </div>
  );
}
