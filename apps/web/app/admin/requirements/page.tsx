"use client";

import { useEffect, useMemo, useState } from "react";
import { Books, MagnifyingGlass, Plus, X } from "@phosphor-icons/react";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";

import { AdminShell } from "../_shell";
import {
  type AdminInstitution,
  type AdminRequirement,
  createRequirement,
  listInstitutions,
  listRequirements,
  updateRequirement,
} from "@/lib/api/admin";
import {
  CADENCE_LABELS_ES,
  cadenceLabel,
  riskLabel,
  riskVariant,
} from "@/lib/constants/labels";

// ---------------------------------------------------------------------------
// Canonical enum option sets. Free-text inputs here used to let a typo
// ("mensaul") create a requirement the slot engine never recognizes —
// these mirror the backend so the form can only emit valid codes.
// ---------------------------------------------------------------------------

/** Mirrors LOAD_TYPES in apps/api/app/core/catalogs.py — the exact set
 *  uploads are validated against (_VALID_LOAD_TYPES). */
const LOAD_TYPE_CODES: readonly string[] = [
  "alta_inicial",
  "contrato",
  "mensual",
  "bimestral",
  "cuatrimestral",
  "anual",
  "renovacion",
  "evento",
];

/** cadenceLabel covers most load-type codes; the two non-cadence codes
 *  get explicit labels (the humanizer would drop the accent in
 *  "Renovación"). Matches the backend catalog labels. */
const LOAD_TYPE_LABELS_EXTRA: Record<string, string> = {
  contrato: "Contrato",
  renovacion: "Renovación",
};

function loadTypeLabel(code: string): string {
  return LOAD_TYPE_LABELS_EXTRA[code] ?? cadenceLabel(code);
}

const FREQUENCY_CODES: readonly string[] = Object.keys(CADENCE_LABELS_ES);

const RISK_CODES: readonly string[] = ["bajo", "medio", "alto", "critico"];

/** The backend stores risk inconsistently (seed writes "alto", the old
 *  admin form defaulted to English "medium"). Normalize whatever a row
 *  carries onto the canonical Spanish codes so the select matches. */
const RISK_TO_CANONICAL: Record<string, string> = {
  low: "bajo",
  medium: "medio",
  med: "medio",
  high: "alto",
  critical: "critico",
  "crítico": "critico",
};

function canonicalRiskCode(code: string | null | undefined): string {
  if (!code) return "medio";
  const lower = code.toLowerCase();
  if (RISK_CODES.includes(lower)) return lower;
  return RISK_TO_CANONICAL[lower] ?? "medio";
}

export default function AdminRequirementsPage() {
  const [rows, setRows] = useState<AdminRequirement[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<AdminRequirement | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState("");
  // null until the catalog loads; the form falls back to the raw UUID
  // input when it never does (institutionsError) so it stays usable.
  const [institutions, setInstitutions] = useState<AdminInstitution[] | null>(null);
  const [institutionsError, setInstitutionsError] = useState(false);

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
    listInstitutions()
      .then((data) => setInstitutions(data.items))
      .catch(() => setInstitutionsError(true));
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        r.code.toLowerCase().includes(q) ||
        r.name.toLowerCase().includes(q) ||
        r.load_type.toLowerCase().includes(q),
    );
  }, [rows, search]);

  return (
    <AdminShell
      title="Catálogo de requisitos"
      description="Documentos REPSE que CheckWise rastrea por proveedor — alta, frecuencia y nivel de riesgo."
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
              Nuevo requisito
            </>
          )}
        </Button>
      }
    >
      <div className="space-y-5">
        {(createOpen || editing) && (
          <Surface
            title={editing ? `Editar ${editing.code}` : "Nuevo requisito"}
            icon={Books}
          >
            <RequirementForm
              mode={editing ? "edit" : "create"}
              initial={editing ?? undefined}
              institutions={institutions}
              institutionsError={institutionsError}
              onSubmit={async (data) => {
                if (editing) {
                  await updateRequirement(editing.id, data);
                  setEditing(null);
                } else {
                  await createRequirement(data);
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
            placeholder="Código, nombre o tipo"
            className="h-8 pl-8 text-xs"
            aria-label="Buscar requisito"
          />
        </div>

        <DataTable<AdminRequirement>
          items={loading ? null : filtered}
          loading={loading}
          error={error}
          onRetry={refresh}
          columns={[
            {
              id: "code",
              header: "Código",
              width: "220px",
              cell: (row) => (
                <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-secondary)]">
                  {row.code}
                </span>
              ),
            },
            {
              id: "name",
              header: "Nombre",
              cell: (row) => (
                <p className="text-[13px] font-medium text-[color:var(--text-primary)]">
                  {row.name}
                </p>
              ),
            },
            {
              id: "load_type",
              header: "Carga",
              width: "100px",
              cell: (row) => (
                <span className="text-[12px] text-[color:var(--text-secondary)]">
                  {cadenceLabel(row.load_type)}
                </span>
              ),
            },
            {
              id: "frequency",
              header: "Frecuencia",
              width: "120px",
              cell: (row) => (
                <Badge variant="outline">{cadenceLabel(row.frequency)}</Badge>
              ),
            },
            {
              id: "risk",
              header: "Riesgo",
              width: "100px",
              cell: (row) => (
                <Badge variant={riskVariant(row.risk_level)}>
                  {riskLabel(row.risk_level)}
                </Badge>
              ),
            },
            {
              id: "active",
              header: "Activo",
              width: "80px",
              cell: (row) =>
                row.is_active ? (
                  <Badge variant="success">Sí</Badge>
                ) : (
                  <Badge variant="secondary">No</Badge>
                ),
            },
            {
              id: "version",
              header: "Versión",
              width: "80px",
              cell: (row) => (
                <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-tertiary)]">
                  v{row.current_version}
                </span>
              ),
            },
            {
              id: "action",
              header: "",
              width: "100px",
              align: "right",
              cell: (row) => (
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
              ),
            },
          ]}
          rowKey={(row) => row.id}
          ariaLabel="Catálogo de requisitos"
          emptyTitle="Sin requisitos"
          emptyDescription="No hay requisitos con esos filtros."
          metaBadge={`${filtered.length} requisito${filtered.length === 1 ? "" : "s"}`}
        />
      </div>
    </AdminShell>
  );
}

