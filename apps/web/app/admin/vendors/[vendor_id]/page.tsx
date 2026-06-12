"use client";

import { Suspense, use, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  DownloadSimple,
  FileText,
  Storefront,
  Warning,
} from "@phosphor-icons/react";

import { AdminShell } from "../../_shell";
import { EmptyState, Surface } from "@/components/checkwise/dashboard/stat-card";
import { RequirementStatusBadge } from "@/components/checkwise/portal/requirement-status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MetadataStrip } from "@/components/ui/metadata-strip";
import { withReturnTo } from "@/lib/navigation/return-to";
import {
  adminVendorExpedienteZipUrl,
  getClient,
  type AdminClient,
} from "@/lib/api/admin";
import { downloadAuthenticatedFile } from "@/lib/api/download";
import {
  getClientVendorDetail,
  type ClientVendorDetail,
} from "@/lib/api/client";
import type { RequirementStatus } from "@/lib/api/portal";
import { statusLabel } from "@/lib/constants/statuses";
import {
  entityStatusLabel,
  entityStatusVariant,
  INSTITUTION_LABELS,
  personaLabel,
} from "@/lib/constants/labels";

type PageProps = {
  params: Promise<{ vendor_id: string }>;
};

/**
 * /admin/vendors/[vendor_id] — operations-side vendor expediente.
 *
 * Before this route, the only vendor detail surface was the client
 * portal page (`/client/vendors/[id]`). When an internal_admin clicked
 * a vendor from an admin table, `VendorRef` dropped them into the
 * client-facing ClientShell (wrong nav, client framing) and the page
 * ignored the `?client_id=` scope. This surface keeps staff inside the
 * AdminShell and links every submission straight to the reviewer.
 *
 * The data comes from the same `GET /api/v1/client/vendors/{id}`
 * endpoint, which resolves cross-tenant scope for internal_admin via
 * the vendor's own client_id (see `_resolve_client_id_for_vendor`).
 */
export default function AdminVendorDetailPage({ params }: PageProps) {
  const { vendor_id } = use(params);
  return (
    <Suspense fallback={null}>
      <AdminVendorDetail vendorId={vendor_id} />
    </Suspense>
  );
}

const COUNT_LABELS: { key: keyof ClientVendorDetail["document_state_counts"]; label: string }[] = [
  { key: "approved", label: "Aprobados" },
  { key: "in_review", label: "En revisión" },
  { key: "needs_review", label: "Por revisar" },
  { key: "uploaded", label: "Recibidos" },
  { key: "pending", label: "Pendientes" },
  { key: "rejected", label: "Requieren corrección" },
  { key: "expired", label: "Vencidos" },
  { key: "exception", label: "Con nota legal" },
];

const SEMAPHORE_TONE: Record<
  ClientVendorDetail["semaphore"]["level"],
  { variant: "success" | "warning" | "destructive"; dot: string }
> = {
  green: { variant: "success", dot: "var(--status-success-text)" },
  yellow: { variant: "warning", dot: "var(--status-warning-text)" },
  red: { variant: "destructive", dot: "var(--status-error-text)" },
};

