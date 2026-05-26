"use client";

/**
 * Phase 7 / Slice N8b — notification preferences panel.
 *
 * Composes:
 *   1. Channel preference radio (email / whatsapp / both)
 *   2. Phone verification flow (PhoneVerificationFlow)
 *   3. Per-category mute matrix (renewal / reporting / verification /
 *      account / admin)
 *   4. Footer note explaining the critical-email-unmuteable rule
 *
 * Hosted on `/portal/perfil`. Loads state from
 * `GET /me/notification-preferences` on mount; persists via PUT.
 * Refetches after a successful OTP confirmation so the WhatsApp
 * preference toggles unlock visually.
 *
 * WhatsApp is permitted as a preference only when the user has a
 * verified phone — choosing it before verification triggers the
 * inline OTP flow, never a confusing 422.
 */

import { useEffect, useState } from "react";
import { Bell, ShieldCheck, Spinner } from "@phosphor-icons/react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  CATEGORY_DESCRIPTIONS,
  CATEGORY_LABELS,
  type CategoryMute,
  type ContactPreference,
  type NotificationCategory,
  type NotificationPreferencesResponse,
  fetchNotificationPreferences,
  updateNotificationPreferences,
} from "@/lib/api/notifications";

import { PhoneVerificationFlow } from "./phone-verification-flow";

const CATEGORY_ORDER: NotificationCategory[] = [
  "renewal",
  "reporting",
  "verification",
  "account",
  "admin",
];

const CONTACT_OPTIONS: { value: ContactPreference; label: string; helper: string }[] = [
  {
    value: "email",
    label: "Solo correo",
    helper: "Avisos por email; nada por WhatsApp.",
  },
  {
    value: "whatsapp",
    label: "Solo WhatsApp",
    helper: "Requiere número verificado.",
  },
  {
    value: "both",
    label: "Ambos canales",
    helper: "Recomendado — correo + WhatsApp en paralelo.",
  },
];

