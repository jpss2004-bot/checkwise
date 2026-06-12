"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUpRight } from "@phosphor-icons/react";

import { ContactForm } from "@/components/marketing/contact-form";
import { trackBookingIntent } from "@/lib/api/contact";
import {
  DEMO_BOOKING_EMBED_URL,
  DEMO_BOOKING_URL,
} from "@/lib/marketing/booking";

type DemoPath = "booking" | "form";

/**
 * Dual-path demo CTA for the landing `#contacto` section.
 *
 * One card, two equal-weight paths behind a segmented toggle in the
 * chrome bar: "Agendar 30 min" embeds the Google Calendar appointment
 * picker inline (the conversion path the old site relied on, until now
 * buried as a one-line footnote under the form); "Escríbenos" keeps the
 * existing contact form untouched. Both panels stay mounted so a
 * visitor who typed half the form and peeked at the calendar doesn't
 * lose their draft.
 *
 * Intent tracking: the first real interaction with the scheduler —
 * clicking into the calendar iframe, switching to the booking tab, or
 * opening the calendar in a new tab — fires one best-effort beacon per
 * page load so the team gets a Slack ping. Mere page views don't fire;
 * the booking tab is the default and that alone signals nothing.
 */
export function DemoScheduler() {
  const [path, setPath] = useState<DemoPath>("booking");
  const [embedSrc, setEmbedSrc] = useState<string | null>(null);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const intentFired = useRef(false);

  // Calendly's inline embed wants the embedding hostname for its
  // postMessage handshake; only known client-side, so the iframe
  // mounts after hydration.
  useEffect(() => {
    setEmbedSrc(
      `${DEMO_BOOKING_EMBED_URL}&embed_domain=${window.location.hostname}`,
    );
  }, []);

  function fireIntent(source: string) {
    if (intentFired.current) return;
    intentFired.current = true;
    trackBookingIntent(source);
  }

  // Cross-origin iframes swallow clicks, so we can't listen inside the
  // calendar. When the visitor clicks into it, the window blurs and the
  // iframe becomes the active element — that pair is the click signal.
  useEffect(() => {
    function onWindowBlur() {
      if (document.activeElement === iframeRef.current) {
        fireIntent("landing#contacto/calendar");
      }
    }
    window.addEventListener("blur", onWindowBlur);
    return () => window.removeEventListener("blur", onWindowBlur);
  }, []);

  function selectPath(next: DemoPath) {
    setPath(next);
    if (next === "booking") fireIntent("landing#contacto/tab");
  }

  return (
    <div className="relative">
      {/* Chrome bar — carries the path toggle instead of a static
          label, so both demo paths read with the same weight. */}
      <div
        role="tablist"
        aria-label="Elige cómo coordinar tu demo"
        className="flex items-center gap-1 rounded-t-[10px] border-x border-t border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2"
      >
        <PathTab
          active={path === "booking"}
          panelId="demo-panel-booking"
          id="demo-tab-booking"
          onSelect={() => selectPath("booking")}
        >
          Agendar 30 min
        </PathTab>
        <PathTab
          active={path === "form"}
          panelId="demo-panel-form"
          id="demo-tab-form"
          onSelect={() => selectPath("form")}
        >
          Escríbenos
        </PathTab>
        <span className="ml-auto hidden items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-teal)] sm:inline-flex">
          <span className="cw-pulse-soft inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)]" />
          {path === "booking"
            ? "Horarios en vivo · 30 min"
            : "Respuesta el mismo día hábil"}
        </span>
      </div>

      <div className="rounded-b-[10px] border border-[color:var(--border-default)] border-t-0 bg-[color:var(--surface-raised)] shadow-[0_22px_50px_-32px_hsl(var(--brand-navy)/0.22)]">
        <div
          role="tabpanel"
          id="demo-panel-booking"
          aria-labelledby="demo-tab-booking"
          hidden={path !== "booking"}
          className="p-3 sm:p-4"
        >
          {/* Calendly renders the picker on white regardless of theme,
              so the frame gets an explicit white well. */}
          <div className="overflow-hidden rounded-[8px] border border-[color:var(--border-subtle)] bg-white">
            {embedSrc && (
              <iframe
                ref={iframeRef}
                src={embedSrc}
                title="Agendar demo de 30 minutos con el equipo CheckWise"
                loading="lazy"
                className="h-[660px] w-full"
              />
            )}
          </div>
          <p className="mt-3 pb-1 text-center text-[12px] text-[color:var(--text-secondary)]">
            ¿No carga el calendario?{" "}
            <a
              href={DEMO_BOOKING_URL}
              target="_blank"
              rel="noreferrer noopener"
              onClick={() => fireIntent("landing#contacto/external")}
              className="group inline-flex items-center gap-1 font-medium text-[color:var(--text-teal)] underline-offset-2 hover:underline"
            >
              Ábrelo en una pestaña nueva
              <ArrowUpRight
                className="h-3 w-3 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
                weight="bold"
                aria-hidden="true"
              />
            </a>
          </p>
        </div>

        <div
          role="tabpanel"
          id="demo-panel-form"
          aria-labelledby="demo-tab-form"
          hidden={path !== "form"}
          className="px-6 py-8 sm:px-10 sm:py-10"
        >
          <ContactForm />
        </div>
      </div>
    </div>
  );
}

function PathTab({
  active,
  id,
  panelId,
  onSelect,
  children,
}: {
  active: boolean;
  id: string;
  panelId: string;
  onSelect: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      id={id}
      aria-selected={active}
      aria-controls={panelId}
      onClick={onSelect}
      className={`rounded-[6px] px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.18em] transition-colors ${
        active
          ? "border border-[color:var(--border-default)] bg-[color:var(--surface-page)] text-[color:var(--text-teal)]"
          : "border border-transparent text-[color:var(--text-tertiary)] hover:text-[color:var(--text-secondary)]"
      }`}
    >
      {children}
    </button>
  );
}
