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

// Light bands are translucent so the fixed MarketingAtmosphere (scroll-reactive
// semáforo glows + living grid + grain) bleeds through and gives them life.
// Alpha is high enough to keep dark text at full contrast. Navy stays opaque —
// the dark beats carry their own treatment and occlude the atmosphere on purpose.
const BAND_CLASS: Record<Band, string> = {
  page: "bg-[hsl(var(--gray-50)_/_0.58)] text-[color:var(--text-primary)]",
  raised: "bg-[hsl(0_0%_100%_/_0.54)] text-[color:var(--text-primary)]",
  // Soft = a barely-there navy wash that lifts off white without a hard edge.
  soft: "bg-[linear-gradient(180deg,hsl(var(--navy-50)_/_0.55),hsl(0_0%_100%_/_0.46))] text-[color:var(--text-primary)]",
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
        "font-mono text-[12px] font-medium uppercase tracking-[0.18em]",
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
        "text-[clamp(2.3rem,4.2vw,3.85rem)] leading-[1.03]",
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
        "max-w-[60ch] text-[18px] leading-[1.6] md:text-[20px]",
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

/**
 * Living texture for the dark beats — a faint light grid + grain so the opaque
 * dark sections share the atmosphere's depth. The translucent light bands pick
 * this up from the fixed MarketingAtmosphere; the dark sections are opaque, so
 * they carry their own. Pair with each section's semáforo beat glow. Static,
 * aria-hidden, pointer-events-none; sits behind the section's Container.
 */
export function DarkAtmo({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn("pointer-events-none absolute inset-0 -z-0 overflow-hidden", className)}
    >
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            "linear-gradient(to right, hsl(0 0% 100% / 0.04) 1px, transparent 1px), linear-gradient(to bottom, hsl(0 0% 100% / 0.04) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          maskImage: "radial-gradient(125% 90% at 50% 0%, #000 32%, transparent 80%)",
          WebkitMaskImage: "radial-gradient(125% 90% at 50% 0%, #000 32%, transparent 80%)",
        }}
      />
      <div
        className="absolute inset-0 opacity-[0.05] mix-blend-overlay"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />
    </div>
  );
}
