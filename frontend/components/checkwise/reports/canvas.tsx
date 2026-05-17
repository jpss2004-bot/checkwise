"use client";

import { useCallback, useState } from "react";
import { Plus, Sparkle } from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";
import type { ReportBlock, ReportContent } from "@/lib/api/reports";
import {
  BLOCK_REGISTRY,
  PALETTE_ORDER,
  getBlockDefinition,
} from "@/lib/reports/registry";
import { BlockHeader } from "@/components/checkwise/reports/block-header";

/**
 * Canvas — the report editor surface for Phase 3.2.
 *
 * Renders a vertical stack of blocks. Each block is rendered through
 * the registry. Editable mode adds a per-block header (drag/lock/
 * delete) and a "+ Add block" palette at the bottom.
 *
 * Phase 3.2 deliberately does NOT use BlockNote's prose editor model
 * — compliance blocks are atomic and typed, not text-rich. BlockNote
 * stays installed for the `text` block's prose mode polish in 3.5.
 *
 * Autosave + versioning rules from VISUAL_DIRECTION_2_X.md §9.3 land
 * in Phase 3.5. For 3.2 the Canvas calls onChange on every edit; the
 * parent page debounces + persists.
 */

interface CanvasProps {
  content: ReportContent;
  editable: boolean;
  onChange: (next: ReportContent) => void;
}

export function Canvas({ content, editable, onChange }: CanvasProps) {
  const [paletteOpen, setPaletteOpen] = useState(false);

  const patchBlock = useCallback(
    (blockId: string, patch: Partial<ReportBlock>) => {
      const blocks = content.blocks.map((b) =>
        b.id === blockId ? { ...b, ...patch, config: patch.config ?? b.config } : b,
      );
      onChange({ ...content, blocks });
    },
    [content, onChange],
  );

  const deleteBlock = useCallback(
    (blockId: string) => {
      onChange({
        ...content,
        blocks: content.blocks.filter((b) => b.id !== blockId),
      });
    },
    [content, onChange],
  );

  const toggleLock = useCallback(
    (blockId: string) => {
      patchBlock(blockId, {
        locked: !content.blocks.find((b) => b.id === blockId)?.locked,
      });
    },
    [content, patchBlock],
  );

  const insertBlock = useCallback(
    (type: string) => {
      const def = BLOCK_REGISTRY[type];
      if (!def) return;
      const id = cryptoUuid();
      const next: ReportBlock = {
        id,
        type,
        config: structuredClone(def.defaultConfig),
        ai_summary: null,
        layout: { width: "full" },
      };
      onChange({ ...content, blocks: [...content.blocks, next] });
      setPaletteOpen(false);
    },
    [content, onChange],
  );

  return (
    <div className="space-y-6">
      {content.blocks.length === 0 ? (
        <EmptyCanvas editable={editable} />
      ) : (
        content.blocks.map((block) => {
          const def = getBlockDefinition(block.type);
          if (!def) {
            return (
              <UnknownBlock key={block.id} type={block.type} />
            );
          }
          const BlockComponent = def.Component;
          return (
            <article
              key={block.id}
              className="cw-fade-up group/block space-y-2"
              data-block-id={block.id}
              data-block-type={block.type}
            >
              <BlockHeader
                type={block.type}
                label={def.label}
                icon={def.icon}
                locked={block.locked}
                editable={editable}
                onLockToggle={() => toggleLock(block.id)}
                onDelete={() => deleteBlock(block.id)}
              />
              <BlockComponent
                block={block}
                editable={editable && !block.locked}
                onPatch={(patch) => patchBlock(block.id, patch)}
              />
              {block.ai_summary && (
                <div className="flex items-center gap-1.5 text-[11px] text-[color:var(--text-ai)]">
                  <Sparkle className="h-3 w-3" weight="fill" aria-hidden="true" />
                  <span>Generado por IA · Verificar antes de compartir</span>
                </div>
              )}
            </article>
          );
        })
      )}

      {editable && (
        <div className="border-t border-dashed border-[color:var(--border-subtle)] pt-4">
          {paletteOpen ? (
            <BlockPalette
              onPick={insertBlock}
              onCancel={() => setPaletteOpen(false)}
            />
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPaletteOpen(true)}
            >
              <Plus className="h-4 w-4" weight="bold" aria-hidden="true" />
              Añadir bloque
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Empty state ────────────────────────────────────────────────

function EmptyCanvas({ editable }: { editable: boolean }) {
  return (
    <div className="rounded-md border border-dashed border-[color:var(--border-subtle)] py-16 text-center">
      <Sparkle
        className="mx-auto mb-2 h-6 w-6 text-[color:var(--text-ai)]"
        weight="fill"
        aria-hidden="true"
      />
      <p className="text-[14px] font-medium text-[color:var(--text-primary)]">
        Lienzo vacío
      </p>
      <p className="mt-1 text-[13px] text-[color:var(--text-secondary)]">
        {editable
          ? "Empieza añadiendo un bloque o pídele al copiloto que arme el reporte por ti."
          : "Aún no hay contenido en este reporte."}
      </p>
    </div>
  );
}

// ─── Unknown block fallback ─────────────────────────────────────

function UnknownBlock({ type }: { type: string }) {
  return (
    <article className="rounded-sm border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] p-3 text-[13px] text-[color:var(--status-warning-text)]">
      Bloque de tipo desconocido:{" "}
      <code className="font-mono text-[11px]">{type}</code>. Actualiza la app
      para verlo.
    </article>
  );
}

// ─── Palette ────────────────────────────────────────────────────

function BlockPalette({
  onPick,
  onCancel,
}: {
  onPick: (type: string) => void;
  onCancel: () => void;
}) {
  return (
    <div className="rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-3 shadow-[var(--shadow-sm)]">
      <div className="mb-2 flex items-center justify-between">
        <span className="cw-eyebrow">Añadir bloque</span>
        <button
          type="button"
          onClick={onCancel}
          className="text-[11px] text-[color:var(--text-tertiary)] hover:text-[color:var(--text-primary)]"
        >
          Cerrar
        </button>
      </div>
      <ul className="space-y-1">
        {PALETTE_ORDER.map((type) => {
          const def = BLOCK_REGISTRY[type];
          if (!def) return null;
          const IconComponent = def.icon;
          return (
            <li key={type}>
              <button
                type="button"
                onClick={() => onPick(type)}
                className="flex w-full items-start gap-3 rounded-sm px-2 py-1.5 text-left hover:bg-[color:var(--surface-hover)]"
              >
                <IconComponent
                  className="mt-0.5 h-4 w-4 text-[color:var(--text-secondary)]"
                  weight="regular"
                  aria-hidden="true"
                />
                <div className="min-w-0">
                  <div className="text-[13px] font-medium text-[color:var(--text-primary)]">
                    {def.label}
                  </div>
                  <div className="text-[11px] text-[color:var(--text-tertiary)]">
                    {def.description}
                  </div>
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ─── ID helper ──────────────────────────────────────────────────

function cryptoUuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // Fallback for older runtimes — not as strong but stable.
  return `block-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`;
}
