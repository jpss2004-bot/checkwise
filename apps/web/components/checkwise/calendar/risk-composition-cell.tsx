import { RISK_BAR_COLOR, type RiskSegment } from "./calendar-shared";

/**
 * The shared inner of a calendar heat cell: the obligation count over a thin,
 * proportional bar segmented by the six risk severities (worst-first, each its
 * own vivid hue via RISK_BAR_COLOR). Used by BOTH the client matrix
 * (compliance-matrix) and the provider grid (month-cell) so a provider-month
 * and a client-vendor-month read in exactly the same visual language — a
 * neutral cell whose bar shows how the month splits across overdue / awaiting-
 * correction / due-soon / in-review / upcoming / on-track, instead of one flat
 * worst-case color block.
 */
export function RiskCompositionContent({
  count,
  segments,
}: {
  count: number;
  segments: RiskSegment[];
}) {
  return (
    <>
      <span className="font-mono text-sm font-semibold leading-none tabular-nums text-[color:var(--text-primary)]">
        {count}
      </span>
      <span
        aria-hidden="true"
        className="flex h-1.5 w-full gap-px overflow-hidden rounded-full bg-[color:var(--surface-sunken)]"
      >
        {segments.map((s) => (
          <span
            key={s.risk}
            className="h-full"
            style={{
              flexGrow: s.n,
              minWidth: "3px",
              backgroundColor: RISK_BAR_COLOR[s.risk],
            }}
          />
        ))}
      </span>
    </>
  );
}
