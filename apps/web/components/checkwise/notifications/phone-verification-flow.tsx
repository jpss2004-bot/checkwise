"use client";

/**
 * Phase 7 / Slice N8b — phone verification flow.
 *
 * Two-step UI: capture phone → request OTP → enter 6-digit code →
 * confirm. Wraps the /api/v1/me/phone/verify + /confirm endpoints.
 *
 * Renders inline (not a modal) so the component composes inside
 * the `NotificationPreferencesPanel` and any future alta form. The
 * caller passes `onVerified` to chain off a successful confirmation —
 * the panel uses it to re-fetch /me/notification-preferences so the
 * "WhatsApp (no verificado)" badge flips to "Verificado".
 */

import { useState } from "react";
import {
  CheckCircle,
  PhoneCall,
  ShieldCheck,
  Warning,
} from "@phosphor-icons/react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  confirmPhoneVerification,
  requestPhoneVerification,
  type PhoneConfirmResponse,
} from "@/lib/api/notifications";

type Stage = "phone" | "code" | "verified";

export function PhoneVerificationFlow({
  initialPhone,
  alreadyVerified = false,
  onVerified,
}: {
  /** Pre-fill the input — e.g. with the User's stored phone. */
  initialPhone?: string | null;
  /** Show the verified state on mount when the user already confirmed. */
  alreadyVerified?: boolean;
  onVerified?: (data: PhoneConfirmResponse) => void;
}) {
  const [stage, setStage] = useState<Stage>(
    alreadyVerified ? "verified" : "phone",
  );
  const [phone, setPhone] = useState(initialPhone ?? "");
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [info, setInfo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const phoneError = (() => {
    if (!phone) return null;
    const digits = phone.replace(/\D+/g, "");
    if (digits.length < 10) {
      return "Captura al menos 10 dígitos (puedes incluir +52).";
    }
    return null;
  })();

  async function handleRequestOtp() {
    if (phoneError || !phone) return;
    setSubmitting(true);
    setError(null);
    setInfo(null);
    const out = await requestPhoneVerification(phone);
    setSubmitting(false);
    if (!out.ok) {
      if (out.status === 429) {
        setError(
          out.detail ??
            "Demasiados intentos. Espera unos minutos antes de volver a intentar.",
        );
      } else if (out.status === 422) {
        setError(out.detail ?? "Número de teléfono inválido.");
      } else if (out.status === 0) {
        setError(
          "No pudimos contactar al servidor. Verifica tu conexión.",
        );
      } else {
        setError(out.detail ?? "No pudimos enviar el código. Intenta de nuevo.");
      }
      return;
    }
    if (out.data.status === "sent") {
      setInfo(
        "Te enviamos un código de 6 dígitos por WhatsApp. Llega en menos de un minuto.",
      );
    } else {
      // ``skipped`` / ``failed`` — the OTP row still exists; in dev
      // the operator reads the code off the server log. Tell the
      // user that delivery is being investigated but they can
      // proceed if they see the code.
      setInfo(
        "Generamos el código. Si no te llega por WhatsApp en un minuto, contáctanos a soporte.",
      );
    }
    setStage("code");
  }

  async function handleConfirm() {
    if (code.length !== 6 || !/^\d{6}$/.test(code)) {
      setError("El código debe tener 6 dígitos.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setInfo(null);
    const out = await confirmPhoneVerification(phone, code);
    setSubmitting(false);
    if (!out.ok) {
      setError(
        out.detail ?? "Código de verificación inválido o expirado.",
      );
      return;
    }
    setStage("verified");
    setInfo("Tu número quedó verificado. Ya puedes recibir avisos por WhatsApp.");
    onVerified?.(out.data);
  }

  if (stage === "verified") {
    return (
      <div className="rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5">
        <header className="flex items-center gap-3">
          <span
            className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-50"
            aria-hidden
          >
            <ShieldCheck className="h-5 w-5 text-emerald-700" weight="duotone" />
          </span>
          <div>
            <h3 className="text-base font-semibold text-[color:var(--text-primary)]">
              WhatsApp verificado
            </h3>
            <p className="text-sm text-[color:var(--text-secondary)]">
              Tu número está confirmado. Puedes cambiarlo desde el botón abajo.
            </p>
          </div>
        </header>
        {info ? (
          <Alert variant="success" className="mt-4">
            <CheckCircle className="h-4 w-4" />
            <AlertTitle>Listo</AlertTitle>
            <AlertDescription>{info}</AlertDescription>
          </Alert>
        ) : null}
        <Button
          variant="outline"
          size="sm"
          className="mt-4"
          onClick={() => {
            setStage("phone");
            setInfo(null);
          }}
        >
          Cambiar número
        </Button>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5">
      <header className="mb-4 flex items-center gap-3">
        <span
          className="flex h-9 w-9 items-center justify-center rounded-full bg-[color:var(--surface-teal-muted)]"
          aria-hidden
        >
          <PhoneCall className="h-5 w-5 text-[color:var(--text-teal)]" weight="duotone" />
        </span>
        <div>
          <h3 className="text-base font-semibold text-[color:var(--text-primary)]">
            Verifica tu número de WhatsApp
          </h3>
          <p className="text-sm text-[color:var(--text-secondary)]">
            Te enviamos un código de 6 dígitos. Recibirás los avisos críticos
            por WhatsApp solo después de verificar.
          </p>
        </div>
      </header>

      {error ? (
        <Alert variant="error" className="mb-4">
          <Warning className="h-4 w-4" />
          <AlertTitle>No se pudo continuar</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {info ? (
        <Alert variant="success" className="mb-4">
          <CheckCircle className="h-4 w-4" />
          <AlertTitle>Código enviado</AlertTitle>
          <AlertDescription>{info}</AlertDescription>
        </Alert>
      ) : null}

      {stage === "phone" ? (
        <div className="flex flex-col gap-4">
          <Field
            label="Número con código de país"
            htmlFor="phone-verify-input"
            error={phoneError}
            helper="Formato: +52 55 1234 5678. Espacios y guiones son opcionales."
          >
            <Input
              id="phone-verify-input"
              type="tel"
              inputMode="tel"
              placeholder="+52 55 1234 5678"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              autoComplete="tel"
            />
          </Field>
          <Button
            type="button"
            onClick={handleRequestOtp}
            disabled={submitting || !!phoneError || !phone}
            className="self-start"
          >
            {submitting ? "Enviando…" : "Enviar código por WhatsApp"}
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-[color:var(--text-secondary)]">
            Captura el código de 6 dígitos que enviamos a{" "}
            <strong className="text-[color:var(--text-primary)]">
              {phone}
            </strong>
            .
          </p>
          <Field
            label="Código de verificación"
            htmlFor="phone-verify-code"
            helper="6 dígitos. Expira en 10 minutos."
          >
            <Input
              id="phone-verify-code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              placeholder="123456"
            />
          </Field>
          <div className="flex items-center gap-3">
            <Button
              type="button"
              onClick={handleConfirm}
              disabled={submitting || code.length !== 6}
            >
              {submitting ? "Verificando…" : "Confirmar código"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setStage("phone");
                setCode("");
                setInfo(null);
                setError(null);
              }}
              disabled={submitting}
            >
              Cambiar número
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
