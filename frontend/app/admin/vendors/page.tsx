"use client";

import { useEffect, useState } from "react";

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

  return (
    <AdminShell title="Proveedores">
      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">
          {loading ? "Cargando…" : `${rows.length} proveedor(es)`}
        </p>
        <Button
          size="sm"
          onClick={() => setCreateOpen((v) => !v)}
          disabled={clients.length === 0}
        >
          {createOpen ? "Cancelar" : "Nuevo proveedor"}
        </Button>
      </div>

      {clients.length === 0 ? (
        <p className="mb-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">
          Crea un cliente antes de registrar proveedores.
        </p>
      ) : null}

      {createOpen ? (
        <VendorForm
          mode="create"
          clients={clients}
          onSubmit={async (data) => {
            await createVendor(data);
            setCreateOpen(false);
            await refresh();
          }}
          onCancel={() => setCreateOpen(false)}
        />
      ) : null}

      {editing ? (
        <VendorForm
          mode="edit"
          initial={editing}
          clients={clients}
          onSubmit={async (data) => {
            await updateVendor(editing.id, data);
            setEditing(null);
            await refresh();
          }}
          onCancel={() => setEditing(null)}
        />
      ) : null}

      {error ? (
        <p className="mb-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {error}
        </p>
      ) : null}

      <div className="overflow-x-auto rounded-md border border-border bg-white">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-3 py-2">Nombre</th>
              <th className="px-3 py-2">RFC</th>
              <th className="px-3 py-2">Cliente</th>
              <th className="px-3 py-2">Tipo</th>
              <th className="px-3 py-2">Contacto</th>
              <th className="px-3 py-2">Estado</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const client = clients.find((c) => c.id === row.client_id);
              return (
                <tr key={row.id} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 font-medium">{row.name}</td>
                  <td className="px-3 py-2 font-mono text-xs">{row.rfc}</td>
                  <td className="px-3 py-2">{client?.name ?? row.client_id}</td>
                  <td className="px-3 py-2">{row.persona_type ?? "—"}</td>
                  <td className="px-3 py-2 text-xs">
                    {row.contact_email ?? row.contact_name ?? "—"}
                  </td>
                  <td className="px-3 py-2">{row.status}</td>
                  <td className="px-3 py-2 text-right">
                    <Button size="sm" variant="outline" onClick={() => setEditing(row)}>
                      Editar
                    </Button>
                  </td>
                </tr>
              );
            })}
            {!loading && rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-xs text-muted-foreground">
                  Sin proveedores registrados.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
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
  const [clientId, setClientId] = useState(initial?.client_id ?? clients[0]?.id ?? "");
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
    <form
      onSubmit={handleSubmit}
      className="mb-4 rounded-md border border-border bg-muted/30 p-4"
    >
      <p className="mb-3 text-xs font-medium uppercase text-muted-foreground">
        {mode === "create" ? "Nuevo proveedor" : `Editar ${initial?.name ?? ""}`}
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {mode === "create" ? (
          <div>
            <Label htmlFor="ven-client">Cliente</Label>
            <select
              id="ven-client"
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              className="h-9 w-full rounded-md border border-border bg-white px-2 text-sm"
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
        <div>
          <Label htmlFor="ven-name">Nombre</Label>
          <Input id="ven-name" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        {mode === "create" ? (
          <div>
            <Label htmlFor="ven-rfc">RFC</Label>
            <Input
              id="ven-rfc"
              value={rfc}
              onChange={(e) => setRfc(e.target.value.toUpperCase())}
              minLength={12}
              maxLength={13}
              required
            />
          </div>
        ) : null}
        <div>
          <Label htmlFor="ven-contact">Contacto</Label>
          <Input id="ven-contact" value={contactName} onChange={(e) => setContactName(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="ven-email">Email</Label>
          <Input
            id="ven-email"
            type="email"
            value={contactEmail}
            onChange={(e) => setContactEmail(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="ven-repse">REPSE ID</Label>
          <Input id="ven-repse" value={repseId} onChange={(e) => setRepseId(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="ven-persona">Persona</Label>
          <select
            id="ven-persona"
            value={persona}
            onChange={(e) => setPersona(e.target.value)}
            className="h-9 w-full rounded-md border border-border bg-white px-2 text-sm"
          >
            <option value="moral">moral</option>
            <option value="fisica">fisica</option>
          </select>
        </div>
        <div>
          <Label htmlFor="ven-status">Estado</Label>
          <select
            id="ven-status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="h-9 w-full rounded-md border border-border bg-white px-2 text-sm"
          >
            <option value="active">active</option>
            <option value="inactive">inactive</option>
          </select>
        </div>
      </div>
      {err ? <p className="mt-3 text-xs text-red-700">{err}</p> : null}
      <div className="mt-3 flex gap-2">
        <Button type="submit" size="sm" loading={submitting}>
          Guardar
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onCancel}>
          Cancelar
        </Button>
      </div>
    </form>
  );
}
