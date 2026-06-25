"use client";

import { useMemo, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Check, LockKey, ShieldCheck } from "@phosphor-icons/react";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { PasswordInput } from "@/components/ui/password-input";
import { evaluatePassword } from "@/lib/email-inference";
import { AuthApiError, setPassword } from "@/lib/api/auth";
import {
  clearAdminSession,
  readAdminSession,
  setAdminAccessToken,
  writeAdminSession,
} from "@/lib/session/admin";

/**
 * ChangePasswordCard — self-service password change for a signed-in user
 * (audit Move 2, "Mi cuenta"). Shell-agnostic: used by both the staff
 * and client settings hubs.
 *
 * Posts to the same ``/auth/set-password`` endpoint as the forced
 * first-login ``/activate`` flow. That endpoint bumps the server session
 * epoch — invalidating every OTHER session — and re-mints THIS session's
 * token (CW-AUTH-002), so we MUST adopt the returned token + expiry or
 * the next request 401s. We don't collect the current password: the
 * endpoint doesn't verify one (the active session is the proof of
 * identity), so asking for it would be UI theater. Unlike ``/activate``,
 * a voluntary change does not redirect — it confirms inline.
 */
export function ChangePasswordCard() {
  const router = useRouter();
  const [password, setPasswordValue] = useState("");
  const [confirm, setConfirm] = useState("");
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const rules = useMemo(() => evaluatePassword(password), [password]);
  const allRulesPassed = rules.every((rule) => rule.passed);
  const passwordsMatch = password.length > 0 && password === confirm;
  const canSubmit = allRulesPassed && passwordsMatch;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const stored = readAdminSession();
    if (!stored) {
      router.replace("/login");
      return;
    }
    if (!passwordsMatch) {
      setConfirmError("Las contraseñas no coinciden.");
      return;
    }
    setConfirmError(null);
    setError(null);
    setSuccess(false);
    setSubmitting(true);
    try {
      const result = await setPassword(password);
      // CW-AUTH-002 — adopt the re-minted token + expiry so this session
      // survives the epoch bump that just signed out every other session.
      setAdminAccessToken(result.access_token);
      writeAdminSession({
        ...stored,
        expires_at: result.expires_at,
        user: { ...stored.user, ...result.user },
      });
      setPasswordValue("");
      setConfirm("");
      setSuccess(true);
    } catch (err) {
      if (err instanceof AuthApiError && err.status === 401) {
        clearAdminSession();
        setError("Tu sesión expiró. Vuelve a iniciar sesión.");
        setTimeout(() => router.replace("/login"), 1200);
      } else if (err instanceof AuthApiError && err.status === 422) {
        setError("La contraseña no cumple los requisitos mínimos.");
      } else {
        setError("No pudimos guardar tu nueva contraseña. Intenta de nuevo.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Surface
      title="Contraseña"
      icon={LockKey}
      description="Define una nueva contraseña permanente. Por seguridad, esto cierra tu sesión en cualquier otro dispositivo."
    >
      <form onSubmit={handleSubmit} className="space-y-5" noValidate>
        {success ? (
          <Alert variant="success">
            <AlertTitle className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4" weight="bold" aria-hidden="true" />
              Contraseña actualizada
            </AlertTitle>
            <AlertDescription>
              Tu nueva contraseña ya está activa. La usarás la próxima vez que
              inicies sesión.
            </AlertDescription>
          </Alert>
        ) : null}

        {error ? (
          <Alert variant="error">
            <AlertTitle>No pudimos completar el cambio</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        <Field label="Nueva contraseña" htmlFor="settings-new-password" required>
          <PasswordInput
            id="settings-new-password"
            value={password}
            onChange={(e) => {
              setPasswordValue(e.target.value);
              setSuccess(false);
            }}
            autoComplete="new-password"
          />
        </Field>

        <ul
          className="grid gap-2 sm:grid-cols-2"
          aria-label="Requisitos de la contraseña"
        >
          {rules.map(({ rule, passed }) => (
            <li
              key={rule.label}
              className={
                "flex items-center gap-2 rounded-sm border px-3 py-2 text-xs " +
                (passed
                  ? "border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]"
                  : "border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)] text-[color:var(--text-secondary)]")
              }
            >
              {passed ? (
                <Check className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
              ) : (
                <span
                  className="h-3.5 w-3.5 rounded-full border border-current opacity-50"
                  aria-hidden="true"
                />
              )}
              <span>{rule.label}</span>
            </li>
          ))}
        </ul>

        <Field
          label="Confirma tu nueva contraseña"
          htmlFor="settings-confirm-password"
          required
          error={confirmError}
        >
          <PasswordInput
            id="settings-confirm-password"
            value={confirm}
            onChange={(e) => {
              setConfirm(e.target.value);
              setConfirmError(null);
            }}
            autoComplete="new-password"
          />
        </Field>

        <div className="flex justify-end">
          <Button
            type="submit"
            loading={submitting}
            disabled={!canSubmit && !submitting}
          >
            Guardar contraseña
          </Button>
        </div>
      </form>
    </Surface>
  );
}