export function NotificationPreferencesPanel() {
  const [prefs, setPrefs] = useState<NotificationPreferencesResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let mounted = true;
    void (async () => {
      const data = await fetchNotificationPreferences();
      if (!mounted) return;
      if (!data) {
        setError(
          "No pudimos cargar tus preferencias. Recarga la página o intenta más tarde.",
        );
      } else {
        setPrefs(data);
      }
      setLoading(false);
    })();
    return () => {
      mounted = false;
    };
  }, []);

  async function refresh() {
    const data = await fetchNotificationPreferences();
    if (data) setPrefs(data);
  }

  function updateLocal(patch: Partial<NotificationPreferencesResponse>) {
    setPrefs((p) => (p ? { ...p, ...patch } : p));
    setSaved(false);
  }

  function setCategory(category: NotificationCategory, next: Partial<CategoryMute>) {
    setPrefs((p) => {
      if (!p) return p;
      const cats = p.categories.map((c) =>
        c.category === category ? { ...c, ...next } : c,
      );
      return { ...p, categories: cats };
    });
    setSaved(false);
  }

  async function handleSave() {
    if (!prefs) return;
    setSaving(true);
    setError(null);
    const updated = await updateNotificationPreferences({
      contact_preference: prefs.contact_preference,
      categories: prefs.categories,
    });
    setSaving(false);
    if (!updated) {
      setError(
        "No pudimos guardar tus preferencias. Verifica tu conexión e intenta de nuevo.",
      );
      return;
    }
    setPrefs(updated);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2500);
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 text-sm text-[color:var(--text-secondary)]">
        <Spinner className="h-4 w-4 animate-spin" />
        Cargando preferencias…
      </div>
    );
  }

  if (!prefs) {
    return (
      <Alert variant="error">
        <AlertTitle>No disponible</AlertTitle>
        <AlertDescription>
          {error ?? "No pudimos cargar tus preferencias."}
        </AlertDescription>
      </Alert>
    );
  }

  const phoneVerified = prefs.phone_verified;
  const wantsWhatsApp =
    prefs.contact_preference === "whatsapp" ||
    prefs.contact_preference === "both";

  return (
    <section
      data-testid="notification-preferences-panel"
      className="cw-fade-up flex flex-col gap-6 rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-sm sm:p-8"
    >
      <header className="flex items-start gap-3">
        <span
          className="flex h-10 w-10 items-center justify-center rounded-full bg-[color:var(--surface-teal-muted)]"
          aria-hidden
        >
          <Bell className="h-5 w-5 text-[color:var(--text-teal)]" weight="duotone" />
        </span>
        <div>
          <h2 className="text-xl font-semibold tracking-tight text-[color:var(--text-primary)]">
            Centro de notificaciones
          </h2>
          <p className="mt-1 max-w-prose text-sm text-[color:var(--text-secondary)]">
            Elige cómo quieres recibir tus avisos. La campana dentro de
            CheckWise siempre tiene la información completa — el correo y
            WhatsApp son refuerzos.
          </p>
        </div>
      </header>

      {error ? (
        <Alert variant="error">
          <AlertTitle>No pudimos completar la acción</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {saved ? (
        <Alert variant="success">
          <AlertTitle>Guardado</AlertTitle>
          <AlertDescription>
            Tus preferencias se actualizaron correctamente.
          </AlertDescription>
        </Alert>
      ) : null}

      {/* Channel preference */}
      <fieldset className="flex flex-col gap-3">
        <legend className="text-sm font-medium text-[color:var(--text-primary)]">
          Canal preferido
        </legend>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {CONTACT_OPTIONS.map((opt) => {
            const checked = prefs.contact_preference === opt.value;
            const disabled =
              (opt.value === "whatsapp" || opt.value === "both") &&
              !phoneVerified;
            return (
              <label
                key={opt.value}
                className={`flex cursor-pointer flex-col gap-1 rounded-lg border p-3 text-sm transition ${
                  checked
                    ? "border-[color:var(--border-strong)] bg-[color:var(--surface-teal-muted)]"
                    : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)]"
                } ${disabled ? "cursor-not-allowed opacity-60" : "hover:bg-[color:var(--surface-hover)]"}`}
              >
                <div className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="contact_preference"
                    value={opt.value}
                    checked={checked}
                    disabled={disabled}
                    onChange={() =>
                      updateLocal({ contact_preference: opt.value })
                    }
                    className="h-4 w-4 accent-[color:var(--text-teal)]"
                  />
                  <span className="font-medium text-[color:var(--text-primary)]">
                    {opt.label}
                  </span>
                </div>
                <span className="text-xs text-[color:var(--text-secondary)]">
                  {opt.helper}
                </span>
              </label>
            );
          })}
        </div>
        {!phoneVerified ? (
          <p className="text-xs text-[color:var(--text-secondary)]">
            Verifica tu número abajo para habilitar las opciones con WhatsApp.
          </p>
        ) : null}
      </fieldset>

      {/* Phone verification */}
      <PhoneVerificationFlow
        initialPhone={prefs.phone_e164}
        alreadyVerified={phoneVerified}
        onVerified={() => {
          void refresh();
        }}
      />

      {/* Per-category mute matrix */}
      <section className="flex flex-col gap-3">
        <header>
          <h3 className="text-sm font-medium text-[color:var(--text-primary)]">
            ¿Por qué categorías quieres recibir avisos?
          </h3>
          <p className="text-xs text-[color:var(--text-secondary)]">
            Silencia categorías individuales. Los avisos críticos por correo
            siempre llegan — no se pueden desactivar (es el respaldo de
            auditoría).
          </p>
        </header>
        <div className="overflow-hidden rounded-lg border border-[color:var(--border-default)]">
          <table className="w-full border-collapse text-sm">
            <thead className="bg-[color:var(--surface-page)]">
              <tr>
                <th className="px-4 py-2 text-left font-medium text-[color:var(--text-secondary)]">
                  Categoría
                </th>
                <th className="w-28 px-4 py-2 text-center font-medium text-[color:var(--text-secondary)]">
                  Correo
                </th>
                <th className="w-28 px-4 py-2 text-center font-medium text-[color:var(--text-secondary)]">
                  WhatsApp
                </th>
              </tr>
            </thead>
            <tbody>
              {CATEGORY_ORDER.map((cat) => {
                const row = prefs.categories.find((c) => c.category === cat) ?? {
                  category: cat,
                  email_muted: false,
                  whatsapp_muted: false,
                };
                return (
                  <tr
                    key={cat}
                    className="border-t border-[color:var(--border-default)]"
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium text-[color:var(--text-primary)]">
                        {CATEGORY_LABELS[cat]}
                      </div>
                      <div className="text-xs text-[color:var(--text-secondary)]">
                        {CATEGORY_DESCRIPTIONS[cat]}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <Checkbox
                        checked={!row.email_muted}
                        onCheckedChange={(v) =>
                          setCategory(cat, { email_muted: v !== true })
                        }
                        aria-label={`Recibir ${CATEGORY_LABELS[cat]} por correo`}
                      />
                    </td>
                    <td className="px-4 py-3 text-center">
                      <Checkbox
                        checked={!row.whatsapp_muted && phoneVerified && wantsWhatsApp}
                        disabled={!phoneVerified || !wantsWhatsApp}
                        onCheckedChange={(v) =>
                          setCategory(cat, { whatsapp_muted: v !== true })
                        }
                        aria-label={`Recibir ${CATEGORY_LABELS[cat]} por WhatsApp`}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="flex items-start gap-2 rounded-md border border-[color:var(--status-info-border)] bg-[color:var(--status-info-bg)] p-3 text-xs text-[color:var(--status-info-text)]">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" weight="duotone" />
          <span>
            Los avisos críticos por correo (documento vencido o rechazado,
            invitaciones, restablecimientos) siempre llegan, aunque silencies
            esa categoría. Es el respaldo formal de auditoría.
          </span>
        </p>
      </section>

      <footer className="flex items-center justify-end gap-3">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? "Guardando…" : "Guardar preferencias"}
        </Button>
      </footer>
    </section>
  );
}
