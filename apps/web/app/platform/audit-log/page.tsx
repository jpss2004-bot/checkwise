"use client";

import { useEffect, useState } from "react";
import { MagnifyingGlass, Robot, User } from "@phosphor-icons/react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { PlatformShell } from "../_shell";
import {
  type AdminAuditLogItem,
  listAuditLog,
} from "@/lib/api/admin";

export default function AdminAuditLogPage() {
  const [rows, setRows] = useState<AdminAuditLogItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    actor_type: "",
    action: "",
    entity_type: "",
    entity_id: "",
    limit: 50,
  });

  async function refresh(applied = filters) {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string | number> = { limit: applied.limit };
      if (applied.actor_type) params.actor_type = applied.actor_type;
      if (applied.action) params.action = applied.action;
      if (applied.entity_type) params.entity_type = applied.entity_type;
      if (applied.entity_id) params.entity_id = applied.entity_id;
      const data = await listAuditLog(params);
      setRows(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar audit log.");
      setRows(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const columns: DataTableColumn<AdminAuditLogItem>[] = [
    {
      id: "when",
      header: "Cuándo",
      width: "180px",
      cell: (row) => (
        <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-secondary)]">
          {new Date(row.created_at).toLocaleString("es-MX")}
        </span>
      ),
    },
    {
      id: "actor",
      header: "Actor",
      cell: (row) => (
        <ActorChip actorType={row.actor_type} actorId={row.actor_id} />
      ),
    },
    {
      id: "action",
      header: "Acción",
      cell: (row) => (
        <code className="rounded-sm bg-[color:var(--surface-sunken)] px-1.5 py-0.5 font-mono text-[11px] text-[color:var(--text-primary)]">
          {row.action}
        </code>
      ),
    },
    {
      id: "entity",
      header: "Entidad",
      width: "120px",
      cell: (row) => <Badge variant="outline">{row.entity_type}</Badge>,
    },
    {
      id: "id",
      header: "ID",
      width: "140px",
      cell: (row) => (
        <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-tertiary)]">
          {row.entity_id.slice(0, 8)}…
        </span>
      ),
    },
    {
      id: "source",
      header: "Fuente",
      width: "120px",
      cell: (row) => (
        <span className="text-[11px] text-[color:var(--text-secondary)]">
          {(row.event_metadata?.source as string | undefined) ?? "—"}
        </span>
      ),
    },
  ];

  return (
    <PlatformShell
      title="Audit log"
      description="Bitácora completa de eventos del sistema. Cada cambio firma el actor, la acción, la entidad y el diff antes/después."
    >
      <div className="space-y-5">
        <section
          aria-label="Filtros"
          className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs"
        >
          <header className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] px-5 py-3">
            <MagnifyingGlass
              className="h-3.5 w-3.5 text-[color:var(--text-tertiary)]"
              weight="bold"
              aria-hidden
            />
            <p className="cw-eyebrow">Filtros</p>
          </header>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              refresh();
            }}
            className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-5"
          >
            <div className="space-y-1">
              <Label htmlFor="al-actor">Actor type</Label>
              <Input
                id="al-actor"
                value={filters.actor_type}
                onChange={(e) => setFilters({ ...filters, actor_type: e.target.value })}
                placeholder="internal_admin"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="al-action">Action</Label>
              <Input
                id="al-action"
                value={filters.action}
                onChange={(e) => setFilters({ ...filters, action: e.target.value })}
                placeholder="admin.client.updated"
                className="font-mono"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="al-entity">Entity type</Label>
              <Input
                id="al-entity"
                value={filters.entity_type}
                onChange={(e) => setFilters({ ...filters, entity_type: e.target.value })}
                placeholder="client"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="al-entid">Entity id</Label>
              <Input
                id="al-entid"
                value={filters.entity_id}
                onChange={(e) => setFilters({ ...filters, entity_id: e.target.value })}
                className="font-mono"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="al-limit">Límite</Label>
              <Input
                id="al-limit"
                type="number"
                min={1}
                max={200}
                value={filters.limit}
                onChange={(e) =>
                  setFilters({ ...filters, limit: Number(e.target.value) || 50 })
                }
              />
            </div>
            <div className="sm:col-span-2 lg:col-span-5">
              <Button type="submit" size="sm" loading={loading}>
                Aplicar filtros
              </Button>
            </div>
          </form>
        </section>

        <DataTable<AdminAuditLogItem>
          items={rows}
          loading={loading}
          error={error}
          onRetry={() => refresh()}
          columns={columns}
          rowKey={(row) => row.id}
          ariaLabel="Eventos del audit log"
          emptyTitle="Sin eventos"
          emptyDescription="No hay eventos para los filtros aplicados."
          metaBadge={`${rows?.length ?? 0} eventos`}
          skeletonRows={8}
        />
      </div>
    </PlatformShell>
  );
}

function ActorChip({
  actorType,
  actorId,
}: {
  actorType: string;
  actorId: string | null;
}) {
  const isBot = actorType.includes("system") || actorType.includes("bot");
  const IconComponent = isBot ? Robot : User;
  return (
    <div className="flex items-center gap-2">
      <span
        className={
          "flex h-6 w-6 shrink-0 items-center justify-center rounded-full " +
          (isBot
            ? "bg-[color:var(--surface-teal-muted)] text-[color:var(--text-teal)]"
            : "bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]")
        }
        aria-hidden="true"
      >
        <IconComponent className="h-3 w-3" weight="bold" />
      </span>
      <div className="min-w-0">
        <p className="text-[12px] font-medium text-[color:var(--text-primary)]">
          {actorType}
        </p>
        {actorId ? (
          <p className="font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
            {actorId.slice(0, 12)}…
          </p>
        ) : null}
      </div>
    </div>
  );
}
