import { Activity, Database, FileCheck2, ShieldCheck } from "lucide-react";

import { DocumentSubmissionForm } from "@/components/checkwise/document-submission-form";
import { Badge } from "@/components/ui/badge";

const metrics = [
  { label: "Modelo", value: "REPSE V1", icon: ShieldCheck },
  { label: "Estado inicial", value: "pendiente_revision", icon: FileCheck2 },
  { label: "Fuente futura", value: "PostgreSQL", icon: Database },
  { label: "Validación", value: "Humana + señales", icon: Activity },
];

export default function Home() {
  return (
    <main className="min-h-screen bg-background">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-5 px-5 py-5 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary text-primary-foreground">
                <ShieldCheck className="h-5 w-5" aria-hidden="true" />
              </div>
              <div>
                <p className="text-sm font-semibold text-primary">CheckWise</p>
                <h1 className="text-2xl font-semibold text-foreground">Carga documental REPSE</h1>
              </div>
            </div>
          </div>
          <Badge variant="outline">V1 foundation</Badge>
        </div>
      </header>

      <section className="border-b border-border bg-white">
        <div className="mx-auto grid max-w-7xl grid-cols-2 gap-3 px-5 py-4 md:grid-cols-4">
          {metrics.map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.label} className="flex items-center gap-3 rounded-md border border-border px-3 py-3">
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

      <div className="mx-auto grid max-w-7xl gap-5 px-5 py-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <DocumentSubmissionForm />

        <aside className="space-y-4">
          <section className="rounded-md border border-border bg-white p-5 shadow-soft">
            <h2 className="text-base font-semibold">Trazabilidad mínima</h2>
            <div className="mt-4 space-y-3 text-sm">
              {[
                "cliente",
                "proveedor",
                "contrato si aplica",
                "periodo",
                "institución",
                "requisito versionable",
                "archivo + hash",
                "validación + estado",
                "audit_log",
              ].map((item) => (
                <div key={item} className="flex items-center gap-2">
                  <FileCheck2 className="h-4 w-4 text-primary" aria-hidden="true" />
                  <span>{item}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-md border border-border bg-white p-5 shadow-soft">
            <h2 className="text-base font-semibold">Estados base</h2>
            <div className="mt-4 flex flex-wrap gap-2">
              {[
                "pendiente",
                "recibido",
                "pendiente_revision",
                "prevalidado",
                "aprobado",
                "rechazado",
                "vencido",
                "no_aplica",
                "requiere_aclaracion",
                "excepcion_legal",
              ].map((status) => (
                <Badge key={status} variant={status === "pendiente_revision" ? "default" : "secondary"}>
                  {status}
                </Badge>
              ))}
            </div>
          </section>
        </aside>
      </div>
    </main>
  );
}
