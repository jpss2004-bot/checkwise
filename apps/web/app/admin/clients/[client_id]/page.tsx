"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowSquareOut,
  Buildings,
  ChartBar,
  Storefront,
  Warning,
} from "@phosphor-icons/react";

import { AdminShell } from "../../_shell";
import { EmptyState, Surface } from "@/components/checkwise/dashboard/stat-card";
import { VendorRef } from "@/components/checkwise/vendor-ref";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { MetadataStrip } from "@/components/ui/metadata-strip";
import {
  getAdminClientPlan,
  getClient,
  getClientCompliance,
  type AdminClient,
  type ClientCompliance,
  type ClientComplianceVendorRow,
} from "@/lib/api/admin";
import { AdminPlanControls } from "@/components/checkwise/admin/plan-controls";
import { AdminEntitlementsControls } from "@/components/checkwise/admin/entitlements-controls";
import { readAdminSession } from "@/lib/session/admin";
import type { ClientPlan } from "@/lib/api/client";
import { entityStatusLabel, entityStatusVariant } from "@/lib/constants/labels";
import {
  bucketLabel,
  semaphoreLabel,
  semaphoreVariant,
  type SemaphoreLevel,
} from "@/lib/constants/statuses";

type PageProps = {
  params: Promise<{ client_id: string }>;
};

/**
 * /admin/clients/[client_id] — client detail + compliance rollup.
 *
 * The client is the central business entity, but until this page a
 * client row in /admin/clients dead-ended (only "Metadata" and inline
 * edit). This surface mirrors the vendor expediente page idioms
 * (AdminShell, MetadataStrip, Surface, skeleton/404/network states)
 * and answers the operations question "¿cómo va este cliente?" with a
 * worst-first vendor compliance table from
 * `GET /admin/clients/{id}/compliance`.
 */
export default function AdminClientDetailPage({ params }: PageProps) {
  const { client_id } = use(params);
  return <AdminClientDetail clientId={client_id} />;
}

const SEMAPHORE_ORDER: SemaphoreLevel[] = ["red", "yellow", "green"];

