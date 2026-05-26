"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  ChatTeardrop,
  CheckCircle,
  DownloadSimple,
  Eye,
  FileText,
  Files,
  Lightning,
  Warning,
  WarningOctagon,
  type Icon,
} from "@phosphor-icons/react";

import {
  Donut,
  RadialGauge,
  StackedBars,
  type ChartSegment,
} from "@/components/checkwise/charts";
import {
  EmptyState,
  Surface,
} from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { ClientShell } from "../../_shell";
import {
  clientSubmissionDocumentUrl,
  clientVendorExpedienteZipUrl,
  fetchClientSubmissionDocumentBlob,
  getClientVendorDetail,
  type ClientVendorContractDoc,
  type ClientVendorDetail,
} from "@/lib/api/client";

type PageProps = {
  params: Promise<{ vendor_id: string }>;
};

export default function ClientVendorDetailPage({ params }: PageProps) {
  const { vendor_id } = use(params);
  const [detail, setDetail] = useState<ClientVendorDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getClientVendorDetail(vendor_id)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Error al cargar proveedor.");
      });
    return () => {
      cancelled = true;
    };
  }, [vendor_id]);

  return (
    <ClientShell
      title={
        detail
          ? String(detail.vendor.name ?? "Detalle de proveedor")
          : "Detalle de proveedor"
      }
      description={
        detail
          ? `RFC ${String(detail.vendor.rfc ?? "—")} · ${detail.semaphore.label}`
          : "Cargando información del proveedor…"
      }
      actions={
        <>
          {/* Phase 5 / Slice 5C — client-scoped vendor expediente
              ZIP. No filter UI here yet (V1) — the modal lives on
              the provider dashboard. Cookie-auth navigation pattern
              (target=_blank). The backend audits the request as
              ``client.vendor_expediente_downloaded`` so the
              forensic trail distinguishes this from a provider
              self-pull. */}
          <Button asChild size="sm" variant="outline">
            <a
              href={clientVendorExpedienteZipUrl(vendor_id)}
              target="_blank"
              rel="noreferrer"
            >
              <DownloadSimple
                className="h-4 w-4"
                weight="bold"
                aria-hidden="true"
              />
              Descargar expediente
            </a>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link href="/client/vendors">
              <ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
              Volver
            </Link>
          </Button>
        </>
      }
    >
      {error ? (
        <p className="rounded-md border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] p-3 text-sm text-[color:var(--status-warning-text)]">
          {error}
        </p>
      ) : !detail ? (
        <DetailSkeleton />
      ) : (
        <div className="space-y-6">
          <VendorHero detail={detail} />
          <div className="grid gap-5 lg:grid-cols-3">
            <div className="space-y-5 lg:col-span-2">
              <ContractDocumentsCard detail={detail} />
              <SuggestedActionsCard detail={detail} />
              <AttentionTodayCard detail={detail} />
              <RecentSubmissionsCard detail={detail} />
            </div>
            <div className="space-y-5">
              <DocumentBreakdownCard detail={detail} />
              <UpcomingDeadlinesCard detail={detail} />
              <ReviewerNotesCard detail={detail} />
            </div>
          </div>
        </div>
      )}
    </ClientShell>
  );
}

// ─── Hero ────────────────────────────────────────────────────────

function VendorHero({ detail }: { detail: ClientVendorDetail }) {
  const tone =
    detail.semaphore.level === "green"
      ? "success"
      : detail.semaphore.level === "yellow"
        ? "warning"
        : "error";
  const ToneIcon =
    detail.semaphore.level === "green"
      ? CheckCircle
      : detail.semaphore.level === "yellow"
        ? Warning
        : WarningOctagon;
  return (
    <section className="cw-fade-up rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-xs md:p-6">
      <div className="grid gap-5 md:grid-cols-[auto,1fr] md:items-center md:gap-8">
        <RadialGauge
          value={detail.semaphore.compliance_pct}
          tone={tone}
          size={140}
          thickness={11}
          label={`${detail.semaphore.compliance_pct}%`}
          caption="cumplimiento"
        />
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant={
                tone === "success" ? "success" : tone === "warning" ? "warning" : "destructive"
              }
            >
              <ToneIcon className="h-3 w-3" weight="bold" aria-hidden="true" />
              {detail.semaphore.label}
            </Badge>
            <span className="cw-eyebrow">
              {detail.semaphore.on_track} de {detail.semaphore.total_tracked} obligaciones al día
            </span>
            {detail.onboarding_summary.is_gate_satisfied ? (
              <Badge variant="brand">Expediente listo</Badge>
            ) : (
              <Badge variant="warning">Expediente pendiente</Badge>
            )}
          </div>
          <p className="text-[15px] leading-relaxed text-[color:var(--text-primary)]">
            {detail.semaphore.reason}
          </p>
          <ExpedienteMicroBar detail={detail} />
        </div>
      </div>
    </section>
  );
}

