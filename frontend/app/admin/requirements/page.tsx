"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { AdminShell } from "../_shell";
import {
  type AdminRequirement,
  createRequirement,
  listRequirements,
  updateRequirement,
} from "@/lib/api/admin";

export default function AdminRequirementsPage() {
  const [rows, setRows] = useState<AdminRequirement[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<AdminRequirement | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  async function refresh() {
    setError(null);
    setLoading(true);
    try {
      const data = await listRequirements();
      setRows(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar requisitos.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <AdminShell title="Requisitos">
      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">
          {loading ? "Cargando…" : `${rows.length} requisito(s)`}
        </p>
        <Button size="sm" onClick={() => setCreateOpen((v) => !v)}>
          {createOpen ? "Cancelar" : "Nuevo requisito"}
        </Button>
      </div>

      {createOpen ? (
        <RequirementForm
          mode="create"
          onSubmit={async (data) => {
            await createRequirement(data);
            setCreateOpen(false);
            await refresh();
          }}
          onCancel={() => setCreateOpen(false)}
        />
      ) : null}

      {editing ? (
        <RequirementForm
          mode="edit"
          initial={editing}
          onSubmit={async (data) => {
            await updateRequirement(editing.id, data);
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
              <th className="px-3 py-2">Código</th>
              <th className="px-3 py-2">Nombre</th>
              <th className="px-3 py-2">Tipo</th>
              <th className="px-3 py-2">Frecuencia</th>
              <th className="px-3 py-2">Riesgo</th>
              <th className="px-3 py-2">Activo</th>
              <th className="px-3 py-2">Versión</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-b border-border last:border-0">
                <td className="px-3 py-2 font-mono text-xs">{row.code}</td>
                <td className="px-3 py-2">{row.name}</td>
                <td className="px-3 py-2">{row.load_type}</td>
                <td className="px-3 py-2">{row.frequency}</td>
                <td className="px-3 py-2">{row.risk_level}</td>
                <td className="px-3 py-2">{row.is_active ? "sí" : "no"}</td>
                <td className="px-3 py-2">v{row.current_version}</td>
                <td className="px-3 py-2 text-right">
                  <Button size="sm" variant="outline" onClick={() => setEditing(row)}>
                    Editar
                  </Button>
                </td>
              </tr>
            ))}
            {!loading && rows.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center text-xs text-muted-foreground">
                  Sin requisitos registrados.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </AdminShell>
  );
}

function RequirementForm({
  mode,
  initial,
  onSubmit,
  onCancel,
}: {
  mode: "create" | "edit";
  initial?: AdminRequirement;
  onSubmit: (data: {
    code: string;
    name: string;
    institution_id: string;
    load_type: string;
    frequency: string;
    risk_level: string;
    is_active: boolean;
    legal_basis?: string | null;
    required?: boolean;
    human_review_required?: boolean;
  }) => Promise<void>;
  onCancel: () => void;
}) {
  const [code, setCode] = useState(initial?.code ?? "");
  const [name, setName] = useState(initial?.name ?? "");
  const [institutionId, setInstitutionId] = useState(initial?.institution_id ?? "");
  const [loadType, setLoadType] = useState(initial?.load_type ?? "mensual");
  const [frequency, setFrequency] = useState(initial?.frequency ?? "mensual");
  const [riskLevel, setRiskLevel] = useState(initial?.risk_level ?? "medium");
  const [isActive, setIsActive] = useState(initial?.is_active ?? true);
  const [legalBasis, setLegalBasis] = useState(initial?.version?.legal_basis ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setErr(null);
    try {
      const base = {
        code: code.trim(),
        name: name.trim(),
        institution_id: institutionId.trim(),
        load_type: loadType,
        frequency,
        risk_level: riskLevel,
        is_active: isActive,
      };
      if (mode === "create" && legalBasis.trim()) {
        await onSubmit({
          ...base,
          legal_basis: legalBasis.trim() || null,
          required: true,
          human_review_required: true,
        });
      } else {
        await onSubmit(base);
      }
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
        {mode === "create" ? "Nuevo requisito" : `Editar ${initial?.code ?? ""}`}
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {mode === "create" ? (
          <>
            <div>
              <Label htmlFor="req-code">Código</Label>
              <Input id="req-code" value={code} onChange={(e) => setCode(e.target.value)} required />
            </div>
            <div>
              <Label htmlFor="req-inst">Institution ID (uuid)</Label>
              <Input
                id="req-inst"
                value={institutionId}
                onChange={(e) => setInstitutionId(e.target.value)}
                required
              />
            </div>
          </>
        ) : null}
        <div className={mode === "create" ? "" : "sm:col-span-2"}>
          <Label htmlFor="req-name">Nombre</Label>
          <Input id="req-name" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div>
          <Label htmlFor="req-load">Tipo de carga</Label>
          <Input id="req-load" value={loadType} onChange={(e) => setLoadType(e.target.value)} required />
        </div>
        <div>
          <Label htmlFor="req-freq">Frecuencia</Label>
          <Input id="req-freq" value={frequency} onChange={(e) => setFrequency(e.target.value)} required />
        </div>
        <div>
          <Label htmlFor="req-risk">Nivel de riesgo</Label>
          <Input id="req-risk" value={riskLevel} onChange={(e) => setRiskLevel(e.target.value)} />
        </div>
        <div className="flex items-center gap-2 pt-6">
          <input
            id="req-active"
            type="checkbox"
            checked={isActive}
            onChange={(e) => setIsActive(e.target.checked)}
          />
          <Label htmlFor="req-active">Activo</Label>
        </div>
        {mode === "create" ? (
          <div className="sm:col-span-2">
            <Label htmlFor="req-legal">Base legal (opcional, crea version 1)</Label>
            <Input
              id="req-legal"
              value={legalBasis}
              onChange={(e) => setLegalBasis(e.target.value)}
              placeholder="Ej. Art. 15-A LFT"
            />
          </div>
        ) : null}
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
