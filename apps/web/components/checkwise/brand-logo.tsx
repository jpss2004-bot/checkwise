/**
 * CheckWise brand mark.
 *
 * Renders the official trademark artwork (cropped tight from
 * brand_assets/Logos CW/CheckWise Fon Blanco / IMPI) so the logo
 * on every surface is byte-identical to the registered mark. The
 * inline-SVG version that previously lived here was an
 * approximation; replacing it with the real PNG ensures 100%
 * fidelity to the trademark colors (#013557 navy, #09c1b0 teal,
 * #02558a blue) and to the exact "rounded cushion stack" shape.
 *
 * Variants:
 *
 * - ``full`` — icon + "CheckWise" wordmark side by side, taken
 *   from the official horizontal lockup PNG. Default; used by
 *   header, login, footer.
 * - ``compact`` — icon-only crop of the same artwork, for tight
 *   nav chips and collapsed sidebars.
 *
 * The optional ``poweredBy`` slot renders the "Powered by Legal
 * Shelf" tag — text rather than image, kept inline so it stays
 * crisp and recolors with the surface.
 */

import Image from "next/image";

import { cn } from "@/lib/utils";

// Heights in px. The lockup PNG is 455×77 (aspect ≈ 5.91:1); Next/Image
// derives the rendered width from height × intrinsic aspect ratio.
const HEIGHT_PX: Record<"sm" | "md" | "lg", number> = {
  sm: 22,
  md: 30,
  lg: 44,
};

type Variant = "full" | "compact";

type Props = {
  variant?: Variant;
  size?: "sm" | "md" | "lg";
  poweredBy?: boolean;
  className?: string;
};

export function BrandLogo({
  variant = "full",
  size = "md",
  poweredBy = false,
  className,
}: Props) {
  const h = HEIGHT_PX[size];

  if (variant === "compact") {
    return (
      <span
        className={cn("inline-flex items-center", className)}
        aria-label="CheckWise"
      >
        <Image
          src="/brand/checkwise-icon.png"
          alt="CheckWise"
          width={h}
          height={h}
          priority
        />
      </span>
    );
  }

  // full — official horizontal lockup
  return (
    <span
      className={cn("inline-flex items-center gap-3", className)}
      aria-label="CheckWise"
    >
      <Image
        src="/brand/checkwise-lockup.png"
        alt="CheckWise"
        // Intrinsic 455×77 → width derived from requested height.
        width={Math.round((h * 455) / 77)}
        height={h}
        priority
      />
      {poweredBy ? <PoweredBy /> : null}
    </span>
  );
}

function PoweredBy() {
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
      Powered by
      <span style={{ color: "hsl(var(--brand-blue))" }} className="font-semibold">
        Legal Shelf
      </span>
    </span>
  );
}