function ExpedienteMicroBar({ detail }: { detail: ClientVendorDetail }) {
  const s = detail.onboarding_summary;
  const remaining = Math.max(
    0,
    s.total_required - s.completed - s.in_review - s.needs_action,
  );
  const segments: ChartSegment[] = [
    { label: "Aprobados", value: s.completed, tone: "success" },
    { label: "En revisión", value: s.in_review, tone: "info" },
    { label: "Por atender", value: s.needs_action, tone: "warning" },
    { label: "Sin iniciar", value: remaining, tone: "neutral" },
  ];
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-[11px]">
        <p className="cw-eyebrow">
          Expediente inicial · {s.completion_pct}%
        </p>
        <p className="font-mono tabular-nums text-[color:var(--text-tertiary)]">
          {s.completed + s.in_review} / {s.total_required}
        </p>
      </div>
      <StackedBars segments={segments} height={10} showLegend={false} />
    </div>
  );
}

// ─── Contracts (item 1) ──────────────────────────────────────────

function ContractDocumentsCard({ detail }: { detail: ClientVendorDetail }) {
  // Sorted newest-first on the backend (created_at DESC). Surface the
  // entire history so the client_admin can see the chain: original
  // contract, modifications, service orders. Each row offers an
  // inline "Ver" (Blob URL → window.open) plus a "Descargar" link.
  const contracts = detail.contracts ?? [];
  return (
    <Surface
      title="Contratos del proveedor"
      icon={FileText}
      description="Contrato firmado, modificaciones y órdenes de servicio. Aquí puedes consultarlos o descargarlos directamente."
    >
      {contracts.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="Sin contratos registrados"
          description="Cuando el proveedor suba el contrato firmado y sus anexos, aparecerán aquí."
        />
      ) : (
        <ul className="divide-y divide-[color:var(--border-subtle)]">
          {contracts.map((c) => (
            <ContractRow key={c.submission_id} contract={c} />
          ))}
        </ul>
      )}
    </Surface>
  );
}

function ContractRow({ contract }: { contract: ClientVendorContractDoc }) {
  const [viewing, setViewing] = useState(false);
  const [viewError, setViewError] = useState<string | null>(null);

  async function onView() {
    setViewing(true);
    setViewError(null);
    try {
      const url = await fetchClientSubmissionDocumentBlob(contract.submission_id);
      const win = window.open(url, "_blank", "noopener,noreferrer");
      // Revoke a few seconds later — the new tab has already loaded
      // the PDF by then, but we don't want the Blob URL to leak.
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
      if (!win) {
        setViewError("Permite ventanas emergentes para ver el contrato.");
      }
    } catch {
      setViewError("No pudimos abrir el contrato. Intenta descargarlo.");
    } finally {
      setViewing(false);
    }
  }

  const downloadHref = clientSubmissionDocumentUrl(contract.submission_id, {
    download: true,
  });

  const sizeText =
    contract.size_bytes != null
      ? contract.size_bytes >= 1024 * 1024
        ? `${(contract.size_bytes / (1024 * 1024)).toFixed(1)} MB`
        : `${Math.max(1, Math.round(contract.size_bytes / 1024))} KB`
      : null;

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium text-[color:var(--text-primary)]">
          {contract.requirement_name}
        </p>
        <p className="mt-0.5 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
          {new Date(contract.submitted_at).toLocaleString("es-MX", {
            day: "2-digit",
            month: "short",
            year: "numeric",
          })}
          {sizeText ? ` · ${sizeText}` : ""}
          {contract.filename ? ` · ${contract.filename}` : ""}
        </p>
        {viewError ? (
          <p className="mt-1 text-[11px] text-[color:var(--status-error-text)]">
            {viewError}
          </p>
        ) : null}
      </div>
      <div className="flex items-center gap-2">
        <Badge variant="outline">{contract.status}</Badge>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={onView}
          disabled={viewing}
        >
          <Eye className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          {viewing ? "Abriendo…" : "Ver"}
        </Button>
        <Button asChild size="sm" variant="outline">
          <a
            href={downloadHref}
            target="_blank"
            rel="noreferrer"
            download={contract.filename ?? undefined}
          >
            <DownloadSimple
              className="h-3.5 w-3.5"
              weight="bold"
              aria-hidden="true"
            />
            Descargar
          </a>
        </Button>
      </div>
    </li>
  );
}

