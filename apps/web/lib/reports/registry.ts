/**
 * Frontend block registry — Phase 3.2.
 *
 * One definition per block type. The Canvas reads this registry to
 * populate the slash-menu palette and to render each block.
 *
 * Adding a new block: implement the React component under
 * `components/checkwise/reports/blocks/<type>.tsx`, then append a
 * BlockDefinition entry below.
 *
 * Backend mirror: apps/api/app/services/reports/blocks/<type>.py (lands
 * with the AI sub-phase, 3.3). The frontend can render the block
 * without the backend mirror — it just lacks server-side data
 * fetching + DOCX rendering, which is fine for the editor flow.
 */

import type { ComponentType } from "react";
import type { Icon } from "@phosphor-icons/react";

import type { ReportBlock } from "@/lib/api/reports";

/**
 * What every block component receives from the canvas.
 *
 * Generic over TConfig + TData so each block file can be strongly
 * typed against its own config shape. The registry below stores
 * components type-erased through `BlockComponent`.
 */
export interface BlockProps<TConfig = unknown, TData = unknown> {
  block: ReportBlock<TConfig> & { data?: TData };
  editable: boolean;
  /**
   * Patch the block's config or data in place. The canvas debounces
   * patches into the parent ReportContent. AI summary fields are
   * patched through a separate code path (Phase 3.3+).
   */
  onPatch: (patch: Partial<ReportBlock<TConfig>>) => void;
}

/**
 * Strongly-typed block definition. Used per-block as the export type
 * of each block module — the registry stores the erased form below.
 */
export interface BlockDefinition<TConfig = unknown, TData = unknown> {
  /** Discriminant. Matches backend block type. */
  type: string;
  /** Slash-menu display name. */
  label: string;
  /** Phosphor icon, regular weight. */
  icon: Icon;
  /** One-line description for the slash menu. */
  description: string;
  /** Default config when the user inserts a fresh block from the palette. */
  defaultConfig: TConfig;
  /** Renderer (canvas + print). */
  Component: ComponentType<BlockProps<TConfig, TData>>;
}

/**
 * Type-erased registry entry. Concrete blocks register through this
 * shape; the canvas trusts the type discriminant at runtime.
 */
type ErasedBlockDefinition = {
  type: string;
  label: string;
  icon: Icon;
  description: string;
  defaultConfig: unknown;
  Component: ComponentType<BlockProps>;
};

// Registry assembly. Imports live at the bottom so circular deps in
// individual block files (which sometimes import shared canvas types)
// resolve cleanly.

import { TextBlock, textDefinition } from "@/components/checkwise/reports/blocks/text";
import {
  DividerBlock,
  dividerDefinition,
} from "@/components/checkwise/reports/blocks/divider";
import {
  ExecutiveSummaryBlock,
  executiveSummaryDefinition,
} from "@/components/checkwise/reports/blocks/executive-summary";
import {
  KpiStripBlock,
  kpiStripDefinition,
} from "@/components/checkwise/reports/blocks/kpi-strip";
import {
  VendorRiskMatrixBlock,
  vendorRiskMatrixDefinition,
} from "@/components/checkwise/reports/blocks/vendor-risk-matrix";
import {
  AiRecommendationBlock,
  aiRecommendationDefinition,
} from "@/components/checkwise/reports/blocks/ai-recommendation";
import {
  ComplianceStateBlock,
  complianceStateDefinition,
} from "@/components/checkwise/reports/blocks/compliance-state";
import {
  AttentionListBlock,
  attentionListDefinition,
} from "@/components/checkwise/reports/blocks/attention-list";
import {
  UpcomingDeadlinesBlock,
  upcomingDeadlinesDefinition,
} from "@/components/checkwise/reports/blocks/upcoming-deadlines";
import {
  PrioritizedActionsBlock,
  prioritizedActionsDefinition,
} from "@/components/checkwise/reports/blocks/prioritized-actions";
import {
  ComplianceRadarBlock,
  complianceRadarDefinition,
} from "@/components/checkwise/reports/blocks/compliance-radar";
import {
  ComplianceOverviewBlock,
  complianceOverviewDefinition,
} from "@/components/checkwise/reports/blocks/compliance-overview";

function register<TConfig, TData>(
  partial: Omit<BlockDefinition<TConfig, TData>, "Component">,
  Component: ComponentType<BlockProps<TConfig, TData>>,
): ErasedBlockDefinition {
  return {
    ...partial,
    Component: Component as unknown as ComponentType<BlockProps>,
  };
}

export const BLOCK_REGISTRY: Record<string, ErasedBlockDefinition> = {
  [textDefinition.type]: register(textDefinition, TextBlock),
  [dividerDefinition.type]: register(dividerDefinition, DividerBlock),
  [executiveSummaryDefinition.type]: register(
    executiveSummaryDefinition,
    ExecutiveSummaryBlock,
  ),
  [kpiStripDefinition.type]: register(kpiStripDefinition, KpiStripBlock),
  [vendorRiskMatrixDefinition.type]: register(
    vendorRiskMatrixDefinition,
    VendorRiskMatrixBlock,
  ),
  [aiRecommendationDefinition.type]: register(
    aiRecommendationDefinition,
    AiRecommendationBlock,
  ),
  [complianceStateDefinition.type]: register(
    complianceStateDefinition,
    ComplianceStateBlock,
  ),
  [attentionListDefinition.type]: register(
    attentionListDefinition,
    AttentionListBlock,
  ),
  [upcomingDeadlinesDefinition.type]: register(
    upcomingDeadlinesDefinition,
    UpcomingDeadlinesBlock,
  ),
  [prioritizedActionsDefinition.type]: register(
    prioritizedActionsDefinition,
    PrioritizedActionsBlock,
  ),
  [complianceRadarDefinition.type]: register(
    complianceRadarDefinition,
    ComplianceRadarBlock,
  ),
  [complianceOverviewDefinition.type]: register(
    complianceOverviewDefinition,
    ComplianceOverviewBlock,
  ),
};

/** Slash-menu order. New blocks append. */
export const PALETTE_ORDER: string[] = [
  // 2026-06-03 — the deterministic compliance_overview band leads the
  // cliente palette: it's the scannable cover-stat block authors reach
  // for first when composing a portfolio report.
  complianceOverviewDefinition.type,
  // M4 (2026-06-02) — radar leads the cliente Resumen ejecutivo so
  // it's the first block authors think to insert when composing a
  // portfolio report manually.
  complianceRadarDefinition.type,
  complianceStateDefinition.type,
  attentionListDefinition.type,
  upcomingDeadlinesDefinition.type,
  prioritizedActionsDefinition.type,
  textDefinition.type,
  executiveSummaryDefinition.type,
  kpiStripDefinition.type,
  vendorRiskMatrixDefinition.type,
  aiRecommendationDefinition.type,
  dividerDefinition.type,
];

export function getBlockDefinition(type: string): ErasedBlockDefinition | undefined {
  return BLOCK_REGISTRY[type];
}
