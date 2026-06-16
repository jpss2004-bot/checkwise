import type { ReactNode } from "react";
import { Schibsted_Grotesk } from "next/font/google";

import { SmoothScroll } from "@/components/marketing/v2/motion";

/**
 * /v2 layout — loads the redesign's display typeface (Schibsted Grotesk)
 * and exposes it as --font-display, scoped to this route subtree so the
 * rest of the app (product UI) keeps Geist untouched.
 *
 * Evolve-within-identity (SCOPE.md #10): navy/teal + logo stay; the
 * distinctive display face on headings is the visual evolution. Body and
 * UI remain Geist; eyebrows remain Geist Mono.
 */
const display = Schibsted_Grotesk({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-display",
  display: "swap",
});

export default function V2Layout({ children }: { children: ReactNode }) {
  return (
    <div className={display.variable}>
      <SmoothScroll>{children}</SmoothScroll>
    </div>
  );
}
