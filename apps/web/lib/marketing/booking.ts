/**
 * Demo-booking entry point for the public site. Every booking CTA on
 * the site (contact card, footer, REPSE article CTAs) imports these
 * constants — replace the URLs here and nowhere else.
 *
 * The old legalshelf.mx/checkwise/repse page used a Google Calendar
 * appointment schedule (https://calendar.app.google/XHSc4vMA4XK8ySAL8),
 * but as of 2026-06-12 that schedule renders "Appointment not found" —
 * it was deleted or expired (it belonged to hgomez@legalshelf.mx). The
 * Calendly schedule the old site kept as fallback is alive ("30 Minute
 * Meeting - Legal Shelf"), so it is now the single booking path. If the
 * team restores a Google schedule, swap both URLs here: the share link
 * for DEMO_BOOKING_URL, and the schedule token under
 * calendar.google.com/calendar/appointments/schedules/<token>?gv=true
 * for the embed.
 */
export const DEMO_BOOKING_URL = "https://calendly.com/legalshelf/30min";

/**
 * Inline-embed form of the same schedule, derived from the URL above —
 * paste any Calendly event link into DEMO_BOOKING_URL and the embed,
 * footer and article CTAs all follow. Calendly serves booking pages
 * with `X-Frame-Options: ALLOWALL`; `embed_type=Inline` strips the
 * page chrome so only the picker renders, and `primary_color` matches
 * --brand-teal (hsl 175 91% 40%). The component appends `embed_domain`
 * at runtime (Calendly uses it for postMessage). NOTE: this derivation
 * is Calendly-specific — a Google Calendar link would need its own
 * embed form (schedule token + `?gv=true`).
 */
export const DEMO_BOOKING_EMBED_URL = `${DEMO_BOOKING_URL}?embed_type=Inline&hide_gdpr_banner=1&primary_color=09c3b3`;

export const DEMO_BOOKING_LABEL = "Agendar demo de 30 min";
