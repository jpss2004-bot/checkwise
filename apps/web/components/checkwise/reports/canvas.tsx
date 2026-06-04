"use client";

import { useCallback, useState } from "react";
import { Plus, Sparkle } from "@phosphor-icons/react";
import { Reorder, useDragControls, type DragControls } from "motion/react";

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
  /**
   * Whether block items render their action CTAs (e.g. the "Subir"
   * upload link). True only when the audience is the provider itself
   * (``vendor_facing``); otherwise blocks render as read-only findings.
   * Defaults to true so existing callers are unchanged.
   */
  interactive?: boolean;
  /** Block types that carry an AI summary (per backend ai_summaries.py). */
  aiAwareTypes?: string[];
  /** Block currently being regenerated. */
  regeneratingBlockId?: string | null;
  /** Per-block actions; if omitted the action button is hidden. */
  onRegenerateBlock?: (blockId: string) => void;
  onExplainBlock?: (blockId: string) => void;
}

const DEFAULT_AI_AWARE_TYPES = ["executive_summary", "ai_recommendation"];

export function Canvas({
  content,
  editable,
  onChange,
  interactive = true,
  aiAwareTypes = DEFAULT_AI_AWARE_TYPES,
  regeneratingBlockId = null,
  onRegenerateBlock,
  onExplainBlock,
}: CanvasProps) {
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

  // R5 (drag-drop reordering): motion/react's Reorder.Group hands us
  // the reordered ``ReportBlock[]`` directly; we just splice it into
  // the content envelope. The page-level autosave picks it up like any
  // other canvas edit.
  const onReorder = useCallback(
    (nextBlocks: ReportBlock[]) => {
      onChange({ ...content, blocks: nextBlocks });
    },
    [content, onChange],
  );

  // Shared per-block render — used by both the static (read-only) path
  // and each Reorder.Item in the editable path. Centralising it keeps
  // the two paths from drifting on prop wiring.
  const renderBlockBody = (
    block: ReportBlock,
    dragControls?: DragControls,
  ) => {
    const def = getBlockDefinition(block.type);
    if (!def) return <UnknownBlock key={block.id} type={block.type} />;
    const BlockComponent = def.Component;
    return (
      <>
        <BlockHeader
          type={block.type}
          label={def.label}
          icon={def.icon}
          locked={block.locked}
          editable={editable}
          hasAiSummary={aiAwareTypes.includes(block.type)}
          regenerating={regeneratingBlockId === block.id}
          onLockToggle={() => toggleLock(block.id)}
          onDelete={() => deleteBlock(block.id)}
          onRegenerate={
            onRegenerateBlock && aiAwareTypes.includes(block.type)
              ? () => onRegenerateBlock(block.id)
              : undefined
          }
          onExplain={onExplainBlock ? () => onExplainBlock(block.id) : undefined}
          dragControls={dragControls}
        />
        <BlockComponent
          block={block}
          editable={editable && !block.locked}
          interactive={interactive}
          onPatch={(patch) => patchBlock(block.id, patch)}
        />
        {/* The generic per-block AI label was removed (2026-06-03): the
            only AI-bearing blocks — executive_summary and ai_recommendation
            — now render their own labelled caption ("Lectura del equipo ·
            IA" / "Generado por IA · Verificar antes de compartir"), so this
            duplicated the warning right beneath them. */}
      </>
    );
  };

  return (
    <div className="space-y-6">
      {content.blocks.length === 0 ? (
        <EmptyCanvas editable={editable} />
      ) : editable ? (
        <Reorder.Group
          as="div"
          axis="y"
          values={content.blocks}
          onReorder={onReorder}
          className="space-y-6"
        >
          {content.blocks.map((block) => (
            <DraggableBlock
              key={block.id}
              block={block}
              renderBody={renderBlockBody}
            />
          ))}
        </Reorder.Group>
      ) : (
        content.blocks.map((block) => {
          const def = getBlockDefinition(block.type);
          if (!def) return <UnknownBlock key={block.id} type={block.type} />;
          return (
            <article
              key={block.id}
              className="cw-fade-up group/block space-y-2"
              data-block-id={block.id}
              data-block-type={block.type}
            >
              {renderBlockBody(block)}
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

// ─── Draggable block wrapper ───────────────────────────────────
//
// Each block owns its own ``useDragControls()`` instance so the dots
// handle in the header can initiate a drag without React re-rendering
// every block on hover. ``dragListener={false}`` keeps the entire
// article from being a drag target — only the handle starts a drag,
// which means clicks inside the block body (table rows, BlockNote
// editor, lock/delete buttons) keep working normally.
//
// Locked blocks intentionally do NOT get a drag handle in the header
// because they're meant to stay where the user pinned them.
function DraggableBlock({
  block,
  renderBody,
}: {
  block: ReportBlock;
  renderBody: (
    block: ReportBlock,
    dragControls?: DragControls,
  ) => React.ReactNode;
}) {
  const controls = useDragControls();
  return (
    <Reorder.Item
      as="article"
      value={block}
      dragListener={false}
      dragControls={controls}
      className="cw-fade-up group/block space-y-2"
      data-block-id={block.id}
      data-block-type={block.type}
    >
      {renderBody(block, block.locked ? undefined : controls)}
    </Reorder.Item>
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
