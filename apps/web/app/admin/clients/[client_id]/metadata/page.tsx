"use client";

import { use, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  DownloadSimple,
  FileXls,
  MagnifyingGlass,
} from "@phosphor-icons/react";

import { AdminShell } from "../../../_shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MetadataStrip } from "@/components/ui/metadata-strip";
import {
  EmptyState,
  ErrorState,
  Skeleton,
} from "@/components/checkwise/portal/state-surfaces";
import {
  downloadClientMasterMetadata,
  getClientMetadata,
  type ClientMetadataDocument,
  type ClientMetadataResponse,
} from "@/lib/api/admin";

type PageProps = {
  params: Promise<{ client_id: string }>;
};

export default function ClientMetadataPage({ params }: PageProps) {
  const { client_id } = use(params);
  const [data, setData] = useState<ClientMetadataResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getClientMetadata(client_id)
      .then((payload) => {
        if (!cancelled) setData(payload);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "No pudimos cargar metadata.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [client_id, reloadKey]);

  const documents = useMemo(() => data?.documents ?? [], [data?.documents]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return documents;
    return documents.filter((item) =>
      [
        item.proveedor,
        item.periodo,
        item.nombre_documento,
        item.tipo_documento,
        item.subtipo,
        item.institucion,
        item.etiquetas,
        item.archivo_pdf,
      ]
        .join(" ")
        .toLowerCase()
        .includes(q),
    );
  }, [documents, query]);

  const retry = useCallback(() => setReloadKey((key) => key + 1), []);

  async function onDownload() {
    if (!data?.master_available) return;
    setDownloading(true);
    try {
      const blob = await downloadClientMasterMetadata(client_id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${slug(data.client.name)}_metadata.xlsx`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <AdminShell
      title={data?.client.name ?? "Metadata del cliente"}
      description="Archivo maestro de metadata documental generado automáticamente con las cargas de sus proveedores."
      actions={
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href="/admin/clients">
              <ArrowLeft className="h-3.5 w-3.5" weight="bold" aria-hidden />
              Clientes
            </Link>
          </Button>
          <Button
            type="button"
            size="sm"
            loading={downloading}
            disabled={!data?.master_available}
            onClick={onDownload}
          >
            <DownloadSimple className="h-3.5 w-3.5" weight="bold" aria-hidden />
            Descargar Excel
          </Button>
        </div>
      }
    >
      {loading ? (
        <ClientMetadataSkeleton />
      ) : error ? (
        <ErrorState
          title="No pudimos cargar la metadata"
          description={error}
          onRetry={retry}
        />
      ) : !data || !data.master_available ? (
        <EmptyState
          icon={FileXls}
          title="Este cliente todavía no tiene metadata"
          description="Cuando alguno de sus proveedores cargue un documento compatible, CheckWise generará el archivo maestro automáticamente."
          variant="muted"
        />
      ) : (
        <div className="space-y-5">
          <MetadataStrip
            items={[
              { label: "Cliente", value: data.client.name },
              { label: "Documentos", value: documents.length, mono: true },
              {
                label: "Maestro",
                value: data.master_available ? "Disponible" : "Sin generar",
                tone: "teal",
              },
            ]}
          />

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="relative w-full max-w-sm">
              <MagnifyingGlass
                className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[color:var(--text-tertiary)]"
                weight="bold"
                aria-hidden
              />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Buscar proveedor, documento o periodo"
                className="h-8 pl-8 text-xs"
                aria-label="Buscar metadata"
              />
            </div>
            <p className="font-mono text-[11px] text-[color:var(--text-tertiary)]">
              {filtered.length} de {documents.length} documentos
            </p>
          </div>

          {filtered.length === 0 ? (
            <EmptyState
              icon={FileXls}
              title="Sin resultados"
              description="Cambia la búsqueda para ver otros documentos."
              variant="muted"
            />
          ) : (
            <MetadataDocumentTable documents={filtered} />
          )}
        </div>
      )}
    </AdminShell>
  );
}

function MetadataDocumentTable({
  documents,
}: {
  documents: ClientMetadataDocument[];
}) {
  return (
    <section className="overflow-hidden rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs">
      <div className="overflow-auto">
        <table className="w-full min-w-[1180px] border-collapse text-left text-[12px]">
          <thead className="sticky top-0 z-10 bg-[color:var(--surface-sunken)]">
            <tr className="border-b border-[color:var(--border-default)]">
              {[
                "Proveedor",
                "Periodo",
                "Documento",
                "Tipo",
                "Subtipo",
                "Institución",
                "Fecha",
                "Participantes",
                "Descripción",
                "Anexos",
                "Etiquetas",
                "Archivo PDF",
              ].map((header) => (
                <th
                  key={header}
                  className="px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-[color:var(--text-secondary)]"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {documents.map((item, index) => (
              <tr
                key={`${item.archivo_pdf}-${index}`}
                className="border-b border-[color:var(--border-subtle)]"
              >
                <Cell strong>{item.proveedor}</Cell>
                <Cell mono>{item.periodo}</Cell>
                <Cell strong>{item.nombre_documento}</Cell>
                <Cell>{item.tipo_documento}</Cell>
                <Cell>{item.subtipo}</Cell>
                <Cell>{item.institucion}</Cell>
                <Cell>{item.fecha_principal}</Cell>
                <Cell wide>{item.participantes}</Cell>
                <Cell wide>{item.descripcion}</Cell>
                <Cell wide>{item.anexos}</Cell>
                <Cell wide>{item.etiquetas}</Cell>
                <Cell mono>{item.archivo_pdf}</Cell>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Cell({
  children,
  strong = false,
  mono = false,
  wide = false,
}: {
  children: string;
  strong?: boolean;
  mono?: boolean;
  wide?: boolean;
}) {
  const value = children || "—";
  return (
    <td
      className={[
        "max-w-[260px] px-3 py-3 align-top text-[color:var(--text-primary)]",
        wide ? "min-w-[200px]" : "min-w-[140px]",
        strong ? "font-medium" : "",
        mono ? "font-mono text-[11px]" : "",
      ].join(" ")}
    >
      {/* Clamp long free-text cells to two lines so rows stay uniform
          height instead of going ragged; the full value is available on
          hover via the title attribute. */}
      <span
        className="block overflow-hidden text-ellipsis [-webkit-box-orient:vertical] [-webkit-line-clamp:2] [display:-webkit-box]"
        title={children || undefined}
      >
        {value}
      </span>
    </td>
  );
}

function ClientMetadataSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-8 w-80" />
      <Skeleton className="h-[420px] w-full" />
    </div>
  );
}

function slug(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/gi, "_")
    .replace(/^_+|_+$/g, "");
}
