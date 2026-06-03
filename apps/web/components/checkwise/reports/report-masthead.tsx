import { BrandLogo } from "@/components/checkwise/brand-logo";

/**
 * ReportMasthead — the bold, branded cover of a CheckWise report.
 *
 * This is the single element that makes a generated report read as a
 * *document* (a deliverable compliance artifact) rather than another
 * app screen. It pairs the official CheckWise lockup on a light brand
 * strip with a navy title panel and a teal accent rule — the brand's
 * "navy carries authority, teal marks intelligence" signature from
 * DESIGN.md, applied at document scale.
 *
 * Presentational only: the caller (StoryView / print cover) owns the
 * data lifecycle and passes pre-formatted strings. Meta entries with no
 * value are dropped so the row never shows empty cells.
 *
 * Print: the navy panel keeps its fill via `print-color-adjust: exact`
 * so the cover survives the PDF render instead of washing out to white.
 */

export interface MastheadMeta {
  label: string;
  value: string | null | undefined;
}

export interface ReportMastheadProps {
  title: string;
  description?: string | null;
  /** Short kicker above the title, e.g. "Reporte de cumplimiento REPSE". */
  kicker?: string;
  meta: MastheadMeta[];
}

export function ReportMasthead({
  title,
  description,
  kicker = "Reporte de cumplimiento REPSE",
  meta,
}: ReportMastheadProps) {
  const shownMeta = meta.filter((m) => m.value);

  return (
    <header className="cw-fade-up print:break-inside-avoid">
      {/* Brand strip — official lockup on light, reads correctly. */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4">
        <BrandLogo size="md" />
        <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[color:var(--text-teal)]">
          {kicker}
        </span>
      </div>

      {/* Navy title panel — the bold, branded anchor. */}
      <div
        className="overflow-hidden rounded-2xl bg-[color:var(--surface-brand)] px-7 py-7 sm:px-9 sm:py-8"
        style={{ printColorAdjust: "exact", WebkitPrintColorAdjust: "exact" }}
      >
        <h1 className="max-w-[24ch] text-[28px] font-semibold leading-[1.12] tracking-tight text-white sm:text-[34px]">
          {title}
        </h1>
        {description ? (
          <p className="mt-3 max-w-[58ch] text-[14px] leading-relaxed text-white/70">
            {description}
          </p>
        ) : null}

        {/* Teal accent rule — the "intelligence" signature. */}
        <div className="mt-6 h-[3px] w-16 rounded-full bg-[color:var(--border-ai)]" />

        {shownMeta.length > 0 ? (
          <dl className="mt-5 flex flex-wrap gap-x-10 gap-y-4">
            {shownMeta.map((m) => (
              <div key={m.label}>
                <dt className="text-[10px] font-medium uppercase tracking-[0.1em] text-[hsl(var(--teal-300))]">
                  {m.label}
                </dt>
                <dd className="mt-0.5 text-[13px] font-medium text-white/95">
                  {m.value}
                </dd>
              </div>
            ))}
          </dl>
        ) : null}
      </div>
    </header>
  );
}
