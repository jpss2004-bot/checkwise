import type { Metadata } from "next";

import { V2AiHuman } from "@/components/marketing/v2/ai-human";
import { V2CloseDemo } from "@/components/marketing/v2/close-demo";
import { V2Faq } from "@/components/marketing/v2/faq";
import { V2Footer } from "@/components/marketing/v2/footer";
import { V2Hero } from "@/components/marketing/v2/hero";
import { V2HowItWorks } from "@/components/marketing/v2/how-it-works";
import { V2Hub } from "@/components/marketing/v2/hub";
import { V2Nav } from "@/components/marketing/v2/nav";
import { V2Proof } from "@/components/marketing/v2/proof";
import { V2Roles } from "@/components/marketing/v2/roles";
import { V2Shift } from "@/components/marketing/v2/shift";
import { V2Stakes } from "@/components/marketing/v2/stakes";

/**
 * /v2 — the from-scratch landing redesign (work in progress).
 *
 * Built in parallel to the live landing (app/page.tsx) so the new design
 * can be perfected before it replaces production. noindex while in draft.
 * Narrative arc: Riesgo → Control → Prevención → Prueba → Cierre.
 * See outputs/landing-redesign-2026-06-15/{BLUEPRINT,SCOPE}.md.
 */
export const metadata: Metadata = {
  title: "CheckWise · rediseño (borrador v2)",
  robots: { index: false, follow: false },
};

export default function V2Page() {
  return (
    <>
      <V2Nav />
      <main>
        <V2Hero />
        <V2Stakes />
        <V2Shift />
        <V2HowItWorks />
        <V2Roles />
        <V2AiHuman />
        <V2Proof />
        <V2Hub />
        <V2Faq />
        <V2CloseDemo />
      </main>
      <V2Footer />
    </>
  );
}
