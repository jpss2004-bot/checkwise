"use client";

import { useEffect, useState } from "react";

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
    <AdminShell title="Audit log">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          refresh();
        }}
        className="mb-4 grid gap-3 rounded-md border border-border bg-muted/30 p-4 sm:grid-cols-3 lg:grid-cols-5"
      >
        <div>
          <Label htmlFor="al-actor">Actor type</Label>
          <Input
            id="al-actor"
            value={filters.actor_type}
            onChange={(e) => setFilters({ ...filters, actor_type: e.target.value })}
            placeholder="internal_admin"
          />
        </div>
        <div>
          <Label htmlFor="al-action">Action</Label>
          <Input
            id="al-action"
            value={filters.action}
            onChange={(e) => setFilters({ ...filters, action: e.target.value })}
            placeholder="admin.client.updated"
          />
        </div>
        <div>
          <Label htmlFor="al-entity">Entity type</Label>
          <Input
            id="al-entity"
            value={filters.entity_type}
            onChange={(e) => setFilters({ ...filters, entity_type: e.target.value })}
            placeholder="client"
          />
        </div>
        <div>
          <Label htmlFor="al-entid">Entity id</Label>
          <Input
            id="al-entid"
            value={filters.entity_id}
            onChange={(e) => setFilters({ ...filters, entity_id: e.target.value })}
          />
        </div>
        <div>
          <Label htmlFor="al-limit">Limit</Label>
          <Input
            id="al-limit"
            type="number"
            min={1}
            max={200}
            value={filters.limit}
            onChange={(e) => setFilters({ ...filters, limit: Number(e.target.value) || 50 })}
          />
        </div>
        <div className="sm:col-span-3 lg:col-span-5">
          <Button type="submit" size="sm" loading={loading}>
            Filtrar
          </Button>
        </div>
      </form>

      {error ? (
        <p className="mb-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {error}
        </p>
      ) : null}

      <div className="overflow-x-auto rounded-md border border-border bg-white">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-3 py-2">Cuándo</th>
              <th className="px-3 py-2">Actor</th>
              <th className="px-3 py-2">Acción</th>
              <th className="px-3 py-2">Entidad</th>
              <th className="px-3 py-2">ID</th>
              <th className="px-3 py-2">Fuente</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-b border-border align-top last:border-0">
                <td className="px-3 py-2 font-mono text-xs">
                  {new Date(row.created_at).toLocaleString("es-MX")}
                </td>
                <td className="px-3 py-2 text-xs">
                  {row.actor_type}
                  {row.actor_id ? <div className="font-mono text-[10px] text-muted-foreground">{row.actor_id}</div> : null}
                </td>
                <td className="px-3 py-2 font-mono text-xs">{row.action}</td>
                <td className="px-3 py-2">{row.entity_type}</td>
                <td className="px-3 py-2 font-mono text-xs">{row.entity_id}</td>
                <td className="px-3 py-2 text-xs">
                  {(row.event_metadata?.source as string | undefined) ?? "—"}
                </td>
              </tr>
            ))}
            {!loading && rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-xs text-muted-foreground">
                  Sin eventos con esos filtros.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </AdminShell>
  );
}
