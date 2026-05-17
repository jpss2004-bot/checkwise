"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Buildings,
  MagnifyingGlass,
  Plus,
  Storefront,
  X,
} from "@phosphor-icons/react";

import { EmptyState, Surface } from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { AdminShell } from "../_shell";
import {
  type AdminClient,
  type AdminVendor,
  createVendor,
  listClients,
  listVendors,
  updateVendor,
} from "@/lib/api/admin";

export default function AdminVendorsPage() {
  const [rows, setRows] = useState<AdminVendor[]>([]);
  const [clients, setClients] = useState<AdminClient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<AdminVendor | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [clientFilter, setClientFilter] = useState("");

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

        <Surface
          title={`${filtered.length} proveedor${filtered.length === 1 ? "" : "es"}`}
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative w-44">
                <MagnifyingGlass
                  className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[color:var(--text-tertiary)]"
                  weight="bold"
                  aria-hidden="true"
                />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Buscar"
                  className="h-8 pl-8 text-xs"
                />
              </div>
              <select
                value={clientFilter}
                onChange={(e) => setClientFilter(e.target.value)}
                className="h-8 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2 text-xs"
              >
                <option value="">Todos los clientes</option>
                {clients.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
          }
          bodyClassName="p-0"
        >
          {error ? (
            <p className="p-4 text-sm text-[color:var(--status-warning-text)]">
              {error}
            </p>
          ) : !loading && filtered.length === 0 ? (
            <div className="p-8">
              <EmptyState
                icon={Storefront}
                title="Sin proveedores"
                description="No hay proveedores con esos filtros."
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] text-left font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  <tr>
                    <th className="px-4 py-2.5">Proveedor</th>
                    <th className="px-3 py-2.5">RFC</th>
                    <th className="px-3 py-2.5">Cliente</th>
                    <th className="px-3 py-2.5">Tipo</th>
                    <th className="px-3 py-2.5">Contacto</th>
                    <th className="px-3 py-2.5">Estado</th>
                    <th className="px-3 py-2.5"></th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((row) => {
                    const client = clients.find((c) => c.id === row.client_id);
                    return (
                      <tr
                        key={row.id}
                        className="border-b border-[color:var(--border-subtle)] transition-colors last:border-0 hover:bg-[color:var(--surface-hover)]"
                      >
                        <td className="px-4 py-2.5 font-medium text-[color:var(--text-primary)]">
                          {row.name}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-[11px] text-[color:var(--text-secondary)]">
                          {row.rfc}
                        </td>
                        <td className="px-3 py-2.5 text-[12px] text-[color:var(--text-secondary)]">
                          <Badge variant="brand">
                            <Buildings
                              className="h-3 w-3"
                              weight="bold"
                              aria-hidden="true"
                            />
                            {client?.name ?? row.client_id.slice(0, 8)}
                          </Badge>
                        </td>
                        <td className="px-3 py-2.5">
                          <Badge variant="outline">
                            {row.persona_type ?? "—"}
                          </Badge>
                        </td>
                        <td className="px-3 py-2.5 text-[11px] text-[color:var(--text-secondary)]">
                          {row.contact_email ?? row.contact_name ?? "—"}
                        </td>
                        <td className="px-3 py-2.5">
                          {row.status === "active" ? (
                            <Badge variant="success">Activo</Badge>
                          ) : (
                            <Badge variant="secondary">{row.status}</Badge>
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-right">
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
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Surface>
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
            <option value="moral">moral</option>
            <option value="fisica">fisica</option>
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
            <option value="active">active</option>
            <option value="inactive">inactive</option>
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
