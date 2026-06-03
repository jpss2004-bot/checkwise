"use client";

import { Buildings } from "@phosphor-icons/react";

import { FreshnessLabel } from "@/components/checkwise/reports/freshness-label";
import type { BlockDefinition, BlockProps } from "@/lib/reports/registry";

/**
 * compliance_by_institution — the "por área de cumplimiento" view that
 * real GRC reports lead with, rendered as one stacked bar per
 * institution (SAT / IMSS / INFONAVIT / STPS-REPSE), split al día / en
 * proceso / en riesgo.
 *
 * Scope-adaptive on the backend: a cliente/interno report rolls up the
 * whole portfolio; a proveedor report shows that provider's own
 * documents — so the same block carries the deterministic, graphic,
 * no-AI principle into every portal. Pure counts; nothing to
 * hallucinate. Hand-rolled SVG/CSS, no chart library.
 */

interface ComplianceByInstitutionConfig {
  // No config — the block always renders every canonical institution.
  [k: string]: unknown;
}

interface InstitutionRow {
  code: string;
  label: string;
  al_dia: number;
  en_proceso: number;
  en_riesgo: number;
  total: number;
}

interface ComplianceByInstitutionData {
  scope_kind?: "vendor" | "client";
  institutions?: InstitutionRow[];
  fetched_at?: string | null;
}

export const complianceByInstitutionDefinition: Omit<
  BlockDefinition<ComplianceByInstitutionConfig, ComplianceByInstitutionData>,
  "Component"
> = {
  type: "compliance_by_institution",
  label: "Cumplimiento por institución",
  icon: Buildings,
  description:
    "Barras por institución (SAT / IMSS / INFONAVIT / STPS) al día / en proceso / en riesgo. Solo datos, sin IA.",
  defaultConfig: {},
};

const SEGMENTS: Array<{
  key: "al_dia" | "en_proceso" | "en_riesgo";
  label: string;
  color: string;
}> = [
  { key: "al_dia", label: "Al día", color: "var(--status-success-text)" },
  { key: "en_proceso", label: "En proceso", color: "var(--status-warning-text)" },
  { key: "en_riesgo", label: "En riesgo", color: "var(--status-error-text)" },
];

export function ComplianceByInstitutionBlock({
  block,
}: BlockProps<ComplianceByInstitutionConfig, ComplianceByInstitutionData>) {
  const data = block.data;
  const institutions = data?.institutions ?? [];

  if (!data || institutions.length === 0) {
    return (
      <section
        className="space-y-2 py-2"
        data-block-type="compliance_by_institution"
      >
        <p className="cw-eyebrow">Cumplimiento por institución</p>
        <div className="border-y border-[color:var(--border-subtle)] py-6 text-center text-[13px] text-[color:var(--text-tertiary)]">
          Aún no hay documentos registrados por institución.
        </div>
      </section>
    );
  }

  const maxTotal = Math.max(1, ...institutions.map((i) => i.total));

  return (
    <section
      className="space-y-3 py-2 print:break-inside-avoid"
      data-block-type="compliance_by_institution"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="cw-eyebrow">Cumplimiento por institución</p>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-[color:var(--text-secondary)]">
          {SEGMENTS.map((s) => (
            <span key={s.key} className="inline-flex items-center gap-1">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ backgroundColor: s.color }}
                aria-hidden="true"
              />
              {s.label}
            </span>
          ))}
        </div>
      </div>

      <ul className="space-y-2.5">
        {institutions.map((inst) => (
          <li key={inst.code} className="flex items-center gap-3">
            <span className="w-20 shrink-0 truncate font-mono text-[11px] uppercase tracking-wide text-[color:var(--text-secondary)]">
              {inst.label}
            </span>
            <div className="flex flex-1 items-center gap-2">
              {/* Bar width is proportional to the institution's total so
                  volume reads across rows; segments split the semáforo. */}
              <span
                className="flex h-2.5 overflow-hidden rounded-full bg-[color:var(--surface-hover)]"
                style={{ width: `${Math.max(4, (inst.total / maxTotal) * 100)}%` }}
              >
                {inst.total > 0
                  ? SEGMENTS.map((s) =>
                      inst[s.key] > 0 ? (
                        <span
                          key={s.key}
                          className="block h-full"
                          style={{
                            width: `${(inst[s.key] / inst.total) * 100}%`,
                            backgroundColor: s.color,
                          }}
                          title={`${s.label}: ${inst[s.key]}`}
                        />
                      ) : null,
                    )
                  : null}
              </span>
              <span className="shrink-0 font-mono text-[11px] tabular-nums text-[color:var(--text-tertiary)]">
                {inst.total > 0 ? (
                  <>
                    {inst.total}
                    {inst.en_riesgo > 0 ? (
                      <span className="text-[color:var(--status-error-text)]">
                        {" "}
                        · {inst.en_riesgo} en riesgo
                      </span>
                    ) : null}
                  </>
                ) : (
                  "—"
                )}
              </span>
            </div>
          </li>
        ))}
      </ul>

      <FreshnessLabel fetchedAt={data.fetched_at} />
    </section>
  );
}
