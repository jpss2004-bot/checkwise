"use client";

import { Table } from "@phosphor-icons/react";

import { BlockIntro } from "@/components/checkwise/reports/block-intro";
import { FreshnessLabel } from "@/components/checkwise/reports/freshness-label";
import type { BlockDefinition, BlockProps } from "@/lib/reports/registry";

/**
 * Vendor risk matrix — the flagship table block. Rows are vendors,
 * columns are institutions (SAT/IMSS/INFONAVIT/STPS-REPSE) plus a
 * derived risk score and a last-event timestamp.
 *
 * Phase 3.2 ships the rendering shell. The data_fetcher (Phase 3.3)
 * resolves the filter into actual rows; until then the block accepts
 * caller-provided rows or renders an empty state.
 *
 * Composition follows VISUAL_DIRECTION_2_X.md §"Layout doctrine":
 * full borders top/bottom, no card chrome, mono for IDs + timestamps,
 * status pills with tint-only (no border by default).
 */

type DocumentStateCode =
  | "pending"
  | "uploaded"
  | "in_review"
  | "approved"
  | "rejected"
  | "expired"
  | "needs_review"
  | "empty";

type InstitutionCode = "sat" | "imss" | "infonavit" | "stps_repse";

interface VendorRiskMatrixConfig {
  filter: {
    missing_institution?: InstitutionCode;
    min_risk_score?: number;
  };
  columns: Array<InstitutionCode | "risk_score" | "last_event">;
  sort: "risk_desc" | "risk_asc" | "name";
  max_rows: number;
}

interface VendorRiskMatrixData {
  rows: Array<{
    vendor_id: string;
    // Nullable: the backend masks vendor identity for vendor_facing /
    // external_signed audiences (a provider must not see other named
    // vendors). client_facing + internal_only carry the real name.
    vendor_name: string | null;
    vendor_rfc: string | null;
    risk_score: number;
    cells: Record<
      string,
      { state: DocumentStateCode; age_days: number; period: string }
    >;
    last_event_at: string;
  }>;
  /** P1.7: ISO8601 stamp from the backend fetcher. */
  fetched_at?: string | null;
}

const INSTITUTION_LABEL: Record<InstitutionCode, string> = {
  sat: "SAT",
  imss: "IMSS",
  infonavit: "INFONAVIT",
  stps_repse: "STPS",
};

// R4 (user-language taxonomy): chips in the risk matrix go in front of
// auditors and executives — replaced punitive / vague terms with what
// the reader actually needs to know ("Con observaciones" instead of
// "Rechazado"; "Pendiente aclaración" instead of the cryptic "Acción").
// State codes stay unchanged on the wire so the backend contract is
// untouched.
const STATE_TONE: Record<
  DocumentStateCode,
  { bg: string; text: string; label: string }
> = {
  pending: {
    bg: "bg-[color:var(--doc-pending-bg)]",
    text: "text-[color:var(--doc-pending-text)]",
    label: "Por entregar",
  },
  uploaded: {
    bg: "bg-[color:var(--doc-uploaded-bg)]",
    text: "text-[color:var(--doc-uploaded-text)]",
    label: "En revisión",
  },
  in_review: {
    bg: "bg-[color:var(--doc-in-review-bg)]",
    text: "text-[color:var(--doc-in-review-text)]",
    label: "En revisión",
  },
  approved: {
    bg: "bg-[color:var(--doc-approved-bg)]",
    text: "text-[color:var(--doc-approved-text)]",
    label: "Aprobado",
  },
  rejected: {
    bg: "bg-[color:var(--doc-rejected-bg)]",
    text: "text-[color:var(--doc-rejected-text)]",
    label: "Requiere corrección",
  },
  expired: {
    bg: "bg-[color:var(--doc-expired-bg)]",
    text: "text-[color:var(--doc-expired-text)]",
    label: "Vencido",
  },
  needs_review: {
    bg: "bg-[color:var(--doc-needs-review-bg)]",
    text: "text-[color:var(--doc-needs-review-text)]",
    label: "Necesita aclaración",
  },
  empty: {
    bg: "bg-[color:var(--doc-empty-bg)]",
    text: "text-[color:var(--doc-empty-text)]",
    label: "—",
  },
};

export const vendorRiskMatrixDefinition: Omit<
  BlockDefinition<VendorRiskMatrixConfig, VendorRiskMatrixData>,
  "Component"
