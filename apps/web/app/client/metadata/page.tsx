"use client";

import { useEffect, useMemo, useState } from "react";
import { DownloadSimple, FileXls } from "@phosphor-icons/react";

import {
  EmptyState,
  Surface,
} from "@/components/checkwise/dashboard/stat-card";
import { Button } from "@/components/ui/button";
import { SearchInput } from "@/components/ui/search-input";
import { MetadataStrip } from "@/components/ui/metadata-strip";
import { matchesAnyField } from "@/lib/search/normalize";
import {
  downloadClientMetadata,
  getClientMetadata,
  type ClientMetadataDocument,
  type ClientMetadataResponse,
} from "@/lib/api/client";

import { ClientShell } from "../_shell";

export default function ClientMetadataPage() {
  const [data, setData] = useState<ClientMetadataResponse | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    getClientMetadata()
      .then((payload) => {
        if (!cancelled) setData(payload);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "No pudimos cargar metadata.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const documents = useMemo(() => data?.documents ?? [], [data?.documents]);
  const filtered = useMemo(() => {
    if (!query.trim()) return documents;
    return documents.filter((row) =>
      matchesAnyField(
        [
          row.proveedor,
          row.periodo,
          row.nombre_documento,
          row.tipo_documento,
          row.subtipo,
          row.institucion,
          row.etiquetas,
        ],
        query,
      ),
    );
  }, [documents, query]);

  async function downloadWorkbook() {
    if (!data?.master_available) return;
    setDownloading(true);
    try {
      const blob = await downloadClientMetadata();
      const href = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.download = `${slug(data.client_name)}_metadata.xlsx`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(href);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <ClientShell
      title="Metadata documental"
      description="Excel maestro del cliente, actualizado automaticamente con las cargas de proveedores."
      actions={
        data?.master_available ? (
          <Button type="button" size="sm" onClick={downloadWorkbook} loading={downloading}>
            <DownloadSimple className="h-3.5 w-3.5" weight="bold" aria-hidden />
            Descargar Excel
          </Button>
        ) : null
      }
    >
      {error ? (
        <Surface>
          <EmptyState icon={FileXls} title="No pudimos cargar la metadata" description={error} />
        </Surface>
      ) : data === null ? (
        <MetadataSkeleton />
      ) : !data.master_available ? (
        <Surface>
          <EmptyState
            icon={FileXls}
            title="Todavia no hay metadata"
            description="Cuando un proveedor suba un documento, el Excel maestro aparecera aqui."
          />
        </Surface>
      ) : (
        <div className="space-y-5">
          <MetadataStrip
            items={[
              { label: "Cliente", value: data.client_name },
              { label: "Documentos", value: documents.length.toString(), mono: true },
              { label: "Archivo", value: "metadata.xlsx", mono: true, tone: "teal" },
            ]}
          />

          <Surface title="Buscar metadata">
            <SearchInput
              value={query}
              onValueChange={setQuery}
              placeholder="Proveedor, documento, periodo, institución"
              ariaLabel="Buscar metadata"
            />
          </Surface>

          <MetadataTable documents={filtered} />
        </div>
      )}
    </ClientShell>
  );
}

function MetadataTable({ documents }: { documents: ClientMetadataDocument[] }) {
  return (
    <Surface title={`Documentos (${documents.length})`} bodyClassName="p-0">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1100px] text-left text-xs">
          <thead className="border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)] font-mono uppercase tracking-wide text-[color:var(--text-tertiary)]">
            <tr>
              <th className="px-3 py-2">Proveedor</th>
              <th className="px-3 py-2">Periodo</th>
              <th className="px-3 py-2">Documento</th>
              <th className="px-3 py-2">Tipo</th>
              <th className="px-3 py-2">Institucion</th>
              <th className="px-3 py-2">Fecha</th>
              <th className="px-3 py-2">Participantes</th>
              <th className="px-3 py-2">Descripcion</th>
              <th className="px-3 py-2">Etiquetas</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[color:var(--border-subtle)]">
            {documents.map((row, index) => (
              <tr key={`${row.nombre_documento}-${index}`} className="hover:bg-[color:var(--surface-hover)]">
                <td className="px-3 py-2 font-medium text-[color:var(--text-primary)]">
                  {row.proveedor || "-"}
                </td>
                <td className="px-3 py-2 font-mono text-[color:var(--text-secondary)]">
                  {row.periodo || "-"}
                </td>
                <td className="px-3 py-2 text-[color:var(--text-primary)]">
                  {row.nombre_documento || row.archivo_pdf || "-"}
                </td>
                <td className="px-3 py-2 text-[color:var(--text-secondary)]">
                  {row.tipo_documento || row.subtipo || "-"}
                </td>
                <td className="px-3 py-2 text-[color:var(--text-secondary)]">
                  {row.institucion || "-"}
                </td>
                <td className="px-3 py-2 font-mono text-[color:var(--text-secondary)]">
                  {row.fecha_principal || "-"}
                </td>
                <td className="px-3 py-2 text-[color:var(--text-secondary)]">
                  {row.participantes || "-"}
                </td>
                <td className="max-w-sm px-3 py-2 text-[color:var(--text-secondary)]">
                  {row.descripcion || "-"}
                </td>
                <td className="px-3 py-2 text-[color:var(--text-secondary)]">
                  {row.etiquetas || "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Surface>
  );
}

function MetadataSkeleton() {
  return (
    <div className="space-y-4">
      <div className="h-14 animate-pulse rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]" />
      <div className="h-64 animate-pulse rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]" />
    </div>
  );
}

function slug(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "") || "cliente";
}
