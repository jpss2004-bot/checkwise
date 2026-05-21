/**
 * CheckWise brand mark.
 *
 * Renders the official three-layer logo (navy / teal / blue stacked
 * sheets) plus the wordmark. Variants:
 *
 * - ``full`` — icon + "CheckWise" wordmark side by side. For headers
 *   and login surfaces.
 * - ``compact`` — icon-only variant. For tight nav chips and
 *   collapsed surfaces where the wordmark would crowd the layout.
 * - ``stacked`` — icon above wordmark. For hero / lockup placements.
 *
 * The mark is drawn as inline SVG (not an <img>) so it inherits the
 * deep-navy text color when the surface needs an on-dark variant, and
 * so the colors stay locked to the brand HSL tokens defined in
 * globals.css instead of becoming raster-dependent. The optional
 * ``poweredBy`` slot renders the "Powered by Legal Shelf" tag —
 * pulled from the official wordmark — beneath the main lockup.
 */

import { cn } from "@/lib/utils";

const SIZE_PX: Record<"sm" | "md" | "lg", number> = {
  sm: 20,
  md: 28,
  lg: 40,
};

type Variant = "full" | "compact" | "stacked";

type Props = {
  variant?: Variant;
  size?: "sm" | "md" | "lg";
  poweredBy?: boolean;
  className?: string;
  wordmarkClassName?: string;
};

export function BrandLogo({
  variant = "full",
  size = "md",
  poweredBy = false,
  className,
  wordmarkClassName,
}: Props) {
  const iconPx = SIZE_PX[size];

  const wordmarkSize =
    size === "lg" ? "text-2xl" : size === "md" ? "text-lg" : "text-sm";

  if (variant === "compact") {
    return (
      <span
        className={cn("inline-flex items-center", className)}
        aria-label="CheckWise"
      >
        <BrandMark px={iconPx} />
      </span>
    );
  }

  if (variant === "stacked") {
    return (
      <span
        className={cn("inline-flex flex-col items-center gap-2", className)}
        aria-label="CheckWise"
      >
        <BrandMark px={iconPx + 12} />
        <span className="inline-flex items-baseline gap-0">
          <span
            className={cn(
              "font-semibold tracking-tight",
              wordmarkSize,
              wordmarkClassName,
            )}
            style={{ color: "hsl(var(--brand-navy))" }}
          >
            Check
          </span>
          <span
            className={cn(
              "font-semibold tracking-tight",
              wordmarkSize,
              wordmarkClassName,
            )}
            style={{ color: "hsl(var(--brand-teal))" }}
          >
            Wise
          </span>
        </span>
        {poweredBy ? <PoweredBy /> : null}
      </span>
    );
  }

  // full
  return (
    <span
      className={cn("inline-flex items-center gap-2.5", className)}
      aria-label="CheckWise"
    >
      <BrandMark px={iconPx} />
      <span className="inline-flex items-baseline gap-0">
        <span
          className={cn(
            "font-semibold tracking-tight",
            wordmarkSize,
            wordmarkClassName,
          )}
          style={{ color: "hsl(var(--brand-navy))" }}
        >
          Check
        </span>
        <span
          className={cn(
            "font-semibold tracking-tight",
            wordmarkSize,
            wordmarkClassName,
          )}
          style={{ color: "hsl(var(--brand-teal))" }}
        >
          Wise
        </span>
      </span>
      {poweredBy ? <PoweredBy /> : null}
    </span>
  );
}

function BrandMark({ px }: { px: number }) {
  // Three stacked rhombus-style sheets, top-to-bottom: navy, teal, blue.
  // Drawn as a viewBox so it scales cleanly. Matches the official mark
  // in CheckWise IMPI.jpg / "CW sin fondo.png".
  return (
    <svg
      width={px}
      height={px}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      role="presentation"
    >
      <defs>
        <linearGradient id="cw-mark-teal" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="hsl(174, 91%, 45%)" />
          <stop offset="100%" stopColor="hsl(180, 60%, 35%)" />
        </linearGradient>
        <linearGradient id="cw-mark-blue" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="hsl(203, 97%, 27%)" />
          <stop offset="100%" stopColor="hsl(207, 70%, 22%)" />
        </linearGradient>
      </defs>
      {/* top sheet — navy */}
      <path
        d="M24 4 L42 11 L24 18 L6 11 Z"
        fill="hsl(207, 98%, 17%)"
      />
      {/* middle sheet — teal */}
      <path
        d="M24 18 L42 24 L24 30 L6 24 Z"
        fill="url(#cw-mark-teal)"
      />
      {/* bottom sheet — blue */}
      <path
        d="M24 30 L42 37 L24 44 L6 37 Z"
        fill="url(#cw-mark-blue)"
      />
    </svg>
  );
}

function PoweredBy() {
  return (
    <span className="ml-3 inline-flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
      Powered by
      <span style={{ color: "hsl(var(--brand-blue))" }} className="font-semibold">
        Legal Shelf
      </span>
    </span>
  );
}
