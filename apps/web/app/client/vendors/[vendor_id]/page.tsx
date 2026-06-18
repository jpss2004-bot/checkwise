"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  ChartBar,
  ChatTeardrop,
  CheckCircle,
  CircleNotch,
  DownloadSimple,
  Eye,
  FileText,
  FileXls,
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
import { safeReturnTo } from "@/lib/navigation/return-to";

import { ClientShell } from "../../_shell";
import {
  ClientApiError,
  clientVendorExpedienteZipUrl,
  clientVendorMetadataDownloadUrl,
  fetchClientSubmissionDocumentBlob,
  getClientVendorDetail,
  type ClientVendorContractDoc,
  type ClientVendorDetail,
  type ClientVendorDocumentActionItem,
} from "@/lib/api/client";
import {
  ErrorState,
  NotFoundState,
} from "@/components/checkwise/portal/state-surfaces";
import { downloadAuthenticatedFile } from "@/lib/api/download";
import { createReportFromPreset, ReportsApiError } from "@/lib/api/reports";
import {
  contractStatusLabel,
  contractStatusVariant,
  reviewerResultLabel,
  slotStateLabel,
  slotStateVariant,
  suggestedActionLabel,
} from "@/lib/constants/statuses";

type PageProps = {
  params: Promise<{ vendor_id: string }>;
};

const CLIENT_VENDOR_RETURN_PREFIXES = [
  "/client/vendors",
  "/client/calendar",
  "/client/dashboard",
  "/client/auditoria",
] as const;

function clientVendorReturnLabel(href: string): string {
  if (href.startsWith("/client/calendar")) return "Volver al calendario";
  if (href.startsWith("/client/dashboard")) return "Volver al dashboard";
  if (href.startsWith("/client/auditoria")) return "Volver a auditoría";
  return "Volver a proveedores";
}

