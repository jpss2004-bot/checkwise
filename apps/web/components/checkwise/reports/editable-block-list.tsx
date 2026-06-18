"use client";

import type { ReactNode } from "react";
import { Reorder, useDragControls, type DragControls } from "motion/react";

import type { ReportBlock } from "@/lib/api/reports";

interface EditableBlockListProps {
  blocks: ReportBlock[];
  onReorder: (next: ReportBlock[]) => void;
  renderBody: (block: ReportBlock, dragControls?: DragControls) => ReactNode;
}

/**
 * The drag-reorderable block stack for the editable canvas.
 *
 * Split out of Canvas (F-BUNDLE-3) so the motion/react runtime — Reorder plus
 * the per-block drag controls — ships ONLY to the editor. Read-only, print,
 * and StoryView consumers render the static block map in Canvas itself and so
 * carry zero motion code. Canvas lazy-loads this via next/dynamic in its
 * editable branch.
 */
export function EditableBlockList({
  blocks,
  onReorder,
  renderBody,
}: EditableBlockListProps) {
  return (
    <Reorder.Group
      as="div"
      axis="y"
      values={blocks}
      onReorder={onReorder}
      className="space-y-6"
    >
      {blocks.map((block) => (
        <DraggableBlock key={block.id} block={block} renderBody={renderBody} />
      ))}
    </Reorder.Group>
  );
}

// Each block owns its own ``useDragControls()`` instance so the dots handle in
// the header can initiate a drag without React re-rendering every block on
// hover. ``dragListener={false}`` keeps the entire article from being a drag
// target — only the handle starts a drag, which means clicks inside the block
// body (table rows, lock/delete buttons) keep working normally. Locked blocks
// intentionally do NOT get a drag handle in the header.
function DraggableBlock({
  block,
  renderBody,
}: {
  block: ReportBlock;
  renderBody: (block: ReportBlock, dragControls?: DragControls) => ReactNode;
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