function AdminVendorDetail({ vendorId }: { vendorId: string }) {
  const searchParams = useSearchParams();
  const clientId = searchParams.get("client_id") ?? undefined;

  const [detail, setDetail] = useState<ClientVendorDetail | null>(null);
  const [client, setClient] = useState<AdminClient | null>(null);
  const [errorKind, setErrorKind] = useState<"not_found" | "network" | null>(
    null,
  );
  const [reloadKey, setReloadKey] = useState(0);
  const [downloadingZip, setDownloadingZip] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  async function onDownloadExpediente() {
    if (downloadingZip) return;
    setDownloadingZip(true);
    setDownloadError(null);
    try {
      await downloadAuthenticatedFile(
        adminVendorExpedienteZipUrl(vendorId),
        "expediente.zip",
      );
    } catch (e) {
      setDownloadError(
        e instanceof Error ? e.message : "No pudimos preparar la descarga.",
      );
    } finally {
      setDownloadingZip(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    setErrorKind(null);
    setDetail(null);
    getClientVendorDetail(vendorId, clientId ? { client_id: clientId } : undefined)
      .then(async (data) => {
        if (cancelled) return;
        setDetail(data);
        // Resolve the client's display name from the admin catalog so
        // the header reads "Acme S.A." rather than a bare UUID.
        try {
          const c = await getClient(data.client_id);
          if (!cancelled) setClient(c);
        } catch {
          // Non-fatal: the page still renders without the client name.
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const status =
          err && typeof err === "object" && "status" in err
            ? (err as { status?: number }).status
            : undefined;
        setErrorKind(status === 404 ? "not_found" : "network");
      });
    return () => {
      cancelled = true;
    };
  }, [vendorId, clientId, reloadKey]);

  const vendor = detail?.vendor ?? null;
  const vendorName = str(vendor?.name) ?? "Proveedor";
  const rfc = str(vendor?.rfc);
  const persona = str(vendor?.persona_type);
  const vendorStatus = str(vendor?.status);
  const repse = str(vendor?.repse_id);
  const vendorsHref = clientId
    ? `/admin/vendors?client_id=${encodeURIComponent(clientId)}`
    : "/admin/vendors";
  const currentVendorHref = clientId
    ? `/admin/vendors/${encodeURIComponent(vendorId)}?client_id=${encodeURIComponent(clientId)}`
    : `/admin/vendors/${encodeURIComponent(vendorId)}`;
  const reviewerHref = (submissionId: string) =>
    withReturnTo(`/admin/reviewer/${submissionId}`, currentVendorHref);
  return (
    <AdminShell
      title={detail ? vendorName : "Proveedor"}
      description={
        detail
          ? `RFC ${rfc ?? "—"} · ${detail.semaphore.label}`
          : "Cargando el expediente del proveedor…"
      }
      actions={
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href={vendorsHref}>
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
              Proveedores
            </Link>
          </Button>
          {detail ? (
            <Button
              size="sm"
              onClick={onDownloadExpediente}
              disabled={downloadingZip}
              title="Descargar el expediente completo del proveedor"
            >
              <DownloadSimple className="h-4 w-4" aria-hidden="true" />
              {downloadingZip ? "Preparando…" : "Descargar expediente"}
            </Button>
          ) : null}
        </div>
      }
    >
      {downloadError ? (
        <p className="mb-4 rounded-md border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] p-3 text-sm text-[color:var(--status-warning-text)]">
          {downloadError}
        </p>
      ) : null}
      {errorKind === "not_found" ? (
        <EmptyState
          icon={Storefront}
          title="Proveedor no encontrado"
          description="Este proveedor no tiene un expediente registrado o no está disponible para tu alcance."
          action={
            <Button asChild variant="outline" size="sm">
              <Link href={vendorsHref}>Volver a proveedores</Link>
            </Button>
          }
        />
      ) : errorKind === "network" ? (
        <EmptyState
          icon={Warning}
          title="No pudimos cargar el expediente"
          description="Ocurrió un error al consultar el proveedor. Intenta de nuevo."
          action={
            <Button
              variant="outline"
              size="sm"
              onClick={() => setReloadKey((k) => k + 1)}
            >
              Reintentar
            </Button>
          }
        />
      ) : !detail ? (
        <VendorDetailSkeleton />
      ) : (
        <div className="space-y-5">
          {/* Identity */}
          <MetadataStrip
            items={[
              {
                label: "Cliente",
                // MetadataStrip values accept ReactNode, so the client
                // name links straight to the admin client detail page.
                // Hover treatment mirrors VendorRef for consistency.
                value: detail.client_id ? (
                  <Link
                    href={`/admin/clients/${encodeURIComponent(detail.client_id)}`}
                    title={
                      client?.name
                        ? `Abrir cliente ${client.name}`
                        : "Abrir detalle del cliente"
                    }
                    className="rounded-sm underline-offset-2 transition-colors hover:underline hover:text-[color:var(--text-brand)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--interactive-primary)]"
                  >
                    {client?.name ?? "Ver cliente"}
                  </Link>
                ) : (
                  "—"
                ),
                tone: "teal",
              },
              { label: "RFC", value: rfc ?? "—", mono: true },
              { label: "Persona", value: personaLabel(persona) },
              {
                label: "REPSE",
                value: repse ?? "Sin registro",
                mono: true,
              },
            ]}
          />

          {/* Compliance semaphore */}
          <Surface
            title="Estado de cumplimiento"
            description="Resumen operativo del expediente. La revisión humana es la fuente de verdad; los conteos reflejan el estado actual de cada documento."
            icon={CheckCircle}
            actions={
              <Badge variant={SEMAPHORE_TONE[detail.semaphore.level].variant}>
                {detail.semaphore.label}
              </Badge>
            }
          >
            <div className="space-y-4">
              <div className="flex flex-wrap items-end gap-x-8 gap-y-2">
                <Stat
                  value={`${Math.round(detail.semaphore.compliance_pct)}%`}
                  label="Cumplimiento"
                />
                <Stat
                  value={`${detail.semaphore.on_track}/${detail.semaphore.total_tracked}`}
                  label="En regla"
                />
                <Stat
                  value={`${Math.round(detail.onboarding_summary.completion_pct)}%`}
                  label="Alta inicial"
                />
                <Stat
                  value={vendorStatus ? entityStatusLabel(vendorStatus) : "—"}
                  label="Estado del proveedor"
                  badge={
                    vendorStatus
                      ? entityStatusVariant(vendorStatus)
                      : undefined
                  }
                />
              </div>
              <p className="text-[13px] text-[color:var(--text-secondary)]">
                {detail.semaphore.reason}
              </p>
              <div className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--border-subtle)] sm:grid-cols-4">
                {COUNT_LABELS.map(({ key, label }) => (
                  <div
                    key={key}
                    className="bg-[color:var(--surface-raised)] px-3 py-2.5"
                  >
                    <p className="font-mono text-lg font-semibold tabular-nums text-[color:var(--text-primary)]">
                      {detail.document_state_counts[key]}
                    </p>
                    <p className="text-[11px] text-[color:var(--text-tertiary)]">
                      {label}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </Surface>

          {/* Attention today */}
          {detail.attention_today.length > 0 ? (
            <Surface
              title="Requiere atención"
              description="Documentos vencidos, por vencer o con observaciones para este proveedor."
              icon={Warning}
            >
              <ul className="divide-y divide-[color:var(--border-subtle)]">
                {detail.attention_today.map((item) => (
                  <li
                    key={item.id}
                    className="flex flex-wrap items-center justify-between gap-2 py-2.5"
                  >
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-[color:var(--text-primary)]">
                        {item.title}
                      </p>
                      <p className="text-[11px] text-[color:var(--text-tertiary)]">
                        {INSTITUTION_LABELS[item.institution] ?? item.institution}
                        {item.due_in_days !== null
                          ? ` · ${dueLabel(item.due_in_days)}`
                          : ""}
                      </p>
                    </div>
                    <RequirementStatusBadge
                      status={item.state as RequirementStatus}
                    />
                  </li>
                ))}
              </ul>
            </Surface>
          ) : null}

          {/* Recent submissions — each links into the reviewer */}
          <Surface
            title="Entregas recientes"
            description="Las últimas cargas del proveedor. Abre cualquiera para revisarla en la mesa de revisión."
            icon={FileText}
          >
            {detail.recent_submissions.length === 0 ? (
              <p className="py-2 text-[13px] text-[color:var(--text-secondary)]">
                Este proveedor todavía no ha subido documentos.
              </p>
            ) : (
              <ul className="divide-y divide-[color:var(--border-subtle)]">
                {detail.recent_submissions.map((sub) => (
                  <li key={sub.submission_id}>
                    <Link
                      href={reviewerHref(sub.submission_id)}
                      className="flex items-center gap-3 py-2.5 transition-colors hover:bg-[color:var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[color:var(--border-focus)]/40"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] font-medium text-[color:var(--text-primary)]">
                          {sub.requirement_name ??
                            sub.requirement_code ??
                            "Documento"}
                        </p>
                        <p className="truncate text-[11px] text-[color:var(--text-tertiary)]">
                          {sub.period_key ? `${sub.period_key} · ` : ""}
                          {sub.filename ?? "Sin nombre de archivo"}
                        </p>
                      </div>
                      <RequirementStatusBadge
                        status={sub.status as RequirementStatus}
                      />
                      <ArrowRight
                        className="h-4 w-4 shrink-0 text-[color:var(--text-tertiary)]"
                        weight="bold"
                        aria-hidden="true"
                      />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Surface>

          {/* Contracts */}
          {detail.contracts.length > 0 ? (
            <Surface
              title="Documentos contractuales"
              description="Contrato de servicios y sus anexos registrados para el proveedor."
              icon={FileText}
            >
              <ul className="divide-y divide-[color:var(--border-subtle)]">
                {detail.contracts.map((doc) => (
                  <li key={doc.submission_id}>
                    <Link
                      href={reviewerHref(doc.submission_id)}
                      className="flex items-center gap-3 py-2.5 transition-colors hover:bg-[color:var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[color:var(--border-focus)]/40"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] font-medium text-[color:var(--text-primary)]">
                          {doc.requirement_name}
                        </p>
                        <p className="truncate text-[11px] text-[color:var(--text-tertiary)]">
                          {doc.filename ?? "Sin nombre de archivo"}
                        </p>
                      </div>
                      <Badge variant="outline">{statusLabel(doc.status)}</Badge>
                      <ArrowRight
                        className="h-4 w-4 shrink-0 text-[color:var(--text-tertiary)]"
                        weight="bold"
                        aria-hidden="true"
                      />
                    </Link>
                  </li>
                ))}
              </ul>
            </Surface>
          ) : null}
        </div>
      )}
    </AdminShell>
  );
}

function Stat({
  value,
  label,
  badge,
}: {
  value: string;
  label: string;
  badge?: "success" | "warning" | "secondary" | "outline";
}) {
  return (
    <div className="space-y-0.5">
      {badge ? (
        <Badge variant={badge}>{value}</Badge>
      ) : (
        <p className="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)]">
          {value}
        </p>
      )}
      <p className="text-[11px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        {label}
      </p>
    </div>
  );
}

function VendorDetailSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true" aria-live="polite">
      <span className="sr-only">Cargando el expediente del proveedor…</span>
      <div className="h-12 animate-pulse rounded-md bg-[color:var(--surface-sunken)]" />
      <div className="h-56 animate-pulse rounded-lg bg-[color:var(--surface-sunken)]" />
      <div className="h-40 animate-pulse rounded-lg bg-[color:var(--surface-sunken)]" />
    </div>
  );
}

function str(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

function dueLabel(days: number): string {
  if (days < 0) return `Vencido hace ${Math.abs(days)} día${Math.abs(days) === 1 ? "" : "s"}`;
  if (days === 0) return "Vence hoy";
  return `Vence en ${days} día${days === 1 ? "" : "s"}`;
}