function AdminClientDetail({ clientId }: { clientId: string }) {
  const [client, setClient] = useState<AdminClient | null>(null);
  const [compliance, setCompliance] = useState<ClientCompliance | null>(null);
  const [errorKind, setErrorKind] = useState<"not_found" | "network" | null>(
    null,
  );
  const [reloadKey, setReloadKey] = useState(0);
  const [plan, setPlan] = useState<ClientPlan | null>(null);
  // Plan / billing / entitlement mutations are superadmin-only on the API
  // (operations_admin) — separation of duties on revenue-bearing actions.
  // Hide the controls for the review team (platform_admin) so they don't
  // see buttons that would 403. Resolved after mount (localStorage).
  const [isOps, setIsOps] = useState(false);
  useEffect(() => {
    setIsOps(readAdminSession()?.roles.includes("operations_admin") ?? false);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setErrorKind(null);
    setClient(null);
    setCompliance(null);
    setPlan(null);
    Promise.all([
      getClient(clientId),
      getClientCompliance(clientId),
      // Tolerate a plan-read failure so it never blanks the page.
      getAdminClientPlan(clientId).catch(() => null),
    ])
      .then(([clientData, complianceData, planData]) => {
        if (cancelled) return;
        setClient(clientData);
        setCompliance(complianceData);
        setPlan(planData);
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
  }, [clientId, reloadKey]);

  const loaded = client !== null && compliance !== null;
  const vendors = compliance?.vendors ?? [];
  const levelCounts = countByLevel(vendors);
  const totals = sumAttention(vendors);

  return (
    <AdminShell
      title={client?.name ?? "Cliente"}
      description={
        loaded
          ? `RFC ${client.rfc ?? "—"} · ${vendors.length} proveedor${vendors.length === 1 ? "" : "es"} bajo gestión`
          : "Cargando la ficha del cliente…"
      }
      actions={
        <Button asChild variant="outline" size="sm">
          <Link href="/admin/clients">
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Clientes
          </Link>
        </Button>
      }
    >
      {errorKind === "not_found" ? (
        <EmptyState
          icon={Buildings}
          title="Cliente no encontrado"
          description="Este cliente no existe o ya no está disponible en el catálogo."
          action={
            <Button asChild variant="outline" size="sm">
              <Link href="/admin/clients">Volver a clientes</Link>
            </Button>
          }
        />
      ) : errorKind === "network" ? (
        <EmptyState
          icon={Warning}
          title="No pudimos cargar el cliente"
          description="Ocurrió un error al consultar la ficha del cliente. Intenta de nuevo."
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
      ) : !loaded ? (
        <ClientDetailSkeleton />
      ) : (
        <div className="space-y-5">
          {/* Identity */}
          <MetadataStrip
            items={[
              { label: "RFC", value: client.rfc ?? "—", mono: true },
              { label: "Correo", value: client.email ?? "—" },
              {
                label: "Responsable",
                value: client.responsible_name ?? "—",
              },
              {
                label: "Estatus",
                value: (
                  <Badge variant={entityStatusVariant(client.status)}>
                    {entityStatusLabel(client.status)}
                  </Badge>
                ),
              },
              { label: "Alta", value: formatDate(client.created_at) },
            ]}
          />

          {isOps && (
            <>
              <AdminPlanControls
                plan={plan}
                onChanged={() => setReloadKey((k) => k + 1)}
              />

              <AdminEntitlementsControls
                plan={plan}
                onChanged={() => setReloadKey((k) => k + 1)}
              />
            </>
          )}

          {/* Compliance rollup */}
          <Surface
            title="Salud del portafolio"
            description="Semáforo y pendientes agregados de los proveedores del cliente. La revisión humana es la fuente de verdad."
            icon={ChartBar}
          >
            <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
              <Stat value={String(vendors.length)} label="Proveedores" />
              {SEMAPHORE_ORDER.map((level) => (
                <Stat
                  key={level}
                  value={String(levelCounts[level])}
                  label={semaphoreLabel(level)}
                  badge={semaphoreVariant(level)}
                />
              ))}
              <Stat value={String(totals.missing)} label={bucketLabel("missing_required")} />
              <Stat value={String(totals.rejected)} label={bucketLabel("rejected_or_correction")} />
              <Stat value={String(totals.pending)} label={bucketLabel("pending_reviews")} />
              <Stat value={String(totals.dueSoon)} label="Por vencer ≤14 d" />
            </div>
          </Surface>

          {/* Vendor compliance table — ordered worst-first by the API */}
          <Surface
            title="Proveedores"
            description="Ordenados del más crítico al más sano. Abre cualquiera para ver su expediente completo."
            icon={Storefront}
          >
            <DataTable<ClientComplianceVendorRow>
              items={vendors}
              columns={[
                {
                  id: "vendor",
                  header: "Proveedor",
                  cell: (row) => (
                    <p className="font-medium text-[color:var(--text-primary)]">
                      <VendorRef
                        vendorId={row.vendor_id}
                        vendorName={row.vendor_name}
                        clientId={clientId}
                        surface="admin"
                      />
                    </p>
                  ),
                },
                {
                  id: "rfc",
                  header: "RFC",
                  width: "140px",
                  cell: (row) => (
                    <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-secondary)]">
                      {row.vendor_rfc ?? "—"}
                    </span>
                  ),
                },
                {
                  id: "semaphore",
                  header: "Semáforo",
                  width: "110px",
                  cell: (row) => (
                    <Badge variant={semaphoreVariant(row.semaphore_level)}>
                      {semaphoreLabel(row.semaphore_level)}
                    </Badge>
                  ),
                },
                {
                  id: "compliance",
                  header: "Cumplimiento",
                  width: "110px",
                  align: "right",
                  cell: (row) => (
                    <span className="font-mono text-[12px] font-semibold tabular-nums text-[color:var(--text-primary)]">
                      {Math.round(row.compliance_pct)}%
                    </span>
                  ),
                },
                {
                  id: "missing",
                  header: bucketLabel("missing_required"),
                  width: "90px",
                  align: "right",
                  cell: (row) => <CountCell value={row.missing_required_count} />,
                },
                {
                  id: "rejected",
                  header: bucketLabel("rejected_or_correction"),
                  width: "100px",
                  align: "right",
                  cell: (row) => (
                    <CountCell value={row.rejected_or_correction_count} />
                  ),
                },
                {
                  id: "pending",
                  header: bucketLabel("pending_reviews"),
                  width: "100px",
                  align: "right",
                  cell: (row) => <CountCell value={row.pending_reviews_count} />,
                },
                {
                  id: "due_soon",
                  header: bucketLabel("due_soon"),
                  width: "100px",
                  align: "right",
                  cell: (row) => <CountCell value={row.due_soon_count} />,
                },
                {
                  id: "last_activity",
                  header: "Última actividad",
                  width: "140px",
                  cell: (row) => (
                    <span className="text-[11px] text-[color:var(--text-tertiary)]">
                      {formatRelative(row.last_activity_at)}
                    </span>
                  ),
                },
              ]}
              rowKey={(row) => row.vendor_id}
              ariaLabel={`Cumplimiento de proveedores de ${client.name}`}
              emptyTitle="Sin proveedores"
              emptyDescription="Este cliente todavía no tiene proveedores REPSE bajo gestión."
              metaBadge={`${vendors.length} proveedor${vendors.length === 1 ? "" : "es"}`}
            />
          </Surface>

          {/* Quick links */}
          <Surface
            title="Accesos rápidos"
            description="Superficies relacionadas con este cliente."
            icon={ArrowSquareOut}
          >
            <div className="flex flex-wrap gap-2">
              <Button asChild size="sm" variant="outline">
                <Link href={`/admin/clients/${clientId}/metadata`}>
                  Metadata
                </Link>
              </Button>
              <Button asChild size="sm" variant="outline">
                <Link href={`/admin/vendors?client_id=${encodeURIComponent(clientId)}`}>
                  Proveedores
                </Link>
              </Button>
              <Button asChild size="sm" variant="outline">
                <Link href="/admin/reports">Reportes</Link>
              </Button>
            </div>
          </Surface>
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
  badge?: ReturnType<typeof semaphoreVariant>;
}) {
  return (
    <div className="space-y-0.5">
      <p className="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)]">
        {value}
      </p>
      {badge ? (
        <Badge variant={badge}>{label}</Badge>
      ) : (
        <p className="text-[11px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
          {label}
        </p>
      )}
    </div>
  );
}

function CountCell({ value }: { value: number }) {
  return (
    <span
      className={
        value > 0
          ? "font-mono text-[12px] font-semibold tabular-nums text-[color:var(--text-primary)]"
          : "font-mono text-[12px] tabular-nums text-[color:var(--text-tertiary)]"
      }
    >
      {value}
    </span>
  );
}

function ClientDetailSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true" aria-live="polite">
      <span className="sr-only">Cargando la ficha del cliente…</span>
      <div className="h-12 animate-pulse rounded-md bg-[color:var(--surface-sunken)]" />
      <div className="h-32 animate-pulse rounded-lg bg-[color:var(--surface-sunken)]" />
      <div className="h-56 animate-pulse rounded-lg bg-[color:var(--surface-sunken)]" />
    </div>
  );
}

function countByLevel(
  vendors: ClientComplianceVendorRow[],
): Record<SemaphoreLevel, number> {
  const counts: Record<SemaphoreLevel, number> = {
    green: 0,
    yellow: 0,
    red: 0,
  };
  for (const v of vendors) counts[v.semaphore_level] += 1;
  return counts;
}

function sumAttention(vendors: ClientComplianceVendorRow[]) {
  return vendors.reduce(
    (acc, v) => ({
      missing: acc.missing + v.missing_required_count,
      rejected: acc.rejected + v.rejected_or_correction_count,
      pending: acc.pending + v.pending_reviews_count,
      dueSoon: acc.dueSoon + v.due_soon_count,
    }),
    { missing: 0, rejected: 0, pending: 0, dueSoon: 0 },
  );
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("es-MX", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const diffMs = Date.now() - d.getTime();
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 1) return "ahora mismo";
  if (diffMin < 60) return `hace ${diffMin} min`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `hace ${diffHr} h`;
  const diffDay = Math.round(diffHr / 24);
  if (diffDay < 31) return `hace ${diffDay} día${diffDay === 1 ? "" : "s"}`;
  return formatDate(iso);
}
