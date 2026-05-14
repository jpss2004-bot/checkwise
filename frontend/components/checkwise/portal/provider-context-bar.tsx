"use client";

import { useRouter } from "next/navigation";
import { ClipboardCheck, LogOut } from "lucide-react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { clearPortalSession, type PortalSession } from "@/lib/portal-session";

type Props = {
  session: PortalSession;
  onboardingPct?: number | null;
};

export function ProviderContextBar({ session, onboardingPct }: Props) {
  const router = useRouter();
  const pct =
    typeof onboardingPct === "number" && Number.isFinite(onboardingPct)
      ? Math.min(100, Math.max(0, Math.round(onboardingPct)))
      : null;
  const isComplete = pct !== null && pct >= 100;

  return (
    <header className="border-b border-border bg-white">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 px-5 py-4 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-4">
          <BrandLogo variant="compact" size="md" />
          <div className="min-w-0 border-l border-border pl-4">
            <p className="text-xs text-muted-foreground">Sesión proveedor</p>
            <p className="truncate text-sm font-semibold">
              {session.vendor_name}{" "}
              <span className="text-muted-foreground">· {session.vendor_rfc}</span>
            </p>
            <p className="truncate text-xs text-muted-foreground">
              Cliente: {session.client_name}
              {session.filial_name ? ` / ${session.filial_name}` : ""}
              {session.contract_reference ? ` · ${session.contract_reference}` : ""}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {pct !== null ? (
            <div
              className={`flex items-center gap-2 rounded-full border px-3 py-1 text-xs ${
                isComplete
                  ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                  : "border-primary/30 bg-primary/5 text-primary"
              }`}
              role="status"
              aria-label={`Expediente al ${pct} por ciento`}
              title={
                isComplete
                  ? "Expediente corporativo completo"
                  : `Llevas ${pct}% del expediente corporativo`
              }
            >
              <ClipboardCheck className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="font-medium">Expediente</span>
              <span
                aria-hidden="true"
                className="h-1.5 w-12 overflow-hidden rounded-full bg-white/60"
              >
                <span
                  className={`block h-full rounded-full transition-[width] duration-500 ease-out ${
                    isComplete ? "bg-emerald-500" : "bg-primary"
                  }`}
                  style={{ width: `${pct}%` }}
                />
              </span>
              <span className="tabular-nums font-semibold">{pct}%</span>
            </div>
          ) : null}
          <Badge variant="outline">
            {session.persona_type === "moral" ? "Persona Moral" : "Persona Física"}
          </Badge>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              clearPortalSession();
              router.push("/");
            }}
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
            Cerrar sesión demo
          </Button>
        </div>
      </div>
    </header>
  );
}
