"use client";

import { useEffect, useState } from "react";
import {
  ListMagnifyingGlass,
  MagnifyingGlass,
  Robot,
  User,
} from "@phosphor-icons/react";

import {
  EmptyState,
  Surface,
} from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { AdminShell } from "../_shell";
import {
  type AdminAuditLogItem,
  listAuditLog,
} from "@/lib/api/admin";

export default function AdminAuditLogPage() {
  const [rows, setRows] = useState<AdminAuditLogItem[]>([]);
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
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <AdminShell
      title="Audit log"
      description="Bitácora completa de eventos del sistema. Cada cambio firma el actor, la acción, la entidad y el diff antes/después."
    >
      <div className="space-y-5">
        <Surface title="Filtros" icon={MagnifyingGlass}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              refresh();
            }}
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5"
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
        </Surface>

        {error ? (
          <p className="rounded-md border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] p-3 text-sm text-[color:var(--status-warning-text)]">
            {error}
          </p>
        ) : null}

        <Surface
          title={`Resultados (${rows.length})`}
          icon={ListMagnifyingGlass}
          bodyClassName="p-0"
        >
          {!loading && rows.length === 0 ? (
            <div className="p-8">
              <EmptyState
                icon={ListMagnifyingGlass}
                title="Sin eventos"
                description="No hay eventos para los filtros aplicados."
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] text-left font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  <tr>
                    <th className="px-3 py-2.5">Cuándo</th>
                    <th className="px-3 py-2.5">Actor</th>
                    <th className="px-3 py-2.5">Acción</th>
                    <th className="px-3 py-2.5">Entidad</th>
                    <th className="px-3 py-2.5">ID</th>
                    <th className="px-3 py-2.5">Fuente</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr
                      key={row.id}
                      className="border-b border-[color:var(--border-subtle)] align-top transition-colors last:border-0 hover:bg-[color:var(--surface-hover)]"
                    >
                      <td className="px-3 py-2.5 font-mono text-[11px] text-[color:var(--text-secondary)]">
                        {new Date(row.created_at).toLocaleString("es-MX")}
                      </td>
                      <td className="px-3 py-2.5 text-[12px]">
                        <ActorChip actorType={row.actor_type} actorId={row.actor_id} />
                      </td>
                      <td className="px-3 py-2.5">
                        <code className="rounded-sm bg-[color:var(--surface-sunken)] px-1.5 py-0.5 font-mono text-[11px] text-[color:var(--text-primary)]">
                          {row.action}
                        </code>
                      </td>
                      <td className="px-3 py-2.5">
                        <Badge variant="outline">{row.entity_type}</Badge>
                      </td>
                      <td className="px-3 py-2.5 font-mono text-[11px] text-[color:var(--text-tertiary)]">
                        {row.entity_id.slice(0, 8)}…
                      </td>
                      <td className="px-3 py-2.5 text-[11px] text-[color:var(--text-secondary)]">
                        {(row.event_metadata?.source as string | undefined) ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Surface>
      </div>
    </AdminShell>
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
          "flex h-6 w-6 items-center justify-center rounded-full " +
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
          <p className="font-mono text-[10px] text-[color:var(--text-tertiary)]">
            {actorId.slice(0, 12)}…
          </p>
        ) : null}
      </div>
    </div>
  );
}
