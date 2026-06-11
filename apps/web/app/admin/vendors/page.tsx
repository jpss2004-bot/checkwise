"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Buildings,
  DownloadSimple,
  MagnifyingGlass,
  Plus,
  Storefront,
  X,
} from "@phosphor-icons/react";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { AdminShell } from "../_shell";
import { VendorRef } from "@/components/checkwise/vendor-ref";
import {
  entityStatusLabel,
  entityStatusVariant,
  personaLabel,
} from "@/lib/constants/labels";
import {
  adminVendorExpedienteZipUrl,
  type AdminClient,
  type AdminVendor,
  createVendor,
  listClients,
  listVendors,
  updateVendor,
} from "@/lib/api/admin";

export default function AdminVendorsPage() {
  // useSearchParams must live under a Suspense boundary so Next can
  // statically prerender the shell (same pattern as /admin/reviewer).
  return (
    <Suspense fallback={null}>
      <AdminVendorsBody />
    </Suspense>
  );
}

function AdminVendorsBody() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [rows, setRows] = useState<AdminVendor[]>([]);
  const [clients, setClients] = useState<AdminClient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<AdminVendor | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState("");
  // Audit fix 2026-06-10 — the client filter seeds from `?client_id=`
  // so deep links (e.g. the "Proveedores" quick link on the client
  // detail page) land pre-scoped, and mirrors back to the URL so the
  // filtered view is shareable and survives back-navigation.
  const [clientFilter, setClientFilter] = useState(
    () => searchParams?.get("client_id") ?? "",
  );

  useEffect(() => {
    const params = new URLSearchParams();
    if (clientFilter) params.set("client_id", clientFilter);
    const qs = params.toString();
    router.replace(`/admin/vendors${qs ? `?${qs}` : ""}`, { scroll: false });
  }, [clientFilter, router]);

  async function refresh() {
    setError(null);
    setLoading(true);
    try {
      const [vendorsResp, clientsResp] = await Promise.all([
        listVendors(),
        listClients(),
      ]);
      setRows(vendorsResp.items);
      setClients(clientsResp.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar proveedores.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (clientFilter && r.client_id !== clientFilter) return false;
      if (!q) return true;
      return (
        r.name.toLowerCase().includes(q) ||
        r.rfc.toLowerCase().includes(q) ||
        (r.contact_email ?? "").toLowerCase().includes(q)
      );
    });
  }, [rows, search, clientFilter]);

  return (
    <AdminShell
      title="Proveedores"
      description="Catálogo completo de proveedores REPSE bajo gestión, sus contactos y tipo de persona."
      actions={
        <Button
          size="sm"
          disabled={clients.length === 0}
          onClick={() => {
            setEditing(null);
            setCreateOpen((v) => !v);
          }}
        >
          {createOpen ? (
            <>
              <X className="h-4 w-4" weight="bold" aria-hidden="true" />
              Cancelar
            </>
          ) : (
            <>
              <Plus className="h-4 w-4" weight="bold" aria-hidden="true" />
              Nuevo proveedor
            </>
          )}
        </Button>
      }
    >
      <div className="space-y-5">
        {clients.length === 0 ? (
          <p className="rounded-md border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] p-3 text-xs text-[color:var(--status-warning-text)]">
            Crea un cliente antes de registrar proveedores.
          </p>
        ) : null}

        {(createOpen || editing) && (
          <Surface
            title={editing ? `Editar ${editing.name}` : "Nuevo proveedor"}
            icon={Storefront}
          >
            <VendorForm
              mode={editing ? "edit" : "create"}
              initial={editing ?? undefined}
              clients={clients}
              onSubmit={async (data) => {
                if (editing) {
                  await updateVendor(editing.id, data);
                  setEditing(null);
                } else {
                  await createVendor(data);
                  setCreateOpen(false);
                }
                await refresh();
              }}
              onCancel={() => {
                setCreateOpen(false);
                setEditing(null);
              }}
            />
          </Surface>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative w-56">
            <MagnifyingGlass
              className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[color:var(--text-tertiary)]"
              weight="bold"
              aria-hidden="true"
            />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar por nombre, RFC o email"
              className="h-8 pl-8 text-xs"
              aria-label="Buscar proveedor"
            />
          </div>
          <select
            value={clientFilter}
            onChange={(e) => setClientFilter(e.target.value)}
            className="h-8 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2 text-xs"
            aria-label="Filtrar por cliente"
          >
            <option value="">Todos los clientes</option>
            {clients.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        <DataTable<AdminVendor>
          items={loading ? null : filtered}
          loading={loading}
          error={error}
          onRetry={refresh}
          columns={[
            {
              id: "name",
              header: "Proveedor",
              cell: (row) => (
                <p className="font-medium text-[color:var(--text-primary)]">
                  <VendorRef
                    vendorId={row.id}
                    vendorName={row.name}
                    clientId={row.client_id}
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
                  {row.rfc}
                </span>
              ),
            },
            {
              id: "client",
              header: "Cliente",
              cell: (row) => {
                const client = clients.find((c) => c.id === row.client_id);
                return (
                  <Badge variant="brand">
                    <Buildings
                      className="h-3 w-3"
                      weight="bold"
                      aria-hidden="true"
                    />
                    {client?.name ?? "Cliente no disponible"}
                  </Badge>
                );
              },
            },
            {
              id: "persona",
              header: "Tipo",
              width: "120px",
              cell: (row) => (
                <Badge variant="outline">{personaLabel(row.persona_type)}</Badge>
              ),
            },
            {
              id: "contact",
              header: "Contacto",
              cell: (row) => (
                <span className="text-[11px] text-[color:var(--text-secondary)]">
                  {row.contact_email ?? row.contact_name ?? "—"}
                </span>
              ),
            },
            {
              id: "status",
              header: "Estado",
              width: "100px",
              cell: (row) => (
                <Badge variant={entityStatusVariant(row.status)}>
                  {entityStatusLabel(row.status)}
                </Badge>
              ),
            },
            {
              id: "action",
              header: "",
              width: "240px",
              align: "right",
              cell: (row) => (
                <div className="flex items-center justify-end gap-2">
                  <Button asChild size="sm" variant="outline">
                    <a
                      href={adminVendorExpedienteZipUrl(row.id)}
                      target="_blank"
                      rel="noreferrer"
                      title="Descargar el expediente completo del proveedor"
                    >
                      <DownloadSimple
                        className="h-3.5 w-3.5"
                        weight="bold"
                        aria-hidden="true"
                      />
                      Descargar expediente
                    </a>
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setCreateOpen(false);
                      setEditing(row);
                    }}
                  >
                    Editar
                  </Button>
                </div>
              ),
            },
          ]}
          rowKey={(row) => row.id}
          ariaLabel="Catálogo de proveedores"
          emptyTitle="Sin proveedores"
          emptyDescription="No hay proveedores con esos filtros."
          metaBadge={`${filtered.length} proveedor${filtered.length === 1 ? "" : "es"}`}
        />
      </div>
    </AdminShell>
  );
}

