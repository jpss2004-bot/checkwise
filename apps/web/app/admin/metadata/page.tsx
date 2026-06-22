"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowSquareOut,
  CircleNotch,
  Info,
  Warning,
} from "@phosphor-icons/react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { SearchInput } from "@/components/ui/search-input";
import { matchesAnyField } from "@/lib/search/normalize";

import { AdminShell } from "../_shell";
import {
  AdminApiError,
  getMetadataCatalog,
  type MetadataCatalog,
  type MetadataCatalogField,
} from "@/lib/api/admin";

/**
 * /admin/metadata — operational documentation of the metadata system (P2-09).
 *
 * Replaces the old redirect-to-/clients stub. Explains, from the rulebook
 * single source of truth (core/metadata_rules.py via GET
 * /admin/metadata/catalog): which document types CheckWise tracks, the fields
 * extracted per type, how each is sourced (extraction method), and whether it
 * needs human review before it's trustworthy — plus how that crosses into the
 * client portal (/client/metadata shows the validated projection).
 */

const LEVEL_LABEL: Record<string, string> = {
  required: "Obligatorio",
  conditional: "Condicional",
  optional: "Opcional",
  blank: "En blanco",
};

const LEVEL_VARIANT: Record<string, "warning" | "secondary" | "outline"> = {
  required: "warning",
  conditional: "secondary",
  optional: "outline",
  blank: "outline",
};

function FieldRow({ field }: { field: MetadataCatalogField }) {
  return (
    <tr className="border-b border-[color:var(--border-subtle)] last:border-0 align-top">
      <td className="py-2 pr-3">
        <div className="text-[12px] font-medium text-[color:var(--text-primary)]">
          {field.label}
        </div>
        <div className="font-mono text-[10px] text-[color:var(--text-tertiary)]">
          {field.key}
        </div>
      </td>
      <td className="py-2 pr-3">
        <Badge variant={LEVEL_VARIANT[field.requirement_level] ?? "outline"}>
          {LEVEL_LABEL[field.requirement_level] ?? field.requirement_level}
        </Badge>
      </td>
      <td className="py-2 pr-3">
        <span className="flex flex-wrap gap-1">
          {field.extraction_methods.map((m) => (
            <Badge key={m} variant="outline" className="font-mono text-[10px]">
              {m}
            </Badge>
          ))}
        </span>
      </td>
      <td className="py-2">
        {field.human_review_required ? (
          <Badge variant="warning">Revisión humana</Badge>
        ) : (
          <Badge variant="success">Automático</Badge>
        )}
      </td>
    </tr>
  );
}

