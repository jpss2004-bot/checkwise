"use client";

import { useRouter } from "next/navigation";
import { Building2, LogOut } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { clearPortalSession, type PortalSession } from "@/lib/portal-session";

export function ProviderContextBar({ session }: { session: PortalSession }) {
  const router = useRouter();
  return (
    <header className="border-b border-border bg-white">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 px-5 py-4 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Building2 className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground">Sesión demo</p>
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
        <div className="flex items-center gap-2">
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