export default function ClientVendorDetailPage({ params }: PageProps) {
  const { vendor_id } = use(params);
  const [detail, setDetail] = useState<ClientVendorDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  // HTTP status of a load failure so a true 404/403 (provider not found /
  // not in scope) reads differently from a transient blip.
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const router = useRouter();
  const [generating, setGenerating] = useState(false);
  const [downloadingZip, setDownloadingZip] = useState(false);
  const [downloadingMetadata, setDownloadingMetadata] = useState(false);
  const [vendorsReturnHref, setVendorsReturnHref] = useState("/client/vendors");
  const [focusKey, setFocusKey] = useState<string | null>(null);

  const onDownloadExpediente = useCallback(async () => {
    if (downloadingZip) return;
    setDownloadingZip(true);
    try {
      await downloadAuthenticatedFile(
        clientVendorExpedienteZipUrl(vendor_id),
        "expediente.zip",
      );
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "No pudimos preparar la descarga.",
      );
    } finally {
      setDownloadingZip(false);
    }
  }, [downloadingZip, vendor_id]);

  const onDownloadMetadata = useCallback(async () => {
    if (downloadingMetadata) return;
    setDownloadingMetadata(true);
    try {
      await downloadAuthenticatedFile(
        clientVendorMetadataDownloadUrl(vendor_id),
        "metadata.xlsx",
      );
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "No pudimos preparar la descarga de metadata.",
      );
    } finally {
      setDownloadingMetadata(false);
    }
  }, [downloadingMetadata, vendor_id]);

  const onGenerateReport = useCallback(async () => {
    if (generating) return;
    setGenerating(true);
    try {
      const r = await createReportFromPreset("client-vendor-detail", true, {
        vendorId: vendor_id,
      });
      router.push(`/client/reports/${r.id}`);
    } catch (e) {
      setGenerating(false);
      setError(
        e instanceof ReportsApiError ? e.message : "Error generando el reporte.",
      );
    }
  }, [generating, router, vendor_id]);

  useEffect(() => {
    const raw = new URLSearchParams(window.location.search).get("returnTo");
    setVendorsReturnHref(
      safeReturnTo(raw, CLIENT_VENDOR_RETURN_PREFIXES, "/client/vendors"),
    );
  }, [vendor_id]);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setErrorStatus(null);
    getClientVendorDetail(vendor_id)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setErrorStatus(err instanceof ClientApiError ? err.status : null);
        setError(err instanceof Error ? err.message : "Error al cargar proveedor.");
      });
    return () => {
      cancelled = true;
    };
  }, [vendor_id, reloadKey]);

  // Deep-link focus: report findings, alerts, and the vendors-list count
  // cells link here with ?focus=<requirement_code|bucket>#documentos. Once the
  // detail loads, scroll the "Documentos por atender" card into view and
  // briefly highlight the matching rows, then let the highlight fade.
  useEffect(() => {
    if (!detail) return;
    const focus = new URLSearchParams(window.location.search).get("focus");
    const wantsDocs = focus || window.location.hash === "#documentos";
    if (!wantsDocs) return;
    if (focus) setFocusKey(focus);
    document
      .getElementById("documentos")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
    if (!focus) return;
    const t = window.setTimeout(() => setFocusKey(null), 4000);
    return () => window.clearTimeout(t);
  }, [detail]);

  // Turn the (previously dead-end) suggested-action / attention rows into
  // one-click drills: scroll to "Documentos por atender" and briefly
  // highlight the rows matching this requirement (audit P2.12). Reuses the
  // same focusKey machinery the deep-link effect above uses.
  const focusOnDocuments = useCallback((code: string | null) => {
    if (code) setFocusKey(code);
    document
      .getElementById("documentos")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
    if (code) window.setTimeout(() => setFocusKey(null), 4000);
  }, []);

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
              the provider dashboard. Fetched with the staff JWT via
              downloadAuthenticatedFile — a plain navigation cannot
              carry the Bearer header (audit 2026-06-12). The backend
              audits the request as
              ``client.vendor_expediente_downloaded`` so the
              forensic trail distinguishes this from a provider
              self-pull. */}
          <Button
            size="sm"
            variant="default"
            onClick={onGenerateReport}
            disabled={generating}
            title="Generar un reporte visual de este proveedor"
          >
            {generating ? (
              <CircleNotch className="h-4 w-4 animate-spin" weight="bold" aria-hidden="true" />
            ) : (
              <ChartBar className="h-4 w-4" weight="bold" aria-hidden="true" />
            )}
            Generar reporte
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={onDownloadExpediente}
            disabled={downloadingZip}
            title="Descargar el expediente completo del proveedor"
          >
            {downloadingZip ? (
              <CircleNotch
                className="h-4 w-4 animate-spin"
                weight="bold"
                aria-hidden="true"
              />
            ) : (
              <DownloadSimple
                className="h-4 w-4"
                weight="bold"
                aria-hidden="true"
              />
            )}
            Descargar expediente
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={onDownloadMetadata}
            disabled={downloadingMetadata}
            title="Descargar la metadata de este proveedor en Excel"
          >
            {downloadingMetadata ? (
              <CircleNotch
                className="h-4 w-4 animate-spin"
                weight="bold"
                aria-hidden="true"
              />
            ) : (
              <FileXls className="h-4 w-4" weight="bold" aria-hidden="true" />
            )}
            Descargar metadata
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link href={vendorsReturnHref}>
              <ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
              {clientVendorReturnLabel(vendorsReturnHref)}
            </Link>
          </Button>
        </>
      }
    >
      {error ? (
        errorStatus === 404 || errorStatus === 403 ? (
          <NotFoundState
            title="Proveedor no disponible"
            description="Este proveedor no existe o no está dentro de tu portafolio."
            action={
              <Link href={vendorsReturnHref}>
                <Button size="sm" variant="outline">
                  {clientVendorReturnLabel(vendorsReturnHref)}
                </Button>
              </Link>
            }
          />
        ) : (
          <ErrorState
            tone="error"
            title="No pudimos cargar el proveedor"
            description={error}
            onRetry={() => setReloadKey((k) => k + 1)}
            secondary={
              <Link href={vendorsReturnHref}>
                <Button size="sm" variant="outline">
                  {clientVendorReturnLabel(vendorsReturnHref)}
                </Button>
              </Link>
            }
          />
        )
      ) : !detail ? (
        <DetailSkeleton />
      ) : (
        <div className="space-y-6">
          <VendorHero detail={detail} />
          <div className="grid gap-5 lg:grid-cols-3">
            <div className="space-y-5 lg:col-span-2">
              <ContractDocumentsCard detail={detail} />
              <div id="documentos" className="scroll-mt-24">
                <DocumentActionItemsCard detail={detail} focusKey={focusKey} />
              </div>
              <SuggestedActionsCard detail={detail} onFocus={focusOnDocuments} />
              <AttentionTodayCard detail={detail} onFocus={focusOnDocuments} />
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
    { label: slotStateLabel("needs_correction"), value: s.needs_action, tone: "warning" },
    { label: slotStateLabel("missing"), value: remaining, tone: "neutral" },
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
  const [downloading, setDownloading] = useState(false);
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

  async function onDownload() {
    if (downloading) return;
    setDownloading(true);
    setViewError(null);
    try {
      const url = await fetchClientSubmissionDocumentBlob(contract.submission_id, {
        download: true,
      });
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = contract.filename ?? "documento.pdf";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      setViewError("No pudimos descargar el contrato. Intenta de nuevo.");
    } finally {
      setDownloading(false);
    }
  }

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
        <Badge variant={contractStatusVariant(contract.status)}>
          {contractStatusLabel(contract.status)}
        </Badge>
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
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={onDownload}
          disabled={downloading}
        >
          <DownloadSimple
            className="h-3.5 w-3.5"
            weight="bold"
            aria-hidden="true"
          />
          {downloading ? "Descargando…" : "Descargar"}
        </Button>
      </div>
    </li>
  );
}