function RequirementForm({
  mode,
  initial,
  institutions,
  institutionsError,
  onSubmit,
  onCancel,
}: {
  mode: "create" | "edit";
  initial?: AdminRequirement;
  institutions: AdminInstitution[] | null;
  institutionsError: boolean;
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
  const [riskLevel, setRiskLevel] = useState(canonicalRiskCode(initial?.risk_level));
  const [isActive, setIsActive] = useState(initial?.is_active ?? true);
  const [legalBasis, setLegalBasis] = useState(initial?.version?.legal_basis ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Legacy rows can carry off-catalog codes (the seed wrote
  // load_type=frequency for recurring requirements). Surface the stored
  // value as an extra option on edit so opening the form never silently
  // rewrites it — the operator opts into a canonical code explicitly.
  const legacyLoadType =
    initial && !LOAD_TYPE_CODES.includes(initial.load_type)
      ? initial.load_type
      : null;
  const legacyFrequency =
    initial && !FREQUENCY_CODES.includes(initial.frequency)
      ? initial.frequency
      : null;

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
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        {mode === "create" ? (
          <>
            <div className="space-y-1">
              <Label htmlFor="req-code">Código</Label>
              <Input
                id="req-code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="font-mono"
                required
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="req-inst">Institución</Label>
              {institutions ? (
                <Select
                  id="req-inst"
                  value={institutionId}
                  onChange={(e) => setInstitutionId(e.target.value)}
                  required
                >
                  <option value="" disabled>
                    Selecciona una institución
                  </option>
                  {institutions.map((inst) => (
                    <option key={inst.id} value={inst.id}>
                      {inst.name}
                    </option>
                  ))}
                </Select>
              ) : (
                <>
                  <Input
                    id="req-inst"
                    value={institutionId}
                    onChange={(e) => setInstitutionId(e.target.value)}
                    className="font-mono"
                    placeholder="UUID de la institución"
                    required
                  />
                  {institutionsError ? (
                    <p className="text-[11px] text-[color:var(--status-warning-text)]">
                      No se pudo cargar el catálogo de instituciones — captura
                      el UUID manualmente.
                    </p>
                  ) : null}
                </>
              )}
            </div>
          </>
        ) : null}
        <div className={mode === "create" ? "space-y-1" : "space-y-1 sm:col-span-2"}>
          <Label htmlFor="req-name">Nombre</Label>
          <Input
            id="req-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="req-load">Tipo de carga</Label>
          <Select
            id="req-load"
            value={loadType}
            onChange={(e) => setLoadType(e.target.value)}
            required
          >
            {legacyLoadType ? (
              <option value={legacyLoadType}>
                {loadTypeLabel(legacyLoadType)} (valor actual)
              </option>
            ) : null}
            {LOAD_TYPE_CODES.map((code) => (
              <option key={code} value={code}>
                {loadTypeLabel(code)}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="req-freq">Frecuencia</Label>
          <Select
            id="req-freq"
            value={frequency}
            onChange={(e) => setFrequency(e.target.value)}
            required
          >
            {legacyFrequency ? (
              <option value={legacyFrequency}>
                {cadenceLabel(legacyFrequency)} (valor actual)
              </option>
            ) : null}
            {FREQUENCY_CODES.map((code) => (
              <option key={code} value={code}>
                {CADENCE_LABELS_ES[code]}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="req-risk">Nivel de riesgo</Label>
          <Select
            id="req-risk"
            value={riskLevel}
            onChange={(e) => setRiskLevel(e.target.value)}
            required
          >
            {RISK_CODES.map((code) => (
              <option key={code} value={code}>
                {riskLabel(code)}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex items-end gap-2 pb-1">
          <input
            id="req-active"
            type="checkbox"
            checked={isActive}
            onChange={(e) => setIsActive(e.target.checked)}
            className="h-4 w-4"
          />
          <Label htmlFor="req-active">Activo</Label>
        </div>
        {mode === "create" ? (
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="req-legal">Base legal (opcional · crea versión 1)</Label>
            <Input
              id="req-legal"
              value={legalBasis}
              onChange={(e) => setLegalBasis(e.target.value)}
              placeholder="Ej. Art. 15-A LFT"
            />
          </div>
        ) : null}
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
