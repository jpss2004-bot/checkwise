"use client";

import {
  CheckCircle,
  Info,
  Warning,
  WarningOctagon,
  type Icon,
} from "@phosphor-icons/react";

import type { BlockDefinition, BlockProps } from "@/lib/reports/registry";

/**
 * Key findings — the "lo más importante" callouts that follow the verdict.
 * Two or three tone-coloured, scannable cards naming the things that actually
 * matter (the worst provider + its issue, a renewal coming due, the review
 * backlog…). Computed deterministically in services/reports/insights.py.
 */

type Tone = "red" | "yellow" | "green" | "info";

interface Finding {
  tone: Tone;
  title: string;
  detail: string;
}

interface FindingsData {
  findings?: Finding[];
}

export const keyFindingsDefinition: Omit<
  BlockDefinition<Record<string, never>, FindingsData>,
  "Component"
> = {
  type: "key_findings",
  label: "Lo más importante",
  icon: WarningOctagon,
  description: "Los 2-3 hallazgos que más importan, con su severidad.",
  defaultConfig: {},
};

const TONE: Record<Tone, { color: string; Icon: Icon }> = {
  red: { color: "var(--state-red,#dc2626)", Icon: WarningOctagon },
  yellow: { color: "var(--state-yellow,#d97706)", Icon: Warning },
  green: { color: "var(--state-green,#16a34a)", Icon: CheckCircle },
  info: { color: "var(--text-ai)", Icon: Info },
};

export function KeyFindingsBlock({
  block,
}: BlockProps<Record<string, never>, FindingsData>) {
  const findings = block.data?.findings ?? [];
  if (findings.length === 0) return null;

  return (
    <div className="space-y-2">
      <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">
        Lo más importante
      </p>
      <ul className="space-y-2">
        {findings.map((f, i) => {
          const t = TONE[f.tone] ?? TONE.info;
          const FindingIcon = t.Icon;
          return (
            <li
              key={i}
              className="flex items-start gap-3 rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] p-3"
            >
              <FindingIcon
                className="mt-0.5 h-5 w-5 shrink-0"
                weight="fill"
                style={{ color: t.color }}
                aria-hidden="true"
              />
              <div className="min-w-0">
                <p className="text-[13px] font-semibold text-[color:var(--text-primary)]">
                  {f.title}
                </p>
                <p className="text-[12px] leading-snug text-[color:var(--text-secondary)]">
                  {f.detail}
                </p>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