> = {
  type: "vendor_risk_matrix",
  label: "Matriz de riesgo por proveedor",
  icon: Table,
  description: "Tabla cruzada proveedor × institución con riesgo y último evento.",
  defaultConfig: {
    filter: {},
    columns: ["sat", "imss", "infonavit", "stps_repse", "risk_score"],
    sort: "risk_desc",
    max_rows: 25,
  },
};

function riskTone(score: number): string {
  if (score >= 70) return "text-[color:var(--status-error-text)]";
  if (score >= 40) return "text-[color:var(--status-warning-text)]";
  return "text-[color:var(--text-secondary)]";
}

// Render the last-event stamp as a compact es-MX date. Falls back to the
// raw value if it isn't a parseable ISO string, and to an em dash when
// the backend hasn't recorded an event yet.
function formatEventDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("es-MX", { day: "2-digit", month: "short", year: "numeric" });
}

export function VendorRiskMatrixBlock({
  block,
}: BlockProps<VendorRiskMatrixConfig, VendorRiskMatrixData>) {
  const { columns } = block.config;
  const rows = block.data?.rows ?? [];

  if (rows.length === 0) {
    return (
      <section
        className="space-y-2 py-2"
        data-block-type="vendor_risk_matrix"
      >
        <div className="rounded-sm border border-dashed border-[color:var(--border-subtle)] p-6 text-center">
          <Table
            className="mx-auto mb-2 h-5 w-5 text-[color:var(--text-tertiary)]"
            weight="regular"
            aria-hidden="true"
          />
          <p className="text-[13px] text-[color:var(--text-secondary)]">
            La matriz se llenará automáticamente cuando se generen los datos.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section
      className="space-y-2 py-2"
      data-block-type="vendor_risk_matrix"
    >
      <BlockIntro
        title="Matriz de riesgo por proveedor"
        caption="Cada renglón es un proveedor con su estado por institución y un puntaje de riesgo de 0 a 100, donde un número más alto significa mayor riesgo. La tabla está ordenada de mayor a menor riesgo, así que lo más urgente aparece primero."
      />
      <div className="overflow-x-auto border-t border-b border-[color:var(--border-default)]">
        <table className="min-w-full text-[13px]">
          <thead>
            <tr className="border-b border-[color:var(--border-subtle)]">
              <th className="cw-eyebrow py-2 pr-4 text-left">Proveedor</th>
              {columns.map((c) => (
                <th
                  key={c}
                  className="cw-eyebrow py-2 pr-4 text-left"
                >
                  {c === "risk_score"
                    ? "Riesgo"
                    : c === "last_event"
                      ? "Última actualización"
                      : INSTITUTION_LABEL[c as InstitutionCode]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.vendor_id}
                className="border-b border-[color:var(--border-subtle)] last:border-0"
              >
                <td className="py-2 pr-4">
                  <div
                    className={`text-[13px] font-medium ${
                      row.vendor_name
                        ? "text-[color:var(--text-primary)]"
                        : "italic text-[color:var(--text-tertiary)]"
                    }`}
                  >
                    {row.vendor_name || "Proveedor reservado"}
                  </div>
                  <div className="font-mono text-[11px] text-[color:var(--text-tertiary)]">
                    {row.vendor_rfc || "RFC reservado"}
                  </div>
                </td>
                {columns.map((c) => {
                  if (c === "risk_score") {
                    return (
                      <td
                        key={c}
                        className={`py-2 pr-4 font-mono text-[13px] font-semibold tabular-nums ${riskTone(row.risk_score)}`}
                      >
                        {row.risk_score}
                      </td>
                    );
                  }
                  if (c === "last_event") {
                    return (
                      <td
                        key={c}
                        className="py-2 pr-4 font-mono text-[11px] text-[color:var(--text-tertiary)]"
                      >
                        {formatEventDate(row.last_event_at)}
                      </td>
                    );
                  }
                  const cell = row.cells[c];
                  if (!cell) {
                    return (
                      <td
                        key={c}
                        className="py-2 pr-4 text-[color:var(--text-tertiary)]"
                      >
                        —
                      </td>
                    );
                  }
                  const tone = STATE_TONE[cell.state] ?? STATE_TONE.empty;
                  return (
                    <td key={c} className="py-2 pr-4">
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${tone.bg} ${tone.text}`}
                      >
                        {tone.label}
                      </span>
                      {cell.age_days > 0 && (
                        <span className="ml-2 font-mono text-[10px] text-[color:var(--text-tertiary)]">
                          {cell.age_days}d
                        </span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <FreshnessLabel fetchedAt={block.data?.fetched_at} />
    </section>
  );
}