// ─── Suggested actions ───────────────────────────────────────────

const PRIORITY_META: Record<"high" | "medium" | "low", { icon: Icon; tone: "destructive" | "warning" | "info"; label: string }> = {
  high: { icon: Lightning, tone: "destructive", label: "Alta" },
  medium: { icon: Warning, tone: "warning", label: "Media" },
  low: { icon: ChatTeardrop, tone: "info", label: "Baja" },
};

function SuggestedActionsCard({ detail }: { detail: ClientVendorDetail }) {
  return (
    <Surface
      title="Acciones sugeridas"
      icon={Lightning}
      description="Lo que el equipo legal recomienda priorizar para este proveedor."
    >
      {detail.suggested_actions.length === 0 ? (
        <EmptyState
          icon={CheckCircle}
          title="Sin acciones sugeridas"
          description="El proveedor está al día, no hay pasos accionables ahora mismo."
        />
      ) : (
        <ul className="space-y-3">
          {detail.suggested_actions.map((a) => {
            const meta = PRIORITY_META[a.priority];
            const IconComponent = meta.icon;
            return (
              <li
                key={a.id}
                className="cw-hover-lift rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-3"
              >
                <div className="flex items-start gap-3">
                  <span
                    className={
                      "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md " +
                      (meta.tone === "destructive"
                        ? "bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)]"
                        : meta.tone === "warning"
                          ? "bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)]"
                          : "bg-[color:var(--status-info-bg)] text-[color:var(--status-info-text)]")
                    }
                    aria-hidden="true"
                  >
                    <IconComponent className="h-4 w-4" weight="bold" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={meta.tone}>{meta.label}</Badge>
                      <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                        {a.type}
                      </span>
                    </div>
                    <p className="mt-1 text-[13px] font-medium text-[color:var(--text-primary)]">
                      {a.title}
                    </p>
                    <p className="mt-0.5 text-[12px] leading-relaxed text-[color:var(--text-secondary)]">
                      {a.body}
                    </p>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Surface>
  );
}

// ─── Attention today ─────────────────────────────────────────────

function AttentionTodayCard({ detail }: { detail: ClientVendorDetail }) {
  return (
    <Surface title="Atención inmediata" icon={Warning}>
      {detail.attention_today.length === 0 ? (
        <EmptyState
          icon={CheckCircle}
          title="Sin pendientes urgentes"
          description="No hay obligaciones que requieran atención inmediata."
        />
      ) : (
        <ul className="divide-y divide-[color:var(--border-subtle)]">
          {detail.attention_today.map((a) => (
            <li
              key={a.id}
              className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
            >
              <div className="min-w-0">
                <p className="text-[13px] font-medium text-[color:var(--text-primary)]">
                  {a.title}
                </p>
                <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  {a.institution}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {a.due_in_days !== null ? (
                  <span
                    className={
                      "rounded-full px-2 py-0.5 font-mono text-[10px] tabular-nums " +
                      (a.due_in_days < 0
                        ? "bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)]"
                        : a.due_in_days <= 7
                          ? "bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)]"
                          : "bg-[color:var(--surface-sunken)] text-[color:var(--text-tertiary)]")
                    }
                  >
                    {a.due_in_days >= 0
                      ? `vence en ${a.due_in_days}d`
                      : `vencido ${Math.abs(a.due_in_days)}d`}
                  </span>
                ) : null}
                <Badge variant="outline">{a.state}</Badge>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Surface>
  );
}

// ─── Recent submissions ──────────────────────────────────────────

function RecentSubmissionsCard({ detail }: { detail: ClientVendorDetail }) {
  return (
    <Surface
      title={`Entregas recientes (${detail.recent_submissions.length})`}
      icon={Files}
    >
      {detail.recent_submissions.length === 0 ? (
        <EmptyState
          icon={Files}
          title="Sin entregas registradas"
          description="Cuando el proveedor suba documentos, aparecerán aquí."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="border-b border-[color:var(--border-subtle)] text-left font-mono uppercase tracking-wide text-[color:var(--text-tertiary)]">
              <tr>
                <th className="px-2 py-2">Fecha</th>
                <th className="px-2 py-2">Requisito</th>
                <th className="px-2 py-2">Periodo</th>
                <th className="px-2 py-2">Estado</th>
                <th className="px-2 py-2">Archivo</th>
              </tr>
            </thead>
            <tbody>
              {detail.recent_submissions.map((s) => (
                <tr
                  key={s.submission_id}
                  className="border-b border-[color:var(--border-subtle)] last:border-0 hover:bg-[color:var(--surface-hover)]"
                >
                  <td className="px-2 py-2 font-mono text-[11px]">
                    {new Date(s.submitted_at).toLocaleString("es-MX", {
                      day: "2-digit",
                      month: "short",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </td>
                  <td className="px-2 py-2">
                    {s.requirement_name ?? s.requirement_code ?? "—"}
                  </td>
                  <td className="px-2 py-2 font-mono">{s.period_key ?? "—"}</td>
                  <td className="px-2 py-2">
                    <Badge variant="outline">{s.status}</Badge>
                  </td>
                  <td className="px-2 py-2 truncate text-[color:var(--text-secondary)]">
                    {s.filename ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Surface>
  );
}

// ─── Document breakdown ──────────────────────────────────────────

function DocumentBreakdownCard({ detail }: { detail: ClientVendorDetail }) {
  const c = detail.document_state_counts;
  const all: ChartSegment[] = [
    { label: "Aprobados", value: c.approved, tone: "success" },
    { label: "En revisión", value: c.in_review, tone: "info" },
    { label: "Recibidos", value: c.uploaded, tone: "info" },
    { label: "Necesitan acción", value: c.needs_review, tone: "warning" },
    { label: "Rechazados", value: c.rejected, tone: "error" },
    { label: "Vencidos", value: c.expired, tone: "error" },
    { label: "Pendientes", value: c.pending, tone: "neutral" },
  ];
  const segments: ChartSegment[] = all.filter((s) => s.value > 0);
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  return (
    <Surface title="Documentos por estado">
      {total === 0 ? (
        <EmptyState
          title="Sin documentos cargados"
          description="Aún no hay documentos para este proveedor."
        />
      ) : (
        <Donut
          segments={segments}
          size={132}
          thickness={14}
          centerLabel={total}
          centerCaption="documentos"
        />
      )}
    </Surface>
  );
}

// ─── Upcoming deadlines ──────────────────────────────────────────

function UpcomingDeadlinesCard({ detail }: { detail: ClientVendorDetail }) {
  return (
    <Surface title="Próximos vencimientos">
      {detail.upcoming_deadlines.length === 0 ? (
        <EmptyState
          icon={CheckCircle}
          title="Sin vencimientos próximos"
          description="No hay obligaciones próximas a vencer."
        />
      ) : (
        <ul className="space-y-2.5">
          {detail.upcoming_deadlines.slice(0, 6).map((d) => (
            <li
              key={d.id}
              className="flex items-start justify-between gap-3 border-b border-[color:var(--border-subtle)] pb-2.5 last:border-0 last:pb-0"
            >
              <div className="min-w-0">
                <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  {d.institution} {d.period_key ? `· ${d.period_key}` : ""}
                </p>
                <p className="mt-0.5 text-[12px] font-medium text-[color:var(--text-primary)]">
                  {d.title}
                </p>
              </div>
              <ArrowRight
                className="mt-1 h-3.5 w-3.5 text-[color:var(--text-tertiary)]"
                weight="bold"
                aria-hidden="true"
              />
            </li>
          ))}
        </ul>
      )}
    </Surface>
  );
}

// ─── Reviewer notes ──────────────────────────────────────────────

function ReviewerNotesCard({ detail }: { detail: ClientVendorDetail }) {
  return (
    <Surface title="Notas del revisor">
      {detail.recent_reviewer_notes.length === 0 ? (
        <EmptyState
          title="Sin notas recientes"
          description="El revisor aún no ha agregado comentarios sobre este proveedor."
        />
      ) : (
        <ul className="space-y-2.5">
          {detail.recent_reviewer_notes.map((n) => (
            <li
              key={`${n.submission_id}-${n.occurred_at}`}
              className="rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-2.5"
            >
              <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                {new Date(n.occurred_at).toLocaleString("es-MX")} · {n.result}
              </p>
              <p className="mt-1 text-[12px] text-[color:var(--text-primary)]">
                {n.message ?? "(sin mensaje)"}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Surface>
  );
}

// ─── Skeleton ────────────────────────────────────────────────────

function DetailSkeleton() {
  return (
    <div className="space-y-6">
      <div className="h-40 animate-pulse rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <div className="h-48 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
          <div className="h-48 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
        </div>
        <div className="space-y-5">
          <div className="h-40 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
          <div className="h-40 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
        </div>
      </div>
    </div>
  );
}
