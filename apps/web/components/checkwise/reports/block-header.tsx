"use client";

import {
  ChatCircle,
  DotsSixVertical,
  Lock,
  LockOpen,
  Sparkle,
  Trash,
} from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";
import type { DragControls } from "motion/react";

/**
 * Shared block chrome. Sits above each rendered block and carries the
 * actions every block supports: drag handle, label, lock toggle,
 * delete. AI-aware blocks also get Regenerate + Explain.
 */

interface BlockHeaderProps {
  /**
   * The block's machine type (e.g. "kpi_strip"). Kept on the API for
   * future surfaces that may want it, but the human-readable `label`
   * is what we render. Drop this prop if no caller ever needs it again.
   */
  type?: string;
  label: string;
  icon: Icon;
  locked?: boolean;
  editable: boolean;
  /** Block carries an ai_summary field — show Regenerate. */
  hasAiSummary?: boolean;
  onLockToggle?: () => void;
  onDelete?: () => void;
  onRegenerate?: () => void;
  onExplain?: () => void;
  regenerating?: boolean;
  /**
   * R5: motion/react drag controls owned by the parent Reorder.Item.
   * When present, the DotsSixVertical handle initiates a drag via
   * ``controls.start(event)``; when absent (e.g. locked block, read-
   * only canvas) the handle renders as a passive visual cue.
   */
  dragControls?: DragControls;
}

export function BlockHeader({
  label,
  icon: IconComponent,
  locked,
  editable,
  hasAiSummary,
  onLockToggle,
  onDelete,
  onRegenerate,
  onExplain,
  regenerating,
  dragControls,
}: BlockHeaderProps) {
  // F1 (2026-05-19 visual audit): in read-only / print mode, drop the
  // whole header chrome. Blocks already carry their own internal titles
  // (h2 in Executive Summary, label rows in KPI strip, etc.) so the
  // eyebrow type-label ("TEXTO", "TIRA DE KPIS", "DIVISOR", …) only
  // added wireframe noise on the printable surface.
  if (!editable) return null;

  return (
    <div className="group/blockheader flex items-center justify-between border-b border-[color:var(--border-subtle)] pb-1 text-[color:var(--text-tertiary)]">
      <div className="flex items-center gap-2">
        {/* R5: when ``dragControls`` is provided, the dots handle
            initiates a Reorder.Item drag on pointerdown. Without
            controls (locked block or read-only mode) the handle is
            rendered as a passive visual cue — never interactive. We
            also clamp touch-action so finger drags don't fight the
            page's scroll gesture. */}
        {dragControls ? (
          <button
            type="button"
            onPointerDown={(event) => dragControls.start(event)}
            className="cursor-grab touch-none rounded-sm p-0.5 text-[color:var(--text-tertiary)] opacity-0 transition-opacity group-hover/blockheader:opacity-100 hover:bg-[color:var(--surface-hover)] active:cursor-grabbing"
            aria-label="Arrastrar para reordenar"
            title="Arrastrar para reordenar"
          >
            <DotsSixVertical className="h-4 w-4" weight="regular" aria-hidden="true" />
          </button>
        ) : (
          <DotsSixVertical
            className="h-4 w-4 opacity-0 transition-opacity group-hover/blockheader:opacity-100"
            weight="regular"
            aria-hidden="true"
          />
        )}
        <IconComponent className="h-3.5 w-3.5" weight="regular" aria-hidden="true" />
        {/* R3 (softer labels): dropped the uppercase mono eyebrow —
            authoring chrome was reading like a Figma layer panel. The
            sentence-case sans label keeps enough context for the
            editor without screaming system terminology at non-author
            viewers who are skimming the canvas. */}
        <span className="text-[12px] font-medium text-[color:var(--text-tertiary)] print:hidden">
          {label}
        </span>
      </div>
      <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover/blockheader:opacity-100">
        {onExplain && (
          <button
            type="button"
            onClick={onExplain}
            className="rounded-sm p-1 text-[color:var(--text-ai)] hover:bg-[color:var(--status-ai-bg)]"
            aria-label="Explicar bloque"
            title="Explicar este bloque con IA"
          >
            <ChatCircle className="h-3.5 w-3.5" weight="regular" aria-hidden="true" />
          </button>
        )}
        {hasAiSummary && onRegenerate && (
          <button
            type="button"
            onClick={onRegenerate}
            disabled={regenerating}
            className="rounded-sm p-1 text-[color:var(--text-ai)] hover:bg-[color:var(--status-ai-bg)] disabled:opacity-50"
            aria-label="Regenerar resumen IA"
            title="Regenerar el resumen con IA"
          >
            <Sparkle
              className={`h-3.5 w-3.5 ${regenerating ? "animate-spin" : ""}`}
              weight="bold"
              aria-hidden="true"
            />
          </button>
        )}
        {onLockToggle && (
          <button
            type="button"
            onClick={onLockToggle}
            className="rounded-sm p-1 hover:bg-[color:var(--surface-hover)]"
            aria-label={locked ? "Desbloquear bloque" : "Bloquear bloque"}
            title={locked ? "Desbloquear bloque" : "Bloquear bloque"}
          >
            {locked ? (
              <Lock className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            ) : (
              <LockOpen className="h-3.5 w-3.5" weight="regular" aria-hidden="true" />
            )}
          </button>
        )}
        {onDelete && (
          <button
            type="button"
            onClick={onDelete}
            className="rounded-sm p-1 text-[color:var(--status-error-text)] hover:bg-[color:var(--status-error-bg)]"
            aria-label="Eliminar bloque"
            title="Eliminar bloque"
          >
            <Trash className="h-3.5 w-3.5" weight="regular" aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
}
