"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";

import { ClientShell } from "../../_shell";
import {
  getClientVendorDetail,
  type ClientVendorDetail,
} from "@/lib/api/client";

type PageProps = {
  params: Promise<{ vendor_id: string }>;
};

export default function ClientVendorDetailPage({ params }: PageProps) {
  const { vendor_id } = use(params);
  const [detail, setDetail] = useState<ClientVendorDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getClientVendorDetail(vendor_id)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Error al cargar proveedor.");
      });
    return () => {
      cancelled = true;
    };
  }, [vendor_id]);

  return (
    <ClientShell title="Detalle de proveedor">
      <p className="mb-3">
        <Link href="/client/vendors" className="text-xs text-primary hover:underline">
          ← Volver a proveedores
        </Link>
      </p>

      {error ? (
        <p className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {error}
        </p>
      ) : !detail ? (
        <p className="text-sm text-muted-foreground">Cargando…</p>
      ) : (
        <div className="space-y-5">
          <section className="rounded-md border border-border bg-white p-4">
            <h2 className="text-sm font-semibold">
              {String(detail.vendor.name ?? "")}
            </h2>
            <p className="text-xs text-muted-foreground">
              RFC: <span className="font-mono">{String(detail.vendor.rfc ?? "—")}</span>
              {detail.vendor.persona_type ? (
                <> · {String(detail.vendor.persona_type)}</>
              ) : null}
            </p>
            <p className="mt-2 text-sm">
              <strong>Semáforo:</strong> {detail.semaphore.level} ·{" "}
              {detail.semaphore.compliance_pct}% · {detail.semaphore.reason}
            </p>
          </section>

          <section className="rounded-md border border-border bg-white p-4">
            <h3 className="mb-2 text-sm font-semibold">Resumen de documentos</h3>
            <dl className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
              {Object.entries(detail.document_state_counts).map(([k, v]) => (
                <div key={k} className="rounded border border-border bg-muted/30 px-2 py-1.5">
                  <dt className="font-mono uppercase text-muted-foreground">{k}</dt>
                  <dd className="font-mono text-base tabular-nums">{v}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section className="rounded-md border border-border bg-white p-4">
            <h3 className="mb-2 text-sm font-semibold">
              Acciones sugeridas ({detail.suggested_actions.length})
            </h3>
            <ul className="space-y-2 text-sm">
              {detail.suggested_actions.length === 0 ? (
                <li className="text-xs text-muted-foreground">
                  Sin acciones sugeridas.
                </li>
              ) : (
                detail.suggested_actions.map((a) => (
                  <li
                    key={a.id}
                    className="rounded border border-border bg-muted/30 p-3"
                  >
                    <p className="text-xs font-mono uppercase text-muted-foreground">
                      {a.priority} · {a.type}
                    </p>
                    <p className="mt-1 font-medium">{a.title}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{a.body}</p>
                  </li>
                ))
              )}
            </ul>
          </section>

          <section className="rounded-md border border-border bg-white p-4">
            <h3 className="mb-2 text-sm font-semibold">
              Atención hoy ({detail.attention_today.length})
            </h3>
            <ul className="space-y-1 text-xs">
              {detail.attention_today.length === 0 ? (
                <li className="text-muted-foreground">Sin pendientes urgentes.</li>
              ) : (
                detail.attention_today.map((a) => (
                  <li key={a.id} className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{a.title}</span>
                    <span className="font-mono uppercase text-muted-foreground">
                      {a.institution}
                    </span>
                    <span className="rounded-full bg-muted px-2 py-0.5">{a.state}</span>
                    {a.due_in_days !== null ? (
                      <span className="font-mono text-muted-foreground">
                        {a.due_in_days >= 0
                          ? `vence en ${a.due_in_days}d`
                          : `vencido hace ${Math.abs(a.due_in_days)}d`}
                      </span>
                    ) : null}
                  </li>
                ))
              )}
            </ul>
          </section>

          <section className="rounded-md border border-border bg-white p-4">
            <h3 className="mb-2 text-sm font-semibold">
              Entregas recientes ({detail.recent_submissions.length})
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-muted/40 text-left uppercase text-muted-foreground">
                  <tr>
                    <th className="px-2 py-1">Fecha</th>
                    <th className="px-2 py-1">Requisito</th>
                    <th className="px-2 py-1">Periodo</th>
                    <th className="px-2 py-1">Estado</th>
                    <th className="px-2 py-1">Archivo</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.recent_submissions.map((s) => (
                    <tr key={s.submission_id} className="border-t border-border">
                      <td className="px-2 py-1 font-mono">
                        {new Date(s.submitted_at).toLocaleString("es-MX")}
                      </td>
                      <td className="px-2 py-1">
                        {s.requirement_name ?? s.requirement_code ?? "—"}
                      </td>
                      <td className="px-2 py-1 font-mono">{s.period_key ?? "—"}</td>
                      <td className="px-2 py-1">{s.status}</td>
                      <td className="px-2 py-1">{s.filename ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-md border border-border bg-white p-4">
            <h3 className="mb-2 text-sm font-semibold">
              Notas recientes del revisor ({detail.recent_reviewer_notes.length})
            </h3>
            <ul className="space-y-2 text-xs">
              {detail.recent_reviewer_notes.length === 0 ? (
                <li className="text-muted-foreground">Sin notas registradas.</li>
              ) : (
                detail.recent_reviewer_notes.map((n) => (
                  <li
                    key={`${n.submission_id}-${n.occurred_at}`}
                    className="rounded border border-border bg-muted/30 p-2"
                  >
                    <p className="font-mono uppercase text-muted-foreground">
                      {new Date(n.occurred_at).toLocaleString("es-MX")} · {n.result}
                    </p>
                    <p className="mt-1">{n.message ?? "(sin mensaje)"}</p>
                  </li>
                ))
              )}
            </ul>
          </section>
        </div>
      )}
    </ClientShell>
  );
}
