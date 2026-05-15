"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { AdminShell } from "../_shell";
import {
  type AdminClient,
  createClient,
  listClients,
  updateClient,
} from "@/lib/api/admin";

export default function AdminClientsPage() {
  const [rows, setRows] = useState<AdminClient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<AdminClient | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  async function refresh() {
    setError(null);
    setLoading(true);
    try {
      const data = await listClients();
      setRows(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar clientes.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <AdminShell title="Clientes">
      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">
          {loading ? "Cargando…" : `${rows.length} cliente(s)`}
        </p>
        <Button size="sm" onClick={() => setCreateOpen((v) => !v)}>
          {createOpen ? "Cancelar" : "Nuevo cliente"}
        </Button>
      </div>

      {createOpen ? (
        <ClientForm
          mode="create"
          onSubmit={async (data) => {
            await createClient(data);
            setCreateOpen(false);
            await refresh();
          }}
          onCancel={() => setCreateOpen(false)}
        />
      ) : null}

      {editing ? (
        <ClientForm
          mode="edit"
          initial={editing}
          onSubmit={async (data) => {
            await updateClient(editing.id, data);
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
              <th className="px-3 py-2">Responsable</th>
              <th className="px-3 py-2">Estado</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-b border-border last:border-0">
                <td className="px-3 py-2 font-medium">{row.name}</td>
                <td className="px-3 py-2 font-mono text-xs">{row.rfc ?? "—"}</td>
                <td className="px-3 py-2">{row.responsible_name ?? "—"}</td>
                <td className="px-3 py-2">{row.status}</td>
                <td className="px-3 py-2 text-right">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setEditing(row)}
                  >
                    Editar
                  </Button>
                </td>
              </tr>
            ))}
            {!loading && rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center text-xs text-muted-foreground">
                  Sin clientes registrados.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </AdminShell>
  );
}

function ClientForm({
  mode,
  initial,
  onSubmit,
  onCancel,
}: {
  mode: "create" | "edit";
  initial?: AdminClient;
  onSubmit: (data: {
    name: string;
    rfc: string | null;
    responsible_name: string | null;
    status: string;
  }) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [rfc, setRfc] = useState(initial?.rfc ?? "");
  const [responsible, setResponsible] = useState(initial?.responsible_name ?? "");
  const [status, setStatus] = useState(initial?.status ?? "active");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setErr(null);
    try {
      await onSubmit({
        name: name.trim(),
        rfc: rfc.trim() || null,
        responsible_name: responsible.trim() || null,
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
        {mode === "create" ? "Nuevo cliente" : `Editar ${initial?.name ?? ""}`}
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <Label htmlFor="cli-name">Nombre</Label>
          <Input id="cli-name" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div>
          <Label htmlFor="cli-rfc">RFC</Label>
          <Input id="cli-rfc" value={rfc} onChange={(e) => setRfc(e.target.value.toUpperCase())} maxLength={13} />
        </div>
        <div>
          <Label htmlFor="cli-resp">Responsable</Label>
          <Input
            id="cli-resp"
            value={responsible}
            onChange={(e) => setResponsible(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="cli-status">Estado</Label>
          <select
            id="cli-status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="h-9 w-full rounded-md border border-border bg-white px-2 text-sm"
          >
            <option value="active">active</option>
            <option value="inactive">inactive</option>
          </select>
        </div>
      </div>
      {err ? (
        <p className="mt-3 text-xs text-red-700">{err}</p>
      ) : null}
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
