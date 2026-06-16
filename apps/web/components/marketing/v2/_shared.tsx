import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import { Reveal } from "./motion";

/**
 * Shared primitives for the v2 marketing rebuild.
 *
 * This is a from-scratch landing (see outputs/landing-redesign-2026-06-15/
 * BLUEPRINT.md): the narrative arc is Riesgo → Control → Prevención →
 * Prueba → Cierre, carried by a deliberate light/navy band rhythm. These
 * primitives keep every section on the same measure, spacing scale and
 * token set so the page reads as one composed surface, not stitched parts.
 *
 * Built on the real design tokens in app/globals.css — no throwaway CSS.
 */

export function Container({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mx-auto w-full max-w-[1200px] px-6 md:px-10", className)}>
      {children}
    </div>
  );
}

type Band = "page" | "raised" | "soft" | "navy";

const BAND_CLASS: Record<Band, string> = {
  page: "bg-[color:var(--surface-page)] text-[color:var(--text-primary)]",
  raised: "bg-[color:var(--surface-raised)] text-[color:var(--text-primary)]",
  // Soft = a barely-there navy wash that lifts off white without a hard edge.
  soft: "bg-[linear-gradient(180deg,var(--surface-brand-muted),var(--surface-raised))] text-[color:var(--text-primary)]",
  // Navy = gravity. Carries risk + trust beats. Inverse text tokens guarantee contrast.
  navy: "bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]",
};

/**
 * A full-bleed band with an inner container. Vertical rhythm is fluid and
 * generous; sections vary their own internal spacing for cadence.
 */
export function Section({
  id,
  band = "page",
  className,
  innerClassName,
  children,
}: {
  id?: string;
  band?: Band;
  className?: string;
  innerClassName?: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      data-band={band}
      className={cn("relative scroll-mt-20", BAND_CLASS[band], className)}
    >
      <Container className={cn("py-[clamp(4.5rem,9vw,8.5rem)]", innerClassName)}>
        <Reveal>{children}</Reveal>
      </Container>
    </section>
  );
}

type EyebrowTone = "teal" | "muted" | "onNavy";

const EYEBROW_TONE: Record<EyebrowTone, string> = {
  teal: "text-[color:var(--text-teal)]",
  muted: "text-[color:var(--text-tertiary)]",
  onNavy: "text-[hsl(var(--teal-300))]",
};

/** Section kicker. One per section, deliberate — not scaffolding. */
export function Eyebrow({
  children,
  tone = "teal",
  className,
}: {
  children: ReactNode;
  tone?: EyebrowTone;
  className?: string;
}) {
  return (
    <p
      className={cn(
        "font-mono text-[11px] font-medium uppercase tracking-[0.18em]",
        EYEBROW_TONE[tone],
        className,
      )}
    >
      {children}
    </p>
  );
}

/**
 * Section heading. Editorial scale with strong weight contrast; the teal
 * accent lands on the operative phrase (passed as `accent`).
 */
export function SectionTitle({
  children,
  accent,
  onNavy = false,
  className,
}: {
  children: ReactNode;
  accent?: ReactNode;
  onNavy?: boolean;
  className?: string;
}) {
  return (
    <h2
      className={cn(
        "font-display max-w-[20ch] font-semibold tracking-[-0.02em] [text-wrap:balance]",
        "text-[clamp(1.9rem,3.4vw,3rem)] leading-[1.05]",
        onNavy ? "text-[color:var(--text-inverse)]" : "text-[color:var(--text-primary)]",
        className,
      )}
    >
      {children}
      {accent ? (
        <span
          className={onNavy ? "text-[hsl(var(--teal-300))]" : "text-[color:var(--text-teal)]"}
        >
          {" "}
          {accent}
        </span>
      ) : null}
    </h2>
  );
}

/** Body lead under a section title. Capped measure, calm secondary tone. */
export function Lead({
  children,
  onNavy = false,
  className,
}: {
  children: ReactNode;
  onNavy?: boolean;
  className?: string;
}) {
  return (
    <p
      className={cn(
        "max-w-[58ch] text-[16px] leading-[1.65] md:text-[17px]",
        onNavy
          ? "text-[color:var(--text-inverse-secondary)]"
          : "text-[color:var(--text-secondary)]",
        className,
      )}
    >
      {children}
    </p>
  );
}
