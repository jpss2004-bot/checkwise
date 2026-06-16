import Link from "next/link";
import { ArrowRight } from "@phosphor-icons/react/dist/ssr";

import { Button } from "@/components/ui/button";

/**
 * Thin mid-page CTA strip that sits between HowItWorks and Roles.
 * Gives visitors who are already convinced a conversion point without
 * waiting until the bottom of the page.
 */
export function V2MidCta() {
  return (
    <div className="border-y border-[color:var(--border-default)] bg-[color:var(--surface-raised)]">
      <div className="mx-auto flex max-w-[1200px] flex-col items-center gap-4 px-6 py-8 text-center sm:flex-row sm:justify-between sm:text-left md:px-10">
        <p className="text-[15px] font-medium text-[color:var(--text-primary)]">
          ¿Quieres ver CheckWise funcionando con tus propios proveedores?
        </p>
        <Button asChild size="sm" className="shrink-0 rounded-full">
          <Link href="#contacto">
            Solicitar demo
            <ArrowRight
              className="ml-1.5 h-3.5 w-3.5"
              weight="bold"
              aria-hidden="true"
            />
          </Link>
        </Button>
      </div>
    </div>
  );
}
