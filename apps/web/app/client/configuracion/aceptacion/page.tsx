"use client";

/**
 * Phase 5 / Axis 2 — client acceptance preferences.
 *
 * One setting today: auto-accept-on-valid. Reading is open to any client
 * seat (the GET is viewer-readable); only an Approver may change it (the
 * PATCH is Approver-gated and the backend 403s a Viewer). Viewers therefore
 * see the toggle disabled, not hidden.
 */

import { useCallback, useEffect, useState } from "react";
import { CheckCircle, Warning } from "@phosphor-icons/react";

import { ClientShell } from "../../_shell";
import { SettingsNav } from "@/components/checkwise/settings/settings-nav";
import { clientSettingsTabs } from "@/components/checkwise/settings/tabs";
import { Surface } from "@/components/checkwise/dashboard/stat-card";
import {
  getClientAcceptancePrefs,
  updateClientAcceptancePrefs,
} from "@/lib/api/client";
import { apiErrorDetail } from "@/lib/api/error-detail";
import { useUrlClientId } from "@/lib/workspace/use-url-client-id";
import { useClientApprover } from "@/lib/session/client-tier";

export default function ClientAcceptanceSettingsPage() {
  const urlClientId = useUrlClientId();
  const clientParam = urlClientId ? { client_id: urlClientId } : undefined;
  const isApprover = useClientApprover();

  const [autoAccept, setAutoAccept] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justSaved, setJustSaved] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const prefs = await getClientAcceptancePrefs(clientParam);
      setAutoAccept(prefs.auto_accept_valid);
    } catch (err) {
      setError(apiErrorDetail(err));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlClientId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function onToggle(next: boolean) {
    setSaving(true);
    setError(null);
    setJustSaved(false);
    // Optimistic — revert on failure.
    setAutoAccept(next);
    try {
      const res = await updateClientAcceptancePrefs(
        { auto_accept_valid: next },
        clientParam,
      );
      setAutoAccept(res.auto_accept_valid);
      setJustSaved(true);
    } catch (err) {
      setAutoAccept(!next);
      setError(apiErrorDetail(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <ClientShell
      title="Configuración"
      description="Define cómo tu empresa acepta los documentos de tus proveedores. La aceptación es independiente del dictamen de cumplimiento de CheckWise."
    >
      <div className="space-y-5">
        <SettingsNav tabs={clientSettingsTabs(urlClientId)} />
        {error ? (
          <div
            role="alert"
            className="flex items-center gap-2 rounded-lg border border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] px-4 py-3 text-[13px] text-[color:var(--status-error-text)]"
          >
            <Warning className="h-4 w-4 shrink-0" weight="fill" />
            {error}
          </div>
        ) : null}

        <Surface title="Aceptación automática">
          {loading ? (
            <p className="text-[13px] text-[color:var(--text-secondary)]">Cargando…</p>
          ) : (
            <label className="flex items-start gap-3">
              <input
                type="checkbox"
                checked={autoAccept}
                disabled={!isApprover || saving}
                onChange={(e) => void onToggle(e.target.checked)}
                className="mt-0.5 h-4 w-4 accent-[color:var(--interactive-primary)] disabled:cursor-not-allowed"
              />
              <span className="text-sm text-[color:var(--text-primary)]">
                Aceptar automáticamente los documentos que CheckWise apruebe.
                <span className="mt-1 block text-[12px] text-[color:var(--text-tertiary)]">
                  Cuando un documento pasa a <strong>Aprobado</strong>, se marca
                  como <strong>Aceptado por el cliente</strong> sin intervención
                  manual. Aplica a partir de ahora; para ponerte al día con lo ya
                  aprobado usa &ldquo;Aceptar&rdquo; en cada entrega.
                </span>
              </span>
            </label>
          )}

          {!isApprover && !loading ? (
            <p className="mt-3 text-[12px] text-[color:var(--text-tertiary)]">
              Tienes acceso de Visor (solo lectura). Solo un Aprobador puede
              cambiar esta preferencia.
            </p>
          ) : null}

          {justSaved ? (
            <p
              className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-[color:var(--status-success-text)]"
              role="status"
            >
              <CheckCircle className="h-4 w-4" weight="fill" aria-hidden="true" />
              Guardado
            </p>
          ) : null}
        </Surface>
      </div>
    </ClientShell>
  );
}
