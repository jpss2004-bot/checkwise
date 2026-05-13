"use client";

import Link from "next/link";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  FileText,
  ShieldCheck,
  UploadCloud,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  INSTITUTION_LABELS,
  type OnboardingItem,
  type OnboardingSummary,
  type RequirementStatus,
} from "@/lib/portal-client";
import { RequirementStatusBadge } from "./requirement-status-badge";

const ATTENTION_STATUSES: RequirementStatus[] = [
  "rechazado",
  "vencido",
  "posible_mismatch",
  "requiere_aclaracion",
];

const NEXT_ACTION_LABEL: Partial<Record<RequirementStatus, string>> = {
  pendiente: "Tu próximo paso",
  rechazado: "Corrige este documento",
  vencido: "Documento vencido",
  posible_mismatch: "Revisa este documento",
  requiere_aclaracion: "Necesitamos una aclaración",
};

const NEXT_ACTION_CTA: Partial<Record<RequirementStatus, string>> = {
  pendiente: "Cargar ahora",
  rechazado: "Volver a cargar",
  vencido: "Cargar versión vigente",
  posible_mismatch: "Verificar y recargar",
  requiere_aclaracion: "Aclarar y recargar",
};

type Props = {
  data: OnboardingSummary;
};

export function OnboardingChecklist({ data }: Props) {
  const { summary } = data;
  const completionPct = Math.min(100, Math.max(0, summary.completion_pct));
  const nextAction = findNextAction(data);

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <CardTitle>Expediente corporativo</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Documentos iniciales requeridos antes de habilitar el calendario de cumplimiento
              recurrente.
            </p>
          </div>
          <Badge
            variant={summary.completed ? "default" : "outline"}
            className="self-start whitespace-nowrap"
          >
            {summary.received_required} de {summary.total_required} obligatorios ·{" "}
            {completionPct}%
          </Badge>
        </div>

        <div
          className="mt-4 h-2 w-full overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={completionPct}
          aria-label="Avance del expediente corporativo"
        >
          <div
            className={`h-full rounded-full transition-[width] duration-500 ease-out ${
              summary.completed ? "bg-emerald-500" : "bg-primary"
            }`}
            style={{ width: `${completionPct}%` }}
          />
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        {summary.completed ? (
          <CompletedBanner total={summary.total_required} />
        ) : nextAction ? (
          <NextActionCallout item={nextAction} />
        ) : null}

        {data.sections.map((section) => {
          const sectionPct =
            section.required === 0
              ? 100
              : Math.round((section.received / section.required) * 100);
          const sectionComplete = section.required > 0 && section.received >= section.required;

          return (
            <section
              key={section.section}
              className="rounded-md border border-border bg-white p-4"
              data-section={section.section}
            >
              <header className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  {sectionComplete ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" />
                  ) : (
                    <FileText className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                  )}
                  <h3 className="text-sm font-semibold">{section.section}</h3>
                </div>
                <span className="text-xs text-muted-foreground">
                  {section.received} de {section.required} obligatorios
                </span>
              </header>

              {section.required > 0 ? (
                <div
                  className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-muted"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={sectionPct}
                  aria-label={`Avance ${section.section}`}
                >
                  <div
                    className={`h-full rounded-full transition-[width] duration-500 ease-out ${
                      sectionComplete ? "bg-emerald-500" : "bg-primary/70"
                    }`}
                    style={{ width: `${sectionPct}%` }}
                  />
                </div>
              ) : null}

              <ul className="mt-4 space-y-2">
                {section.items.map((item) => {
                  const uploadHref = buildUploadHref(item);
                  return (
                    <li
                      key={item.code}
                      className="flex flex-col gap-2 rounded-md border border-border/70 px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="flex items-start gap-2">
                        <ItemStatusIcon status={item.status} />
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
          );
        })}
      </CardContent>
    </Card>
  );
}

function NextActionCallout({ item }: { item: OnboardingItem }) {
  const uploadHref = buildUploadHref(item);
  const needsAttention = ATTENTION_STATUSES.includes(item.status);
  const heading = NEXT_ACTION_LABEL[item.status] ?? "Tu próximo paso";
  const cta = NEXT_ACTION_CTA[item.status] ?? "Cargar ahora";

  const containerClass = needsAttention
    ? "rounded-md border border-amber-300 bg-amber-50 p-4 sm:p-5"
    : "rounded-md border border-primary/30 bg-primary/5 p-4 sm:p-5";
  const iconWrapperClass = needsAttention
    ? "mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-amber-500 text-white"
    : "mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground";
  const headingClass = needsAttention
    ? "text-xs font-medium uppercase tracking-wide text-amber-700"
    : "text-xs font-medium uppercase tracking-wide text-primary";

  return (
    <div className={containerClass}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <div className={iconWrapperClass}>
            {needsAttention ? (
              <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            ) : (
              <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            )}
          </div>
          <div className="min-w-0">
            <p className={headingClass}>{heading}</p>
            <p className="mt-1 text-sm font-semibold">{item.name}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {INSTITUTION_LABELS[item.institution] ?? item.institution}
              {item.note ? ` · ${item.note}` : ""}
            </p>
          </div>
        </div>
        <Button
          asChild
          size="sm"
          variant={needsAttention ? "default" : "default"}
          className="self-start sm:self-auto"
        >
          <Link href={uploadHref}>
            {cta}
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </Button>
      </div>
    </div>
  );
}

function ItemStatusIcon({ status }: { status: RequirementStatus }) {
  if (status === "pendiente") {
    return <FileText className="mt-0.5 h-4 w-4 text-muted-foreground" aria-hidden="true" />;
  }
  if (status === "rechazado" || status === "vencido") {
    return <AlertCircle className="mt-0.5 h-4 w-4 text-red-600" aria-hidden="true" />;
  }
  if (status === "posible_mismatch" || status === "requiere_aclaracion") {
    return <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-600" aria-hidden="true" />;
  }
  if (status === "pendiente_revision" || status === "recibido") {
    return <Clock3 className="mt-0.5 h-4 w-4 text-primary" aria-hidden="true" />;
  }
  if (status === "no_aplica") {
    return <FileText className="mt-0.5 h-4 w-4 text-muted-foreground/60" aria-hidden="true" />;
  }
  return <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-600" aria-hidden="true" />;
}

function CompletedBanner({ total }: { total: number }) {
  return (
    <div className="rounded-md border border-emerald-200 bg-emerald-50 p-4 sm:p-5">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-white">
          <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-emerald-900">
            Expediente corporativo completo
          </p>
          <p className="mt-1 text-xs text-emerald-900/80">
            Recibimos los {total} documentos obligatorios. La revisión humana sigue su curso; ya
            puedes avanzar al calendario REPSE.
          </p>
        </div>
      </div>
    </div>
  );
}

function findNextAction(data: OnboardingSummary): OnboardingItem | null {
  let attention: OnboardingItem | null = null;
  let pending: OnboardingItem | null = null;
  for (const section of data.sections) {
    for (const item of section.items) {
      if (!item.required) continue;
      if (!attention && ATTENTION_STATUSES.includes(item.status)) {
        attention = item;
      }
      if (!pending && item.status === "pendiente") {
        pending = item;
      }
    }
    if (attention) break;
  }
  return attention ?? pending;
}

function buildUploadHref(item: OnboardingItem): string {
  // Attention items already submitted route through the Correction Flow so
  // the provider sees the reviewer reason / signals before re-uploading.
  if (item.submission_id && ATTENTION_STATUSES.includes(item.status)) {
    return `/portal/submissions/${item.submission_id}`;
  }
  const params = new URLSearchParams({
    requirement: item.name,
    requirement_code: item.code,
    institution: item.institution,
    load_type: "alta_inicial",
  });
  return `/portal/upload?${params.toString()}`;
}
