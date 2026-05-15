/**
 * CheckWise · app/layout.tsx — Phase 1 changes
 *
 * This is NOT a drop-in replacement — your existing layout.tsx likely has
 * Providers, metadata, viewport configuration, etc. Apply this as a DIFF.
 *
 * The four required changes are:
 *   1. Add the `geist/font/sans` import
 *   2. Add the `geist/font/mono` import
 *   3. Add both `.variable` class names to the <html> element
 *   4. (Optional) Set `<html lang="es">` if not already
 */

// ─── ADD THESE IMPORTS at the top of app/layout.tsx ─────────────────
import { GeistSans } from 'geist/font/sans';
import { GeistMono } from 'geist/font/mono';

// ─── KEEP your existing imports ─────────────────────────────────────
import type { Metadata } from 'next';
import './globals.css';

// ─── KEEP your existing metadata/viewport exports ───────────────────
export const metadata: Metadata = {
  title: 'CheckWise',
  description: 'Plataforma guiada de cumplimiento REPSE.',
  // …whatever else you already have
};

// ─── MODIFY your existing RootLayout body ───────────────────────────
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="es"
      // ▼▼▼ This is the only line that materially changes ▼▼▼
      className={`${GeistSans.variable} ${GeistMono.variable}`}
      // ▲▲▲                                              ▲▲▲
      suppressHydrationWarning
    >
      <body>
        {/* keep your existing Providers / Toaster / etc */}
        {children}
      </body>
    </html>
  );
}

/* ─── Optional: confirm the variable names ──────────────────────────
 *
 * `GeistSans.variable`  exposes `--font-geist-sans` on the html element.
 * `GeistMono.variable`  exposes `--font-geist-mono` on the html element.
 * Both are referenced by globals.css and tailwind.config.ts.
 *
 * If you ever swap Geist for another font, change BOTH:
 *   - The import + .variable here
 *   - The CSS variable name in globals.css `body { font-family: ... }`
 *   - The fontFamily.sans/mono entry in tailwind.config.ts
 */
