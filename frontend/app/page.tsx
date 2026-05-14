"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ChartLineUp, Database, FileText, ShieldCheck } from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { ProviderAccessForm } from "@/components/checkwise/portal/provider-access-form";
import { Badge } from "@/components/ui/badge";
import { readPortalSession } from "@/lib/session/portal";

const metrics = [
  { label: "Plataforma", value: "REPSE V1.2", icon: ShieldCheck },
  { label: "Trazabilidad", value: "Cliente → Periodo", icon: FileText },
  { label: "Fuente futura", value: "PostgreSQL", icon: Database },
  { label: "Validación", value: "Humana + señales", icon: ChartLineUp },
];

export default function HomePage() {
  const router = useRouter();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const existing = readPortalSession();
    if (existing) {
      router.replace("/portal/onboarding");
      return;
    }
    setChecked(true);
  }, [router]);

  if (!checked) {
    return null;
  }

  return (
    <main className="min-h-screen bg-background">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-5 px-5 py-5 md:flex-row md:items-center md:justify-between">
          <div className="flex items-start gap-3">
            <BrandLogo size="lg" poweredBy />
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline">Portal proveedor</Badge>
          </div>
        </div>
        <div className="mx-auto max-w-7xl px-5 pb-5">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            Plataforma de cumplimiento REPSE
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Carga documental, prevalidación automática y revisión humana
            trazable. Para proveedores, revisores y administradores.
          </p>
        </div>
      </header>

      <section className="border-b border-border bg-white">
        <div className="mx-auto grid max-w-7xl grid-cols-2 gap-3 px-5 py-4 md:grid-cols-4">
          {metrics.map((item) => {
            const Icon = item.icon;
            return (
              <div
                key={item.label}
                className="flex items-center gap-3 rounded-md border border-border px-3 py-3"
              >
                <Icon className="h-5 w-5 text-primary" aria-hidden="true" />
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">{item.label}</p>
                  <p className="truncate text-sm font-semibold">{item.value}</p>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-6">
        <ProviderAccessForm />
      </section>

      <section className="mx-auto max-w-7xl px-5 pb-10">
        <div className="grid gap-5 md:grid-cols-3">
          <div className="rounded-md border border-border bg-white p-5">
            <h2 className="text-base font-semibold">Expediente inicial</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Contrato, documentación corporativa, registro REPSE y registro patronal.
            </p>
          </div>
          <div className="rounded-md border border-border bg-white p-5">
            <h2 className="text-base font-semibold">Calendario REPSE</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              SAT mensual, IMSS mensual, INFONAVIT bimestral, Acuses cuatrimestrales y anual.
            </p>
          </div>
          <div className="rounded-md border border-border bg-white p-5">
            <h2 className="text-base font-semibold">Trazabilidad mínima</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Cliente, proveedor, periodo, institución, requisito, archivo + hash, validación,
              auditoría.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
