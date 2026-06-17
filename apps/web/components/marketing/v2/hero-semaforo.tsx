"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import {
  motion,
  useInView,
  useMotionValue,
  useSpring,
  useTransform,
} from "motion/react";

import { useMotionPreference } from "@/components/marketing/motion-preference";
import { cn } from "@/lib/utils";

import { PlayableExpediente } from "./hero-expediente";

/**
 * Animated semáforo dashboard — the hero's signature motif, staged in 3D.
 *
 * Layers, back to front:
 *   1. A true-WebGL 3D semáforo ring (hero-semaforo-3d), lazy-mounted on
 *      desktop only and paused when the hero scrolls offscreen. MUST-KEEP.
 *   2. The playable expediente card (hero-expediente): the visitor drags a
 *      pending document onto the at-risk provider and watches the compliance
 *      loop resolve it red→green.
 *
 * On pointer the card tilts gyroscopically while the ring shifts at its own
 * rate (z-depth parallax); on scroll a GSAP ScrollTrigger scrub drifts the
 * two layers apart. The tilt flattens while the visitor is dragging the doc
 * (mx/my zeroed) so the gesture isn't skewed. Everything is gated behind the
 * resolved motion preference: under reduced motion it renders the static card
 * with a tap-to-validate fallback — no WebGL, no tilt, no triggers.
 */

const HeroSemaforo3D = dynamic(() => import("./hero-semaforo-3d"), {
  ssr: false,
});

export function HeroSemaforo() {
  const { reduced } = useMotionPreference();

  const hostRef = useRef<HTMLDivElement>(null);
  const cardScrollRef = useRef<HTMLDivElement>(null);
  const canvasWrapRef = useRef<HTMLDivElement>(null);

  const inView = useInView(hostRef, { amount: 0.3 });
  const inViewOnce = useInView(hostRef, { once: true, amount: 0.4 });

  const [mounted, setMounted] = useState(false);
  const [can3d, setCan3d] = useState(false);
  const [dragging, setDragging] = useState(false);

  // Gyroscopic card tilt (no-op under reduced motion; flattens while dragging).
  const mx = useMotionValue(0);
  const my = useMotionValue(0);
  const cfg = { stiffness: 140, damping: 18, mass: 0.4 };
  const rotateX = useSpring(useTransform(my, [-0.5, 0.5], [7, -7]), cfg);
  const rotateY = useSpring(useTransform(mx, [-0.5, 0.5], [-9, 9]), cfg);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    // WebGL only where it earns its weight: real pointer + desktop width.
    // Re-evaluate on resize too (window event fires where matchMedia change
    // may not), so crossing the breakpoint mounts/unmounts the 3D cleanly.
    const mq = window.matchMedia("(min-width: 768px) and (pointer: fine)");
    const update = () => setCan3d(mq.matches);
    update();
    mq.addEventListener("change", update);
    window.addEventListener("resize", update);
    return () => {
      mq.removeEventListener("change", update);
      window.removeEventListener("resize", update);
    };
  }, []);

  // Scroll-travel proof: the layers drift apart as the hero scrolls out.
  useEffect(() => {
    if (reduced) return;

    let cancelled = false;
    let ctx: { revert: () => void } | undefined;

    // Load GSAP + ScrollTrigger lazily — only at runtime, only when motion is
    // enabled. They are ~300 KB and were shipping in the landing's First Load
    // JS via this static import; the dynamic import code-splits them out,
    // matching how SmoothScroll and the 3D layer already load.
    void (async () => {
      const [{ default: gsap }, { ScrollTrigger }] = await Promise.all([
        import("gsap"),
        import("gsap/ScrollTrigger"),
      ]);
      if (cancelled) return;

      gsap.registerPlugin(ScrollTrigger);
      ctx = gsap.context(() => {
        const trig = {
          trigger: "#inicio",
          start: "top top",
          end: "bottom top",
          scrub: true,
        } as const;
        if (cardScrollRef.current) {
          gsap.to(cardScrollRef.current, {
            yPercent: -9,
            scale: 0.95,
            opacity: 0.65,
            ease: "none",
            scrollTrigger: trig,
          });
        }
        if (canvasWrapRef.current) {
          gsap.to(canvasWrapRef.current, {
            yPercent: 16,
            scale: 1.12,
            ease: "none",
            scrollTrigger: trig,
          });
        }
      });
    })();

    return () => {
      cancelled = true;
      ctx?.revert();
    };
  }, [reduced]);

  const onMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (reduced || dragging) return;
    const r = e.currentTarget.getBoundingClientRect();
    mx.set((e.clientX - r.left) / r.width - 0.5);
    my.set((e.clientY - r.top) / r.height - 0.5);
  };
  const onLeave = () => {
    mx.set(0);
    my.set(0);
  };

  // Flatten the tilt the instant a drag starts so the gesture isn't skewed.
  const handleDragging = (d: boolean) => {
    setDragging(d);
    if (d) {
      mx.set(0);
      my.set(0);
    }
  };

  const mount3d = mounted && can3d && !reduced;

  return (
    <div
      ref={hostRef}
      className="relative"
      onPointerMove={onMove}
      onPointerLeave={onLeave}
    >
      {/* back plane — 3D ring (desktop) or aura fallback, parallax-drifted */}
      <div
        ref={canvasWrapRef}
        aria-hidden="true"
        className="pointer-events-none absolute -inset-x-12 -inset-y-36 -z-10 will-change-transform"
      >
        {mount3d ? (
          <HeroSemaforo3D active={inView} />
        ) : (
          <Aura className="absolute inset-0" />
        )}
      </div>

      {/* front plane — the card: scroll-parallax outer, perspective + tilt inner */}
      <div
        ref={cardScrollRef}
        style={{ perspective: "1100px" }}
        className="will-change-transform"
      >
        <motion.div
          style={reduced ? undefined : { rotateX, rotateY }}
          className="will-change-transform"
        >
          <PlayableExpediente
            reduced={reduced}
            inView={inViewOnce}
            onDraggingChange={handleDragging}
          />
        </motion.div>
      </div>
    </div>
  );
}

function Aura({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "pointer-events-none opacity-70 [background:radial-gradient(60%_55%_at_70%_28%,hsl(var(--teal-500)/0.12),transparent_70%)]",
        className,
      )}
    />
  );
}
