import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import { ProductShot, type ProductShotFocus } from "./product-shot";

/**
 * Shared browser-chrome frame for real product screenshots on the
 * public landing.
 *
 * Why this exists: every marketing section previously hand-rolled the
 * same "three dots + mono chrome label + live status" bar around a
 * screenshot. Centralising it keeps the framing byte-identical across
 * hero, roles, loop and the AI section, and lets the responsive crop
 * behaviour live in one place.
 *
 * The screenshots it frames are the REAL product captures in
 * ``public/marketing/product`` — they carry no baked-in caption band,
 * so the only caption a visitor reads is the React one we render around
 * the frame (this removed the earlier triple-caption duplication).
 */

export type ProductFrameProps = {
  src: string;
  alt: string;
  /** Mono label shown in the chrome bar (left). */
  chrome: string;
  /** Optional status pill (right) — e.g. "Vista en vivo". */
  status?: string;
  /** Aspect ratio of the screenshot viewport, e.g. "16/10". */
  aspect?: string;
  priority?: boolean;
  loading?: "eager" | "lazy";
  sizes?: string;
  focus?: ProductShotFocus;
  /** Extra content rendered below the screenshot, inside the frame. */
  footer?: ReactNode;
  className?: string;
};

export function ProductFrame({
  src,
  alt,
  chrome,
  status,
  aspect = "16/10",
  priority,
  loading,
  sizes = "(min-width: 1024px) 60vw, 92vw",
  focus,
  footer,
  className,
}: ProductFrameProps) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-[14px] border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]",
        "shadow-[0_38px_90px_-44px_hsl(var(--brand-navy)/0.45),0_14px_28px_-18px_hsl(var(--brand-navy)/0.18)]",
        className,
      )}
    >
      {/* Chrome bar */}
      <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]/88 px-3 py-2">
        <span className="flex gap-1.5" aria-hidden="true">
          <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/70" />
          <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/45" />
          <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/30" />
        </span>
        <span className="ml-1 truncate font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-secondary)]">
          {chrome}
        </span>
        {status ? (
          <span className="ml-auto inline-flex shrink-0 items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-teal)]">
            <span className="cw-pulse-soft inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)]" />
            {status}
          </span>
        ) : null}
      </div>

      {/* Screenshot — object-cover keeps it crisp; the real captures are
          full app windows, so top-center framing shows the header +
          primary content rather than an awkward middle slice. */}
      <div
        className="relative w-full bg-[color:var(--surface-page)]"
        style={{ aspectRatio: aspect }}
      >
        <ProductShot
          src={src}
          alt={alt}
          sizes={sizes}
          priority={priority}
          loading={loading}
          focus={focus ?? { position: "top center" }}
        />
      </div>

      {footer ? (
        <div className="border-t border-[color:var(--border-subtle)]">{footer}</div>
      ) : null}
    </div>
  );
}
