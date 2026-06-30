"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, IdentificationCard, UserPlus } from "@phosphor-icons/react";
import { useInfiniteQuery } from "@tanstack/react-query";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SearchInput } from "@/components/ui/search-input";
import { useDebouncedValue } from "@/lib/hooks/use-debounced-value";

import { AdminShell } from "../_shell";
import {
  type AdminClient,
  listClients,
  updateClient,
} from "@/lib/api/admin";
import { entityStatusLabel, entityStatusVariant } from "@/lib/constants/labels";

const PAGE_SIZE = 50;

export default function AdminClientsPage() {
  const [editing, setEditing] = useState<AdminClient | null>(null);
  const [search, setSearch] = useState("");
  // Search runs SERVER-side now (ILIKE on name/RFC/responsible). Debounce so a
  // query fires once typing settles, not on every keystroke.
  const debouncedSearch = useDebouncedValue(search.trim(), 300);

  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isFetchNextPageError,
  } = useInfiniteQuery({
    queryKey: ["admin-clients", debouncedSearch],
    queryFn: ({ pageParam }) =>
      listClients({
        search: debouncedSearch || undefined,
        limit: PAGE_SIZE,
        offset: pageParam,
      }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((n, p) => n + p.items.length, 0);
      return loaded < lastPage.total ? loaded : undefined;
    },
  });

  const rows = useMemo(
    () => data?.pages.flatMap((p) => p.items) ?? [],
    [data],
  );
  const total = data?.pages[0]?.total ?? 0;

  return (
    <AdminShell
      title="Clientes"
      description="Empresas dadas de alta en CheckWise. Cada cliente puede tener uno o varios proveedores REPSE bajo gestión."
      actions={
        <Button asChild size="sm">
          <Link href="/admin/cuentas/new">
            <UserPlus className="h-4 w-4" weight="bold" aria-hidden="true" />
            Nuevo cliente
            <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          </Link>
        </Button>
      }
    >
      <div className="space-y-5">
        {editing && (
          <Surface
            title={`Editar ${editing.name}`}
            icon={IdentificationCard}
          >
            <ClientForm
              initial={editing}
              onSubmit={async (data) => {
                await updateClient(editing.id, {
                  name: data.name,
                  rfc: data.rfc,
                  email: data.email,
                  responsible_name: data.responsible_name,
                  status: data.status,
                });
                setEditing(null);
                await refetch();
              }}
              onCancel={() => setEditing(null)}
            />
          </Surface>
        )}

        <SearchInput
          value={search}
          onValueChange={setSearch}
          placeholder="Buscar nombre o RFC"
          ariaLabel="Buscar cliente"
          className="w-56"
          inputClassName="h-8 text-xs"
        />

        <DataTable<AdminClient>
          items={isLoading ? null : rows}
          loading={isLoading}
          error={
            isError
              ? error instanceof Error
                ? error.message
                : "Error al cargar clientes."
              : null
          }
          onRetry={() => refetch()}
          columns={[
            {
              id: "name",
              header: "Nombre",
              cell: (row) => (
                <p className="font-medium text-[color:var(--text-primary)]">
                  {/* Same affordance as VendorRef: the entity name is the
                      navigation into its detail page. */}
                  <Link
                    href={`/admin/clients/${row.id}`}
                    title={`Abrir la ficha de ${row.name}`}
                    className="rounded-sm underline-offset-2 transition-colors hover:text-[color:var(--text-brand)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--interactive-primary)]"
                  >
                    {row.name}
                  </Link>
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
                    onClick={() => setEditing(row)}
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
          metaBadge={`${rows.length} de ${total}`}
        />

        {hasNextPage ? (
          <div className="flex items-center justify-center gap-3">
            {isFetchNextPageError ? (
              <span className="text-xs text-[color:var(--status-error-text)]">
                No pudimos cargar más. Intenta de nuevo.
              </span>
            ) : null}
            <Button
              variant="outline"
              size="sm"
              loading={isFetchingNextPage}
              onClick={() => fetchNextPage()}
            >
              Cargar más
            </Button>
          </div>
        ) : null}
      </div>
    </AdminShell>
  );
}

function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant={entityStatusVariant(status)}>
      {entityStatusLabel(status)}
    </Badge>
  );
}

function ClientForm({
  initial,
  onSubmit,
  onCancel,
}: {
  initial: AdminClient;
  onSubmit: (data: {
    name: string;
    rfc: string | null;
    email: string | null;
    responsible_name: string | null;
    status: string;
  }) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial.name ?? "");
  const [rfc, setRfc] = useState(initial.rfc ?? "");
  const [email, setEmail] = useState(initial.email ?? "");
  const [responsible, setResponsible] = useState(initial.responsible_name ?? "");
  const [status, setStatus] = useState(initial.status ?? "active");
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
        email: email.trim() || null,
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
          <Label htmlFor="cli-email">Correo</Label>
          <Input
            id="cli-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            placeholder="contacto@empresa.com"
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
            <option value="active">Activo</option>
            <option value="inactive">Inactivo</option>
          </select>
        </div>
      </div>
      {err ? <p className="text-xs text-[color:var(--status-error-text)]">{err}</p> : null}
      <div className="flex gap-2">
        <Button type="submit" size="sm" loading={submitting}>
          Guardar cambios
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onCancel}>
          Cancelar
        </Button>
      </div>
    </form>
  );
}

