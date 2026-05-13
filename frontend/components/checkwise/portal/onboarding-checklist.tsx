"use client";

import Link from "next/link";
import { CheckCircle2, FileText, UploadCloud } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { INSTITUTION_LABELS, type OnboardingSummary } from "@/lib/portal-client";
import { RequirementStatusBadge } from "./requirement-status-badge";

type Props = {
  data: OnboardingSummary;
};

export function OnboardingChecklist({ data }: Props) {
  const { summary } = data;
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle>Expediente corporativo</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Documentos iniciales requeridos antes de habilitar el calendario de cumplimiento
              recurrente.
            </p>
          </div>
          <Badge variant={summary.completed ? "default" : "outline"}>
            {summary.received_required} de {summary.total_required} entregados ·{" "}
            {summary.completion_pct}%
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {data.sections.map((section) => (
          <section
            key={section.section}
            className="rounded-md border border-border bg-white p-4"
            data-section={section.section}
          >
            <header className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">{section.section}</h3>
              <span className="text-xs text-muted-foreground">
                {section.received} de {section.required} obligatorios
              </span>
            </header>
            <ul className="mt-3 space-y-2">
              {section.items.map((item) => {
                const uploadHref = `/portal/upload?requirement=${encodeURIComponent(
                  item.name,
                )}&institution=${item.institution}&load_type=alta_inicial`;
                return (
                  <li
                    key={item.code}
                    className="flex flex-col gap-2 rounded-md border border-border/70 px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="flex items-start gap-2">
                      {item.status === "pendiente" ? (
                        <FileText className="mt-0.5 h-4 w-4 text-muted-foreground" />
                      ) : (
                        <CheckCircle2 className="mt-0.5 h-4 w-4 text-primary" />
                      )}
                      <div className="min-w-0">
                        <p className="text-sm font-medium">
                          {item.name}{" "}
                          {!item.required ? (
                            <span className="text-xs text-muted-foreground">(opcional)</span>
                          ) : null}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {INSTITUTION_LABELS[item.institution] ?? item.institution}
                          {item.note ? ` · ${item.note}` : ""}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <RequirementStatusBadge status={item.status} />
                      <Button asChild size="sm" variant="outline">
                        <Link href={uploadHref}>
                          <UploadCloud className="h-4 w-4" aria-hidden="true" />
                          {item.status === "pendiente" ? "Cargar" : "Recargar"}
                        </Link>
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </CardContent>
    </Card>
  );
}
