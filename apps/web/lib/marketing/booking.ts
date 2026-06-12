/**
 * Demo-booking entry point for the public site.
 *
 * This is the same Google Calendar appointment schedule the old
 * legalshelf.mx/checkwise/repse page used for its "Agendar una demo"
 * CTA (verified live 2026-06-12; it resolves to a calendar.google.com
 * booking page). TODO(confirm): verify with Héctor that this schedule
 * belongs to hgomez@legalshelf.mx and has current availability — if
 * not, replace the URL here and nowhere else; every booking CTA on the
 * site imports this constant.
 *
 * The old site also exposed https://calendly.com/legalshelf/30min as a
 * fallback; we deliberately surface a single booking path to keep the
 * conversion flow unambiguous.
 */
export const DEMO_BOOKING_URL = "https://calendar.app.google/XHSc4vMA4XK8ySAL8";

export const DEMO_BOOKING_LABEL = "Agendar demo de 30 min";