export default function AdminMetadataPage() {
  const router = useRouter();
  const [catalog, setCatalog] = useState<MetadataCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    getMetadataCatalog()
      .then((data) => {
        if (!cancelled) setCatalog(data);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof AdminApiError && err.status === 401) {
          router.replace("/login");
          return;
        }
        setError(
          "No pudimos cargar el catálogo de metadata. Vuelve a intentarlo en unos segundos.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  const docTypes = useMemo(() => {
    if (!catalog) return [];
    if (!query.trim()) return catalog.document_types;
    return catalog.document_types.filter((d) =>
      matchesAnyField([d.name, d.code, d.institution], query),
    );
  }, [catalog, query]);

  return (
    <AdminShell
      title="Metadata documental"
      description="Qué metadata extrae CheckWise por tipo de documento, de qué fuente, y cómo se cruza con el portal del cliente. Es documentación operativa del modelo — los datos reales por cliente viven en cada expediente."
    >
      {error ? (
        <Alert variant="warning">
          <AlertTitle className="flex items-center gap-2">
            <Warning className="h-4 w-4" weight="bold" aria-hidden="true" />
            No se pudo cargar
          </AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : !catalog ? (
        <div className="flex items-center gap-2 py-10 text-[12px] text-[color:var(--text-tertiary)]">
          <CircleNotch className="h-4 w-4 animate-spin" weight="bold" aria-hidden="true" />
          Cargando catálogo de metadata…
        </div>
      ) : (
        <div className="space-y-6">
          {/* How metadata works — the model + the client-portal crossover. */}
          <section className="rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-4">
            <h2 className="flex items-center gap-2 text-[13px] font-semibold text-[color:var(--text-primary)]">
              <Info className="h-4 w-4 text-[color:var(--text-ai)]" weight="bold" aria-hidden="true" />
              Cómo funciona
            </h2>
            <p className="mt-2 max-w-prose text-[12px] leading-relaxed text-[color:var(--text-secondary)]">
              Cada documento que sube un proveedor se clasifica en uno de los{" "}
              <strong>{catalog.document_types.length}</strong> tipos de abajo.
              Por cada tipo, CheckWise extrae un conjunto de campos de metadata.
              La <strong>fuente</strong> (método de extracción) indica de dónde
              sale cada campo, y <strong>Revisión humana</strong> marca los
              campos que un revisor debe confirmar antes de considerarse
              válidos.
            </p>
            <ul className="mt-3 space-y-1 text-[12px] text-[color:var(--text-secondary)]">
              <li>
                <strong>Extraída:</strong> el sistema propone un valor (contexto,
                determinista, OCR/IA). Si requiere revisión humana, queda{" "}
                <em>pendiente</em> hasta confirmarse.
              </li>
              <li>
                <strong>Validada:</strong> un revisor confirmó el valor; es lo
                que ve el cliente.
              </li>
              <li>
                <strong>Editable:</strong> los campos con revisión humana pueden
                corregirse en el expediente antes de validarse.
              </li>
            </ul>
            <p className="mt-3 max-w-prose text-[12px] leading-relaxed text-[color:var(--text-secondary)]">
              El cliente ve la <strong>proyección validada</strong> de esta
              metadata en su portal (Metadata documental); el nivel de confianza
              por campo y su estado de revisión se consultan en el expediente de
              cada cliente.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Link
                href="/admin/clients"
                className="inline-flex items-center gap-1 text-[12px] text-[color:var(--text-link)] hover:underline"
              >
                Ver metadata real por cliente
                <ArrowSquareOut className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
              </Link>
            </div>
          </section>

          {/* Extraction-method glossary. */}
          <section>
            <h2 className="cw-eyebrow mb-2">Fuentes de extracción</h2>
            <div className="grid gap-2 sm:grid-cols-2">
              {Object.entries(catalog.extraction_methods).map(([code, desc]) => (
                <div
                  key={code}
                  className="flex items-start gap-2 rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] px-3 py-2"
                >
                  <Badge variant="outline" className="font-mono text-[10px]">
                    {code}
                  </Badge>
                  <span className="text-[11px] leading-snug text-[color:var(--text-secondary)]">
                    {desc}
                  </span>
                </div>
              ))}
            </div>
          </section>

          {/* Document-type catalog. */}
          <section className="space-y-3">
            <header className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="cw-eyebrow">
                Tipos de documento ({docTypes.length})
              </h2>
              <SearchInput
                value={query}
                onValueChange={setQuery}
                placeholder="Buscar tipo o institución…"
                ariaLabel="Buscar tipo de documento"
                className="w-56"
                inputClassName="h-8 text-[12px]"
              />
            </header>

            <div className="space-y-2">
              {docTypes.map((doc) => (
                <details
                  key={doc.code}
                  className="group rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] open:shadow-[var(--shadow-sm)]"
                >
                  <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 px-4 py-3">
                    <span className="text-[13px] font-medium text-[color:var(--text-primary)]">
                      {doc.name}
                    </span>
                    <Badge variant="outline" className="font-mono text-[10px]">
                      {doc.institution}
                    </Badge>
                    <Badge variant="outline">{doc.frequency}</Badge>
                    {doc.legal_approval_allowed ? (
                      <Badge variant="success">Aprobación legal</Badge>
                    ) : null}
                    <span className="ml-auto text-[11px] text-[color:var(--text-tertiary)]">
                      {doc.fields.length} campos
                    </span>
                  </summary>
                  <div className="overflow-x-auto border-t border-[color:var(--border-subtle)] px-4 py-2">
                    <table className="min-w-full">
                      <thead>
                        <tr className="border-b border-[color:var(--border-subtle)]">
                          <th scope="col" className="cw-eyebrow py-1.5 pr-3 text-left">Campo</th>
                          <th scope="col" className="cw-eyebrow py-1.5 pr-3 text-left">Nivel</th>
                          <th scope="col" className="cw-eyebrow py-1.5 pr-3 text-left">Fuente</th>
                          <th scope="col" className="cw-eyebrow py-1.5 text-left">Validación</th>
                        </tr>
                      </thead>
                      <tbody>
                        {doc.fields.map((f) => (
                          <FieldRow key={f.key} field={f} />
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              ))}
              {docTypes.length === 0 ? (
                <p className="rounded-md border border-dashed border-[color:var(--border-subtle)] px-4 py-6 text-center text-[12px] text-[color:var(--text-tertiary)]">
                  Ningún tipo de documento coincide con «{query}».
                </p>
              ) : null}
            </div>
          </section>

          <p className="text-[10px] text-[color:var(--text-tertiary)]">
            Catálogo: {catalog.rulebook_title} · versión {catalog.rulebook_version}
          </p>
        </div>
      )}
    </AdminShell>
  );
}
