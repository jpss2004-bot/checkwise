"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { IdentificationCard, MagnifyingGlass, Plus, X } from "@phosphor-icons/react";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
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
  const [search, setSearch] = useState("");

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

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        r.name.toLowerCase().includes(q) ||
        (r.rfc ?? "").toLowerCase().includes(q) ||
        (r.responsible_name ?? "").toLowerCase().includes(q),
    );
  }, [rows, search]);

  return (
    <AdminShell
      title="Clientes"
      description="Empresas dadas de alta en CheckWise. Cada cliente puede tener uno o varios proveedores REPSE bajo gestión."
      actions={
        <Button
          size="sm"
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
              Nuevo cliente
            </>
          )}
        </Button>
      }
    >
      <div className="space-y-5">
        {(createOpen || editing) && (
          <Surface
            title={editing ? `Editar ${editing.name}` : "Nuevo cliente"}
            icon={IdentificationCard}
          >
            <ClientForm
              mode={editing ? "edit" : "create"}
              initial={editing ?? undefined}
              onSubmit={async (data) => {
                if (editing) {
                  await updateClient(editing.id, data);
                  setEditing(null);
                } else {
                  await createClient(data);
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

        <div className="relative w-56">
          <MagnifyingGlass
            className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[color:var(--text-tertiary)]"
            weight="bold"
            aria-hidden="true"
          />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar nombre o RFC"
            className="h-8 pl-8 text-xs"
            aria-label="Buscar cliente"
          />
        </div>

        <DataTable<AdminClient>
          items={loading ? null : filtered}
          loading={loading}
          error={error}
          onRetry={refresh}
          columns={[
            {
              id: "name",
              header: "Nombre",
              cell: (row) => (
                <p className="font-medium text-[color:var(--text-primary)]">
                  {row.name}
                </p>
              ),
            },
            {
              id: "rfc",
              header: "RFC",
              width: "160px",
              cell: (row) => (
                <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-secondary)]">
                  {row.rfc ?? "—"}
                </span>
              ),
            },
            {
              id: "responsible",
              header: "Responsable",
              cell: (row) => (
                <span className="text-[12px] text-[color:var(--text-primary)]">
                  {row.responsible_name ?? "—"}
                </span>
              ),
            },
            {
              id: "status",
              header: "Estado",
              width: "120px",
              cell: (row) => <StatusBadge status={row.status} />,
            },
            {
              id: "action",
              header: "",
              width: "190px",
              align: "right",
              cell: (row) => (
                <div className="flex justify-end gap-2">
                  <Button asChild size="sm" variant="outline">
                    <Link href={`/admin/clients/${row.id}/metadata`}>
                      Metadata
                    </Link>
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
          ariaLabel="Catálogo de clientes"
          emptyTitle="Sin clientes"
          emptyDescription="Aún no hay clientes registrados con esos filtros."
          metaBadge={`${filtered.length} cliente${filtered.length === 1 ? "" : "s"}`}
        />
      </div>
    </AdminShell>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "active") return <Badge variant="success">Activo</Badge>;
  if (status === "inactive") return <Badge variant="secondary">Inactivo</Badge>;
  return <Badge variant="outline">{status}</Badge>;
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
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="cli-name">Nombre</Label>
          <Input
            id="cli-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="cli-rfc">RFC</Label>
          <Input
            id="cli-rfc"
            value={rfc}
            onChange={(e) => setRfc(e.target.value.toUpperCase())}
            maxLength={13}
            className="font-mono"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="cli-resp">Responsable</Label>
          <Input
            id="cli-resp"
            value={responsible}
            onChange={(e) => setResponsible(e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="cli-status">Estado</Label>
          <select
            id="cli-status"
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