function VendorForm({
  mode,
  initial,
  clients,
  onSubmit,
  onCancel,
}: {
  mode: "create" | "edit";
  initial?: AdminVendor;
  clients: AdminClient[];
  onSubmit: (data: {
    client_id: string;
    name: string;
    rfc: string;
    contact_name: string | null;
    contact_email: string | null;
    repse_id: string | null;
    persona_type: "moral" | "fisica" | null;
    status: string;
  }) => Promise<void>;
  onCancel: () => void;
}) {
  const [clientId, setClientId] = useState(
    initial?.client_id ?? clients[0]?.id ?? "",
  );
  const [name, setName] = useState(initial?.name ?? "");
  const [rfc, setRfc] = useState(initial?.rfc ?? "");
  const [contactName, setContactName] = useState(initial?.contact_name ?? "");
  const [contactEmail, setContactEmail] = useState(initial?.contact_email ?? "");
  const [repseId, setRepseId] = useState(initial?.repse_id ?? "");
  const [persona, setPersona] = useState<string>(initial?.persona_type ?? "moral");
  const [status, setStatus] = useState(initial?.status ?? "active");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setErr(null);
    try {
      await onSubmit({
        client_id: clientId,
        name: name.trim(),
        rfc: rfc.trim().toUpperCase(),
        contact_name: contactName.trim() || null,
        contact_email: contactEmail.trim() || null,
        repse_id: repseId.trim() || null,
        persona_type: (persona as "moral" | "fisica") ?? null,
        status,
      });
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Error al guardar.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        {mode === "create" ? (
          <div className="space-y-1">
            <Label htmlFor="ven-client">Cliente</Label>
            <select
              id="ven-client"
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              className="h-9 w-full rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2 text-sm"
              required
            >
              {clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        ) : null}
        <div className="space-y-1">
          <Label htmlFor="ven-name">Nombre</Label>
          <Input
            id="ven-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>
        {mode === "create" ? (
          <div className="space-y-1">
            <Label htmlFor="ven-rfc">RFC</Label>
            <Input
              id="ven-rfc"
              value={rfc}
              onChange={(e) => setRfc(e.target.value.toUpperCase())}
              minLength={12}
              maxLength={13}
              className="font-mono"
              required
            />
          </div>
        ) : null}
        <div className="space-y-1">
          <Label htmlFor="ven-contact">Contacto</Label>
          <Input
            id="ven-contact"
            value={contactName}
            onChange={(e) => setContactName(e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="ven-email">Email</Label>
          <Input
            id="ven-email"
            type="email"
            value={contactEmail}
            onChange={(e) => setContactEmail(e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="ven-repse">REPSE ID</Label>
          <Input
            id="ven-repse"
            value={repseId}
            onChange={(e) => setRepseId(e.target.value)}
            className="font-mono"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="ven-persona">Persona</Label>
          <select
            id="ven-persona"
            value={persona}
            onChange={(e) => setPersona(e.target.value)}
            className="h-9 w-full rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2 text-sm"
          >
            <option value="moral">Persona moral</option>
            <option value="fisica">Persona física</option>
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="ven-status">Estado</Label>
          <select
            id="ven-status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="h-9 w-full rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2 text-sm"
          >
            <option value="active">Activo</option>
            <option value="inactive">Inactivo</option>
          </select>
        </div>
      </div>
      {err ? <p className="text-xs text-[color:var(--status-error-text)]">{err}</p> : null}
      <div className="flex gap-2">
        <Button type="submit" size="sm" loading={submitting}>
          {mode === "create" ? "Crear" : "Guardar cambios"}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onCancel}>
          Cancelar
        </Button>
      </div>
    </form>
  );
}