// ─── Documents To Act On ────────────────────────────────────────

const ACTION_KIND_LABEL: Record<ClientVendorDocumentActionItem["kind"], string> = {
  missing: "Por entregar",
  rejected: "Requiere corrección",
  needs_correction: "Necesita aclaración",
  possible_mismatch: "Posible inconsistencia",
  expired: "Vencido",
  due_soon: "Por vencer",
};

function formatDeadline(value: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("es-MX", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

const FOCUS_KINDS: Record<
  string,
  ReadonlyArray<ClientVendorDocumentActionItem["kind"]>
> = {
  missing: ["missing"],
  // The vendors-list "rechazos/correcciones" column aggregates every
  // actionable state, so focus=rejected highlights all of them at once.
  rejected: ["rejected", "needs_correction", "possible_mismatch", "expired"],
  due_soon: ["due_soon"],
};

function isActionItemFocused(
  item: ClientVendorDocumentActionItem,
  focusKey: string | null,
): boolean {
  if (!focusKey) return false;
  if (item.requirement_code === focusKey) return true;
  return FOCUS_KINDS[focusKey]?.includes(item.kind) ?? false;
}

function DocumentActionItemsCard({
  detail,
  focusKey = null,
}: {
  detail: ClientVendorDetail;
  focusKey?: string | null;
}) {
  const items = detail.document_action_items ?? [];
  return (
    <Surface
      title="Documentos por atender"
      icon={WarningOctagon}
      description="Faltantes, correcciones y vencimientos del proveedor."
    >
      {items.length === 0 ? (
        <EmptyState
          icon={CheckCircle}
          title="Sin documentos por atender"
          description="No hay faltantes, correcciones ni vencimientos abiertos para este proveedor."
        />
      ) : (
        <ul className="divide-y divide-[color:var(--border-subtle)]">
          {items.map((item) => (
            <ActionItemRow
              key={item.id}
              item={item}
              focused={isActionItemFocused(item, focusKey)}
            />
          ))}
        </ul>
      )}
    </Surface>
  );
}

function ActionItemRow({
  item,
  focused,
}: {
  item: ClientVendorDocumentActionItem;
  focused: boolean;
}) {
  const [viewing, setViewing] = useState(false);
  const [viewError, setViewError] = useState<string | null>(null);

  async function onView() {
    if (!item.submission_id || viewing) return;
    setViewing(true);
    setViewError(null);
    try {
      const url = await fetchClientSubmissionDocumentBlob(item.submission_id);
      const win = window.open(url, "_blank", "noopener,noreferrer");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
      if (!win) {
        setViewError("Permite ventanas emergentes para ver el documento.");
      }
    } catch {
      setViewError("No pudimos abrir el documento. Intenta de nuevo.");
    } finally {
      setViewing(false);
    }
  }

  return (
    <li
      className={
        "grid gap-3 py-3 first:pt-0 last:pb-0 md:grid-cols-[1fr,auto] md:items-center" +
        (focused
          ? " -mx-2 rounded-md px-2 ring-2 ring-[color:var(--text-ai)] bg-[color:var(--surface-hover)]"
          : "")
      }
    >
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={slotStateVariant(item.state)}>
            {slotStateLabel(item.state)}
          </Badge>
          <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            {item.institution ?? "—"}
            {item.period_key ? ` · ${item.period_key}` : ""}
          </span>
          <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            vence {formatDeadline(item.deadline_iso)}
          </span>
        </div>
        <p className="truncate text-[13px] font-medium text-[color:var(--text-primary)]">
          {item.requirement_name ?? item.requirement_code ?? "Documento requerido"}
        </p>
        <p className="text-[11px] text-[color:var(--text-secondary)]">
          {ACTION_KIND_LABEL[item.kind]}
          {item.due_in_days !== null && item.due_in_days >= 0
            ? ` · ${item.due_in_days} día(s)`
            : ""}
        </p>
        {viewError ? (
          <p className="text-[11px] text-[color:var(--status-error-text)]">
            {viewError}
          </p>
        ) : null}
      </div>
      {/* The client monitors; it cannot upload the provider's documents. When
          the provider HAS submitted (rejected / needs correction / expired),
          let the client open that document to see what's wrong. Purely missing
          items have nothing to open yet, so they read as a finding. */}
      {item.submission_id ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={onView}
          disabled={viewing}
        >
          <Eye className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          {viewing ? "Abriendo…" : "Ver documento"}
        </Button>
      ) : null}
    </li>
  );
}

// ─── Suggested actions ───────────────────────────────────────────

const PRIORITY_META: Record<"high" | "medium" | "low", { icon: Icon; tone: "destructive" | "warning" | "info"; label: string }> = {
  high: { icon: Lightning, tone: "destructive", label: "Alta" },
  medium: { icon: Warning, tone: "warning", label: "Media" },
  low: { icon: ChatTeardrop, tone: "info", label: "Baja" },
};

function SuggestedActionsCard({
  detail,
  onFocus,
}: {
  detail: ClientVendorDetail;
  onFocus: (code: string | null) => void;
}) {
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
                      <span className="text-[11px] text-[color:var(--text-tertiary)]">
                        {suggestedActionLabel(a.type)}
                      </span>
                    </div>
                    <p className="mt-1 text-[13px] font-medium text-[color:var(--text-primary)]">
                      {a.title}
                    </p>
                    <p className="mt-0.5 text-[12px] leading-relaxed text-[color:var(--text-secondary)]">
                      {a.body}
                    </p>
                    <button
                      type="button"
                      onClick={() => onFocus(a.requirement_code)}
                      className="mt-2 inline-flex items-center gap-1 rounded-sm text-[12px] font-medium text-[color:var(--text-link)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)] focus-visible:ring-offset-1"
                    >
                      Ver documentos
                      <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden />
                    </button>
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

function AttentionTodayCard({
  detail,
  onFocus,
}: {
  detail: ClientVendorDetail;
  onFocus: (code: string | null) => void;
}) {
  return (
    <Surface
      title="Atención inmediata"
      icon={Warning}
      description="Lo más urgente de este proveedor. Toca un pendiente para ir a sus documentos."
    >
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
                <button
                  type="button"
                  onClick={() => onFocus(null)}
                  className="rounded-sm text-left text-[13px] font-medium text-[color:var(--text-primary)] hover:text-[color:var(--text-link)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)] focus-visible:ring-offset-1"
                >
                  {a.title}
                </button>
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
                <Badge variant={slotStateVariant(a.state)}>
                  {slotStateLabel(a.state)}
                </Badge>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Surface>
  );
}

// ─── Document breakdown ──────────────────────────────────────────

function DocumentBreakdownCard({ detail }: { detail: ClientVendorDetail }) {
  const c = detail.document_state_counts;
  const all: ChartSegment[] = [
    { label: "Aprobados", value: c.approved, tone: "success" },
    // 2026-06-10: "Recibidos" (uploaded) and "En revisión" (in_review)
    // collapsed to a single client-facing state — sum both counts.
    { label: "En revisión", value: c.in_review + c.uploaded, tone: "info" },
    { label: slotStateLabel("needs_correction"), value: c.needs_review, tone: "warning" },
    { label: slotStateLabel("rejected"), value: c.rejected, tone: "error" },
    { label: "Vencidos", value: c.expired, tone: "error" },
    // D6 — was "Pendientes", which collided with the Dashboard KPI
    // "Faltantes obligatorios" (same numeric definition, different
    // label) and with the calendar's "Pendientes" (an active
    // ``pendiente_revision`` reviewer-queue state, NOT this). Renamed
    // to "Sin iniciar" — same word ExpedienteMicroBar above uses for
    // the same set, so the two charts on this page now agree.
    { label: slotStateLabel("missing"), value: c.pending, tone: "neutral" },
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
              <p className="text-[11px] text-[color:var(--text-tertiary)]">
                {new Date(n.occurred_at).toLocaleString("es-MX")} ·{" "}
                {reviewerResultLabel(n.result)}
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
