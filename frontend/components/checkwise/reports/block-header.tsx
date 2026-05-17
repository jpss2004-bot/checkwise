"use client";

import {
  ArrowsOutSimple,
  ChatCircle,
  DotsSixVertical,
  Lock,
  LockOpen,
  Sparkle,
  Trash,
} from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";

/**
 * Shared block chrome. Sits above each rendered block and carries the
 * actions every block supports: drag handle, label, lock toggle,
 * delete. AI-aware blocks also get Regenerate + Explain.
 */

interface BlockHeaderProps {
  type: string;
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
}

export function BlockHeader({
  type,
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
}: BlockHeaderProps) {
  return (
    <div className="group/blockheader flex items-center justify-between border-b border-[color:var(--border-subtle)] pb-1 text-[color:var(--text-tertiary)]">
      <div className="flex items-center gap-2">
        {editable && (
          <DotsSixVertical
            className="h-4 w-4 cursor-grab opacity-0 transition-opacity group-hover/blockheader:opacity-100"
            weight="regular"
            aria-hidden="true"
          />
        )}
        <IconComponent className="h-3.5 w-3.5" weight="regular" aria-hidden="true" />
        <span className="cw-eyebrow">{label}</span>
        <span className="font-mono text-[10px] text-[color:var(--text-tertiary)]">
          {type}
        </span>
      </div>
      {editable && (
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
      )}
      {!editable && (
        <ArrowsOutSimple className="h-3.5 w-3.5" weight="regular" aria-hidden="true" />
      )}
    </div>
  );
}
