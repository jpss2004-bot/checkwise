"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronLeft, ChevronRight, UploadCloud } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  INSTITUTION_LABELS,
  MONTH_LABELS_ES,
  type CalendarPayload,
} from "@/lib/portal-client";
import { RequirementStatusBadge } from "./requirement-status-badge";

type Props = {
  data: CalendarPayload;
};

export function ComplianceCalendar({ data }: Props) {
  const initial = currentMonthIndex();
  const [selected, setSelected] = useState<number>(initial);

  const month = data.months.find((m) => m.month === selected) ?? data.months[0];

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle>Calendario {data.year}</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Obligaciones REPSE mes a mes: SAT mensual, IMSS mensual, INFONAVIT bimestral,
              Acuses cuatrimestrales y declaración anual.
            </p>
          </div>
          <Badge variant="outline">
            {data.persona_type === "moral" ? "Persona Moral" : "Persona Física"}
          </Badge>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {data.months.map((m) => (
            <button
              key={m.month}
              type="button"
              onClick={() => setSelected(m.month)}
              className={`rounded-md border px-3 py-1.5 text-xs ${
                selected === m.month
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-white hover:bg-muted"
              }`}
            >
              <span className="font-semibold">{MONTH_LABELS_ES[m.month]}</span>
              <span className="ml-2 opacity-80">
                {m.received}/{m.expected}
              </span>
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        <div className="mb-4 flex items-center justify-between">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setSelected((s) => Math.max(1, s - 1))}
            disabled={selected === 1}
          >
            <ChevronLeft className="h-4 w-4" aria-hidden="true" /> Mes anterior
          </Button>
          <h3 className="text-lg font-semibold">
            {MONTH_LABELS_ES[month.month]} {data.year}
          </h3>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setSelected((s) => Math.min(12, s + 1))}
            disabled={selected === 12}
          >
            Siguiente mes <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>

        {month.institutions.length === 0 ? (
          <p className="rounded-md border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
            Sin obligaciones recurrentes para este mes.
          </p>
        ) : (
          <div className="space-y-4">
            {month.institutions.map((inst) => (
              <section
                key={inst.institution}
                className="rounded-md border border-border bg-white p-4"
                data-institution={inst.institution}
              >
                <header className="flex flex-wrap items-center justify-between gap-2">
                  <h4 className="text-sm font-semibold">
                    {INSTITUTION_LABELS[inst.institution] ?? inst.institution}
                  </h4>
                  <span className="text-xs text-muted-foreground">
                    {inst.received} de {inst.expected} entregados
                  </span>
                </header>
                <ul className="mt-3 space-y-2">
                  {inst.items.map((item) => {
                    const uploadHref = `/portal/upload?requirement=${encodeURIComponent(
                      item.name,
                    )}&institution=${inst.institution}&load_type=${item.frequency}&period_label=${encodeURIComponent(
                      item.period_label,
                    )}`;
                    return (
                      <li
                        key={item.code}
                        className="flex flex-col gap-2 rounded-md border border-border/70 px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
                      >
                        <div className="min-w-0">
                          <p className="text-sm font-medium">{item.name}</p>
                          <p className="text-xs text-muted-foreground">{item.period_label}</p>
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
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function currentMonthIndex(): number {
  if (typeof window === "undefined") {
    return 1;
  }
  return new Date().getMonth() + 1;
}
